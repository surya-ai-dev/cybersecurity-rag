"""Production Corpus Cleaning Runner and Checkpoint Coordinator.

Coordinates resumable, batch-controlled text cleaning for the 63 remaining non-pilot documents
in the Cybersecurity RAG corpus using the validated conservative cleaning pipeline.

Features:
- Checkpointing: Atomic updates to data/cleaned_corpus/corpus_cleaning_checkpoint.json.
- State Tracking: PENDING, IN_PROGRESS, SUCCESS, FAILED.
- Strict Validation: Validates structured JSON, Markdown, TXT, manifest, and figure references.
- Safe Recovery: Path-bounded cleanup of incomplete output directories left IN_PROGRESS.
- Pilot Exclusion: Guarantees all 10 Stage 2 pilot documents are permanently excluded.
- Deterministic Batching: 4 non-overlapping batches (16, 16, 16, 15 = 63 documents, 3,592 pages).
- Disk Space Safeguards: Active pre-check and per-document guard with configurable reserve (default 500 MB).
- Dry-Run Support: Comprehensive inspection of plans, disk requirements, and checkpoint states.
- Duplicate Tracking: Preserves source document hashes and mutual cross-references.
"""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
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

from app.ingestion.cleaning.config import CleaningConfig
from app.ingestion.cleaning.pipeline import DocumentCleaningPipeline

# Constants & Paths
DEFAULT_CLEANED_CORPUS_DIR = PROJECT_ROOT / "data" / "cleaned_corpus"
DEFAULT_EXTRACTION_CORPUS_DIR = PROJECT_ROOT / "data" / "extraction_corpus_68"
EXTRACTION_MANIFEST_PATH = DEFAULT_EXTRACTION_CORPUS_DIR / "corpus_checkpoint_manifest.json"
CHECKPOINT_FILENAME = "corpus_cleaning_checkpoint.json"
MIN_FREE_DISK_MB_DEFAULT = 500

# Measured from Stage 2 pilot: 45,764,617 bytes across 1,057 pages (~42.3 KB / page)
BYTES_PER_PAGE_ESTIMATE = 43296.7

# All 10 Pilot Target Documents from Stage 2 (must always be excluded from Stage 3 full cleaning)
PILOT_DOCUMENT_IDS: Set[str] = {
    "NIST_SP_800-152",
    "NIST_SP_800-186",
    "NIST_SP_800-39",
    "NIST_SP_800-53",
    "NIST_SP_800-236",
    "NIST_SP_800-116",
    "NIST_SP_800-234",
    "NIST_SP_800-218",
    "NIST_SP_800-238",
    "NIST.SP.800-61r3",
}

# Deterministic batch partitioning: 16, 16, 16, 15 = 63 documents
BATCH_SIZES = [16, 16, 16, 15]


