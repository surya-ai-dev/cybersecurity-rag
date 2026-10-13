"""Domain data models for the modular document extraction architecture."""

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class ExtractionMethod(str, Enum):
    """Method used to extract text and structure from a page or document."""

    DOCLING = "docling"
    PYMUPDF_STRUCTURED = "pymupdf_structured"
    PYMUPDF_RAW = "pymupdf_raw"
    OCR_FALLBACK = "ocr_fallback"
    HYBRID = "hybrid"


class BlockType(str, Enum):
    """Classification of structured text blocks."""

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    TABLE = "table"
    FIGURE = "figure"
    CODE = "code"
    PAGE_HEADER = "page_header"
    PAGE_FOOTER = "page_footer"
    FOOTNOTE = "footnote"


@dataclass
class BoundingBox:
    """Normalized or absolute bounding box coordinates [left, top, right, bottom]."""

    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return max(0.0, self.right - self.left)

    @property
    def height(self) -> float:
        return max(0.0, self.bottom - self.top)

    def to_dict(self) -> Dict[str, float]:
        return {
            "left": round(self.left, 2),
            "top": round(self.top, 2),
            "right": round(self.right, 2),
            "bottom": round(self.bottom, 2),
            "width": round(self.width, 2),
            "height": round(self.height, 2),
        }

    @classmethod
    def from_tuple(cls, coords: Tuple[float, float, float, float]) -> "BoundingBox":
        return cls(left=coords[0], top=coords[1], right=coords[2], bottom=coords[3])

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BoundingBox":
        """Instantiate BoundingBox from dictionary, safely ignoring extra keys."""
        return cls(
            left=float(data.get("left", 0.0)),
            top=float(data.get("top", 0.0)),
            right=float(data.get("right", 0.0)),
            bottom=float(data.get("bottom", 0.0)),
        )


@dataclass
class QualityWarning:
    """Represents an automated extraction quality observation or potential issue."""

    category: str  # e.g., 'empty_page', 'low_text', 'ocr_candidate', 'garbled_text', 'table_irregularity'
    message: str
    severity: str = "warning"  # 'info', 'warning', 'critical'
    page_number: Optional[int] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "category": self.category,
            "message": self.message,
            "severity": self.severity,
        }
        if self.page_number is not None:
            result["page_number"] = self.page_number
        if self.details:
            result["details"] = self.details
        return result


@dataclass
class TextBlock:
    """Individual block of content with reading order and layout coordinates."""

    block_id: str
    block_type: BlockType
    text: str
    reading_order: int
    bbox: Optional[BoundingBox] = None
    heading_level: Optional[int] = None
    section_title: Optional[str] = None
    confidence: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "block_id": self.block_id,
            "block_type": self.block_type.value if isinstance(self.block_type, BlockType) else self.block_type,
            "text": self.text,
            "reading_order": self.reading_order,
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "heading_level": self.heading_level,
            "section_title": self.section_title,
            "confidence": round(self.confidence, 3),
        }


@dataclass
class TableCell:
    """Individual table cell with coordinate and span information."""

    row_idx: int
    col_idx: int
    text: str
    row_span: int = 1
    col_span: int = 1
    is_header: bool = False
    bbox: Optional[BoundingBox] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "row_idx": self.row_idx,
            "col_idx": self.col_idx,
            "text": self.text,
            "row_span": self.row_span,
            "col_span": self.col_span,
            "is_header": self.is_header,
            "bbox": self.bbox.to_dict() if self.bbox else None,
        }


@dataclass
class TableData:
    """Structured tabular data preserving rows, columns, headers, and Markdown."""

    table_id: str
    page_number: int
    headers: List[str]
    rows: List[List[str]]
    markdown: str
    rows_count: int
    cols_count: int
    bbox: Optional[BoundingBox] = None
    caption: str = ""
    is_headerless: bool = False
    synthetic_headers_applied: bool = False
    cells: List[TableCell] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table_id": self.table_id,
            "page_number": self.page_number,
            "headers": self.headers,
            "rows": self.rows,
            "markdown": self.markdown,
            "rows_count": self.rows_count,
            "cols_count": self.cols_count,
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "caption": self.caption,
            "is_headerless": self.is_headerless,
            "synthetic_headers_applied": self.synthetic_headers_applied,
            "cells": [c.to_dict() for c in self.cells] if self.cells else [],
        }


@dataclass
class FigureAsset:
    """Image or diagram asset preserved from a document page."""

    figure_id: str
    page_number: int
    image_path: Optional[str] = None
    bbox: Optional[BoundingBox] = None
    caption: str = ""
    status: str = "EXTRACTED_VLM_PENDING"  # Explicitly indicates VLM analysis is pending
    diagram_analysis: Optional[str] = None
    width: int = 0
    height: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "figure_id": self.figure_id,
            "page_number": self.page_number,
            "image_path": self.image_path,
            "bbox": self.bbox.to_dict() if self.bbox else None,
            "caption": self.caption,
            "status": self.status,
            "diagram_analysis": self.diagram_analysis,
            "width": self.width,
            "height": self.height,
        }


