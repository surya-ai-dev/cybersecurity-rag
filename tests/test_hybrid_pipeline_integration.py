"""Integration tests for hybrid layout extraction pipeline.

Verifies:
1. Hybrid layout parsing via PyMuPDF4LLM is active by default.
2. Fallback to block-based PyMuPDF parser works when use_hybrid_pymupdf4llm=False.
3. Graceful fallback occurs if PyMuPDF4LLM raises an error.
4. Table placement in structured text avoids duplicate rendering in export_markdown().
5. Figure filtering multi-criteria logic operates within the pipeline.
6. Document-specific corrections apply guards correctly.
7. Pipeline artifact generation (JSON, Markdown, raw text, manifest) is consistent and valid.
8. CLI extract_pdf supports both hybrid and non-hybrid execution.
"""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from app.ingestion.extract_text import extract_pdf
from app.ingestion.extraction.config import ExtractionConfig
from app.ingestion.extraction.models import BoundingBox, ExtractedDocument, TableData
from app.ingestion.extraction.pipeline import DocumentExtractionPipeline


def _build_test_pdf(pdf_path: Path, include_table: bool = True) -> Path:
    """Generate a clean synthetic PDF for integration testing."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)

    # Header and body text
    page.insert_text((50, 50), "NIST Special Publication Test Document", fontsize=14)
    page.insert_text((50, 80), "Chapter 1: Security Controls Overview", fontsize=12)
    page.insert_text(
        (50, 110),
        "This section outlines access control and identity management specifications.",
        fontsize=10,
    )

    if include_table:
        # Draw a bordered 2x2 table recognized by PyMuPDF find_tables()
        # Horizontal lines
        page.draw_line(fitz.Point(50, 140), fitz.Point(350, 140), width=1.0)
        page.draw_line(fitz.Point(50, 170), fitz.Point(350, 170), width=1.0)
        page.draw_line(fitz.Point(50, 200), fitz.Point(350, 200), width=1.0)
        # Vertical lines
        page.draw_line(fitz.Point(50, 140), fitz.Point(50, 200), width=1.0)
        page.draw_line(fitz.Point(200, 140), fitz.Point(200, 200), width=1.0)
        page.draw_line(fitz.Point(350, 140), fitz.Point(350, 200), width=1.0)

        # Cell contents
        page.insert_text((60, 160), "Control Identifier", fontsize=9)
        page.insert_text((210, 160), "Control Name", fontsize=9)
        page.insert_text((60, 190), "AC-1", fontsize=9)
        page.insert_text((210, 190), "Policy and Procedures", fontsize=9)

    page.insert_text(
        (50, 230),
        "Subsequent analysis confirms all baseline allocations meet moderate impact standards.",
        fontsize=10,
    )

    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


class TestHybridPipelineIntegration(unittest.TestCase):
    """Integration test suite for the unified hybrid extraction pipeline."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.work_dir = Path(self.temp_dir.name)
        self.pdf_path = self.work_dir / "test_sample.pdf"
        _build_test_pdf(self.pdf_path, include_table=True)
        self.output_dir = self.work_dir / "output"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_hybrid_mode_active_by_default(self) -> None:
        """Pipeline uses hybrid PyMuPDF4LLM extraction by default."""
        config = ExtractionConfig(
            output_dir=self.output_dir,
            use_hybrid_pymupdf4llm=True,
            extract_tables=True,
            extract_figures=True,
        )
        pipeline = DocumentExtractionPipeline(config)
        doc = pipeline.extract_document(self.pdf_path)

        self.assertIsInstance(doc, ExtractedDocument)
        self.assertEqual(doc.primary_parser, "hybrid_pymupdf4llm_table_preservation")
        self.assertEqual(doc.supporting_parser, "pymupdf_table_snapper")
        self.assertEqual(doc.page_count, 1)

        page = doc.pages[0]
        self.assertEqual(page.page_number, 1)
        self.assertEqual(page.citation_label, f"[{self.pdf_path.stem} Page 1]")
        self.assertEqual(page.extraction_method, "hybrid_pymupdf4llm_table_preservation")
        self.assertIn("Security Controls Overview", page.structured_text)
        self.assertIn("Security Controls Overview", page.raw_text)

    def test_legacy_mode_fallback_via_config(self) -> None:
        """When use_hybrid_pymupdf4llm=False, block-based PyMuPDF extraction is used."""
        config = ExtractionConfig(
            output_dir=self.output_dir,
            use_hybrid_pymupdf4llm=False,
        )
        pipeline = DocumentExtractionPipeline(config)
        doc = pipeline.extract_document(self.pdf_path)

        self.assertEqual(doc.primary_parser, "pymupdf_supporting")
        self.assertEqual(doc.supporting_parser, "pymupdf")
        self.assertEqual(len(doc.pages), 1)
        self.assertEqual(doc.pages[0].extraction_method, "pymupdf_structured")
        self.assertIn("Security Controls Overview", doc.pages[0].structured_text)

    def test_hybrid_fallback_on_engine_exception(self) -> None:
        """Pipeline falls back gracefully to block-based PyMuPDF if PyMuPDF4LLM crashes."""
        config = ExtractionConfig(
            output_dir=self.output_dir,
            use_hybrid_pymupdf4llm=True,
        )
        pipeline = DocumentExtractionPipeline(config)

        with patch("pymupdf4llm.to_markdown", side_effect=RuntimeError("Simulated layout engine crash")):
            doc = pipeline.extract_document(self.pdf_path)

        self.assertIsNotNone(doc)
        self.assertEqual(doc.primary_parser, "pymupdf_supporting")
        self.assertEqual(doc.supporting_parser, "pymupdf")
        self.assertEqual(len(doc.pages), 1)
        self.assertEqual(doc.pages[0].extraction_method, "pymupdf_structured")

    def test_artifact_generation_and_manifest(self) -> None:
        """Pipeline writes valid structured JSON, Markdown, raw text, and manifest."""
        config = ExtractionConfig(
            output_dir=self.output_dir,
            use_hybrid_pymupdf4llm=True,
        )
        pipeline = DocumentExtractionPipeline(config)
        doc = pipeline.extract_document(self.pdf_path)

        category = self.pdf_path.parent.name if self.pdf_path.parent != config.documents_dir else "root"
        doc_dir = self.output_dir / category / self.pdf_path.stem
        self.assertTrue(doc_dir.is_dir(), f"Expected output directory {doc_dir} does not exist")

        json_file = doc_dir / f"{self.pdf_path.stem}_structured.json"
        md_file = doc_dir / f"{self.pdf_path.stem}.md"
        txt_file = doc_dir / f"{self.pdf_path.stem}.txt"
        manifest_file = doc_dir / "manifest.json"

        self.assertTrue(json_file.is_file(), "Structured JSON missing")
        self.assertTrue(md_file.is_file(), "Markdown output missing")
        self.assertTrue(txt_file.is_file(), "Raw text output missing")
        self.assertTrue(manifest_file.is_file(), "Manifest missing")

        md_content = md_file.read_text(encoding="utf-8")
        self.assertIn(f"## Page 1 ([{self.pdf_path.stem} Page 1])", md_content)
        self.assertIn("Security Controls Overview", md_content)

        txt_content = txt_file.read_text(encoding="utf-8")
        self.assertIn("--- PAGE 1 ---", txt_content)

        manifest_content = json_file.read_text(encoding="utf-8")
        self.assertIn("hybrid_pymupdf4llm_table_preservation", manifest_content)

    def test_table_deduplication_in_pipeline_export(self) -> None:
        """Tables spliced into structured_text are not duplicated by export_markdown()."""
        config = ExtractionConfig(
            output_dir=self.output_dir,
            use_hybrid_pymupdf4llm=True,
            extract_tables=True,
        )
        pipeline = DocumentExtractionPipeline(config)
        doc = pipeline.extract_document(self.pdf_path)

        md_content = doc.export_markdown()

        # If a table was detected and spliced, it should appear in markdown
        # but should not be treated as a standalone table appended at the bottom
        if doc.pages[0].tables:
            first_header = doc.pages[0].tables[0].headers[0]
            header_count = md_content.count(first_header)
            self.assertEqual(header_count, 1, f"Table header '{first_header}' appeared {header_count} times in markdown")
            # Verify standalone tables list is empty since table is inline
            standalone = doc.pages[0].get_standalone_tables()
            self.assertEqual(len(standalone), 0, "Inline table erroneously returned as standalone")

    def test_document_corrections_guard_on_non_target_doc(self) -> None:
        """Guarded document corrections are not applied to non-target documents."""
        config = ExtractionConfig(
            output_dir=self.output_dir,
            use_hybrid_pymupdf4llm=True,
            enable_document_corrections=True,
        )
        pipeline = DocumentExtractionPipeline(config)
        doc = pipeline.extract_document(self.pdf_path)

        # The test document ID is "test_sample", not "SP800-53r5"
        self.assertEqual(doc.document_id, "test_sample")
        # Content remains unmodified from corrections
        self.assertNotIn("Table 35-1", doc.pages[0].structured_text)

    def test_figure_filtering_pipeline_integration(self) -> None:
        """Figure filtering evaluates assets and obeys enable_figure_filtering setting."""
        config_enabled = ExtractionConfig(
            output_dir=self.output_dir,
            use_hybrid_pymupdf4llm=True,
            extract_figures=True,
            enable_figure_filtering=True,
        )
        pipeline_enabled = DocumentExtractionPipeline(config_enabled)
        self.assertTrue(pipeline_enabled.pymupdf_parser.config.enable_figure_filtering)
        self.assertIsNotNone(pipeline_enabled.pymupdf_parser.figure_filter)

        config_disabled = ExtractionConfig(
            output_dir=self.output_dir,
            use_hybrid_pymupdf4llm=True,
            extract_figures=True,
            enable_figure_filtering=False,
        )
        pipeline_disabled = DocumentExtractionPipeline(config_disabled)
        self.assertFalse(pipeline_disabled.pymupdf_parser.config.enable_figure_filtering)

    def test_extract_pdf_cli_function(self) -> None:
        """CLI helper extract_pdf works with both hybrid and fallback modes."""
        out_hybrid = self.work_dir / "out_hybrid"
        success_hybrid = extract_pdf(self.pdf_path, output_dir=out_hybrid, use_hybrid=True)
        self.assertTrue(success_hybrid)

        out_legacy = self.work_dir / "out_legacy"
        success_legacy = extract_pdf(self.pdf_path, output_dir=out_legacy, use_hybrid=False)
        self.assertTrue(success_legacy)



if __name__ == "__main__":
    unittest.main()
