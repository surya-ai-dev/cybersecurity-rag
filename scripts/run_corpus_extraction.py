"""Production Corpus Extraction Runner and Checkpoint Coordinator.

Coordinates resumable, batch-controlled extraction for the 68 remaining documents
in the Cybersecurity RAG corpus using the validated production pipeline with
per-document subprocess isolation.

Features:
- Per-document subprocess isolation: each document extracts in its own fresh Python process.
- Parent runner resilience: native C++ segfaults / access violations in worker do not kill runner.
- Immediate native memory & C++ heap cleanup between documents.
- Dedicated output directory (data/extraction_corpus_68/).
- Atomic checkpoint manifest (corpus_checkpoint_manifest.json).
- Resumability: skips completed documents only when artifacts pass strict validation.
- Safe recovery of interrupted IN_PROGRESS documents with path-bounded cleanup.
- Pre-extraction free disk space guard with configurable threshold.
- Strict post-extraction parent validation (page count, JSON, Markdown, text markers, manifest, figures).
- Configurable failure policy: Fail-Fast (default) or Continue-on-Failure.
- Mutual duplicate_of cross-referencing for duplicate source documents (Option A).
- Comprehensive dry-run mode for preflight verification without document processing.
"""

import argparse
from collections import defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple

# Reconfigure stdout/stderr for UTF-8 on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from app.ingestion.extraction.config import ExtractionConfig
from app.ingestion.extraction.models import ExtractedDocument
from app.ingestion.extraction.pipeline import DocumentExtractionPipeline

DOCUMENTS_DIR = PROJECT_ROOT / "documents"
DEFAULT_CORPUS_OUTPUT_DIR = PROJECT_ROOT / "data" / "extraction_corpus_68"
CHECKPOINT_MANIFEST_FILENAME = "corpus_checkpoint_manifest.json"
MIN_FREE_DISK_MB_DEFAULT = 500  # Minimum free space required to proceed
SUBPROCESS_TIMEOUT_DEFAULT = 600  # 10 minutes per document timeout


def interpret_exit_code(code: int) -> str:
    """Provide human-readable explanation of process exit codes, including Windows NTSTATUS / POSIX signals."""
    unsigned = code & 0xFFFFFFFF if code < 0 else code
    hex_code = f"0x{unsigned:08X}"
    known = {
        0xC0000005: "STATUS_ACCESS_VIOLATION (Segmentation Fault / Memory Corruption in mupdfcpp64.dll or runtime)",
        0xC00000FD: "STATUS_STACK_OVERFLOW",
        0xC000001D: "STATUS_ILLEGAL_INSTRUCTION",
        0xC0000409: "STATUS_STACK_BUFFER_OVERRUN",
        0x80000003: "STATUS_BREAKPOINT",
    }
    desc = known.get(
        unsigned,
        "Native Crash / Unhandled Exception" if unsigned >= 0x80000000 else f"Exit code {code}",
    )
    return f"Exit code {code} ({hex_code}: {desc})"


def get_pilot_document_paths(config: Optional[ExtractionConfig] = None) -> Set[Path]:
    """Return resolved absolute paths of the 5 validated pilot documents."""
    cfg = config or ExtractionConfig()
    return {cfg.resolve_pdf_path(p).resolve() for p in cfg.pilot_documents}


def discover_corpus_inventory(
    config: Optional[ExtractionConfig] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, List[str]]]:
    """Discover all 73 PDFs, exclude the 5 pilots, and return 68 remaining docs with duplicate groups."""
    cfg = config or ExtractionConfig()
    pilot_paths = get_pilot_document_paths(cfg)

    all_pdfs = sorted(list(DOCUMENTS_DIR.rglob("*.pdf")), key=lambda p: str(p.as_posix()))

    # Map SHA-256 hashes across all PDFs to detect duplicates
    hash_map: Dict[str, List[str]] = defaultdict(list)
    for p in all_pdfs:
        rel = p.relative_to(PROJECT_ROOT).as_posix()
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        hash_map[h].append(rel)

    duplicate_groups = {h: paths for h, paths in hash_map.items() if len(paths) > 1}

    # Build 68 remaining documents list
    remaining_docs: List[Dict[str, Any]] = []
    for p in all_pdfs:
        if p.resolve() in pilot_paths:
            continue

        rel_path = p.relative_to(PROJECT_ROOT).as_posix()
        cat = p.parent.name if p.parent != DOCUMENTS_DIR else "root"
        h = hashlib.sha256(p.read_bytes()).hexdigest()

        # Check duplicate peers
        dup_peers = [peer for peer in hash_map.get(h, []) if peer != rel_path]

        # Fast page count via PyMuPDF
        doc_obj = fitz.open(p)
        page_count = len(doc_obj)
        doc_obj.close()

        remaining_docs.append({
            "document_id": p.stem,
            "relative_path": rel_path,
            "absolute_path": str(p.resolve()),
            "category": cat,
            "page_count": page_count,
            "file_size_bytes": p.stat().st_size,
            "sha256_hash": h,
            "duplicate_of": dup_peers,
        })

    return remaining_docs, duplicate_groups


