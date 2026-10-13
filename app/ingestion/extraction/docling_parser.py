"""Docling primary layout-aware parser integration.

Provides structured extraction (headings, paragraphs, reading order, lists, tables,
captions, and figure references) using Docling when installed, with a clean integration
boundary and detailed diagnostics when the dependency is missing.
"""

from datetime import datetime
import importlib.util
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.ingestion.extraction.config import ExtractionConfig
from app.ingestion.extraction.models import (
    BlockType,
    BoundingBox,
    ExtractedDocument,
    ExtractedPage,
    ExtractionMethod,
    FigureAsset,
    QualityWarning,
    TableCell,
    TableData,
    TextBlock,
)
from app.ingestion.extraction.preflight import PreflightReport

# Check Docling availability without raising uncaught exceptions
DOCLING_AVAILABLE = False
DOCLING_VERSION: Optional[str] = None

try:
    import docling  # type: ignore

    DOCLING_AVAILABLE = True
    DOCLING_VERSION = getattr(docling, "__version__", "unknown")
except ImportError:
    DOCLING_AVAILABLE = False


class DoclingNotAvailableError(ImportError):
    """Raised when Docling parsing is attempted without docling installed."""

    pass


class DoclingParser:
    """Primary parser utilizing Docling for layout-aware document structuring."""

    def __init__(self, config: ExtractionConfig) -> None:
        self.config = config
        self._converter: Optional[Any] = None

    @classmethod
    def is_available(cls) -> bool:
        """Check if Docling is installed in the current environment."""
        return DOCLING_AVAILABLE

    @classmethod
    def get_diagnostics(cls) -> Dict[str, Any]:
        """Return diagnostic information regarding Docling installation and compatibility."""
        return {
            "installed": DOCLING_AVAILABLE,
            "version": DOCLING_VERSION,
            "primary_package": "docling",
            "status": "READY" if DOCLING_AVAILABLE else "MISSING_DEPENDENCY",
            "memory_and_storage_note": (
                "Docling utilizes local deep-learning models (e.g. DocLayNet layout analysis, "
                "TableFormer for complex tables). On a 16 GB RAM laptop, default pipeline execution "
                "should disable blanket OCR (do_ocr=False) and operate in lightweight mode to prevent "
                "excessive model downloads and memory thrashing."
            ),
        }

    def _init_converter(self) -> Any:
        """Lazy initialization of DocumentConverter with conservative memory options."""
        if not DOCLING_AVAILABLE:
            raise DoclingNotAvailableError(
                "Docling is not installed in the active Python environment. "
                "The pipeline will gracefully use the PyMuPDF supporting parser."
            )

        if self._converter is not None:
            return self._converter

        try:
            from docling.datamodel.base_models import InputFormat  # type: ignore
            from docling.datamodel.pipeline_options import PdfPipelineOptions  # type: ignore
            from docling.document_converter import DocumentConverter, PdfFormatOption  # type: ignore

            pipeline_options = PdfPipelineOptions()
            # Do not run Docling internal heavy OCR automatically (respecting 16 GB RAM constraints)
            pipeline_options.do_ocr = False
            pipeline_options.do_table_structure = True

            self._converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
                }
            )
            return self._converter
        except Exception as exc:
            raise RuntimeError(f"Failed to initialize Docling converter: {exc}") from exc

    def parse_document(
        self,
        pdf_path: Path,
        preflight_report: Optional[PreflightReport] = None,
    ) -> Optional[ExtractedDocument]:
        """Parse PDF with Docling, mapping its document representation to unified ExtractedDocument."""
        if not DOCLING_AVAILABLE:
            return None

        converter = self._init_converter()
        pdf_path = Path(pdf_path).resolve()

        conv_result = converter.convert(str(pdf_path))
        docling_doc = conv_result.document

        doc_id = pdf_path.stem
        category = pdf_path.parent.name
        rel_path = str(
            pdf_path.relative_to(self.config.project_root)
            if pdf_path.is_relative_to(self.config.project_root)
            else pdf_path
        ).replace("\\", "/")

        extracted_doc = ExtractedDocument(
            document_id=doc_id,
            file_path=rel_path,
            absolute_path=str(pdf_path),
            category=category,
            file_size_bytes=pdf_path.stat().st_size,
            sha256_hash=preflight_report.sha256_hash if preflight_report else "",
            page_count=preflight_report.page_count if preflight_report else 0,
            primary_parser=f"docling-{DOCLING_VERSION}",
            supporting_parser="pymupdf",
            extracted_at=datetime.now().isoformat(),
        )

        # In standard Docling, items can be iterated or accessed via docling_doc.iterate_items()
        # Group items by page number
        page_items: Dict[int, List[Any]] = {}
        for item, level in getattr(docling_doc, "iterate_items", lambda: [])():
            provs = getattr(item, "prov", []) or []
            page_no = provs[0].page_no if provs else 1
            if page_no not in page_items:
                page_items[page_no] = []
            page_items[page_no].append((item, level))

        total_pages = preflight_report.page_count if preflight_report else max(page_items.keys(), default=1)

        for p_num in range(1, total_pages + 1):
            items_for_page = page_items.get(p_num, [])
            blocks: List[TextBlock] = []
            tables: List[TableData] = []
            figures: List[FigureAsset] = []
            structured_lines: List[str] = []
            headings_on_page: List[str] = []
            for idx, (item, level) in enumerate(items_for_page):
                raw_label = getattr(item, "label", None)
                if raw_label is not None:
                    label_str = raw_label.value if hasattr(raw_label, "value") else str(raw_label)
                    item_label = label_str.lower()
                else:
                    item_label = ""
                item_text = getattr(item, "text", "") or ""

                provs = getattr(item, "prov", []) or []
                bbox = None
                if provs and hasattr(provs[0], "bbox"):
                    b = provs[0].bbox
                    bbox = BoundingBox(left=b.l, top=b.t, right=b.r, bottom=b.b)

                if "heading" in item_label or "title" in item_label:
                    heading_level = getattr(item, "level", level) or 1
                    headings_on_page.append(item_text)
                    blocks.append(
                        TextBlock(
                            block_id=f"p{p_num}_b{idx}",
                            block_type=BlockType.HEADING,
                            text=item_text,
                            reading_order=idx,
                            bbox=bbox,
                            heading_level=heading_level,
                            section_title=item_text,
                        )
                    )
                    structured_lines.append(f"{'#' * min(heading_level + 1, 6)} {item_text}")

                elif "table" in item_label:
                    table_md = getattr(item, "export_to_markdown", lambda: "")() or item_text
                    tbl = TableData(
                        table_id=f"table_p{p_num}_{len(tables) + 1}",
                        page_number=p_num,
                        headers=[],
                        rows=[],
                        markdown=table_md,
                        rows_count=0,
                        cols_count=0,
                        bbox=bbox,
                    )
                    tables.append(tbl)
                    blocks.append(
                        TextBlock(
                            block_id=f"p{p_num}_b{idx}",
                            block_type=BlockType.TABLE,
                            text=table_md,
                            reading_order=idx,
                            bbox=bbox,
                        )
                    )
                    structured_lines.append(table_md)

                elif "picture" in item_label or "figure" in item_label:
                    cap = getattr(item, "caption", "") or item_text
                    fig = FigureAsset(
                        figure_id=f"fig_p{p_num}_{len(figures) + 1}",
                        page_number=p_num,
                        bbox=bbox,
                        caption=cap,
                        status="EXTRACTED_VLM_PENDING",
                    )
                    figures.append(fig)
                    blocks.append(
                        TextBlock(
                            block_id=f"p{p_num}_b{idx}",
                            block_type=BlockType.FIGURE,
                            text=cap or f"[Figure on Page {p_num}]",
                            reading_order=idx,
                            bbox=bbox,
                        )
                    )

                elif "list" in item_label:
                    blocks.append(
                        TextBlock(
                            block_id=f"p{p_num}_b{idx}",
                            block_type=BlockType.LIST_ITEM,
                            text=item_text,
                            reading_order=idx,
                            bbox=bbox,
                        )
                    )
                    structured_lines.append(f"- {item_text}")

                else:
                    blocks.append(
                        TextBlock(
                            block_id=f"p{p_num}_b{idx}",
                            block_type=BlockType.PARAGRAPH,
                            text=item_text,
                            reading_order=idx,
                            bbox=bbox,
                        )
                    )
                    structured_lines.append(item_text)

            extracted_page = ExtractedPage(
                page_number=p_num,
                citation_label=f"[{doc_id} Page {p_num}]",
                width=612.0,
                height=792.0,
                rotation=0,
                extraction_method=ExtractionMethod.DOCLING.value,
                raw_text="",  # Will be populated by PyMuPDF supporting parser
                structured_text="\n\n".join(structured_lines),
                section_headings=headings_on_page,
                blocks=blocks,
                tables=tables,
                figures=figures,
            )
            extracted_doc.pages.append(extracted_page)

        return extracted_doc
