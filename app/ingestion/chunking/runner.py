"""Runner and orchestrator for sequential corpus chunking with disk safety and atomic writes."""

from dataclasses import asdict, dataclass, field
import gc
import json
import os
from pathlib import Path
import shutil
import statistics
import sys
import time
from typing import Any, Dict, List, Optional

from app.ingestion.chunking.config import ChunkingConfig
from app.ingestion.chunking.models import ChunkRecord
from app.ingestion.chunking.pipeline import DocumentChunkingPipeline, DocumentChunkResult
from app.ingestion.chunking.tokenizer import get_tokenizer_adapter


@dataclass
class PilotRunnerReport:
    """Consolidated execution report for the chunking run."""

    created_at: str
    output_dir: str
    configuration: Dict[str, Any]
    total_documents: int = 0
    total_physical_pages: int = 0
    total_chunks: int = 0
    chunks_text: int = 0
    chunks_table: int = 0
    chunks_figure: int = 0
    chunks_with_encoding_warnings: int = 0
    oversized_chunks_count: int = 0
    missing_assets_count: int = 0
    token_min: int = 0
    token_median: float = 0.0
    token_mean: float = 0.0
    token_max: int = 0
    total_output_size_bytes: int = 0
    documents: List[Dict[str, Any]] = field(default_factory=list)
    failures: List[Dict[str, Any]] = field(default_factory=list)