def get_batch_slice(docs: List[Dict[str, Any]], batch_number: int, batch_size: int = 17) -> List[Dict[str, Any]]:
    """Return the slice of documents corresponding to batch_number (1-indexed)."""
    if batch_number < 1 or batch_number > 4:
        raise ValueError(f"Invalid batch number: {batch_number}. Must be between 1 and 4.")
    start_idx = (batch_number - 1) * batch_size
    end_idx = min(start_idx + batch_size, len(docs))
    return docs[start_idx:end_idx]


class CorpusCheckpointManager:
    """Manages atomic reads and updates to the corpus checkpoint manifest."""

    def __init__(self, output_dir: Path, all_docs: List[Dict[str, Any]]) -> None:
        self.output_dir = output_dir
        self.manifest_path = output_dir / CHECKPOINT_MANIFEST_FILENAME
        self.all_docs = all_docs
        self.data: Dict[str, Any] = self._load_or_initialize()

    def _load_or_initialize(self) -> Dict[str, Any]:
        """Load existing checkpoint manifest or initialize a new structure."""
        if self.manifest_path.is_file():
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data
            except Exception as ex:
                print(f"[WARNING] Checkpoint manifest unreadable ({ex}); reinitializing.")

        # Initialize fresh manifest
        docs_dict: Dict[str, Any] = {}
        for d in self.all_docs:
            doc_id = d["document_id"]
            docs_dict[doc_id] = {
                "document_id": doc_id,
                "relative_path": d["relative_path"],
                "category": d["category"],
                "expected_pages": d["page_count"],
                "file_size_bytes": d["file_size_bytes"],
                "sha256_hash": d["sha256_hash"],
                "duplicate_of": d["duplicate_of"],
                "status": "PENDING",
                "started_at": None,
                "completed_at": None,
                "elapsed_seconds": None,
                "actual_pages": None,
                "total_tables": None,
                "total_figures": None,
                "quality_warnings_count": None,
                "error": None,
                "validation_status": None,
            }

        data = {
            "target_output_dir": str(self.output_dir.resolve()),
            "total_documents": len(self.all_docs),
            "total_pages": sum(d["page_count"] for d in self.all_docs),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "summary": {
                "completed": 0,
                "failed": 0,
                "pending": len(self.all_docs),
                "in_progress": 0,
            },
            "documents": docs_dict,
        }
        return data

    def save(self) -> None:
        """Write checkpoint manifest atomically via temporary file replacement."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.data["updated_at"] = datetime.now().isoformat()

        # Update summary counts
        docs = self.data.get("documents", {})
        completed = sum(1 for d in docs.values() if d.get("status") == "SUCCESS")
        failed = sum(1 for d in docs.values() if d.get("status") == "FAILED")
        in_prog = sum(1 for d in docs.values() if d.get("status") == "IN_PROGRESS")
        pending = sum(1 for d in docs.values() if d.get("status") == "PENDING")

        self.data["summary"] = {
            "completed": completed,
            "failed": failed,
            "in_progress": in_prog,
            "pending": pending,
        }

        tmp_path = self.manifest_path.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        shutil.move(str(tmp_path), str(self.manifest_path))

    def get_document_status(self, doc_id: str) -> str:
        """Return current status of a document."""
        return self.data.get("documents", {}).get(doc_id, {}).get("status", "PENDING")

    def mark_in_progress(self, doc_id: str) -> None:
        """Mark document as actively extracting."""
        if doc_id in self.data["documents"]:
            entry = self.data["documents"][doc_id]
            entry["status"] = "IN_PROGRESS"
            entry["started_at"] = datetime.now().isoformat()
            entry["error"] = None
            self.save()

    def mark_pending(self, doc_id: str) -> None:
        """Reset document status to PENDING during recovery."""
        if doc_id in self.data["documents"]:
            entry = self.data["documents"][doc_id]
            entry["status"] = "PENDING"
            entry["started_at"] = None
            entry["completed_at"] = None
            entry["elapsed_seconds"] = None
            entry["actual_pages"] = None
            entry["total_tables"] = None
            entry["total_figures"] = None
            entry["quality_warnings_count"] = None
            entry["validation_status"] = None
            entry["error"] = None
            self.save()

    def mark_success(
        self,
        doc_id: str,
        elapsed_seconds: float,
        actual_pages: int,
        total_tables: int,
        total_figures: int,
        quality_warnings_count: int,
    ) -> None:
        """Mark document as successfully extracted and validated."""
        if doc_id in self.data["documents"]:
            entry = self.data["documents"][doc_id]
            entry["status"] = "SUCCESS"
            entry["completed_at"] = datetime.now().isoformat()
            entry["elapsed_seconds"] = round(elapsed_seconds, 2)
            entry["actual_pages"] = actual_pages
            entry["total_tables"] = total_tables
            entry["total_figures"] = total_figures
            entry["quality_warnings_count"] = quality_warnings_count
            entry["validation_status"] = "PASSED"
            entry["error"] = None
            self.save()

    def mark_failed(self, doc_id: str, error_msg: str, elapsed_seconds: float) -> None:
        """Mark document as failed with diagnostic details."""
        if doc_id in self.data["documents"]:
            entry = self.data["documents"][doc_id]
            entry["status"] = "FAILED"
            entry["completed_at"] = datetime.now().isoformat()
            entry["elapsed_seconds"] = round(elapsed_seconds, 2)
            entry["validation_status"] = "FAILED"
            entry["error"] = error_msg
            self.save()

    def get_in_progress_documents(self) -> List[str]:
        """Return list of document IDs currently marked IN_PROGRESS."""
        return [
            doc_id
            for doc_id, doc in self.data.get("documents", {}).items()
            if doc.get("status") == "IN_PROGRESS"
        ]


class CorpusExtractionRunner:
    """Coordinates batch extraction with subprocess isolation, disk checks, validation, and recovery."""

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        min_free_disk_mb: int = MIN_FREE_DISK_MB_DEFAULT,
        dry_run: bool = False,
        use_subprocess: bool = True,
        continue_on_failure: bool = False,
        subprocess_timeout_seconds: int = SUBPROCESS_TIMEOUT_DEFAULT,
    ) -> None:
        self.output_dir = output_dir or DEFAULT_CORPUS_OUTPUT_DIR
        self.min_free_disk_mb = min_free_disk_mb
        self.dry_run = dry_run
        self.use_subprocess = use_subprocess
        self.continue_on_failure = continue_on_failure
        self.subprocess_timeout_seconds = subprocess_timeout_seconds
        self.config = ExtractionConfig(
            output_dir=self.output_dir,
            use_hybrid_pymupdf4llm=True,
            extract_tables=True,
            extract_figures=True,
            enable_figure_filtering=True,
            enable_document_corrections=True,
            enable_ocr_fallback=False,
        )
        # Instantiate in-process pipeline only when subprocess isolation is explicitly disabled
        self.pipeline: Optional[DocumentExtractionPipeline] = (
            DocumentExtractionPipeline(self.config) if (not dry_run and not use_subprocess) else None
        )
        self.remaining_docs, self.duplicate_groups = discover_corpus_inventory(self.config)
        self.checkpoint_manager = CorpusCheckpointManager(self.output_dir, self.remaining_docs)

    def check_disk_space(self) -> Tuple[bool, float]:
        """Check available disk space in MB against min_free_disk_mb."""
        check_path = self.output_dir if self.output_dir.exists() else PROJECT_ROOT
        total, used, free = shutil.disk_usage(check_path)
        free_mb = free / (1024 * 1024)
        has_sufficient_space = free_mb >= self.min_free_disk_mb
        return has_sufficient_space, free_mb

    def _clean_partial_directory(self, doc_dir: Path) -> None:
        """Safely remove an incomplete document directory without touching anything outside it."""
        resolved_doc_dir = doc_dir.resolve()
        resolved_output = self.output_dir.resolve()

        # Strict security constraint: doc_dir must be strictly a descendant of self.output_dir
        try:
            rel = resolved_doc_dir.relative_to(resolved_output)
        except ValueError:
            raise ValueError(
                f"Security violation: attempt to clean path outside output directory: {resolved_doc_dir}"
            )

        # Ensure directory is at least 2 levels down (<category>/<doc_id>), never the output dir itself
        if len(rel.parts) < 2:
            raise ValueError(
                f"Security violation: attempt to clean output directory or category level: {resolved_doc_dir}"
            )

        if resolved_doc_dir.is_dir():
            shutil.rmtree(resolved_doc_dir, ignore_errors=True)

    def recover_in_progress_documents(self) -> List[str]:
        """Inspect and safely recover any documents left IN_PROGRESS from an interrupted run."""
        in_progress_ids = self.checkpoint_manager.get_in_progress_documents()
        if not in_progress_ids:
            return []

        print("=" * 80)
        print(f"[RECOVERY] Found {len(in_progress_ids)} document(s) left IN_PROGRESS from an earlier run:")
        recovered: List[str] = []
        for doc_id in in_progress_ids:
            doc_meta = next((d for d in self.remaining_docs if d["document_id"] == doc_id), None)
            if not doc_meta:
                continue
            cat = doc_meta["category"]
            doc_dir = self.output_dir / cat / doc_id

            if doc_dir.is_dir():
                partial_files = [f for f in doc_dir.rglob("*") if f.is_file()]
                disp_path = doc_dir.name
                try:
                    disp_path = str(doc_dir.resolve().relative_to(PROJECT_ROOT.resolve()))
                except ValueError:
                    disp_path = str(doc_dir)
                print(f"[RECOVERY] Inspecting partial directory for {doc_id}: {disp_path}")
                print(f"           Found {len(partial_files)} partial file(s):")
                for pf in partial_files[:5]:
                    print(f"             * {pf.relative_to(doc_dir)}")
                if len(partial_files) > 5:
                    print(f"             * ... and {len(partial_files) - 5} more")

                print(f"[RECOVERY] Safely cleaning incomplete directory: {doc_dir.name}/")
                self._clean_partial_directory(doc_dir)
            else:
                print(f"[RECOVERY] No partial directory found on disk for {doc_id}.")

            self.checkpoint_manager.mark_pending(doc_id)
            print(f"[RECOVERY] Reset status of {doc_id} from IN_PROGRESS -> PENDING in checkpoint manifest.")
            recovered.append(doc_id)

        print("=" * 80 + "\n")
        return recovered

    def recover_document(self, doc_id: str) -> bool:
        """Inspect and safely recover a specific document (whether IN_PROGRESS or FAILED)."""
        doc_meta = next((d for d in self.remaining_docs if d["document_id"] == doc_id), None)
        if not doc_meta:
            print(f"[RECOVERY ERROR] Document {doc_id} not found in inventory.")
            return False
        cat = doc_meta["category"]
        doc_dir = self.output_dir / cat / doc_id
        current_status = self.checkpoint_manager.get_document_status(doc_id)

        print("=" * 80)
        print(f"[RECOVERY] Recovering document: {doc_id} (Current status: {current_status})")
        if doc_dir.is_dir():
            partial_files = [f for f in doc_dir.rglob("*") if f.is_file()]
            disp_path = doc_dir.name
            try:
                disp_path = str(doc_dir.resolve().relative_to(PROJECT_ROOT.resolve()))
            except ValueError:
                disp_path = str(doc_dir)
            print(f"[RECOVERY] Inspecting directory for {doc_id}: {disp_path}")
            if partial_files:
                print(f"           Found {len(partial_files)} unvalidated file(s):")
                for pf in partial_files[:5]:
                    print(f"             * {pf.relative_to(doc_dir)}")
                if len(partial_files) > 5:
                    print(f"             * ... and {len(partial_files) - 5} more")
            print(f"[RECOVERY] Safely cleaning directory: {doc_dir.name}/")
            self._clean_partial_directory(doc_dir)
        else:
            print(f"[RECOVERY] No partial directory found on disk for {doc_id}.")

        self.checkpoint_manager.mark_pending(doc_id)
        print(f"[RECOVERY] Reset status of {doc_id} from {current_status} -> PENDING in checkpoint manifest.")
        print("=" * 80 + "\n")
        return True

    def validate_extracted_artifacts(self, doc_id: str, category: str, expected_pages: int) -> Tuple[bool, str]:
        """Strictly validate extracted artifacts on disk before approving completion."""
        doc_dir = self.output_dir / category / doc_id
        if not doc_dir.is_dir():
            return False, f"Target directory {doc_dir} does not exist"

        json_file = doc_dir / f"{doc_id}_structured.json"
        md_file = doc_dir / f"{doc_id}.md"
        txt_file = doc_dir / f"{doc_id}.txt"
        manifest_file = doc_dir / "manifest.json"

        if not json_file.is_file() or json_file.stat().st_size == 0:
            return False, f"Structured JSON {json_file.name} missing or empty"
        if not md_file.is_file() or md_file.stat().st_size == 0:
            return False, f"Markdown file {md_file.name} missing or empty"
        if not txt_file.is_file() or txt_file.stat().st_size == 0:
            return False, f"Raw text file {txt_file.name} missing or empty"
        if not manifest_file.is_file() or manifest_file.stat().st_size == 0:
            return False, f"Manifest file {manifest_file.name} missing or empty"

        # Check JSON page count and integrity
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                doc_json = json.load(f)
            pages = doc_json.get("pages", [])
            if len(pages) != expected_pages:
                return False, f"Page count mismatch in JSON: expected {expected_pages}, found {len(pages)}"
        except Exception as ex:
            return False, f"Error parsing structured JSON: {ex}"

        # Check manifest valid JSON
        try:
            with open(manifest_file, "r", encoding="utf-8") as f:
                json.load(f)
        except Exception as ex:
            return False, f"Error parsing manifest JSON: {ex}"

        # Check text dividers count
        try:
            txt_content = txt_file.read_text(encoding="utf-8")
            dividers = txt_content.count("--- PAGE ")
            if dividers != expected_pages:
                return False, f"Page divider count mismatch in TXT: expected {expected_pages}, found {dividers}"
        except Exception as ex:
            return False, f"Error reading TXT file: {ex}"

        # Check figures on disk
        figures = [fig for p in pages for fig in p.get("figures", [])]
        for fig in figures:
            rel = fig.get("image_path")
            if rel:
                fig_path = doc_dir / rel
                if not fig_path.is_file() or fig_path.stat().st_size == 0:
                    return False, f"Retained figure missing or empty on disk: {rel}"

        return True, "PASSED"

    def _run_child_worker(self, doc_meta: Dict[str, Any]) -> Tuple[int, str, str]:
        """Run extraction of a single document in an isolated child subprocess.

        Returns:
            Tuple of (returncode, stdout, stderr)
        """
        doc_id = doc_meta["document_id"]
        cmd = [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "run_corpus_extraction.py"),
            "--worker-extract-doc",
            doc_id,
            "--output-dir",
            str(self.output_dir),
        ]
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(PROJECT_ROOT),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.subprocess_timeout_seconds,
            )
            return proc.returncode, proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as exc:
            return -1, exc.stdout or "", f"Extraction timed out after {self.subprocess_timeout_seconds}s"
        except Exception as exc:
            return -1, "", f"Failed to spawn worker subprocess: {exc}"

    def process_document(self, doc_meta: Dict[str, Any]) -> bool:
        """Process a single document with disk checks, subprocess extraction, and validation."""
        doc_id = doc_meta["document_id"]
        rel_path = doc_meta["relative_path"]
        category = doc_meta["category"]
        expected_pages = doc_meta["page_count"]
        pdf_path = PROJECT_ROOT / rel_path
        doc_dir = self.output_dir / category / doc_id

        # 1. Check if already successfully extracted
        existing_status = self.checkpoint_manager.get_document_status(doc_id)
        if existing_status == "SUCCESS":
            # Confirm artifacts still strictly valid on disk
            is_valid, reason = self.validate_extracted_artifacts(doc_id, category, expected_pages)
            if is_valid:
                print(f"[SKIP] Already completed: {doc_id} ({expected_pages} pages)")
                return True
            else:
                print(
                    f"[RE-EXTRACT] Document {doc_id} was marked SUCCESS, but artifacts on disk are invalid/missing ({reason}). Re-extracting."
                )

        # 2. Check disk space
        has_space, free_mb = self.check_disk_space()
        if not has_space:
            err = f"Disk space critically low: {free_mb:.1f} MB free (minimum: {self.min_free_disk_mb} MB). Halting extraction."
            print(f"[CRITICAL] {err}")
            self.checkpoint_manager.mark_failed(doc_id, err, 0.0)
            return False

        # 3. Dry run
        if self.dry_run:
            print(f"[DRY RUN] Would extract: {doc_id} ({expected_pages} pages, {category}) from {rel_path}")
            if doc_meta.get("duplicate_of"):
                print(f"          Mutual duplicate references: {doc_meta['duplicate_of']}")
            return True

        # 4. Safe partial directory cleanup if unvalidated files exist from an interrupted run
        if doc_dir.is_dir():
            is_valid, _ = self.validate_extracted_artifacts(doc_id, category, expected_pages)
            if not is_valid:
                partial_files = [f for f in doc_dir.rglob("*") if f.is_file()]
                if partial_files:
                    disp_path = doc_dir.name
                    try:
                        disp_path = str(doc_dir.resolve().relative_to(PROJECT_ROOT.resolve()))
                    except ValueError:
                        disp_path = str(doc_dir)
                    print(
                        f"[RECOVERY] Found {len(partial_files)} incomplete/unvalidated artifact(s) in {disp_path}:"
                    )
                    for pf in partial_files[:5]:
                        print(f"           - {pf.relative_to(doc_dir)}")
                    if len(partial_files) > 5:
                        print(f"           ... and {len(partial_files) - 5} more")
                    print(f"[RECOVERY] Cleaning partial directory before fresh extraction: {doc_dir.name}/")
                    self._clean_partial_directory(doc_dir)

        # 5. Mark IN_PROGRESS
        print(f"[EXTRACTING] {doc_id} ({expected_pages} pages, {category})...")
        self.checkpoint_manager.mark_in_progress(doc_id)
        t0 = time.perf_counter()

        # 6. Execute extraction via subprocess (or in-process if use_subprocess is False)
        if self.use_subprocess:
            returncode, stdout, stderr = self._run_child_worker(doc_meta)
            elapsed = time.perf_counter() - t0

            if returncode != 0:
                unsigned_code = returncode & 0xFFFFFFFF if returncode < 0 else returncode
                is_native_crash = (
                    returncode in [3221225477, -1073741819]
                    or returncode < 0
                    or unsigned_code >= 0x80000000
                )
                diag_msg = interpret_exit_code(returncode)

                if is_native_crash:
                    err_msg = (
                        f"Native process crash in worker: {diag_msg}. "
                        "Process was terminated by the OS (no Python traceback available)."
                    )
                else:
                    err_msg = f"Worker process exited with failure: {diag_msg}."

                # Capture diagnostic output
                combined = (stderr or "") + "\n" + (stdout or "")
                out_lines = [l.strip() for l in combined.splitlines() if l.strip()]
                if out_lines:
                    err_msg += "\nLast worker output:\n" + "\n".join(out_lines[-10:])

                print(f"[FAILED] {doc_id}: {err_msg}")
                self.checkpoint_manager.mark_failed(doc_id, err_msg, elapsed)
                self._clean_partial_directory(doc_dir)
                return False
        else:
            # In-process execution fallback
            try:
                assert self.pipeline is not None
                self.pipeline.extract_document(
                    pdf_path=pdf_path,
                    output_dir=self.output_dir,
                )
                elapsed = time.perf_counter() - t0
            except Exception as exc:
                elapsed = time.perf_counter() - t0
                err_msg = f"Extraction raised exception: {exc}"
                print(f"[EXCEPTION] {doc_id}: {err_msg}")
                self.checkpoint_manager.mark_failed(doc_id, err_msg, elapsed)
                self._clean_partial_directory(doc_dir)
                return False

        # 7. Post-extraction validation by parent
        # Inject mutual duplicate_of metadata into document manifest if applicable
        if doc_meta.get("duplicate_of"):
            manifest_path = self.output_dir / category / doc_id / "manifest.json"
            if manifest_path.is_file():
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        m_data = json.load(f)
                    m_data["duplicate_of"] = doc_meta["duplicate_of"]
                    with open(manifest_path, "w", encoding="utf-8") as f:
                        json.dump(m_data, f, indent=2, ensure_ascii=False)
                except Exception as ex:
                    print(f"[WARNING] Could not update duplicate_of in manifest for {doc_id}: {ex}")

        is_valid, val_reason = self.validate_extracted_artifacts(doc_id, category, expected_pages)
        if not is_valid:
            err_msg = f"Post-extraction validation failed: {val_reason}"
            print(f"[FAILED] {doc_id}: {err_msg}")
            self.checkpoint_manager.mark_failed(doc_id, err_msg, elapsed)
            self._clean_partial_directory(doc_dir)
            return False

        # 8. Extract metrics from validated JSON
        json_file = doc_dir / f"{doc_id}_structured.json"
        try:
            with open(json_file, "r", encoding="utf-8") as jf:
                doc_json = json.load(jf)
            pages = doc_json.get("pages", [])
            total_tables = sum(len(p.get("tables", [])) for p in pages)
            total_figures = sum(len(p.get("figures", [])) for p in pages)
            quality_warnings = sum(len(p.get("quality_warnings", [])) for p in pages) + len(
                doc_json.get("document_warnings", [])
            )
        except Exception:
            total_tables = 0
            total_figures = 0
            quality_warnings = 0

        self.checkpoint_manager.mark_success(
            doc_id=doc_id,
            elapsed_seconds=elapsed,
            actual_pages=expected_pages,
            total_tables=total_tables,
            total_figures=total_figures,
            quality_warnings_count=quality_warnings,
        )
        print(f"[SUCCESS] {doc_id}: {expected_pages} pages, {total_tables} tables, {total_figures} figures in {elapsed:.1f}s")
        return True

    def run_batch(self, batch_number: int) -> Tuple[int, int]:
        """Run extraction on a specific batch of documents."""
        # Automatic recovery of any lingering IN_PROGRESS documents from previous crashes
        self.recover_in_progress_documents()

        docs = get_batch_slice(self.remaining_docs, batch_number)
        print("=" * 80)
        print(f"CORPUS EXTRACTION RUNNER: BATCH {batch_number} / 4")
        print(f"Documents in Batch  : {len(docs)}")
        print(f"Total Pages in Batch : {sum(d['page_count'] for d in docs):,}")
        print(f"Output Directory    : {self.output_dir.resolve()}")
        print(f"Subprocess Isolation: {self.use_subprocess}")
        print(f"Failure Policy      : {'Continue-on-Failure' if self.continue_on_failure else 'Fail-Fast'}")
        print(f"Dry Run Mode        : {self.dry_run}")
        print("=" * 80 + "\n")

        successful = 0
        failed = 0
        for idx, doc_meta in enumerate(docs, start=1):
            print(f"[{idx}/{len(docs)}] (Batch {batch_number}) -> {doc_meta['document_id']}")
            ok = self.process_document(doc_meta)
            if ok:
                successful += 1
            else:
                failed += 1
                # Check if failure was disk space
                has_space, _ = self.check_disk_space()
                if not has_space:
                    print("[ABORT] Halting batch early due to disk space guard.")
                    break
                if not self.continue_on_failure:
                    print(
                        f"[STOP] Halting Batch {batch_number} early due to document failure on {doc_meta['document_id']} (Policy: Fail-Fast). To continue past failures, use --continue-on-failure."
                    )
                    break

        print("\n" + "=" * 80)
        print(f"BATCH {batch_number} COMPLETE")
        print(f"Successful: {successful} | Failed: {failed}")
        print("=" * 80 + "\n")
        return successful, failed


def run_worker_extract(
    doc_id: str,
    output_dir: Path,
    config: Optional[ExtractionConfig] = None,
) -> int:
    """Worker process entrypoint: extracts a single document in complete process isolation."""
    cfg = config or ExtractionConfig(
        output_dir=output_dir,
        use_hybrid_pymupdf4llm=True,
        extract_tables=True,
        extract_figures=True,
        enable_figure_filtering=True,
        enable_document_corrections=True,
        enable_ocr_fallback=False,
    )

    remaining_docs, _ = discover_corpus_inventory(cfg)
    doc_meta = next((d for d in remaining_docs if d["document_id"] == doc_id), None)
    if not doc_meta:
        print(f"[WORKER ERROR] Document '{doc_id}' not found in corpus inventory.", file=sys.stderr)
        return 2

    pdf_path = PROJECT_ROOT / doc_meta["relative_path"]
    if not pdf_path.is_file():
        print(f"[WORKER ERROR] Source PDF not found: {pdf_path}", file=sys.stderr)
        return 3

    try:
        pipeline = DocumentExtractionPipeline(cfg)
        extracted_doc = pipeline.extract_document(
            pdf_path=pdf_path,
            output_dir=output_dir,
        )
        result_summary = {
            "document_id": doc_id,
            "pages": len(extracted_doc.pages),
            "tables": sum(len(p.tables) for p in extracted_doc.pages),
            "figures": sum(len(p.figures) for p in extracted_doc.pages),
            "warnings": sum(len(p.quality_warnings) for p in extracted_doc.pages) + len(extracted_doc.document_warnings),
        }
        print(f"__WORKER_RESULT__{json.dumps(result_summary)}")
        return 0
    except Exception as exc:
        print(f"[WORKER EXCEPTION] Extraction failed: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return 1


def main() -> None:
    """CLI entry point for corpus extraction runner."""
    parser = argparse.ArgumentParser(
        description="Resumable, process-isolated, quality-first corpus extraction runner for the 68 remaining NIST cybersecurity PDFs."
    )
    parser.add_argument(
        "--batch",
        type=int,
        choices=[1, 2, 3, 4],
        default=None,
        help="Specify batch number to execute (1 to 4, 17 documents per batch).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all 4 batches sequentially (all 68 documents).",
    )
    parser.add_argument(
        "--doc",
        type=str,
        default=None,
        help="Run an individual document by document ID or filename stem with subprocess isolation.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Custom output directory (default: data/extraction_corpus_68).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate execution and verify inventory without extracting PDFs.",
    )
    parser.add_argument(
        "--min-free-disk-mb",
        type=int,
        default=MIN_FREE_DISK_MB_DEFAULT,
        help=f"Minimum free disk space threshold in MB (default: {MIN_FREE_DISK_MB_DEFAULT} MB).",
    )
    parser.add_argument(
        "--continue-on-failure",
        action="store_true",
        help="Continue processing subsequent documents in batch if an individual document fails. (Default policy: Fail-Fast, halts on first failure).",
    )
    parser.add_argument(
        "--recover",
        action="store_true",
        help="Safely recover any documents left IN_PROGRESS or FAILED from an interrupted run, inspect and clean partial files, reset status to PENDING, and exit.",
    )
    parser.add_argument(
        "--recover-doc",
        type=str,
        default=None,
        help="Safely recover a specific document ID (IN_PROGRESS or FAILED), inspect and clean partial files, reset status to PENDING, and exit.",
    )
    parser.add_argument(
        "--subprocess-timeout",
        type=int,
        default=SUBPROCESS_TIMEOUT_DEFAULT,
        help=f"Subprocess timeout in seconds per document (default: {SUBPROCESS_TIMEOUT_DEFAULT}s).",
    )
    parser.add_argument(
        "--no-subprocess",
        action="store_true",
        help="Disable subprocess isolation and execute in parent process (for specialized debugging only).",
    )
    parser.add_argument(
        "--worker-extract-doc",
        type=str,
        default=None,
        help=argparse.SUPPRESS,  # Hidden internal flag for isolated child worker execution
    )

    args = parser.parse_args()

    out_dir = args.output_dir or DEFAULT_CORPUS_OUTPUT_DIR

    # Internal worker child invocation
    if args.worker_extract_doc:
        ret = run_worker_extract(args.worker_extract_doc, out_dir)
        sys.exit(ret)

    runner = CorpusExtractionRunner(
        output_dir=out_dir,
        min_free_disk_mb=args.min_free_disk_mb,
        dry_run=args.dry_run,
        use_subprocess=not args.no_subprocess,
        continue_on_failure=args.continue_on_failure,
        subprocess_timeout_seconds=args.subprocess_timeout,
    )

    has_space, free_mb = runner.check_disk_space()
    print(f"Free Disk Space: {free_mb:.2f} MB (Threshold: {args.min_free_disk_mb} MB)")
    if not has_space:
        print("[ERROR] Insufficient disk space to proceed.")
        sys.exit(1)

    if args.recover_doc:
        print(f"Executing recovery on document {args.recover_doc}...")
        ok = runner.recover_document(args.recover_doc)
        if ok:
            print(f"[RECOVERY COMPLETE] Successfully recovered {args.recover_doc}.")
        else:
            print(f"[RECOVERY FAILED] Could not recover {args.recover_doc}.")
        sys.exit(0 if ok else 1)

    if args.recover:
        print("Executing recovery on any interrupted documents...")
        recovered = runner.recover_in_progress_documents()
        failed_docs = [
            doc_id
            for doc_id, doc in runner.checkpoint_manager.data.get("documents", {}).items()
            if doc.get("status") == "FAILED"
        ]
        for f_id in failed_docs:
            if runner.recover_document(f_id):
                recovered.append(f_id)

        if recovered:
            print(f"[RECOVERY COMPLETE] Successfully recovered: {recovered}")
        else:
            print("[RECOVERY COMPLETE] No interrupted documents found to recover.")
        sys.exit(0)

    if args.doc:
        target_doc = next(
            (d for d in runner.remaining_docs if d["document_id"] == args.doc or d["relative_path"].endswith(args.doc)),
            None,
        )
        if not target_doc:
            print(f"[ERROR] Document '{args.doc}' not found in remaining corpus inventory.")
            sys.exit(1)
        print(f"Running individual document: {target_doc['document_id']}")
        success = runner.process_document(target_doc)
        sys.exit(0 if success else 1)

    elif args.batch:
        successful, failed = runner.run_batch(args.batch)
        sys.exit(0 if failed == 0 else 1)

    elif args.all:
        total_success = 0
        total_failed = 0
        for b in [1, 2, 3, 4]:
            s, f = runner.run_batch(b)
            total_success += s
            total_failed += f
            if f > 0:
                print(f"[NOTICE] Stopping corpus execution after Batch {b} due to failures.")
                break
        sys.exit(0 if total_failed == 0 else 1)

    else:
        print("[SAFETY NOTICE] No execution target specified.")
        print("To run a dry run on Batch 1, use: --batch 1 --dry-run")
        print("To run Batch 1, use: --batch 1")
        print("To recover interrupted documents: --recover")
        print("To test an individual document, use: --doc <doc_id> --dry-run")
        sys.exit(0)


if __name__ == "__main__":
    main()
