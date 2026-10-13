"""Unit tests for models.py export_markdown() table deduplication and rendering."""

import unittest

from app.ingestion.extraction.models import (
    BoundingBox,
    ExtractedDocument,
    ExtractedPage,
    FigureAsset,
    TableData,
)


def _make_sample_doc(pages) -> ExtractedDocument:
    """Helper to construct ExtractedDocument with test pages."""
    return ExtractedDocument(
        document_id="TEST_DOC",
        file_path="documents/test.pdf",
        absolute_path="/abs/test.pdf",
        category="testing",
        file_size_bytes=1024,
        sha256_hash="deadbeef",
        page_count=len(pages),
        primary_parser="hybrid_test",
        supporting_parser="pymupdf",
        extracted_at="2026-10-13T12:00:00",
        title="Test Document",
        pages=pages,
    )


class TestModelsMarkdownExport(unittest.TestCase):
    """Test suite validating export_markdown table deduplication and structural preservation."""

    def test_table_in_both_structured_text_and_tables_rendered_once(self) -> None:
        """A table present in both structured_text and page.tables must be rendered exactly once."""
        t1_md = "| ID | NAME |\n| --- | --- |\n| 1 | Alpha |"
        table1 = TableData(
            table_id="t1",
            page_number=1,
            headers=["ID", "NAME"],
            rows=[["1", "Alpha"]],
            markdown=t1_md,
            rows_count=1,
            cols_count=2,
            caption="Table 1: Test",
        )
        page = ExtractedPage(
            page_number=1,
            citation_label="[TEST_DOC Page 1]",
            width=612.0,
            height=792.0,
            rotation=0,
            extraction_method="hybrid",
            raw_text="Raw text.",
            structured_text=f"Introductory paragraph.\n\n{t1_md}\n\nConcluding paragraph.",
            tables=[table1],
        )
        doc = _make_sample_doc([page])
        md_output = doc.export_markdown()

        # Count occurrences of the table markdown in the exported output
        occurrences = md_output.count("| ID | NAME |")
        self.assertEqual(
            occurrences,
            1,
            f"Expected table to appear exactly once in Markdown export, but found {occurrences} times.",
        )
        # Verify standalone tables method returns empty list
        self.assertEqual(page.get_standalone_tables(), [])

    def test_standalone_table_rendered_when_absent_from_structured_text(self) -> None:
        """A standalone table in page.tables that is absent from structured_text must still be rendered."""
        t1_md = "| PARAM | VALUE |\n| --- | --- |\n| Key | 128 |"
        table1 = TableData(
            table_id="t1",
            page_number=1,
            headers=["PARAM", "VALUE"],
            rows=[["Key", "128"]],
            markdown=t1_md,
            rows_count=1,
            cols_count=2,
            caption="Standalone Parameters",
        )
        page = ExtractedPage(
            page_number=1,
            citation_label="[TEST_DOC Page 1]",
            width=612.0,
            height=792.0,
            rotation=0,
            extraction_method="pymupdf",
            raw_text="Raw parameter text.",
            structured_text="Paragraph content that does not embed the table.",
            tables=[table1],
        )
        doc = _make_sample_doc([page])
        md_output = doc.export_markdown()

        self.assertIn("| PARAM | VALUE |", md_output)
        self.assertIn("**Standalone Parameters**", md_output)
        self.assertEqual(md_output.count("| PARAM | VALUE |"), 1)
        self.assertEqual(page.get_standalone_tables(), [table1])

    def test_two_separate_tables_with_identical_contents_both_rendered(self) -> None:
        """Two separate tables with identical contents must both be rendered when both appear in structured_text."""
        identical_md = "| STEP | ACTION |\n| --- | --- |\n| 1 | Verify |"
        t1 = TableData(table_id="t1", page_number=1, headers=["STEP"], rows=[["1"]], markdown=identical_md, rows_count=1, cols_count=2)
        t2 = TableData(table_id="t2", page_number=1, headers=["STEP"], rows=[["1"]], markdown=identical_md, rows_count=1, cols_count=2)

        page = ExtractedPage(
            page_number=1,
            citation_label="[TEST_DOC Page 1]",
            width=612.0,
            height=792.0,
            rotation=0,
            extraction_method="hybrid",
            raw_text="Raw steps.",
            structured_text=f"First procedure:\n\n{identical_md}\n\nSecond procedure:\n\n{identical_md}\n\nDone.",
            tables=[t1, t2],
        )
        doc = _make_sample_doc([page])
        md_output = doc.export_markdown()

        # Both occurrences inside structured_text must remain intact
        self.assertEqual(md_output.count("| STEP | ACTION |"), 2)
        # Neither should be deemed standalone
        self.assertEqual(page.get_standalone_tables(), [])

    def test_two_identical_tables_one_inline_one_standalone_both_rendered(self) -> None:
        """When two identical tables exist, but only one is inline, the other is rendered as standalone."""
        identical_md = "| METRIC | VAL |\n| --- | --- |\n| CPU | 80% |"
        t_inline = TableData(table_id="t1", page_number=1, headers=["METRIC"], rows=[["CPU"]], markdown=identical_md, rows_count=1, cols_count=2)
        t_standalone = TableData(table_id="t2", page_number=1, headers=["METRIC"], rows=[["CPU"]], markdown=identical_md, rows_count=1, cols_count=2)

        page = ExtractedPage(
            page_number=1,
            citation_label="[TEST_DOC Page 1]",
            width=612.0,
            height=792.0,
            rotation=0,
            extraction_method="hybrid",
            raw_text="Raw metrics.",
            structured_text=f"Inline metrics:\n\n{identical_md}\n\nEnd of section.",
            tables=[t_inline, t_standalone],
        )
        doc = _make_sample_doc([page])
        md_output = doc.export_markdown()

        # One rendered in standalone section, one rendered in structured_text -> exactly 2
        self.assertEqual(md_output.count("| METRIC | VAL |"), 2)
        self.assertEqual(page.get_standalone_tables(), [t_standalone])

    def test_table_ordering_relative_to_surrounding_text_preserved(self) -> None:
        """Inline tables preserve their exact sequential order relative to preceding and succeeding paragraphs."""
        t1_md = "| T1 | DATA |\n| --- | --- |\n| A | 1 |"
        t2_md = "| T2 | DATA |\n| --- | --- |\n| B | 2 |"
        t1 = TableData(table_id="t1", page_number=1, headers=["T1"], rows=[["A"]], markdown=t1_md, rows_count=1, cols_count=2)
        t2 = TableData(table_id="t2", page_number=1, headers=["T2"], rows=[["B"]], markdown=t2_md, rows_count=1, cols_count=2)

        page = ExtractedPage(
            page_number=1,
            citation_label="[TEST_DOC Page 1]",
            width=612.0,
            height=792.0,
            rotation=0,
            extraction_method="hybrid",
            raw_text="Raw.",
            structured_text=f"Paragraph 1\n\n{t1_md}\n\nParagraph 2\n\n{t2_md}\n\nParagraph 3",
            tables=[t1, t2],
        )
        doc = _make_sample_doc([page])
        md_output = doc.export_markdown()

        pos_p1 = md_output.find("Paragraph 1")
        pos_t1 = md_output.find("| T1 | DATA |")
        pos_p2 = md_output.find("Paragraph 2")
        pos_t2 = md_output.find("| T2 | DATA |")
        pos_p3 = md_output.find("Paragraph 3")

        self.assertTrue(
            0 <= pos_p1 < pos_t1 < pos_p2 < pos_t2 < pos_p3,
            f"Expected ordering P1 < T1 < P2 < T2 < P3, got positions: {pos_p1}, {pos_t1}, {pos_p2}, {pos_t2}, {pos_p3}",
        )

    def test_empty_and_table_free_pages_export_cleanly(self) -> None:
        """Pages with no tables or empty structured text export without errors or anomalies."""
        # 1. Page with no tables
        p_no_tables = ExtractedPage(
            page_number=1,
            citation_label="[TEST_DOC Page 1]",
            width=612.0,
            height=792.0,
            rotation=0,
            extraction_method="pymupdf",
            raw_text="Just normal text.",
            structured_text="Just normal structured text.",
            tables=[],
        )
        doc1 = _make_sample_doc([p_no_tables])
        md1 = doc1.export_markdown()
        self.assertIn("Just normal structured text.", md1)

        # 2. Page with empty structured text but raw text and standalone table
        table_standalone = TableData("t1", 2, ["COL"], [["V"]], "| COL |\n| --- |\n| V |", 1, 1)
        p_empty_struct = ExtractedPage(
            page_number=2,
            citation_label="[TEST_DOC Page 2]",
            width=612.0,
            height=792.0,
            rotation=0,
            extraction_method="pymupdf",
            raw_text="Fallback raw text.",
            structured_text="",
            tables=[table_standalone],
        )
        doc2 = _make_sample_doc([p_empty_struct])
        md2 = doc2.export_markdown()
        self.assertIn("| COL |", md2)
        self.assertIn("Fallback raw text.", md2)

    def test_bounding_box_from_dict_tolerance(self) -> None:
        """BoundingBox.from_dict accepts serialized dicts containing computed properties without TypeError."""
        data = {
            "left": 10.0,
            "top": 20.0,
            "right": 100.0,
            "bottom": 200.0,
            "width": 90.0,
            "height": 180.0,
            "page_width": 612.0,
        }
        bbox = BoundingBox.from_dict(data)
        self.assertEqual(bbox.left, 10.0)
        self.assertEqual(bbox.top, 20.0)
        self.assertEqual(bbox.right, 100.0)
        self.assertEqual(bbox.bottom, 200.0)
        self.assertEqual(bbox.width, 90.0)
        self.assertEqual(bbox.height, 180.0)


if __name__ == "__main__":
    unittest.main()
