"""Preflight inspector for document extraction.

Inspects PDF page counts, page dimensions, rotation, text availability, embedded images,
and suspicious pages, reusing existing inventory reports to avoid redundant scans.
"""

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from app.ingestion.extraction.config import ExtractionConfig
from app.ingestion.extraction.models import QualityWarning


@dataclass
class PagePreflightInfo:
    """Preflight diagnostic metrics for an individual page."""

    page_number: int
    width: float
    height: float
    rotation: int  # 0, 90, 180, 270
    is_rotated: bool
    text_length: int = 0
    word_count: int = 0
    image_count: int = 0
    is_empty: bool = False
    is_low_text: bool = False
    is_ocr_candidate: bool = False
    is_garbled_suspect: bool = False
    likely_table_count: int = 0
    flag_reasons: List[str] = field(default_factory=list)


@dataclass
class PreflightReport:
    """Preflight inspection report for a PDF document."""

    file_path: Path
    file_name: str
    file_size_bytes: int
    sha256_hash: str
    page_count: int
    pages: List[PagePreflightInfo] = field(default_factory=list)

    # Document-level flags
    rotated_pages_count: int = 0
    empty_pages_count: int = 0
    low_text_pages_count: int = 0
    ocr_candidate_pages_count: int = 0
    garbled_suspect_pages_count: int = 0
    likely_table_pages_count: int = 0
    non_standard_dimensions_count: int = 0

    reused_inventory: bool = False
    warnings: List[QualityWarning] = field(default_factory=list)


class PreflightInspector:
    """Performs non-destructive preflight diagnostics before full document parsing."""

    def __init__(self, config: ExtractionConfig) -> None:
        self.config = config
        self._inventory_cache: Optional[Dict[str, Dict[str, Any]]] = None

    def _load_inventory(self) -> Dict[str, Dict[str, Any]]:
        """Load pre-scanned inventory records if available."""
        if self._inventory_cache is not None:
            return self._inventory_cache

        self._inventory_cache = {}
        inv_path = self.config.inventory_json_path
        if inv_path.exists():
            try:
                with open(inv_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for doc in data.get("documents", []):
                        fn = doc.get("file_name", "")
                        fp = doc.get("file_path", "")
                        self._inventory_cache[fn] = doc
                        self._inventory_cache[fp] = doc
            except Exception:
                pass
        return self._inventory_cache

    def inspect_pdf(self, pdf_path: Path) -> PreflightReport:
        """Inspect a single PDF, combining cached inventory with PyMuPDF layout checks."""
        pdf_path = Path(pdf_path).resolve()
        if not pdf_path.is_file():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")

        inventory = self._load_inventory()
        cached_record = inventory.get(pdf_path.name) or inventory.get(
            str(pdf_path.relative_to(self.config.project_root) if pdf_path.is_relative_to(self.config.project_root) else pdf_path).replace("\\", "/")
        )

        doc = fitz.open(pdf_path)
        page_count = len(doc)
        file_size = pdf_path.stat().st_size
        sha256 = cached_record.get("sha256_hash", "") if cached_record else ""

        report = PreflightReport(
            file_path=pdf_path,
            file_name=pdf_path.name,
            file_size_bytes=file_size,
            sha256_hash=sha256,
            page_count=page_count,
            reused_inventory=cached_record is not None,
        )

        # Cache per-page metrics from inventory if present
        cached_pages_by_num: Dict[int, Dict[str, Any]] = {}
        if cached_record:
            for cp in cached_record.get("pages", []):
                cached_pages_by_num[cp.get("page_number", 0)] = cp

        for page_idx, page in enumerate(doc, start=1):
            rect = page.rect
            width = float(rect.width)
            height = float(rect.height)
            rotation = int(page.rotation)
            is_rotated = rotation != 0

            # Standard letter is ~612x792, standard A4 is ~595x842
            is_standard = (abs(width - 612) < 20 and abs(height - 792) < 20) or (
                abs(width - 595) < 20 and abs(height - 842) < 20
            )

            cached_page = cached_pages_by_num.get(page_idx)
            if cached_page:
                text_len = cached_page.get("text_length", 0)
                word_cnt = cached_page.get("word_count", 0)
                img_cnt = cached_page.get("image_count", 0)
                is_empty = cached_page.get("is_empty", False)
                is_low_text = cached_page.get("is_low_text", False)
                is_scanned = cached_page.get("is_suspected_scanned", False)
                is_garbled = cached_page.get("is_garbled_text", False)
                table_cnt = cached_page.get("likely_table_heuristic_count", 0)
                reasons = list(cached_page.get("flag_reasons", []))
            else:
                # Fallback: compute directly from page
                text = page.get_text() or ""
                stripped = text.strip()
                text_len = len(stripped)
                word_cnt = len(stripped.split())
                images = page.get_images(full=True)
                img_cnt = len(images) if images else 0
                is_empty = text_len == 0
                is_low_text = 0 < text_len < self.config.low_text_threshold
                is_scanned = (text_len < self.config.ocr_low_text_threshold) and (img_cnt >= 1)
                is_garbled = False
                table_cnt = 0
                reasons = []

            is_ocr_candidate = is_scanned or (text_len < self.config.ocr_low_text_threshold and img_cnt >= 1)

            page_info = PagePreflightInfo(
                page_number=page_idx,
                width=width,
                height=height,
                rotation=rotation,
                is_rotated=is_rotated,
                text_length=text_len,
                word_count=word_cnt,
                image_count=img_cnt,
                is_empty=is_empty,
                is_low_text=is_low_text,
                is_ocr_candidate=is_ocr_candidate,
                is_garbled_suspect=is_garbled,
                likely_table_count=table_cnt,
                flag_reasons=reasons,
            )

            report.pages.append(page_info)

            if is_rotated:
                report.rotated_pages_count += 1
                report.warnings.append(
                    QualityWarning(
                        category="rotated_page",
                        message=f"Page {page_idx} has non-zero rotation ({rotation}°)",
                        severity="info",
                        page_number=page_idx,
                        details={"rotation": rotation},
                    )
                )
            if not is_standard:
                report.non_standard_dimensions_count += 1
            if is_empty:
                report.empty_pages_count += 1
            if is_low_text:
                report.low_text_pages_count += 1
            if is_ocr_candidate:
                report.ocr_candidate_pages_count += 1
                report.warnings.append(
                    QualityWarning(
                        category="ocr_candidate",
                        message=f"Page {page_idx} has little text ({text_len} chars) with {img_cnt} image(s); candidate for OCR verification",
                        severity="warning",
                        page_number=page_idx,
                        details={"text_length": text_len, "image_count": img_cnt},
                    )
                )
            if is_garbled:
                report.garbled_suspect_pages_count += 1
            if table_cnt > 0:
                report.likely_table_pages_count += 1

        doc.close()
        return report
