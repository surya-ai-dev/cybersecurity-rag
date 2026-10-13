"""Unified pipeline orchestrating document extraction stages.

Coordinates: Preflight -> Parser Execution (Docling / PyMuPDF) -> OCR Fallback ->
Diagram Asset Handling -> Quality Assessment -> Artifact Serialization.
"""

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from app.ingestion.extraction.config import ExtractionConfig
from app.ingestion.extraction.diagram_analyzer import PassthroughDiagramAnalyzer
from app.ingestion.extraction.docling_parser import DoclingParser
from app.ingestion.extraction.models import (
    ExtractedDocument,
    ExtractedPage,
    ExtractionMethod,
    QualityWarning,
)
from app.ingestion.extraction.ocr_engine import OCRFallbackManager
from app.ingestion.extraction.preflight import PreflightInspector, PreflightReport
from app.ingestion.extraction.pymupdf_parser import PyMuPDFParser
from app.ingestion.extraction.quality_checker import ExtractionQualityAssessor


class DocumentExtractionPipeline:
    """Master pipeline orchestrating modular document extraction."""

    def __init__(self, config: Optional[ExtractionConfig] = None) -> None:
        self.config = config or ExtractionConfig()
        self.preflight = PreflightInspector(self.config)
        self.docling_parser = DoclingParser(self.config)
        self.pymupdf_parser = PyMuPDFParser(self.config)
        self.ocr_manager = OCRFallbackManager(self.config)
        self.diagram_analyzer = PassthroughDiagramAnalyzer(self.config)
        self.quality_assessor = ExtractionQualityAssessor(self.config)

    def extract_document(
        self,
        pdf_path: Path,
        output_dir: Optional[Path] = None,
    ) -> ExtractedDocument:
        """Run complete extraction on an individual PDF document."""
        pdf_path = Path(pdf_path).resolve()
        if not pdf_path.is_file():
            raise FileNotFoundError(f"Source PDF does not exist: {pdf_path}")

        effective_output_dir = output_dir or self.config.output_dir
        category = pdf_path.parent.name if pdf_path.parent != self.config.documents_dir else "root"
        doc_output_dir = effective_output_dir / category / pdf_path.stem
        figures_dir = doc_output_dir / "figures"
        doc_output_dir.mkdir(parents=True, exist_ok=True)

        # ----------------------------------------------------------------------
        # Stage 1: Preflight
        # ----------------------------------------------------------------------
        preflight_report = self.preflight.inspect_pdf(pdf_path)

        # ----------------------------------------------------------------------
        # Stage 2: Parsing (Docling primary if available, otherwise PyMuPDF)
        # ----------------------------------------------------------------------
        doc: Optional[ExtractedDocument] = None

        if self.config.use_docling_primary and self.docling_parser.is_available():
            try:
                doc = self.docling_parser.parse_document(pdf_path, preflight_report)
                if doc:
                    # Enrich with PyMuPDF raw text, geometry, and evaluate OCR in a single open handle
                    fitz_doc = fitz.open(pdf_path)
                    try:
                        for page in doc.pages:
                            if page.page_number <= len(fitz_doc):
                                fitz_page = fitz_doc[page.page_number - 1]
                                page.raw_text = fitz_page.get_text("text") or ""
                                page.width = float(fitz_page.rect.width)
                                page.height = float(fitz_page.rect.height)
                                page.rotation = int(fitz_page.rotation)
                                # Selective OCR check within the same handle
                                ocr_text, ocr_warn = self.ocr_manager.process_candidate_page(
                                    page=fitz_page,
                                    page_number=page.page_number,
                                    text_length=len(page.raw_text.strip()),
                                    image_count=len(page.figures),
                                )
                                if ocr_text:
                                    page.has_ocr_applied = True
                                    page.structured_text = (page.structured_text + "\n\n" + ocr_text).strip()
                                if ocr_warn:
                                    page.quality_warnings.append(ocr_warn)
                    finally:
                        fitz_doc.close()
            except Exception as exc:
                doc = None

        if doc is None:
            # Execute supporting PyMuPDF parser
            doc = self.pymupdf_parser.parse_document(
                pdf_path=pdf_path,
                preflight_report=preflight_report,
                figures_dir=figures_dir if self.config.extract_figures else None,
            )

            # Selective OCR Fallback: Only open PDF handle if candidate pages actually exist
            candidate_pages = [
                p for p in doc.pages
                if self.ocr_manager.is_page_ocr_candidate(len(p.raw_text.strip()), len(p.figures))
            ]
            if candidate_pages:
                fitz_doc = fitz.open(pdf_path)
                try:
                    for page in candidate_pages:
                        p_num = page.page_number
                        if p_num <= len(fitz_doc):
                            fitz_p = fitz_doc[p_num - 1]
                            ocr_text, ocr_warn = self.ocr_manager.process_candidate_page(
                                page=fitz_p,
                                page_number=p_num,
                                text_length=len(page.raw_text.strip()),
                                image_count=len(page.figures),
                            )
                            if ocr_text:
                                page.has_ocr_applied = True
                                page.structured_text = (page.structured_text + "\n\n" + ocr_text).strip()
                            if ocr_warn:
                                page.quality_warnings.append(ocr_warn)
                finally:
                    fitz_doc.close()

        # Attach preflight warnings to document
        doc.document_warnings.extend(preflight_report.warnings)

        # ----------------------------------------------------------------------
        # Stage 4: Figure & Diagram Handling (VLM Interface)
        # ----------------------------------------------------------------------
        for page in doc.pages:
            for fig in page.figures:
                self.diagram_analyzer.analyze_diagram(fig, page_context=page.raw_text[:300])

        # ----------------------------------------------------------------------
        # Stage 5: Quality Assessment
        # ----------------------------------------------------------------------
        self.quality_assessor.assess_document(doc)

        # ----------------------------------------------------------------------
        # Stage 6: Artifact Serialization
        # ----------------------------------------------------------------------
        self._save_artifacts(doc, doc_output_dir)

        return doc

    def _save_artifacts(self, doc: ExtractedDocument, output_dir: Path) -> Dict[str, Path]:
        """Save structured JSON, Markdown, raw text backup, and manifest to output directory."""
        stem = doc.document_id

        # 1. Structured JSON
        json_path = output_dir / f"{stem}_structured.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(doc.to_dict(), f, indent=2, ensure_ascii=False)

        # 2. Human-readable Markdown
        md_path = output_dir / f"{stem}.md"
        md_content = doc.export_markdown()
        md_path.write_text(md_content, encoding="utf-8")

        # 3. Raw text backup (with --- PAGE N --- markers)
        txt_path = output_dir / f"{stem}.txt"
        txt_content = doc.export_raw_text()
        txt_path.write_text(txt_content, encoding="utf-8")

        # 4. Document extraction manifest
        manifest_path = output_dir / "manifest.json"
        manifest_data = {
            "document_id": doc.document_id,
            "file_path": doc.file_path,
            "category": doc.category,
            "sha256_hash": doc.sha256_hash,
            "page_count": doc.page_count,
            "primary_parser": doc.primary_parser,
            "supporting_parser": doc.supporting_parser,
            "extracted_at": doc.extracted_at,
            "total_raw_characters": sum(len(p.raw_text) for p in doc.pages),
            "total_structured_characters": sum(len(p.structured_text) for p in doc.pages),
            "total_tables": sum(len(p.tables) for p in doc.pages),
            "total_figures": sum(len(p.figures) for p in doc.pages),
            "quality_warnings_count": sum(len(p.quality_warnings) for p in doc.pages) + len(doc.document_warnings),
            "artifacts": {
                "structured_json": str(json_path.name),
                "markdown": str(md_path.name),
                "raw_txt": str(txt_path.name),
            },
        }
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2, ensure_ascii=False)

        return {
            "json": json_path,
            "markdown": md_path,
            "txt": txt_path,
            "manifest": manifest_path,
        }
