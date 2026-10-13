"""Unit tests for extraction quality assessment and table structure validation."""

from pathlib import Path
import unittest

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from app.ingestion.extraction.config import ExtractionConfig
from app.ingestion.extraction.models import ExtractedPage
from app.ingestion.extraction.pymupdf_parser import PyMuPDFParser
from app.ingestion.extraction.quality_checker import ExtractionQualityAssessor


class TestGarbledTextHeuristic(unittest.TestCase):
    """Test suite for ExtractionQualityAssessor garbled-text detection and token exemption."""

    def setUp(self) -> None:
        self.config = ExtractionConfig(garbled_max_token_length=60)
        self.assessor = ExtractionQualityAssessor(self.config)

    def test_long_numeric_token_exempt(self) -> None:
        """A numeric token longer than 60 characters (e.g. P-224 68-char prime) must not trigger warning."""
        decimal_prime = "26959946667150639794667015087019630673557916260026308143510066298881"
        self.assertGreater(len(decimal_prime), 60)
        text = f"The elliptic curve domain parameter modulus is p = {decimal_prime} over prime field."
        issues = self.assessor._detect_garbled_patterns(text)
        self.assertEqual(issues, [], f"Expected no garbled issues for valid long numeric token, got: {issues}")

    def test_long_hexadecimal_token_exempt(self) -> None:
        """A valid 0x-prefixed hexadecimal constant longer than 60 characters must not trigger warning."""
        hex_param = "0xfffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffeffffffff"
        self.assertGreater(len(hex_param), 60)
        text = f"Elliptic curve Weierstrass representation parameter: {hex_param} specified by NIST."
        issues = self.assessor._detect_garbled_patterns(text)
        self.assertEqual(issues, [], f"Expected no garbled issues for valid long 0x hex token, got: {issues}")

    def test_long_suspicious_token_flagged(self) -> None:
        """A long suspicious nonnumeric, non-hex token must still trigger the garbled warning."""
        fused_text = "thisisalongfusedsentencewithoutspacesproducedbybrokenpdfmetrics123"
        self.assertGreater(len(fused_text), 60)
        text = f"Valid document text precedes the corrupted block: {fused_text} following normal text."
        issues = self.assessor._detect_garbled_patterns(text)
        self.assertTrue(
            any("Abnormally long unbroken token" in issue for issue in issues),
            f"Expected 'Abnormally long unbroken token' warning for fused text, got: {issues}",
        )

    def test_long_invalid_hex_token_flagged(self) -> None:
        """A long token starting with 0x but containing invalid non-hex characters must be flagged."""
        invalid_hex = "0x1234567890abcdef1234567890abcdefg1234567890abcdefz1234567890abcdef"
        self.assertGreater(len(invalid_hex), 60)
        text = f"Corrupted hex constant found: {invalid_hex} in specification."
        issues = self.assessor._detect_garbled_patterns(text)
        self.assertTrue(
            any("Abnormally long unbroken token" in issue for issue in issues),
            f"Expected warning for invalid hex containing non-hex chars, got: {issues}",
        )

    def test_normal_short_tokens_unaffected(self) -> None:
        """Normal short tokens of varying types must not trigger garbled token warnings."""
        normal_text = (
            "NIST Special Publication 800-186 Recommendations for Discrete Logarithm-based Cryptography: "
            "Elliptic Curve Domain Parameters. The curves P-256, P-384, and P-521 provide security strengths "
            "of 128, 192, and 256 bits respectively. SHA-256 is used for digital signatures."
        )
        issues = self.assessor._detect_garbled_patterns(normal_text)
        self.assertEqual(issues, [], f"Expected no garbled issues for normal text, got: {issues}")

    def test_assess_page_integration_valid_crypto(self) -> None:
        """ExtractedPage with valid long crypto parameters receives no garbled_text warning."""
        page = ExtractedPage(
            page_number=21,
            citation_label="[NIST_SP_800-186 Page 21]",
            width=612.0,
            height=792.0,
            rotation=0,
            extraction_method="pymupdf",
            raw_text=(
                "Section 3.2.1.2 Curve P-224\n"
                "The order n is 26959946667150639794667015087019630673557916260026308143510066298881\n"
                "The coefficient a is -3\n"
                "The coefficient b in hex is 0xb4050a850c04b3abf54132565044b0b7d7bfd8ba270b39432355ffb4\n"
            ),
            structured_text="Curve P-224 domain parameters.",
        )
        warnings = self.assessor.assess_page(page)
        garbled_warnings = [w for w in warnings if w.category == "garbled_text"]
        self.assertEqual(garbled_warnings, [], f"Expected no garbled_text warnings, got: {garbled_warnings}")

    def test_assess_page_integration_genuine_corruption(self) -> None:
        """ExtractedPage with genuine long corrupted token receives a garbled_text warning."""
        page = ExtractedPage(
            page_number=99,
            citation_label="[CORRUPT_DOC Page 99]",
            width=612.0,
            height=792.0,
            rotation=0,
            extraction_method="pymupdf",
            raw_text=(
                "Regular text block with sufficient volume to exceed minimum analysis thresholds. "
                "Here is genuine corrupted fused content: "
                "theresultofthiscryptographicoperationisindependentoftheunderlyingplatformarchitectureduringexecution "
                "and more trailing text."
            ),
            structured_text="Regular text block.",
        )
        warnings = self.assessor.assess_page(page)
        garbled_warnings = [w for w in warnings if w.category == "garbled_text"]
        self.assertEqual(len(garbled_warnings), 1)
        self.assertIn("Abnormally long unbroken token", garbled_warnings[0].message)

    def test_known_valid_url_slug_exempt(self) -> None:
        """The 63-char URL slug on NIST SP 800-53 Page 402 must not trigger garbled text warning."""
        slug = "strengthening-cybersecurity-federal-networks-critical-infrastructure"
        self.assertGreater(len(slug), 60)
        text = f"Presidential Executive Order on {slug} referenced in the NIST SP 800-53 catalog publication."
        issues = self.assessor._detect_garbled_patterns(text)
        self.assertEqual(issues, [], f"Expected no garbled issues for valid URL slug, got: {issues}")

    def test_valid_slash_and_hyphen_path_exempt(self) -> None:
        """A long path containing slashes, hyphens, and dots with reasonable segment lengths is exempt."""
        path = "csrc.nist.gov/publications/detail/sp/800-53/rev-5/final/appendix-b/acronyms"
        self.assertGreater(len(path), 60)
        text = f"The official reference can be verified at https://{path} for complete catalog details."
        issues = self.assessor._detect_garbled_patterns(text)
        self.assertEqual(issues, [], f"Expected no garbled issues for valid path, got: {issues}")

    def test_valid_url_query_parameters_exempt(self) -> None:
        """A long URL containing query parameters with ?, =, &, and % is exempt."""
        url_token = "search.php?category=risk_management&doc_id=NIST_SP_800-53&version=rev5&format=json"
        self.assertGreater(len(url_token), 60)
        text = f"Query parameter lookup available at endpoint: {url_token} for automated retrieval."
        issues = self.assessor._detect_garbled_patterns(text)
        self.assertEqual(issues, [], f"Expected no garbled issues for URL query parameters, got: {issues}")

    def test_hyphenated_token_with_oversized_subsegment_flagged(self) -> None:
        """A hyphenated token where an individual sub-segment exceeds 35 chars must still be flagged."""
        corrupted_subsegment = "thisisalongfusedsentencewithoutspacesproducedbybrokenpdfmetrics123"
        hyphenated_garbled = f"legit-prefix-{corrupted_subsegment}"
        self.assertGreater(len(hyphenated_garbled), 60)
        text = f"Corrupted token with hyphen embedded: {hyphenated_garbled} following normal text."
        issues = self.assessor._detect_garbled_patterns(text)
        self.assertTrue(
            any("Abnormally long unbroken token" in issue for issue in issues),
            f"Expected garbled warning for token with oversized subsegment, got: {issues}",
        )

    def test_assess_page_integration_valid_url_slug(self) -> None:
        """ExtractedPage representing NIST SP 800-53 Page 402 receives zero garbled_text warnings."""
        page = ExtractedPage(
            page_number=402,
            citation_label="[NIST_SP_800-53 Page 402]",
            width=612.0,
            height=792.0,
            rotation=0,
            extraction_method="pymupdf",
            raw_text=(
                "REFERENCES AND EXECUTIVE ORDERS\n"
                "Executive Order 13800, Strengthening the Cybersecurity of Federal Networks and Critical Infrastructure, "
                "May 2017. Available at: https://www.whitehouse.gov/presidential-actions/"
                "strengthening-cybersecurity-federal-networks-critical-infrastructure/ and national archives.\n"
            ),
            structured_text="Reference section citing Executive Order 13800.",
        )
        warnings = self.assessor.assess_page(page)
        garbled_warnings = [w for w in warnings if w.category == "garbled_text"]
        self.assertEqual(garbled_warnings, [], f"Expected no garbled_text warnings on Page 402, got: {garbled_warnings}")