class CorpusChunkingRunner:
    """Manages sequential chunking execution, disk safety guards, and atomic writes."""

    def __init__(self, config: ChunkingConfig):
        self.config = config
        self.tokenizer = get_tokenizer_adapter(config)
        self.pipeline = DocumentChunkingPipeline(config=config, tokenizer=self.tokenizer)

    def run_pilot(self, target_doc_id: Optional[str] = None) -> PilotRunnerReport:
        """Run chunking for the pilot cohort or a targeted single document."""
        input_dir = Path(self.config.input_dir)
        output_dir = Path(self.config.output_dir)

        if not input_dir.exists():
            raise FileNotFoundError(f"Input directory does not exist: {input_dir}")

        # Check existing output directory conflict
        if output_dir.exists() and not self.config.dry_run:
            existing_jsonl = list(output_dir.rglob("*.jsonl"))
            if existing_jsonl and not target_doc_id and not self.config.overwrite_existing:
                raise RuntimeError(
                    f"Target output directory '{output_dir}' already contains {len(existing_jsonl)} JSONL files. "
                    "Use a new versioned output directory, clear the existing directory explicitly, or pass overwrite_existing=True."
                )

        # Preflight Disk Space Check
        free_mb = self._get_free_disk_space_mb(output_dir.parent if not output_dir.exists() else output_dir)
        print(f"Initial Free Disk Space: {free_mb:.1f} MB (Safety reserve: {self.config.min_free_disk_mb} MB)")
        if free_mb < self.config.min_free_disk_mb:
            raise RuntimeError(
                f"Halting: Available disk space ({free_mb:.1f} MB) is below mandatory reserve ({self.config.min_free_disk_mb} MB)."
            )

        # Discover pilot document directories
        doc_dirs = self._discover_document_directories(input_dir, target_doc_id)
        if not doc_dirs:
            raise RuntimeError(f"No valid document directories found in {input_dir}")

        report = PilotRunnerReport(
            created_at=time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
            output_dir=str(output_dir),
            configuration=self.config.to_dict(),
        )

        all_token_counts: List[int] = []
        doc_results: List[DocumentChunkResult] = []

        for idx, doc_dir in enumerate(doc_dirs, 1):
            doc_id = doc_dir.name
            category = doc_dir.parent.name
            print(f"\n[{idx}/{len(doc_dirs)}] Processing: {category}/{doc_id} ...")

            # Check disk guard before processing
            free_mb = self._get_free_disk_space_mb(output_dir.parent if not output_dir.exists() else output_dir)
            if free_mb < self.config.min_free_disk_mb:
                err_msg = f"Disk safety guard triggered: free space ({free_mb:.1f} MB) dropped below reserve."
                print(f"ERROR: {err_msg}")
                report.failures.append({"document_id": doc_id, "error": err_msg})
                if self.config.fail_fast:
                    break
                continue

            try:
                t0 = time.time()
                res = self.pipeline.process_document(doc_dir)
                elapsed = time.time() - t0

                print(
                    f"  -> Generated {res.total_chunks} chunks ({res.chunks_text} text, "
                    f"{res.chunks_table} table, {res.chunks_figure} figure) in {elapsed:.2f}s"
                )

                if res.validation_errors:
                    for err in res.validation_errors:
                        print(f"  [VALIDATION WARNING] {err}")

                doc_results.append(res)
                for c in res.chunks:
                    all_token_counts.append(c.token_count)

                # Write to disk if not dry-run
                if not self.config.dry_run:
                    doc_output_dir = output_dir / category
                    jsonl_path = doc_output_dir / f"{doc_id}_chunks.jsonl"
                    file_size = self._write_jsonl_atomically(res.chunks, jsonl_path)
                    print(f"  -> Saved {file_size / 1024:.1f} KB to {jsonl_path.name}")

                    report.documents.append({
                        "document_id": doc_id,
                        "category": category,
                        "source_file": res.source_file,
                        "output_file": str(jsonl_path.relative_to(output_dir.parent)),
                        "pages_processed": res.pages_processed,
                        "total_chunks": res.total_chunks,
                        "chunks_text": res.chunks_text,
                        "chunks_table": res.chunks_table,
                        "chunks_figure": res.chunks_figure,
                        "encoding_warnings_count": res.encoding_warnings_count,
                        "missing_assets_count": res.missing_assets_count,
                        "oversized_chunks_count": res.oversized_chunks_count,
                        "file_size_bytes": file_size,
                        "status": "SUCCESS",
                    })
                else:
                    report.documents.append({
                        "document_id": doc_id,
                        "category": category,
                        "source_file": res.source_file,
                        "pages_processed": res.pages_processed,
                        "total_chunks": res.total_chunks,
                        "chunks_text": res.chunks_text,
                        "chunks_table": res.chunks_table,
                        "chunks_figure": res.chunks_figure,
                        "encoding_warnings_count": res.encoding_warnings_count,
                        "status": "DRY_RUN_SUCCESS",
                    })

            except Exception as e:
                print(f"  [ERROR] Failed to chunk {doc_id}: {e}")
                report.failures.append({"document_id": doc_id, "error": str(e)})
                if self.config.fail_fast:
                    raise

            finally:
                gc.collect()

        # Aggregate summary statistics
        report.total_documents = len(doc_results)
        report.total_physical_pages = sum(r.pages_processed for r in doc_results)
        report.total_chunks = sum(r.total_chunks for r in doc_results)
        report.chunks_text = sum(r.chunks_text for r in doc_results)
        report.chunks_table = sum(r.chunks_table for r in doc_results)
        report.chunks_figure = sum(r.chunks_figure for r in doc_results)
        report.chunks_with_encoding_warnings = sum(r.encoding_warnings_count for r in doc_results)
        report.oversized_chunks_count = sum(r.oversized_chunks_count for r in doc_results)
        report.missing_assets_count = sum(r.missing_assets_count for r in doc_results)

        if all_token_counts:
            report.token_min = min(all_token_counts)
            report.token_max = max(all_token_counts)
            report.token_mean = round(statistics.mean(all_token_counts), 1)
            report.token_median = round(statistics.median(all_token_counts), 1)

        if not self.config.dry_run and output_dir.exists():
            report.total_output_size_bytes = sum(
                f.stat().st_size for f in output_dir.rglob("*") if f.is_file()
            )
            # Write global manifest
            manifest_path = output_dir / "chunks_manifest.json"
            self._write_manifest(report, manifest_path)
            print(f"\nManifest saved: {manifest_path}")

        print("\n" + "=" * 80)
        print("PILOT CHUNKING RUN COMPLETE")
        print(f"Documents Completed : {report.total_documents} / {len(doc_dirs)}")
        print(f"Physical Pages      : {report.total_physical_pages}")
        print(f"Total Chunks        : {report.total_chunks}")
        print(f"  - Text Chunks     : {report.chunks_text}")
        print(f"  - Table Chunks    : {report.chunks_table}")
        print(f"  - Figure Chunks   : {report.chunks_figure}")
        print(f"Token Distribution  : Min={report.token_min}, Median={report.token_median}, Max={report.token_max}")
        print(f"Encoding Warnings   : {report.chunks_with_encoding_warnings}")
        print(f"Failures            : {len(report.failures)}")
        print("=" * 80)

        return report

    def _discover_document_directories(
        self, input_dir: Path, target_doc_id: Optional[str]
    ) -> List[Path]:
        """Find valid document directories containing <doc_id>_structured.json."""
        doc_dirs: List[Path] = []
        for cat_dir in sorted(input_dir.iterdir()):
            if cat_dir.is_dir():
                for sub_dir in sorted(cat_dir.iterdir()):
                    if sub_dir.is_dir():
                        doc_id = sub_dir.name
                        if target_doc_id and doc_id != target_doc_id:
                            continue
                        json_file = sub_dir / f"{doc_id}_structured.json"
                        if json_file.exists():
                            doc_dirs.append(sub_dir)
        return doc_dirs

    def _get_free_disk_space_mb(self, path: Path) -> float:
        """Query free disk space in megabytes for the drive containing path."""
        try:
            total, used, free = shutil.disk_usage(path if path.exists() else path.parent)
            return free / (1024 * 1024)
        except Exception:
            return 999999.0

    def _write_jsonl_atomically(self, chunks: List[ChunkRecord], target_path: Path) -> int:
        """Write chunk records to a temporary file, validate, and atomically replace target."""
        target_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = target_path.with_suffix(".jsonl.tmp")

        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                for chunk in chunks:
                    line = json.dumps(chunk.to_dict(), ensure_ascii=False)
                    f.write(line + "\n")

            # Replace atomically
            temp_path.replace(target_path)
            return target_path.stat().st_size
        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            raise

    def _write_manifest(self, report: PilotRunnerReport, manifest_path: Path) -> None:
        """Write global manifest as JSON."""
        data = asdict(report)
        temp_path = manifest_path.with_suffix(".json.tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            temp_path.replace(manifest_path)
        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            raise
