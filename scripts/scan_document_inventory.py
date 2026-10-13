"""Automated Document Inventory and PDF Quality Scanner (Stage 1 Ingestion).

Inspects original source documents recursively under `documents/` using PyMuPDF.
Produces structured JSON and CSV reports under `data/document_inventory/`.

Features:
- File metadata, file size, SHA-256 hash duplicate detection.
- PDF metadata (title, author, creation date, etc.) and page count.
- Per-page text length, word count, and embedded image count.
- Quality flags: empty pages, low-text pages, garbled text, and suspected scanned pages.
- Table detection heuristic using PyMuPDF table finder (clearly labeled as heuristic).
- Flags unreadable/encrypted PDFs and captures extraction exceptions gracefully.
- Generates summary of documents and pages requiring manual or OCR inspection.
- Purely read-only: does not modify source files, does not touch Qdrant, does not run OCR.
"""

import argparse
import csv
from dataclasses import asdict, dataclass, field
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

# Ensure UTF-8 output on Windows consoles
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import PyMuPDF
try:
    import pymupdf as fitz
except ImportError:
    try:
        import fitz
    except ImportError:
        print("[CRITICAL ERROR] PyMuPDF is not installed. Please ensure 'pymupdf' is installed.")
        sys.exit(1)


# ==============================================================================
# DATA MODELS
# ==============================================================================

@dataclass
class PageQualityMetrics:
    """Per-page extraction and quality indicators."""

    page_number: int
    text_length: int
    word_count: int
    image_count: int
    is_empty: bool
    is_low_text: bool
    is_suspected_scanned: bool
    is_garbled_text: bool
    likely_table_heuristic_count: int
    has_likely_table_heuristic: bool
    flag_reasons: List[str] = field(default_factory=list)


@dataclass
class DocumentInventoryRecord:
    """Document-level inventory record and aggregate quality indicators."""

    file_path: str
    absolute_path: str
    file_name: str
    category: str
    file_size_bytes: int
    file_size_formatted: str
    sha256_hash: str
    is_duplicate: bool = False
    duplicate_of: List[str] = field(default_factory=list)

    # PDF Metadata
    page_count: int = 0
    title: str = ""
    author: str = ""
    subject: str = ""
    keywords: str = ""
    creator: str = ""
    producer: str = ""
    creation_date: str = ""
    modification_date: str = ""
    is_encrypted: bool = False

    # Aggregate Extraction Metrics
    total_text_length: int = 0
    total_word_count: int = 0
    total_image_count: int = 0
    empty_pages_count: int = 0
    low_text_pages_count: int = 0
    suspected_scanned_pages_count: int = 0
    garbled_pages_count: int = 0
    likely_table_pages_count: int = 0

    # Inspection Flags & Status
    scan_status: str = "OK"  # OK, NEEDS_INSPECTION, ENCRYPTED, CORRUPTED, ERROR
    requires_inspection: bool = False
    inspection_reasons: List[str] = field(default_factory=list)
    flagged_pages: List[int] = field(default_factory=list)
    error_message: Optional[str] = None

    # Per-page details
    pages: List[PageQualityMetrics] = field(default_factory=list)


# ==============================================================================
# QUALITY DETECTION HEURISTICS
# ==============================================================================

