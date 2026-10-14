"""Automated tests for conservative document cleaning pipeline."""

import unittest
from pathlib import Path
from app.ingestion.cleaning.config import CleaningConfig
from app.ingestion.cleaning.header_footer import HeaderFooterDetector
from app.ingestion.cleaning.hyphenation import HyphenationCleaner
from app.ingestion.cleaning.encoding import EncodingCleaner
from app.ingestion.cleaning.boilerplate import BoilerplateDetector
from app.ingestion.cleaning.pipeline import DocumentCleaningPipeline


class TestCleaningPipeline(unittest.TestCase):
    """Test suite verifying conservative cleaning rules and cybersecurity domain protection."""

    def setUp(self):
        self.config = CleaningConfig()
        self.header_footer = HeaderFooterDetector(self.config)
        self.hyphenation = HyphenationCleaner(self.config)
        self.encoding = EncodingCleaner(self.config)
        self.boilerplate = BoilerplateDetector(self.config)

    def test_running_header_detection_and_removal(self):
        """Verified running headers are discovered and stripped from page top."""
        pages = [
            {"structured_text": "NIST SP 800-53, REV. 5\n\nSection 1 text"},
            {"structured_text": "NIST SP 800-53, REV. 5\n\nSection 2 text"},
            {"structured_text": "NIST SP 800-53, REV. 5\n\nSection 3 text"},
            {"structured_text": "NIST SP 800-53, REV. 5\n\nSection 4 text"},
        ]
        headers, footers = self.header_footer.discover_document_headers_footers(pages)
        self.assertIn("NIST SP 800-53, REV. 5", headers)

        cleaned, h_rem, f_rem = self.header_footer.clean_page(pages[0]["structured_text"], headers, footers)
        self.assertEqual(h_rem, ["NIST SP 800-53, REV. 5"])
        self.assertNotIn("NIST SP 800-53, REV. 5", cleaned.splitlines()[0])
        self.assertIn("Section 1 text", cleaned)

    def test_footer_number_removal(self):
        """Trailing standalone page numbers and roman numerals are removed."""
        text = "This is body text on the page.\n\n42"
        cleaned, h_rem, f_rem = self.header_footer.clean_page(text, set(), set())
        self.assertEqual(f_rem, ["42"])
        self.assertEqual(cleaned.strip(), "This is body text on the page.")

        # Roman numeral footer
        text_roman = "Front matter text.\n\niv"
        cleaned_roman, _, f_rem_roman = self.header_footer.clean_page(text_roman, set(), set())
        self.assertEqual(f_rem_roman, ["iv"])
        self.assertEqual(cleaned_roman.strip(), "Front matter text.")

    def test_section_heading_and_list_number_preserved(self):
        """Numbered headings or lists must NOT be stripped as footers or headers."""
        text = "3.1 Security Control Requirements\n\nDetailed requirements here."
        cleaned, h_rem, f_rem = self.header_footer.clean_page(text, set(), set())
        self.assertEqual(h_rem, [])
        self.assertIn("3.1 Security Control Requirements", cleaned)

    def test_hyphenation_repair(self):
        """Confirmed English words broken across line wraps are repaired."""
        text = "Ensure proper authen-\ntication and implemen-\ntation across the enterprise."
        cleaned, repairs, warns = self.hyphenation.clean_text(text)
        self.assertIn("authentication", cleaned)
        self.assertIn("implementation", cleaned)
        self.assertEqual(len(repairs), 2)

    def test_protection_of_cybersecurity_identifiers_and_urls(self):
        """Cybersecurity identifiers, controls, algorithms, and URLs must NEVER be altered."""
        text = (
            "System uses AES-256-GCM and HMAC-SHA-256 for FIPS-140-3 compliance.\n"
            "Control AC-1 and SC-7(12) protect zero-trust and cross-site requests.\n"
            "Patched vulnerability CVE-2023-12345 in high-performance cluster.\n"
            "Refer to https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final"
        )
        cleaned, repairs, warns = self.hyphenation.clean_text(text)
        self.assertIn("AES-256-GCM", cleaned)
        self.assertIn("HMAC-SHA-256", cleaned)
        self.assertIn("FIPS-140-3", cleaned)
        self.assertIn("AC-1", cleaned)
        self.assertIn("SC-7(12)", cleaned)
        self.assertIn("zero-trust", cleaned)
        self.assertIn("cross-site", cleaned)
        self.assertIn("CVE-2023-12345", cleaned)
        self.assertIn("https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final", cleaned)
        self.assertEqual(len(repairs), 0)

    def test_replacement_character_handling(self):
        """U+FFFD list markers are resolved to bullets, while ambiguous math remains intact."""
        # Bullet list case
        text_bullet = "Requirements:\n\ufffd First requirement\n\ufffd Second requirement"
        cleaned_bullet, transforms, _ = self.encoding.clean_text(text_bullet)
        self.assertIn("* First requirement", cleaned_bullet)
        self.assertIn("* Second requirement", cleaned_bullet)

        # Ambiguous / mathematical formula case (from NIST SP 800-186)
        text_math = "where |t| <= 2 \ufffd q is the bound."
        cleaned_math, _, warns = self.encoding.clean_text(text_math)
        self.assertIn("\ufffd", cleaned_math)
        self.assertTrue(any(w["type"] == "UNCERTAIN_REPLACEMENT_CHAR_PRESERVED" for w in warns))

    def test_markdown_table_and_whitespace_preservation(self):
        """Markdown table syntax, pipes, and indentation must be strictly preserved."""
        table_text = (
            "Here is the control table:\n\n\n\n\n"
            "| Control ID | Name | Priority |\n"
            "| :--- | :--- | :--- |\n"
            "| AC-1 | Access Control Policy | P1 |\n"
            "| SC-7 | Boundary Protection | P1 |\n\n\n"
        )
        cleaned, transforms, _ = self.encoding.clean_text(table_text)
        self.assertIn("| Control ID | Name | Priority |", cleaned)
        self.assertIn("| AC-1 | Access Control Policy | P1 |", cleaned)
        # Excessive blank lines collapsed
        self.assertNotIn("\n\n\n", cleaned)

    def test_boilerplate_tagging(self):
        """NIST commercial disclaimers and statutory notices are tagged without text deletion."""
        boilerplate = (
            "Certain commercial entities, equipment, or materials may be identified in this Web site "
            "or document in order to describe an experimental procedure or concept adequately."
        )
        tags = self.boilerplate.tag_page_boilerplate(boilerplate)
        self.assertEqual(len(tags), 1)
        self.assertEqual(tags[0]["type"], "NIST_COMMERCIAL_DISCLAIMER")

    def test_idempotency_of_cleaning(self):
        """Running the cleaning pipeline twice produces identical output."""
        sample_text = (
            "NIST SP 800-53, REV. 5\n\n"
            "The authen-\ntication system must enforce AC-1 and AES-256 encryption.\n\n\n\n"
            "12"
        )
        verified_headers = {"NIST SP 800-53, REV. 5"}
        verified_footers = set()

        # Pass 1
        t1, _, _ = self.header_footer.clean_page(sample_text, verified_headers, verified_footers)
        t2, _, _ = self.hyphenation.clean_text(t1)
        pass1_cleaned, _, _ = self.encoding.clean_text(t2)

        # Pass 2 on already cleaned text
        p2_t1, h_rem2, f_rem2 = self.header_footer.clean_page(pass1_cleaned, verified_headers, verified_footers)
        p2_t2, rep2, _ = self.hyphenation.clean_text(p2_t1)
        pass2_cleaned, trans2, _ = self.encoding.clean_text(p2_t2)

        self.assertEqual(pass1_cleaned, pass2_cleaned)
        self.assertEqual(h_rem2, [])
        self.assertEqual(f_rem2, [])
        self.assertEqual(rep2, [])


if __name__ == "__main__":
    unittest.main()