@dataclass
class ExtractedPage:
    """Page-level extraction container preserving dual representations (raw + structured)."""

    page_number: int
    citation_label: str  # e.g., "[NIST_SP_800-53 Page 2]"
    width: float
    height: float
    rotation: int  # 0, 90, 180, 270
    extraction_method: str
    raw_text: str  # Unaltered PyMuPDF raw text
    structured_text: str  # Layout-ordered text representation
    section_headings: List[str] = field(default_factory=list)
    blocks: List[TextBlock] = field(default_factory=list)
    tables: List[TableData] = field(default_factory=list)
    figures: List[FigureAsset] = field(default_factory=list)
    quality_warnings: List[QualityWarning] = field(default_factory=list)
    has_ocr_applied: bool = False
    ocr_confidence: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_number": self.page_number,
            "citation_label": self.citation_label,
            "dimensions": {"width": round(self.width, 2), "height": round(self.height, 2)},
            "rotation": self.rotation,
            "extraction_method": self.extraction_method,
            "raw_text": self.raw_text,
            "structured_text": self.structured_text,
            "section_headings": self.section_headings,
            "blocks": [b.to_dict() for b in self.blocks],
            "tables": [t.to_dict() for t in self.tables],
            "figures": [f.to_dict() for f in self.figures],
            "quality_warnings": [w.to_dict() for w in self.quality_warnings],
            "has_ocr_applied": self.has_ocr_applied,
            "ocr_confidence": self.ocr_confidence,
        }

    def get_standalone_tables(self) -> List[TableData]:
        """Return tables that are not already embedded in the page's structured text.

        Tracks used text occurrences so multiple separate tables with identical
        contents are not incorrectly merged or skipped.
        """
        if not self.tables:
            return []
        if not self.structured_text:
            return list(self.tables)

        struct_text = self.structured_text
        used_spans: List[Tuple[int, int]] = []
        standalone: List[TableData] = []

        for table in self.tables:
            table_md = (table.markdown or "").strip()
            if not table_md:
                continue

            found = False
            search_pos = 0
            while search_pos < len(struct_text):
                pos = struct_text.find(table_md, search_pos)
                if pos == -1:
                    break
                end_pos = pos + len(table_md)
                overlap = any(not (end_pos <= s[0] or pos >= s[1]) for s in used_spans)
                if not overlap:
                    used_spans.append((pos, end_pos))
                    found = True
                    break
                search_pos = pos + 1

            if not found:
                standalone.append(table)

        return standalone


@dataclass
class ExtractedDocument:
    """Complete document-level extraction record and metadata container."""

    document_id: str
    file_path: str
    absolute_path: str
    category: str
    file_size_bytes: int
    sha256_hash: str
    page_count: int
    primary_parser: str
    supporting_parser: str
    extracted_at: str
    title: str = ""
    author: str = ""
    creation_date: str = ""
    pages: List[ExtractedPage] = field(default_factory=list)
    document_warnings: List[QualityWarning] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "file_path": self.file_path,
            "absolute_path": self.absolute_path,
            "category": self.category,
            "file_size_bytes": self.file_size_bytes,
            "sha256_hash": self.sha256_hash,
            "page_count": self.page_count,
            "primary_parser": self.primary_parser,
            "supporting_parser": self.supporting_parser,
            "extracted_at": self.extracted_at,
            "title": self.title,
            "author": self.author,
            "creation_date": self.creation_date,
            "document_warnings": [w.to_dict() for w in self.document_warnings],
            "errors": self.errors,
            "pages": [p.to_dict() for p in self.pages],
        }

    def export_markdown(self) -> str:
        """Render document into readable Markdown preserving page-level citation boundaries."""
        lines: List[str] = []
        lines.append(f"# {self.title or self.document_id}")
        lines.append("")
        lines.append(f"**Document ID:** `{self.document_id}`  ")
        lines.append(f"**Source:** `{self.file_path}`  ")
        lines.append(f"**Category:** `{self.category}`  ")
        lines.append(f"**Pages:** {self.page_count}  ")
        lines.append(f"**Extraction Engine:** `{self.primary_parser}` (Supporting: `{self.supporting_parser}`)  ")
        lines.append("")
        lines.append("---")
        lines.append("")

        for page in self.pages:
            lines.append(f"## Page {page.page_number} ({page.citation_label})")
            lines.append("")

            if page.section_headings:
                lines.append(f"*Active Sections:* {', '.join(page.section_headings)}")
                lines.append("")

            # Render standalone tables that are not already embedded in structured text
            standalone_tables = page.get_standalone_tables()
            if standalone_tables:
                for table in standalone_tables:
                    if table.caption:
                        lines.append(f"**{table.caption}**")
                        lines.append("")
                    lines.append(table.markdown)
                    lines.append("")

            # Render structured text blocks
            if page.structured_text:
                lines.append(page.structured_text)
                lines.append("")
            elif page.raw_text:
                lines.append(page.raw_text)
                lines.append("")

            # Render figures references
            if page.figures:
                for fig in page.figures:
                    cap = fig.caption or f"Figure p.{page.page_number}"
                    ref = f"![{cap}]({fig.image_path})" if fig.image_path else f"*[Figure placeholder: {cap}]*"
                    lines.append(ref)
                    lines.append(f"> Note: Status: `{fig.status}` - VLM diagram understanding pending.")
                    lines.append("")

            # Quality warnings footnote if present
            if page.quality_warnings:
                lines.append("> [!WARNING]")
                for w in page.quality_warnings:
                    lines.append(f"> - **{w.category}**: {w.message}")
                lines.append("")

            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    def export_raw_text(self) -> str:
        """Export raw text with --- PAGE N --- markers for backward compatibility."""
        chunks: List[str] = []
        for p in self.pages:
            chunks.append(f"--- PAGE {p.page_number} ---\n\n{p.raw_text}")
        return "\n\n".join(chunks)