def discover_cleaning_inventory(
    extraction_dir: Optional[Path] = None,
    extraction_manifest_path: Optional[Path] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Discover all eligible extracted documents, strictly excluding all 10 pilot documents.
    Preserves exact document order, SHA256 hashes, page counts, and duplicate references.
    """
    ext_dir = extraction_dir or DEFAULT_EXTRACTION_CORPUS_DIR
    manifest_p = extraction_manifest_path or (ext_dir / "corpus_checkpoint_manifest.json")

    eligible_docs: List[Dict[str, Any]] = []

    if manifest_p.is_file():
        try:
            with open(manifest_p, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
            docs_map = manifest_data.get("documents", {})
            for doc_id, doc_entry in docs_map.items():
                if doc_id in PILOT_DOCUMENT_IDS:
                    continue
                cat = doc_entry.get("category", "root")
                in_dir = ext_dir / cat / doc_id
                eligible_docs.append({
                    "document_id": doc_id,
                    "category": cat,
                    "relative_path": doc_entry.get("relative_path", f"documents/{doc_id}.pdf"),
                    "input_dir": str(in_dir.resolve()),
                    "expected_pages": doc_entry.get("expected_pages", doc_entry.get("actual_pages", 0)),
                    "file_size_bytes": doc_entry.get("file_size_bytes", 0),
                    "sha256_hash": doc_entry.get("sha256_hash", ""),
                    "duplicate_of": doc_entry.get("duplicate_of", []),
                })
        except Exception as ex:
            print(f"[WARNING] Could not read extraction checkpoint manifest ({ex}); scanning extraction directory directly.")
            eligible_docs.clear()

    # Fallback if manifest unreadable or in mock testing environment
    if not eligible_docs and ext_dir.is_dir():
        for candidate in sorted(ext_dir.glob("*/*"), key=lambda p: (p.parent.name, p.name)):
            if candidate.is_dir() and candidate.name not in PILOT_DOCUMENT_IDS:
                json_file = candidate / f"{candidate.name}_structured.json"
                if json_file.is_file():
                    try:
                        with open(json_file, "r", encoding="utf-8") as jf:
                            jd = json.load(jf)
                            pages_cnt = len(jd.get("pages", []))
                    except Exception:
                        pages_cnt = 0
                    cat = candidate.parent.name
                    eligible_docs.append({
                        "document_id": candidate.name,
                        "category": cat,
                        "relative_path": f"documents/{candidate.name}.pdf",
                        "input_dir": str(candidate.resolve()),
                        "expected_pages": pages_cnt,
                        "file_size_bytes": json_file.stat().st_size,
                        "sha256_hash": "",
                        "duplicate_of": [],
                    })

    # Build deterministic batches map
    batches_map = get_all_cleaning_batches(eligible_docs)

    # Assign batch_number to each doc metadata
    for b_num, b_docs in batches_map.items():
        b_int = int(b_num)
        for doc in b_docs:
            doc["batch_number"] = b_int

    return eligible_docs, batches_map


def get_cleaning_batch_slice(docs: List[Dict[str, Any]], batch_number: int) -> List[Dict[str, Any]]:
    """Return the deterministic slice of documents for batch_number (1-indexed, 1-4)."""
    if batch_number < 1 or batch_number > 4:
        raise ValueError(f"Invalid batch number: {batch_number}. Must be between 1 and 4.")

    start_idx = sum(BATCH_SIZES[: batch_number - 1])
    end_idx = start_idx + BATCH_SIZES[batch_number - 1]
    return docs[start_idx: min(end_idx, len(docs))]


def get_all_cleaning_batches(docs: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Return dictionary mapping batch number ('1'..'4') to its list of documents."""
    return {
        str(b): get_cleaning_batch_slice(docs, b)
        for b in range(1, 5)
    }


class CleaningCheckpointManager:
    """Manages atomic reads and updates to the corpus cleaning checkpoint manifest."""

    def __init__(
        self,
        output_dir: Path,
        all_docs: List[Dict[str, Any]],
        batches_map: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    ) -> None:
        self.output_dir = output_dir
        self.manifest_path = output_dir / CHECKPOINT_FILENAME
        self.all_docs = all_docs
        self.batches_map = batches_map or get_all_cleaning_batches(all_docs)
        self.data: Dict[str, Any] = self._load_or_initialize()
        if not self.manifest_path.is_file():
            self.save()

    def _load_or_initialize(self) -> Dict[str, Any]:
        """Load existing checkpoint manifest or initialize a new structure."""
        if self.manifest_path.is_file():
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Verify that all documents are represented in the manifest
                existing_docs = data.get("documents", {})
                updated = False
                for d in self.all_docs:
                    did = d["document_id"]
                    if did not in existing_docs:
                        existing_docs[did] = self._create_document_entry(d)
                        updated = True
                if updated:
                    self._recalculate_summary(data)
                return data
            except Exception as ex:
                print(f"[WARNING] Checkpoint manifest unreadable ({ex}); reinitializing.")

        # Fresh manifest
        batches_summary = {}
        for b_str, b_docs in self.batches_map.items():
            batches_summary[b_str] = {
                "document_count": len(b_docs),
                "total_pages": sum(d.get("expected_pages", 0) for d in b_docs),
            }

        docs_dict: Dict[str, Any] = {}
        for d in self.all_docs:
            docs_dict[d["document_id"]] = self._create_document_entry(d)

        data = {
            "target_output_dir": str(self.output_dir.resolve()),
            "total_documents": len(self.all_docs),
            "total_pages": sum(d.get("expected_pages", 0) for d in self.all_docs),
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "batches": batches_summary,
            "summary": {
                "completed": 0,
                "failed": 0,
                "in_progress": 0,
                "pending": len(self.all_docs),
            },
            "documents": docs_dict,
        }
        return data

    def _create_document_entry(self, d: Dict[str, Any]) -> Dict[str, Any]:
        """Create a default PENDING entry for a document."""
        return {
            "document_id": d["document_id"],
            "category": d["category"],
            "batch_number": d.get("batch_number", 0),
            "relative_path": d.get("relative_path", ""),
            "input_dir": d.get("input_dir", ""),
            "expected_pages": d.get("expected_pages", 0),
            "file_size_bytes": d.get("file_size_bytes", 0),
            "sha256_hash": d.get("sha256_hash", ""),
            "duplicate_of": d.get("duplicate_of", []),
            "status": "PENDING",
            "started_at": None,
            "completed_at": None,
            "elapsed_seconds": None,
            "actual_pages": None,
            "original_char_count": None,
            "cleaned_char_count": None,
            "delta_chars": None,
            "total_headers_removed": None,
            "total_footers_removed": None,
            "total_hyphens_repaired": None,
            "total_encoding_transforms": None,
            "validation_status": None,
            "error": None,
        }

    def _recalculate_summary(self, data: Dict[str, Any]) -> None:
        """Update summary counts based on document entries."""
        docs = data.get("documents", {})
        completed = sum(1 for d in docs.values() if d.get("status") == "SUCCESS")
        failed = sum(1 for d in docs.values() if d.get("status") == "FAILED")
        in_prog = sum(1 for d in docs.values() if d.get("status") == "IN_PROGRESS")
        pending = sum(1 for d in docs.values() if d.get("status") == "PENDING")

        data["summary"] = {
            "completed": completed,
            "failed": failed,
            "in_progress": in_prog,
            "pending": pending,
        }

    def save(self) -> None:
        """Write checkpoint manifest atomically via temporary file replacement."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.data["updated_at"] = datetime.now().isoformat()
        self._recalculate_summary(self.data)

        tmp_path = self.manifest_path.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
        # Use os.replace for atomic replacement across platforms
        os.replace(str(tmp_path), str(self.manifest_path))

    def get_document_status(self, doc_id: str) -> str:
        """Return current status of a document."""
        return self.data.get("documents", {}).get(doc_id, {}).get("status", "PENDING")

    def mark_in_progress(self, doc_id: str) -> None:
        """Mark document as actively cleaning."""
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
            entry["original_char_count"] = None
            entry["cleaned_char_count"] = None
            entry["delta_chars"] = None
            entry["total_headers_removed"] = None
            entry["total_footers_removed"] = None
            entry["total_hyphens_repaired"] = None
            entry["total_encoding_transforms"] = None
            entry["validation_status"] = None
            entry["error"] = None
            self.save()

    def mark_success(
        self,
        doc_id: str,
        elapsed_seconds: float,
        actual_pages: int,
        cleaning_summary: Dict[str, Any],
    ) -> None:
        """Mark document as successfully cleaned and validated."""
        if doc_id in self.data["documents"]:
            entry = self.data["documents"][doc_id]
            entry["status"] = "SUCCESS"
            entry["completed_at"] = datetime.now().isoformat()
            entry["elapsed_seconds"] = round(elapsed_seconds, 2)
            entry["actual_pages"] = actual_pages
            entry["original_char_count"] = cleaning_summary.get("original_char_count")
            entry["cleaned_char_count"] = cleaning_summary.get("cleaned_char_count")
            entry["delta_chars"] = cleaning_summary.get("delta_chars")
            entry["total_headers_removed"] = cleaning_summary.get("total_headers_removed")
            entry["total_footers_removed"] = cleaning_summary.get("total_footers_removed")
            entry["total_hyphens_repaired"] = cleaning_summary.get("total_hyphens_repaired")
            entry["total_encoding_transforms"] = cleaning_summary.get("total_encoding_transforms")
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

    def get_failed_documents(self) -> List[str]:
        """Return list of document IDs currently marked FAILED."""
        return [
            doc_id
            for doc_id, doc in self.data.get("documents", {}).items()
            if doc.get("status") == "FAILED"
        ]


class CorpusCleaningRunner:
    """
    Coordinates batch cleaning for the Cybersecurity RAG corpus with atomic checkpointing,
    recovery, artifact validation, and active disk-space guards.
    """

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        extraction_dir: Optional[Path] = None,
        min_free_disk_mb: int = MIN_FREE_DISK_MB_DEFAULT,
        dry_run: bool = False,
        continue_on_failure: bool = False,
        retry_failed: bool = False,
    ) -> None:
        self.output_dir = output_dir or DEFAULT_CLEANED_CORPUS_DIR
        self.extraction_dir = extraction_dir or DEFAULT_EXTRACTION_CORPUS_DIR
        self.min_free_disk_mb = min_free_disk_mb
        self.dry_run = dry_run
        self.continue_on_failure = continue_on_failure
        self.retry_failed = retry_failed

        self.config = CleaningConfig(output_dir=self.output_dir, pilot_mode=False)
        self.pipeline = DocumentCleaningPipeline(self.config) if not dry_run else None

        self.remaining_docs, self.batches_map = discover_cleaning_inventory(self.extraction_dir)
        self.checkpoint_manager = CleaningCheckpointManager(
            self.output_dir, self.remaining_docs, self.batches_map
        )

    def check_disk_space(self, required_mb: float = 0.0) -> Tuple[bool, float]:
        """
        Check available disk space in MB against min_free_disk_mb plus optional required_mb.
        Returns (has_sufficient_space, free_mb).
        """
        check_path = self.output_dir if self.output_dir.exists() else PROJECT_ROOT
        total, used, free = shutil.disk_usage(check_path)
        free_mb = free / (1024 * 1024)
        has_sufficient_space = (free_mb - required_mb) >= self.min_free_disk_mb
        return has_sufficient_space, free_mb

    def estimate_storage_mb(self, doc_count: int, page_count: int) -> float:
        """Estimate expected storage in MB based on measured pilot data."""
        return (page_count * BYTES_PER_PAGE_ESTIMATE) / (1024 * 1024)

    def _clean_partial_directory(self, doc_dir: Path, doc_id: str) -> None:
        """
        Safely remove an incomplete document directory without touching anything outside it.
        Enforces strict path containment.
        """
        resolved_doc_dir = doc_dir.resolve()
        resolved_output = self.output_dir.resolve()

        # Strict security constraint: doc_dir must be strictly a descendant of self.output_dir
        try:
            rel = resolved_doc_dir.relative_to(resolved_output)
        except ValueError:
            raise ValueError(
                f"Security violation: attempt to clean path outside output directory: {resolved_doc_dir}"
            )

        # Ensure directory is at least 2 levels down (<category>/<doc_id>), never output dir or category
        if len(rel.parts) < 2:
            raise ValueError(
                f"Security violation: attempt to clean output directory or category level: {resolved_doc_dir}"
            )

        # Ensure directory basename matches doc_id
        if resolved_doc_dir.name != doc_id:
            raise ValueError(
                f"Security violation: directory name '{resolved_doc_dir.name}' does not match target doc_id '{doc_id}'"
            )

        if resolved_doc_dir.is_dir():
            shutil.rmtree(resolved_doc_dir, ignore_errors=True)

    def recover_in_progress_documents(self) -> List[str]:
        """
        Inspect and safely recover any documents left IN_PROGRESS from an interrupted run.
        This operation is idempotent.
        """
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
                print(f"[RECOVERY] Inspecting partial directory for {doc_id}: {doc_dir.name}")
                print(f"           Found {len(partial_files)} partial file(s). Cleaning directory safely.")
                self._clean_partial_directory(doc_dir, doc_id)
            else:
                print(f"[RECOVERY] No partial directory found on disk for {doc_id}.")

            self.checkpoint_manager.mark_pending(doc_id)
            print(f"[RECOVERY] Reset status of {doc_id} from IN_PROGRESS -> PENDING in checkpoint manifest.")
            recovered.append(doc_id)

        print("=" * 80 + "\n")
        return recovered

    def recover_document(self, doc_id: str) -> bool:
        """
        Inspect and safely recover a specific document (whether IN_PROGRESS or FAILED).
        Cleans partial directory and resets to PENDING.
        """
        doc_meta = next((d for d in self.remaining_docs if d["document_id"] == doc_id), None)
        if not doc_meta:
            print(f"[RECOVERY ERROR] Document {doc_id} not found in inventory.")
            return False
        cat = doc_meta["category"]
        doc_dir = self.output_dir / cat / doc_id
        current_status = self.checkpoint_manager.get_document_status(doc_id)

        print(f"[RECOVERY] Recovering document: {doc_id} (Current status: {current_status})")
        if doc_dir.is_dir():
            self._clean_partial_directory(doc_dir, doc_id)

        self.checkpoint_manager.mark_pending(doc_id)
        print(f"[RECOVERY] Reset status of {doc_id} from {current_status} -> PENDING in checkpoint manifest.")
        return True

    def validate_cleaned_artifacts(
        self,
        doc_id: str,
        category: str,
        expected_pages: int,
        input_dir: Path,
    ) -> Tuple[bool, str]:
        """
        Strictly validate cleaned artifacts on disk before approving completion.
        Verifies JSON, Markdown, TXT, manifest, and figure references.
        """
        doc_dir = self.output_dir / category / doc_id
        if not doc_dir.is_dir():
            return False, f"Target directory {doc_dir} does not exist"

        json_file = doc_dir / f"{doc_id}_structured.json"
        md_file = doc_dir / f"{doc_id}.md"
        txt_file = doc_dir / f"{doc_id}.txt"
        manifest_file = doc_dir / "manifest.json"

        # Check required files exist
        for req_f, label in [
            (json_file, "Structured JSON"),
            (md_file, "Markdown file"),
            (txt_file, "Plain text file"),
            (manifest_file, "Document manifest"),
        ]:
            if not req_f.is_file():
                return False, f"Missing required artifact: {label} ({req_f.name})"
            if req_f.stat().st_size == 0:
                return False, f"Empty artifact file: {label} ({req_f.name})"

        # Validate structured JSON schema & page count
        try:
            with open(json_file, "r", encoding="utf-8") as jf:
                data = json.load(jf)
            pages = data.get("pages", [])
            if len(pages) != expected_pages:
                return False, f"Page count mismatch in structured JSON: expected {expected_pages}, found {len(pages)}"
        except Exception as ex:
            return False, f"Corrupted or invalid structured JSON: {ex}"

        # Validate document manifest
        try:
            with open(manifest_file, "r", encoding="utf-8") as mf:
                mdata = json.load(mf)
            if mdata.get("document_id") != doc_id:
                return False, f"Manifest document_id mismatch: {mdata.get('document_id')} != {doc_id}"
            if mdata.get("total_pages") != expected_pages:
                return False, f"Manifest total_pages mismatch: {mdata.get('total_pages')} != {expected_pages}"
            if "cleaning_summary" not in mdata:
                return False, "Manifest missing cleaning_summary"
        except Exception as ex:
            return False, f"Corrupted or invalid document manifest: {ex}"

        # Validate figure preservation if figures existed in input
        src_fig_dir = input_dir / "figures"
        if src_fig_dir.is_dir():
            src_figs = [f for f in src_fig_dir.iterdir() if f.is_file()]
            dst_fig_dir = doc_dir / "figures"
            if src_figs:
                if not dst_fig_dir.is_dir():
                    return False, f"Missing figures directory in cleaned output ({len(src_figs)} figures expected)"
                dst_figs = [f for f in dst_fig_dir.iterdir() if f.is_file()]
                if len(dst_figs) != len(src_figs):
                    return False, f"Figure count mismatch: expected {len(src_figs)}, found {len(dst_figs)}"

        return True, "All cleaned artifacts validated successfully"

    def clean_single_document(self, doc_meta: Dict[str, Any]) -> bool:
        """
        Execute cleaning for one document with disk guards, timing, validation, and checkpointing.
        """
        doc_id = doc_meta["document_id"]
        category = doc_meta["category"]
        expected_pages = doc_meta["expected_pages"]
        input_dir = Path(doc_meta["input_dir"])

        # Disk space guard before starting document
        est_doc_mb = max(1.0, (expected_pages * BYTES_PER_PAGE_ESTIMATE) / (1024 * 1024) * 1.5)
        has_space, free_mb = self.check_disk_space(est_doc_mb)
        if not has_space:
            err_msg = (
                f"[DISK GUARD] Halting: free disk space ({free_mb:.1f} MB) minus estimated doc requirement "
                f"({est_doc_mb:.1f} MB) is below reserve ({self.min_free_disk_mb} MB)."
            )
            print(f"\n{err_msg}")
            self.checkpoint_manager.mark_failed(doc_id, err_msg, 0.0)
            return False

        current_status = self.checkpoint_manager.get_document_status(doc_id)

        # Resumability check: if already SUCCESS, validate artifacts
        if current_status == "SUCCESS":
            is_valid, reason = self.validate_cleaned_artifacts(doc_id, category, expected_pages, input_dir)
            if is_valid:
                print(f"[SKIP] Already completed and validated: {doc_id} ({expected_pages} pages)")
                return True
            else:
                print(f"[RE-CLEAN] Document marked SUCCESS but disk artifacts invalid ({reason}). Re-cleaning: {doc_id}")
                self.checkpoint_manager.mark_pending(doc_id)

        # Retry check: if FAILED and not retry_failed, skip
        if current_status == "FAILED" and not self.retry_failed:
            print(f"[SKIP] Document marked FAILED (use --retry-failed to retry): {doc_id}")
            return False

        if current_status == "FAILED" and self.retry_failed:
            print(f"[RETRY] Retrying previously failed document: {doc_id}")
            self.recover_document(doc_id)

        print(f"[CLEANING] {doc_id} ({expected_pages} pages, {category})...")
        self.checkpoint_manager.mark_in_progress(doc_id)
        start_time = time.time()

        try:
            assert self.pipeline is not None
            manifest_res = self.pipeline.clean_document_dir(
                input_dir, self.output_dir, doc_id, category
            )

            # Preserve figure assets if present
            src_fig_dir = input_dir / "figures"
            dst_fig_dir = self.output_dir / category / doc_id / "figures"
            if src_fig_dir.is_dir():
                dst_fig_dir.mkdir(parents=True, exist_ok=True)
                for fig_file in src_fig_dir.iterdir():
                    if fig_file.is_file():
                        shutil.copyfile(fig_file, dst_fig_dir / fig_file.name)

            elapsed = time.time() - start_time

            # Strict post-cleaning validation
            is_valid, val_msg = self.validate_cleaned_artifacts(
                doc_id, category, expected_pages, input_dir
            )
            if not is_valid:
                err = f"Post-cleaning validation failed: {val_msg}"
                print(f"[FAILED] {doc_id}: {err}")
                self.checkpoint_manager.mark_failed(doc_id, err, elapsed)
                return False

            summary = manifest_res.get("cleaning_summary", {})
            self.checkpoint_manager.mark_success(doc_id, elapsed, expected_pages, summary)
            print(
                f"[SUCCESS] {doc_id}: {expected_pages} pages in {elapsed:.2f}s | "
                f"Headers: {summary.get('total_headers_removed', 0)} | "
                f"Footers: {summary.get('total_footers_removed', 0)} | "
                f"Enc: {summary.get('total_encoding_transforms', 0)}"
            )
            return True

        except Exception as ex:
            elapsed = time.time() - start_time
            err = f"Exception during cleaning: {type(ex).__name__}: {ex}"
            print(f"[FAILED] {doc_id}: {err}")
            self.checkpoint_manager.mark_failed(doc_id, err, elapsed)
            return False

    def run_documents(self, docs_to_run: List[Dict[str, Any]], run_label: str) -> Tuple[int, int]:
        """Execute cleaning across a specified list of documents."""
        total = len(docs_to_run)
        total_pages = sum(d.get("expected_pages", 0) for d in docs_to_run)
        est_storage_mb = self.estimate_storage_mb(total, total_pages)

        print("=" * 80)
        print(f"CORPUS CLEANING RUNNER: {run_label}")
        print(f"Documents in Run     : {total}")
        print(f"Total Pages in Run   : {total_pages}")
        print(f"Estimated Storage    : {est_storage_mb:.2f} MB")
        print(f"Output Directory     : {self.output_dir.resolve()}")
        print(f"Failure Policy       : {'Continue-on-Failure' if self.continue_on_failure else 'Fail-Fast'}")
        print(f"Dry Run Mode         : {self.dry_run}")
        print("=" * 80 + "\n")

        # Initial recovery of any interrupted documents
        self.recover_in_progress_documents()

        # Check initial disk space
        has_space, free_mb = self.check_disk_space(est_storage_mb)
        print(f"[DISK CHECK] Free disk space: {free_mb:.1f} MB (Required reserve: {self.min_free_disk_mb} MB)")
        if not has_space:
            print(f"[ERROR] Insufficient disk space to proceed safely. Halting.")
            return 0, total

        successful = 0
        failed = 0

        for idx, doc_meta in enumerate(docs_to_run, 1):
            doc_id = doc_meta["document_id"]
            print(f"[{idx}/{total}] ({run_label}) -> {doc_id}")

            ok = self.clean_single_document(doc_meta)
            if ok:
                successful += 1
            else:
                failed += 1
                if not self.continue_on_failure:
                    print(f"\n[STOP] Halting early due to document failure on {doc_id} (Policy: Fail-Fast).")
                    print("To continue past failures, use --continue-on-failure.\n")
                    break

        print("\n" + "=" * 80)
        print(f"{run_label} COMPLETE")
        print(f"Successful: {successful} | Failed: {failed}")
        print("=" * 80 + "\n")
        return successful, failed

    def run_dry_run(self, target_docs: List[Dict[str, Any]], run_label: str) -> None:
        """Display comprehensive dry-run analytics without modifying any files."""
        total = len(target_docs)
        total_pages = sum(d.get("expected_pages", 0) for d in target_docs)
        est_storage_mb = self.estimate_storage_mb(total, total_pages)
        has_space, free_mb = self.check_disk_space(est_storage_mb)

        print("=" * 80)
        print(f"CORPUS CLEANING RUNNER (DRY RUN): {run_label}")
        print(f"Target Documents     : {total}")
        print(f"Total Pages          : {total_pages}")
        print(f"Estimated Storage    : {est_storage_mb:.2f} MB (~42.3 KB/page)")
        print(f"Available Free Space : {free_mb:.1f} MB")
        print(f"Safety Threshold     : {self.min_free_disk_mb} MB reserve")
        print(f"Disk Check Passed    : {'YES' if has_space else 'NO (INSUFFICIENT SPACE)'}")
        print(f"Output Directory     : {self.output_dir.resolve()}")
        print("=" * 80)

        # Verify pilot exclusion
        pilot_found = [d["document_id"] for d in target_docs if d["document_id"] in PILOT_DOCUMENT_IDS]
        if pilot_found:
            print(f"[SECURITY ALERT] Pilot documents detected in workload: {pilot_found}")
        else:
            print("[VERIFIED] All 10 Stage 2 pilot documents strictly excluded.")

        # Checkpoint status summary
        in_prog = self.checkpoint_manager.get_in_progress_documents()
        if in_prog:
            print(f"[NOTICE] Checkpoint has {len(in_prog)} document(s) IN_PROGRESS: {in_prog}")
        else:
            print("[VERIFIED] No documents left in interrupted IN_PROGRESS state.")

        print("\nTarget Documents Itemization:")
        print(f"{'#':<4} {'Document ID':<22} {'Category':<28} {'Pages':<6} {'Status':<12}")
        print("-" * 76)
        for idx, d in enumerate(target_docs, 1):
            did = d["document_id"]
            cat = d["category"]
            pgs = d.get("expected_pages", 0)
            status = self.checkpoint_manager.get_document_status(did)
            print(f"{idx:<4} {did:<22} {cat:<28} {pgs:<6} {status:<12}")

        print("\n" + "=" * 80)
        print("DRY RUN FINISHED — ZERO FILES MODIFIED")
        print("=" * 80 + "\n")

    def run_batch(self, batch_number: int) -> Tuple[int, int]:
        """Execute cleaning for a specific batch (1-4)."""
        docs = get_cleaning_batch_slice(self.remaining_docs, batch_number)
        label = f"BATCH {batch_number} / 4"
        if self.dry_run:
            self.run_dry_run(docs, label)
            return 0, 0
        return self.run_documents(docs, label)

    def run_all(self) -> Tuple[int, int]:
        """Execute cleaning across all 4 batches (all 63 documents)."""
        label = "FULL CORPUS (ALL 4 BATCHES / 63 DOCUMENTS)"
        if self.dry_run:
            self.run_dry_run(self.remaining_docs, label)
            return 0, 0
        return self.run_documents(self.remaining_docs, label)

    def run_doc(self, doc_id: str) -> Tuple[int, int]:
        """Execute cleaning for a single document."""
        doc_meta = next((d for d in self.remaining_docs if d["document_id"] == doc_id), None)
        if not doc_meta:
            print(f"[ERROR] Document '{doc_id}' not found in eligible cleaning inventory.")
            if doc_id in PILOT_DOCUMENT_IDS:
                print(f"[SECURITY GUARD] '{doc_id}' is one of the 10 protected pilot documents and cannot be processed here.")
            return 0, 1

        label = f"SINGLE DOCUMENT: {doc_id}"
        if self.dry_run:
            self.run_dry_run([doc_meta], label)
            return 0, 0
        return self.run_documents([doc_meta], label)


def main() -> None:
    """CLI entry point for the production corpus cleaning runner."""
    parser = argparse.ArgumentParser(
        description="Production Corpus Cleaning Runner and Checkpoint Coordinator for Cybersecurity RAG."
    )
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument(
        "--batch",
        type=str,
        help="Batch number to clean: 1, 2, 3, 4, or '1-4' / 'all'.",
    )
    group.add_argument(
        "--doc",
        type=str,
        help="Clean a single document by its document ID (e.g. NIST_SP_800-233).",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Clean all 63 remaining documents across all 4 batches.",
    )
    group.add_argument(
        "--recover",
        action="store_true",
        help="Inspect and safely recover any interrupted IN_PROGRESS documents, then exit.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform pre-checks, display batch document lists, estimated storage, and checkpoint status without executing cleaning.",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry documents currently marked FAILED in the checkpoint manifest.",
    )
    parser.add_argument(
        "--continue-on-failure",
        action="store_true",
        help="Continue processing remaining documents if a document fails (default: fail-fast).",
    )
    parser.add_argument(
        "--min-free-disk-mb",
        type=int,
        default=MIN_FREE_DISK_MB_DEFAULT,
        help=f"Minimum free disk space in MB required to proceed (default: {MIN_FREE_DISK_MB_DEFAULT}).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_CLEANED_CORPUS_DIR,
        help=f"Target output directory for cleaned documents (default: {DEFAULT_CLEANED_CORPUS_DIR}).",
    )
    parser.add_argument(
        "--extraction-dir",
        type=Path,
        default=DEFAULT_EXTRACTION_CORPUS_DIR,
        help=f"Source extraction directory (default: {DEFAULT_EXTRACTION_CORPUS_DIR}).",
    )

    args = parser.parse_args()

    # Safety notice if no execution target was specified
    if not (args.batch or args.doc or args.all or args.recover or args.dry_run):
        print("[SAFETY NOTICE] Please specify a cleaning target:")
        print("  --dry-run --batch 1      Inspect Batch 1 without modifying files")
        print("  --dry-run --all          Inspect all 63 documents without modifying files")
        print("  --batch 1                Clean Batch 1 (16 documents)")
        print("  --doc <document_id>      Clean a single document")
        print("  --all                    Clean all 63 documents across 4 batches")
        print("  --recover                Recover any interrupted IN_PROGRESS documents")
        sys.exit(0)

    runner = CorpusCleaningRunner(
        output_dir=args.output_dir,
        extraction_dir=args.extraction_dir,
        min_free_disk_mb=args.min_free_disk_mb,
        dry_run=args.dry_run,
        continue_on_failure=args.continue_on_failure,
        retry_failed=args.retry_failed,
    )

    if args.recover:
        recovered = runner.recover_in_progress_documents()
        print(f"[RECOVERY COMPLETE] Recovered {len(recovered)} document(s).")
        sys.exit(0)

    if args.doc:
        runner.run_doc(args.doc)
    elif args.batch:
        b_str = args.batch.strip().lower()
        if b_str in ("all", "1-4"):
            runner.run_all()
        elif b_str in ("1", "2", "3", "4"):
            runner.run_batch(int(b_str))
        else:
            print(f"[ERROR] Invalid batch argument: '{args.batch}'. Must be 1, 2, 3, 4, or '1-4' / 'all'.")
            sys.exit(1)
    elif args.all:
        runner.run_all()
    elif args.dry_run:
        # Default dry-run without explicit batch/doc defaults to all 63 documents
        runner.run_all()


if __name__ == "__main__":
    main()
