"""Unit tests for the isolated document_corrections module."""

import unittest

from app.ingestion.extraction.document_corrections import (
    TARGET_DOCUMENT_ID,
    CorrectionResult,
    apply_document_corrections,
    apply_nist_800_53_specific_corrections,
)
from app.ingestion.extraction.models import BoundingBox, TableData


class TestDocumentCorrections(unittest.TestCase):
    """Test suite validating document-specific correction safeguards and execution."""

    def test_nist_800_53_page_35_table1_correction(self) -> None:
        """Page 35 Table 1 is corrected with clean 4-column headers, 10 rows, and proper spacing."""
        raw_text = "Security and Privacy Control Families in Information Systems."
        input_text = (
            "Leading text describing control families.\n\n"
            "| ID | FAMILY | ID | FAMILY |\n"
            "| --- | --- | --- | --- |\n"
            "| AC | AccessControl | PE | PhysicalandEnvironmentalProtection |\n"
            "| | | | |\n\n"
            "Families of controls contain base controls and control enhancements."
        )
        dummy_table = TableData(
            table_id="table_p35_flawed",
            page_number=35,
            headers=["ID", "FAMILY", "ID", "FAMILY"],
            rows=[["AC", "AccessControl", "PE", "PhysicalandEnvironmentalProtection"]],
            markdown="| flawed |",
            rows_count=1,
            cols_count=4,
        )

        result = apply_document_corrections(
            doc_id="NIST_SP_800-53",
            page_number=35,
            raw_text=raw_text,
            structured_text=input_text,
            tables=[dummy_table],
        )

        self.assertTrue(result.applied)
        self.assertEqual(result.correction_id, "nist_800_53_page_35")
        self.assertEqual(result.reason, "nist_800_53_page_35_table1_corrected")
        self.assertEqual(len(result.tables), 1)

        t1 = result.tables[0]
        self.assertEqual(t1.cols_count, 4)
        self.assertEqual(t1.rows_count, 10)
        self.assertEqual(t1.headers, ["ID", "FAMILY", "ID", "FAMILY"])
        self.assertIn("Access Control", t1.markdown)
        self.assertIn("Personnel Security", t1.markdown)
        self.assertNotIn("| | | | |", t1.markdown)
        self.assertIn("Access Control", result.structured_text)
        self.assertIn("Families of controls contain base controls", result.structured_text)

    def test_nist_800_53_page_452_acronym_tables_restored(self) -> None:
        """Page 452 restores Table 1 (23 acronyms), intervening list, and Table 2 (7 acronyms)."""
        raw_text = "APPENDIX B\nACRONYMS\nDVD-R Digital Versatile Disc-Recordable"
        input_text = "Flawed extraction text with single table overwrite."

        result = apply_document_corrections(
            doc_id="NIST_SP_800-53",
            page_number=452,
            raw_text=raw_text,
            structured_text=input_text,
            tables=[],
        )

        self.assertTrue(result.applied)
        self.assertEqual(result.correction_id, "nist_800_53_page_452")
        self.assertEqual(result.reason, "nist_800_53_page_452_acronym_tables_restored")
        self.assertEqual(len(result.tables), 2)

        t1, t2 = result.tables[0], result.tables[1]
        self.assertEqual(t1.rows_count, 23)
        self.assertIn("DVD-R", t1.markdown)
        self.assertIn("IOC", t1.markdown)

        self.assertEqual(t2.rows_count, 7)
        self.assertIn("ISAC", t2.markdown)
        self.assertIn("MTTF", t2.markdown)

        # Intervening list elements must remain intact
        self.assertIn("- **IoT**", result.structured_text)
        self.assertIn("- **IP**", result.structured_text)
        self.assertIn("- **IR**", result.structured_text)

    def test_nist_800_53_page_471_table_c11_restored(self) -> None:
        """Page 471 restores Table C-11 (4 columns) and prunes raw picture text artifacts."""
        raw_text = "IR-10 Integrated Information Security Analysis Team Table C-11"
        input_text = "<!-- Start of picture text --> IR-10 moved <!-- End of picture text -->"

        result = apply_document_corrections(
            doc_id="NIST_SP_800-53",
            page_number=471,
            raw_text=raw_text,
            structured_text=input_text,
            tables=[],
        )

        self.assertTrue(result.applied)
        self.assertEqual(result.correction_id, "nist_800_53_page_471")
        self.assertEqual(result.reason, "nist_800_53_page_471_table_c11_restored")
        self.assertEqual(len(result.tables), 1)

        t = result.tables[0]
        self.assertEqual(t.cols_count, 4)
        self.assertEqual(t.rows_count, 1)
        self.assertIn("IR-10", t.markdown)
        self.assertIn("W: Moved to IR-4(11).", t.markdown)
        self.assertNotIn("<!-- Start of picture text -->", result.structured_text)

    def test_wrong_document_id_unchanged(self) -> None:
        """Documents other than NIST SP 800-53 are never altered by this module."""
        other_docs = ["NIST_SP_800-152", "NIST_SP_800-186", "NIST_SP_800-39", "NIST_SP_800-236", "OTHER_DOC"]
        sample_text = "Sample text from another document."
        sample_tables = [TableData("t1", 35, ["COL1"], [["VAL1"]], "| COL1 |", 1, 1)]

        for doc_id in other_docs:
            for page_num in (35, 452, 471):
                result = apply_document_corrections(
                    doc_id=doc_id,
                    page_number=page_num,
                    raw_text="APPENDIX B ACRONYMS IR-10 Control Families",
                    structured_text=sample_text,
                    tables=sample_tables,
                )
                self.assertFalse(result.applied)
                self.assertEqual(result.reason, "document_id_mismatch")
                self.assertEqual(result.structured_text, sample_text)
                self.assertEqual(result.tables, sample_tables)

    def test_wrong_page_numbers_unchanged(self) -> None:
        """Pages other than 35, 452, and 471 in NIST SP 800-53 are never altered."""
        sample_text = "Sample content on a non-targeted page."
        sample_tables = []

        for non_target_page in (1, 2, 34, 36, 100, 451, 453, 470, 472, 492):
            result = apply_document_corrections(
                doc_id="NIST_SP_800-53",
                page_number=non_target_page,
                raw_text="Control Families APPENDIX B ACRONYMS IR-10",
                structured_text=sample_text,
                tables=sample_tables,
            )
            self.assertFalse(result.applied)
            self.assertEqual(result.reason, "page_number_not_targeted")
            self.assertEqual(result.structured_text, sample_text)

    def test_mismatched_signatures_safely_skipped(self) -> None:
        """If expected signatures are absent on pages 35, 452, or 471, the correction is safely skipped."""
        irrelevant_text = "Completely different text without any known signature."

        # Page 35 signature mismatch
        r35 = apply_document_corrections("NIST_SP_800-53", 35, irrelevant_text, irrelevant_text, [])
        self.assertFalse(r35.applied)
        self.assertEqual(r35.reason, "page_35_signature_mismatch")
        self.assertEqual(r35.structured_text, irrelevant_text)

        # Page 452 signature mismatch
        r452 = apply_document_corrections("NIST_SP_800-53", 452, irrelevant_text, irrelevant_text, [])
        self.assertFalse(r452.applied)
        self.assertEqual(r452.reason, "page_452_signature_mismatch")
        self.assertEqual(r452.structured_text, irrelevant_text)

        # Page 471 signature mismatch
        r471 = apply_document_corrections("NIST_SP_800-53", 471, irrelevant_text, irrelevant_text, [])
        self.assertFalse(r471.applied)
        self.assertEqual(r471.reason, "page_471_signature_mismatch")
        self.assertEqual(r471.structured_text, irrelevant_text)

    def test_idempotent_repeat_corrections_safe(self) -> None:
        """Applying a correction twice does not corrupt, duplicate, or alter the output (idempotency)."""
        # 1. Page 35 repeated execution
        raw_p35 = "Control Families in Information Systems."
        initial_p35 = "| ID | FAMILY | ID | FAMILY |\n| --- | --- | --- | --- |\n| AC | AccessControl | PE | Physical |\n\nFamilies of controls"
        res_p35_run1 = apply_document_corrections("NIST_SP_800-53", 35, raw_p35, initial_p35, [])
        res_p35_run2 = apply_document_corrections("NIST_SP_800-53", 35, raw_p35, res_p35_run1.structured_text, res_p35_run1.tables)
        self.assertEqual(res_p35_run1.structured_text, res_p35_run2.structured_text)
        self.assertEqual(len(res_p35_run1.tables), len(res_p35_run2.tables))
        self.assertEqual(res_p35_run1.tables[0].markdown, res_p35_run2.tables[0].markdown)

        # 2. Page 452 repeated execution
        raw_p452 = "APPENDIX B ACRONYMS"
        res_p452_run1 = apply_document_corrections("NIST_SP_800-53", 452, raw_p452, "Initial text", [])
        res_p452_run2 = apply_document_corrections("NIST_SP_800-53", 452, raw_p452, res_p452_run1.structured_text, res_p452_run1.tables)
        self.assertEqual(res_p452_run1.structured_text, res_p452_run2.structured_text)
        self.assertEqual(len(res_p452_run1.tables), len(res_p452_run2.tables))

        # 3. Page 471 repeated execution
        raw_p471 = "IR-10 Table C-11"
        res_p471_run1 = apply_document_corrections("NIST_SP_800-53", 471, raw_p471, "Initial text", [])
        res_p471_run2 = apply_document_corrections("NIST_SP_800-53", 471, raw_p471, res_p471_run1.structured_text, res_p471_run1.tables)
        self.assertEqual(res_p471_run1.structured_text, res_p471_run2.structured_text)
        self.assertEqual(len(res_p471_run1.tables), len(res_p471_run2.tables))

    def test_legacy_unpacking_compatibility(self) -> None:
        """The apply_document_corrections return value supports 3-tuple unpacking: (text, tables, applied)."""
        raw_text = "IR-10 Table C-11"
        text, tables, applied = apply_document_corrections(
            "NIST_SP_800-53",
            471,
            raw_text,
            "Initial text",
            [],
        )
        self.assertTrue(applied)
        self.assertIsInstance(text, str)
        self.assertIsInstance(tables, list)
        self.assertEqual(len(tables), 1)

    def test_alias_function_parity(self) -> None:
        """The apply_nist_800_53_specific_corrections alias function behaves identically."""
        raw_text = "IR-10 Table C-11"
        res_direct = apply_document_corrections("NIST_SP_800-53", 471, raw_text, "Initial", [])
        res_alias = apply_nist_800_53_specific_corrections("NIST_SP_800-53", 471, raw_text, "Initial", [])
        self.assertEqual(res_direct.structured_text, res_alias.structured_text)
        self.assertEqual(res_direct.applied, res_alias.applied)
        self.assertEqual(res_direct.reason, res_alias.reason)


if __name__ == "__main__":
    unittest.main()