def format_file_size(size_bytes: int) -> str:
    """Format raw byte count into human-readable representation."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def compute_file_sha256(file_path: Path, chunk_size: int = 65536) -> str:
    """Calculate SHA-256 hash of a file for byte-identical duplicate detection."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def detect_garbled_text(text: str) -> bool:
    """Detect whether extracted page text appears garbled or corrupted.

    Heuristics:
    1. High ratio of replacement characters (U+FFFD) or non-printable control characters.
    2. Abnormally low alphanumeric density on pages with non-trivial text length (ignoring dot leaders/punctuation).
    3. Abnormally long alphanumeric tokens without punctuation/whitespace (indicative of broken ligatures/encodings).
    """
    if not text or len(text.strip()) < 50:
        return False

    stripped = text.strip()
    total_chars = len(stripped)

    # 1. Check replacement character frequency
    replacement_chars = stripped.count("\ufffd")
    if replacement_chars / total_chars > 0.05:
        return True

    # 2. Control characters (excluding newline, carriage return, tab)
    control_chars = sum(
        1 for c in stripped if ord(c) < 32 and c not in ("\n", "\r", "\t")
    )
    if control_chars / total_chars > 0.03:
        return True

    # 3. Alphanumeric density check (strip repeated leaders like '....' to evaluate genuine text density)
    clean_non_dots = "".join(c for c in stripped if c != ".")
    if len(clean_non_dots) >= 50:
        alnum_chars = sum(1 for c in clean_non_dots if c.isalnum())
        if alnum_chars / len(clean_non_dots) < 0.25:
            return True

    # 4. Genuinely garbled token check: abnormally long unbroken ALPHANUMERIC strings (> 60 chars)
    # Exclude URLs, file paths, and divider bars
    for word in stripped.split():
        if word.startswith(("http://", "https://", "ftp://", "www.")) or "://" in word:
            continue
        core = "".join(c for c in word if c.isalnum())
        if len(core) > 60:
            return True

    return False


def detect_likely_tables_heuristic(page: Any) -> int:
    """Heuristic check for possible tables on a page using PyMuPDF table finder.

    NOTE: This is a structural heuristic and does NOT guarantee clean tabular data extraction.
    """
    try:
        if hasattr(page, "find_tables"):
            tabs = page.find_tables()
            if hasattr(tabs, "tables"):
                return len(tabs.tables)
    except Exception:
        pass
    return 0


# ==============================================================================
# CORE SCANNER IMPLEMENTATION
# ==============================================================================