class TestTableExtractionQuality(unittest.TestCase):
    """Test suite for table extraction boundary tolerances and empty column pruning."""

    def setUp(self) -> None:
        self.config = ExtractionConfig(table_snap_x_tolerance=10.0)
        self.parser = PyMuPDFParser(self.config)

    def test_nist_sp_800_53_page_19_errata_table(self) -> None:
        """NIST SP 800-53 page 19 extracts as 4 columns with headers DATE, TYPE, REVISION, PAGE."""
        pdf_path = Path("documents/risk_management/NIST_SP_800-53.pdf")
        self.assertTrue(pdf_path.exists(), f"Source PDF missing: {pdf_path}")
        doc = fitz.open(pdf_path)
        page = doc[18]  # Page 19 (0-indexed 18)
        tables = self.parser._extract_tables(page, 19)
        self.assertGreaterEqual(len(tables), 1, "Expected at least 1 table on page 19")
        t = tables[0]
        self.assertEqual(t.cols_count, 4, f"Expected 4 columns, got {t.cols_count}: {t.headers}")
        self.assertEqual(t.headers, ["DATE", "TYPE", "REVISION", "PAGE"])
        self.assertIn("12-10-2020", t.rows[0][0])
        doc.close()

    def test_nist_sp_800_53_page_468_baseline_table(self) -> None:
        """NIST SP 800-53 page 468 extracts as 4 columns and preserves the √ in ASSURANCE."""
        pdf_path = Path("documents/risk_management/NIST_SP_800-53.pdf")
        self.assertTrue(pdf_path.exists(), f"Source PDF missing: {pdf_path}")
        doc = fitz.open(pdf_path)
        page = doc[467]  # Page 468 (0-indexed 467)
        tables = self.parser._extract_tables(page, 468)
        self.assertGreaterEqual(len(tables), 1, "Expected at least 1 table on page 468")
        t = tables[0]
        self.assertEqual(t.cols_count, 4, f"Expected 4 columns, got {t.cols_count}: {t.headers}")
        self.assertIn("ASSURANCE", t.headers[3])
        # Verify checkmark preservation in row 0 for IA-1
        assurance_cell = t.rows[0][3]
        self.assertEqual(assurance_cell, "√", f"Expected '√' checkmark preserved in ASSURANCE, got '{assurance_cell}'")
        doc.close()

    def test_nist_sp_800_39_page_79_task_table(self) -> None:
        """NIST SP 800-39 page 79 extracts as 2 columns with headers TASK and TASK DESCRIPTION."""
        pdf_path = Path("documents/risk_management/NIST_SP_800-39.pdf")
        self.assertTrue(pdf_path.exists(), f"Source PDF missing: {pdf_path}")
        doc = fitz.open(pdf_path)
        page = doc[78]  # Page 79 (0-indexed 78)
        tables = self.parser._extract_tables(page, 79)
        self.assertGreaterEqual(len(tables), 1, "Expected at least 1 table on page 79")
        t = tables[0]
        self.assertEqual(t.cols_count, 2, f"Expected 2 columns, got {t.cols_count}: {t.headers}")
        self.assertEqual(t.headers, ["TASK", "TASK DESCRIPTION"])
        doc.close()

    def test_nist_sp_800_186_page_18_bordered_tables(self) -> None:
        """NIST SP 800-186 page 18 existing simple bordered tables remain unchanged."""
        pdf_path = Path("documents/cryptography_security/NIST_SP_800-186.pdf")
        self.assertTrue(pdf_path.exists(), f"Source PDF missing: {pdf_path}")
        doc = fitz.open(pdf_path)
        page = doc[17]  # Page 18 (0-indexed 17)
        tables = self.parser._extract_tables(page, 18)
        self.assertEqual(len(tables), 2, "Expected 2 tables on page 18")
        self.assertEqual(tables[0].headers, ["Security Strength", "Recommended Curves"])
        self.assertEqual(tables[0].cols_count, 2)
        self.assertEqual(tables[1].headers, ["Specified Curves", "Allowed Usage"])
        self.assertEqual(tables[1].cols_count, 2)
        doc.close()

    def test_synthetic_table_sparse_column_retained(self) -> None:
        """A synthetic table containing a genuinely sparse column with one meaningful value is retained."""
        grid = [
            ["Control ID", "Baseline", "Assurance", "Notes"],
            ["AC-1", "Low", "√", "Mandatory policy"],
            ["AC-2", "Moderate", "", "Account management"],
            ["AC-3", "High", "", "Access enforcement"],
        ]
        pruned = PyMuPDFParser._prune_empty_columns(grid)
        self.assertEqual(len(pruned[0]), 4, "Expected all 4 columns retained including sparse Assurance column")
        self.assertEqual(pruned[1][2], "√")
        self.assertEqual(pruned[2][2], "")

    def test_synthetic_table_completely_empty_column_removed(self) -> None:
        """A synthetic table containing a completely empty column (all rows empty/whitespace) is safely removed."""
        grid = [
            ["Control ID", "", "Baseline", "   ", "Notes"],
            ["AC-1", "", "Low", "", "Mandatory policy"],
            ["AC-2", "  ", "Moderate", None, "Account management"],
            ["AC-3", "", "High", "", "Access enforcement"],
        ]
        pruned = PyMuPDFParser._prune_empty_columns(grid)
        self.assertEqual(len(pruned[0]), 3, f"Expected 3 columns after pruning, got {len(pruned[0])}")
        self.assertEqual(pruned[0], ["Control ID", "Baseline", "Notes"])
        self.assertEqual(pruned[1], ["AC-1", "Low", "Mandatory policy"])
        self.assertEqual(pruned[2], ["AC-2", "Moderate", "Account management"])


if __name__ == "__main__":
    unittest.main()