class DocumentInventoryScanner:
    """Scans PDF documents recursively to build a quality inventory."""

    def __init__(
        self,
        documents_dir: Path,
        output_dir: Path,
        low_text_threshold: int = 100,
    ) -> None:
        self.documents_dir = Path(documents_dir).resolve()
        self.output_dir = Path(output_dir).resolve()
        self.low_text_threshold = low_text_threshold
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def scan_page(self, page: Any, page_num: int) -> PageQualityMetrics:
        """Analyze a single page and evaluate its quality metrics."""
        text = page.get_text() or ""
        stripped_text = text.strip()
        text_len = len(stripped_text)
        words = stripped_text.split()
        word_count = len(words)

        # Count embedded images
        try:
            images = page.get_images(full=True)
            image_count = len(images) if images else 0
        except Exception:
            image_count = 0

        # Quality evaluations
        is_empty = text_len == 0
        is_low_text = 0 < text_len < self.low_text_threshold

        # Suspected scanned page: page has little or no extractable text, but contains images
        is_suspected_scanned = (text_len < 50) and (image_count >= 1)

        # Garbled text check
        is_garbled = detect_garbled_text(stripped_text)

        # Table heuristic detection
        table_count = detect_likely_tables_heuristic(page)
        has_likely_table = table_count > 0

        flag_reasons: List[str] = []
        if is_empty:
            flag_reasons.append("empty_page")
        if is_low_text:
            flag_reasons.append("low_text_page")
        if is_suspected_scanned:
            flag_reasons.append("suspected_scanned_page")
        if is_garbled:
            flag_reasons.append("garbled_text")
        if has_likely_table:
            flag_reasons.append("likely_table_heuristic")

        return PageQualityMetrics(
            page_number=page_num,
            text_length=text_len,
            word_count=word_count,
            image_count=image_count,
            is_empty=is_empty,
            is_low_text=is_low_text,
            is_suspected_scanned=is_suspected_scanned,
            is_garbled_text=is_garbled,
            likely_table_heuristic_count=table_count,
            has_likely_table_heuristic=has_likely_table,
            flag_reasons=flag_reasons,
        )

    def scan_single_document(self, file_path: Path) -> DocumentInventoryRecord:
        """Perform non-destructive scan of an individual PDF file."""
        rel_path = str(file_path.relative_to(PROJECT_ROOT) if file_path.is_relative_to(PROJECT_ROOT) else file_path)
        category = file_path.parent.name if file_path.parent != self.documents_dir else "root"
        file_size = file_path.stat().st_size
        sha256_hash = compute_file_sha256(file_path)

        record = DocumentInventoryRecord(
            file_path=rel_path.replace("\\", "/"),
            absolute_path=str(file_path.resolve()),
            file_name=file_path.name,
            category=category,
            file_size_bytes=file_size,
            file_size_formatted=format_file_size(file_size),
            sha256_hash=sha256_hash,
        )

        doc = None
        try:
            doc = fitz.open(file_path)

            if getattr(doc, "is_encrypted", False) or getattr(doc, "needs_pass", False):
                record.is_encrypted = True
                record.scan_status = "ENCRYPTED"
                record.requires_inspection = True
                record.inspection_reasons.append("document_is_encrypted")
                record.error_message = "Document is password protected or encrypted"
                return record

            record.page_count = len(doc)

            # Metadata extraction
            metadata = doc.metadata or {}
            record.title = str(metadata.get("title") or "").strip()
            record.author = str(metadata.get("author") or "").strip()
            record.subject = str(metadata.get("subject") or "").strip()
            record.keywords = str(metadata.get("keywords") or "").strip()
            record.creator = str(metadata.get("creator") or "").strip()
            record.producer = str(metadata.get("producer") or "").strip()
            record.creation_date = str(metadata.get("creationDate") or "").strip()
            record.modification_date = str(metadata.get("modDate") or "").strip()

            flagged_pages_set: Set[int] = set()

            # Iterate through pages
            for page_idx, page in enumerate(doc, start=1):
                try:
                    page_metric = self.scan_page(page, page_idx)
                    record.pages.append(page_metric)

                    record.total_text_length += page_metric.text_length
                    record.total_word_count += page_metric.word_count
                    record.total_image_count += page_metric.image_count

                    if page_metric.is_empty:
                        record.empty_pages_count += 1
                        flagged_pages_set.add(page_idx)
                    if page_metric.is_low_text:
                        record.low_text_pages_count += 1
                        flagged_pages_set.add(page_idx)
                    if page_metric.is_suspected_scanned:
                        record.suspected_scanned_pages_count += 1
                        flagged_pages_set.add(page_idx)
                    if page_metric.is_garbled_text:
                        record.garbled_pages_count += 1
                        flagged_pages_set.add(page_idx)
                    if page_metric.has_likely_table_heuristic:
                        record.likely_table_pages_count += 1

                except Exception as page_exc:
                    # Isolate page error without crashing document scan
                    record.pages.append(
                        PageQualityMetrics(
                            page_number=page_idx,
                            text_length=0,
                            word_count=0,
                            image_count=0,
                            is_empty=True,
                            is_low_text=False,
                            is_suspected_scanned=False,
                            is_garbled_text=False,
                            likely_table_heuristic_count=0,
                            has_likely_table_heuristic=False,
                            flag_reasons=[f"page_extraction_error: {str(page_exc)}"],
                        )
                    )
                    flagged_pages_set.add(page_idx)

            record.flagged_pages = sorted(flagged_pages_set)

            # Evaluate inspection needs
            inspection_reasons = []
            if record.suspected_scanned_pages_count > 0:
                inspection_reasons.append(
                    f"{record.suspected_scanned_pages_count} suspected scanned pages (needs OCR verification)"
                )
            if record.garbled_pages_count > 0:
                inspection_reasons.append(
                    f"{record.garbled_pages_count} garbled pages (potential font encoding failure)"
                )
            if record.page_count == 0:
                inspection_reasons.append("zero_page_document")
            elif record.empty_pages_count == record.page_count:
                inspection_reasons.append("all_pages_empty")

            if inspection_reasons:
                record.scan_status = "NEEDS_INSPECTION"
                record.requires_inspection = True
                record.inspection_reasons = inspection_reasons
            else:
                record.scan_status = "OK"

        except Exception as doc_exc:
            record.scan_status = "ERROR"
            record.requires_inspection = True
            record.inspection_reasons.append(f"document_read_error: {str(doc_exc)}")
            record.error_message = str(doc_exc)

        finally:
            if doc is not None:
                try:
                    doc.close()
                except Exception:
                    pass

        return record

    def scan_documents(
        self,
        specific_files: Optional[List[Path]] = None,
        max_docs: Optional[int] = None,
        verbose: bool = True,
    ) -> Dict[str, Any]:
        """Discover and scan PDF documents, generating reports."""
        if specific_files:
            pdf_files = [f.resolve() for f in specific_files if f.is_file() and f.suffix.lower() == ".pdf"]
        else:
            # Exclude non-PDF and generated files
            pdf_files = sorted(
                [
                    p.resolve()
                    for p in self.documents_dir.rglob("*.pdf")
                    if p.is_file() and not p.name.startswith((".", "~$"))
                ]
            )

        if max_docs is not None and max_docs > 0:
            pdf_files = pdf_files[:max_docs]

        total_files = len(pdf_files)
        print("=" * 78)
        print("STAGE 1: AUTOMATED DOCUMENT INVENTORY & PDF QUALITY SCANNER")
        print("=" * 78)
        print(f"Source Directory    : {self.documents_dir}")
        print(f"Output Directory    : {self.output_dir}")
        print(f"Documents to Scan   : {total_files:,}")
        print(f"Scan Mode           : Non-destructive, read-only PyMuPDF inspection")
        print("=" * 78 + "\n")

        records: List[DocumentInventoryRecord] = []
        hash_to_files: Dict[str, List[str]] = {}

        for idx, file_path in enumerate(pdf_files, start=1):
            if verbose:
                print(f"[{idx}/{total_files}] Scanning: {file_path.name} ({format_file_size(file_path.stat().st_size)})")

            record = self.scan_single_document(file_path)
            records.append(record)

            # Duplicate tracking
            h = record.sha256_hash
            if h not in hash_to_files:
                hash_to_files[h] = []
            hash_to_files[h].append(record.file_path)

        # Flag byte-identical duplicates
        duplicate_groups: Dict[str, List[str]] = {
            h: paths for h, paths in hash_to_files.items() if len(paths) > 1
        }
        duplicate_docs_count = 0
        for record in records:
            if len(hash_to_files[record.sha256_hash]) > 1:
                record.is_duplicate = True
                record.duplicate_of = [
                    p for p in hash_to_files[record.sha256_hash] if p != record.file_path
                ]
                duplicate_docs_count += 1
                if "byte_identical_duplicate" not in record.inspection_reasons:
                    record.inspection_reasons.append("byte_identical_duplicate")
                record.requires_inspection = True

        # Aggregate summary metrics
        total_pages = sum(r.page_count for r in records)
        total_bytes = sum(r.file_size_bytes for r in records)
        total_chars = sum(r.total_text_length for r in records)
        total_words = sum(r.total_word_count for r in records)
        total_images = sum(r.total_image_count for r in records)
        total_empty_pages = sum(r.empty_pages_count for r in records)
        total_low_text_pages = sum(r.low_text_pages_count for r in records)
        total_scanned_pages = sum(r.suspected_scanned_pages_count for r in records)
        total_garbled_pages = sum(r.garbled_pages_count for r in records)
        total_table_pages = sum(r.likely_table_pages_count for r in records)
        total_errors = sum(1 for r in records if r.scan_status == "ERROR")
        total_encrypted = sum(1 for r in records if r.is_encrypted)
        flagged_docs = [r for r in records if r.requires_inspection]

        summary = {
            "generated_at": datetime.now().isoformat(),
            "total_documents_scanned": total_files,
            "total_pages_scanned": total_pages,
            "total_file_size_bytes": total_bytes,
            "total_file_size_formatted": format_file_size(total_bytes),
            "total_extractable_characters": total_chars,
            "total_extractable_words": total_words,
            "total_embedded_images": total_images,
            "total_suspected_scanned_pages": total_scanned_pages,
            "total_empty_pages": total_empty_pages,
            "total_low_text_pages": total_low_text_pages,
            "total_garbled_text_pages": total_garbled_pages,
            "total_table_pages_heuristic": total_table_pages,
            "total_errors": total_errors,
            "total_encrypted": total_encrypted,
            "unique_sha256_hashes": len(hash_to_files),
            "duplicate_documents_count": duplicate_docs_count,
            "duplicate_groups_count": len(duplicate_groups),
            "documents_requiring_inspection_count": len(flagged_docs),
        }

        # Write reports
        json_report_path = self.output_dir / "document_inventory.json"
        csv_report_path = self.output_dir / "document_inventory.csv"
        page_csv_path = self.output_dir / "page_inventory.csv"

        self._write_json_report(json_report_path, summary, duplicate_groups, records, flagged_docs)
        self._write_document_csv(csv_report_path, records)
        self._write_page_csv(page_csv_path, records)

        print("\n" + "=" * 78)
        print("STAGE 1 SCAN COMPLETED: SUMMARY & ARTIFACTS")
        print("=" * 78)
        print(f"Total Documents Scanned        : {total_files:,}")
        print(f"Total Pages Analyzed           : {total_pages:,}")
        print(f"Total Extractable Characters   : {total_chars:,} (~{total_words:,} words)")
        print(f"Total Embedded Images Detected : {total_images:,}")
        print(f"Suspected Scanned Pages        : {total_scanned_pages:,}")
        print(f"Empty Pages                    : {total_empty_pages:,}")
        print(f"Low-Text Pages (<{self.low_text_threshold} chars)       : {total_low_text_pages:,}")
        print(f"Garbled Text Pages             : {total_garbled_pages:,}")
        print(f"Likely Table Pages (Heuristic) : {total_table_pages:,}")
        print(f"Encrypted / Unreadable PDFs    : {total_encrypted:,}")
        print(f"Duplicate Documents (SHA-256)  : {duplicate_docs_count:,} in {len(duplicate_groups)} group(s)")
        print(f"Documents Flagged for Review   : {len(flagged_docs):,}")
        print("-" * 78)
        print(f"Generated JSON Report          : {json_report_path}")
        print(f"Generated Document CSV Report  : {csv_report_path}")
        print(f"Generated Page Details CSV     : {page_csv_path}")
        print("=" * 78 + "\n")

        if flagged_docs:
            print("Documents Requiring Inspection:")
            for d in flagged_docs[:10]:
                print(f"  - {d.file_name} ({d.category})")
                print(f"    Reasons: {', '.join(d.inspection_reasons)}")
                if d.flagged_pages:
                    sample_pages = d.flagged_pages[:8]
                    suffix = "..." if len(d.flagged_pages) > 8 else ""
                    print(f"    Flagged Pages: {sample_pages}{suffix}")
            if len(flagged_docs) > 10:
                print(f"  ... and {len(flagged_docs) - 10} more (see document_inventory.json).")
            print("=" * 78 + "\n")

        return {
            "summary": summary,
            "json_path": str(json_report_path),
            "csv_path": str(csv_report_path),
            "page_csv_path": str(page_csv_path),
            "records": records,
        }

    def _write_json_report(
        self,
        output_path: Path,
        summary: Dict[str, Any],
        duplicate_groups: Dict[str, List[str]],
        records: List[DocumentInventoryRecord],
        flagged_docs: List[DocumentInventoryRecord],
    ) -> None:
        """Serialize complete inventory to structured JSON."""
        payload = {
            "summary": summary,
            "duplicate_groups": duplicate_groups,
            "documents_requiring_inspection": [
                {
                    "file_path": r.file_path,
                    "file_name": r.file_name,
                    "category": r.category,
                    "page_count": r.page_count,
                    "scan_status": r.scan_status,
                    "inspection_reasons": r.inspection_reasons,
                    "flagged_pages": r.flagged_pages,
                    "suspected_scanned_pages": r.suspected_scanned_pages_count,
                    "empty_pages": r.empty_pages_count,
                    "low_text_pages": r.low_text_pages_count,
                    "garbled_pages": r.garbled_pages_count,
                    "error_message": r.error_message,
                }
                for r in flagged_docs
            ],
            "documents": [asdict(r) for r in records],
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    def _write_document_csv(
        self,
        output_path: Path,
        records: List[DocumentInventoryRecord],
    ) -> None:
        """Export document-level inventory to CSV."""
        fieldnames = [
            "file_name",
            "category",
            "file_path",
            "file_size_bytes",
            "file_size_formatted",
            "sha256_hash",
            "is_duplicate",
            "duplicate_count",
            "page_count",
            "title",
            "author",
            "creation_date",
            "total_text_length",
            "total_word_count",
            "total_image_count",
            "empty_pages_count",
            "low_text_pages_count",
            "suspected_scanned_pages_count",
            "garbled_pages_count",
            "likely_table_pages_count",
            "scan_status",
            "requires_inspection",
            "inspection_reasons",
            "flagged_pages_count",
            "error_message",
        ]

        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in records:
                writer.writerow(
                    {
                        "file_name": r.file_name,
                        "category": r.category,
                        "file_path": r.file_path,
                        "file_size_bytes": r.file_size_bytes,
                        "file_size_formatted": r.file_size_formatted,
                        "sha256_hash": r.sha256_hash,
                        "is_duplicate": r.is_duplicate,
                        "duplicate_count": len(r.duplicate_of),
                        "page_count": r.page_count,
                        "title": r.title,
                        "author": r.author,
                        "creation_date": r.creation_date,
                        "total_text_length": r.total_text_length,
                        "total_word_count": r.total_word_count,
                        "total_image_count": r.total_image_count,
                        "empty_pages_count": r.empty_pages_count,
                        "low_text_pages_count": r.low_text_pages_count,
                        "suspected_scanned_pages_count": r.suspected_scanned_pages_count,
                        "garbled_pages_count": r.garbled_pages_count,
                        "likely_table_pages_count": r.likely_table_pages_count,
                        "scan_status": r.scan_status,
                        "requires_inspection": r.requires_inspection,
                        "inspection_reasons": "; ".join(r.inspection_reasons),
                        "flagged_pages_count": len(r.flagged_pages),
                        "error_message": r.error_message or "",
                    }
                )

    def _write_page_csv(
        self,
        output_path: Path,
        records: List[DocumentInventoryRecord],
    ) -> None:
        """Export page-level inventory to CSV."""
        fieldnames = [
            "file_name",
            "file_path",
            "page_number",
            "text_length",
            "word_count",
            "image_count",
            "is_empty",
            "is_low_text",
            "is_suspected_scanned",
            "is_garbled_text",
            "likely_table_heuristic_count",
            "has_likely_table_heuristic",
            "flag_reasons",
        ]

        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in records:
                for p in r.pages:
                    writer.writerow(
                        {
                            "file_name": r.file_name,
                            "file_path": r.file_path,
                            "page_number": p.page_number,
                            "text_length": p.text_length,
                            "word_count": p.word_count,
                            "image_count": p.image_count,
                            "is_empty": p.is_empty,
                            "is_low_text": p.is_low_text,
                            "is_suspected_scanned": p.is_suspected_scanned,
                            "is_garbled_text": p.is_garbled_text,
                            "likely_table_heuristic_count": p.likely_table_heuristic_count,
                            "has_likely_table_heuristic": p.has_likely_table_heuristic,
                            "flag_reasons": "; ".join(p.flag_reasons),
                        }
                    )


# ==============================================================================
# CLI ENTRY POINT
# ==============================================================================

def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Automated Document Inventory and PDF Quality Scanner (Stage 1)."
    )
    parser.add_argument(
        "--documents-dir",
        type=Path,
        default=PROJECT_ROOT / "documents",
        help="Root directory containing original source PDFs (default: documents/)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "document_inventory",
        help="Directory to save inventory JSON and CSV reports (default: data/document_inventory/)",
    )
    parser.add_argument(
        "--max-docs",
        type=int,
        default=None,
        help="Maximum number of documents to scan (useful for smoke tests)",
    )
    parser.add_argument(
        "--files",
        nargs="+",
        type=Path,
        default=None,
        help="Specific PDF file paths to scan (overrides recursive discovery)",
    )
    parser.add_argument(
        "--low-text-threshold",
        type=int,
        default=100,
        help="Character count threshold for low-text page flagging (default: 100)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce verbose per-file terminal output",
    )

    args = parser.parse_args()

    scanner = DocumentInventoryScanner(
        documents_dir=args.documents_dir,
        output_dir=args.output_dir,
        low_text_threshold=args.low_text_threshold,
    )

    result = scanner.scan_documents(
        specific_files=args.files,
        max_docs=args.max_docs,
        verbose=not args.quiet,
    )

    if result["summary"]["total_errors"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
