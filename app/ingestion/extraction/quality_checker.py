"""Quality assessment and validation module for document extraction.

Performs cross-parser comparison, layout verification, table consistency checks,
and suspicious content flagging, recording issues as warnings rather than proof of correctness.
"""

from typing import Any, Dict, List, Optional
import re

from app.ingestion.extraction.config import ExtractionConfig
from app.ingestion.extraction.models import (
    BlockType,
    ExtractedDocument,
    ExtractedPage,
    QualityWarning,
    TableData,
)


class ExtractionQualityAssessor:
    """Evaluates extraction fidelity, parser divergence, table integrity, and character anomalies."""

    def __init__(self, config: ExtractionConfig) -> None:
        self.config = config

    def assess_page(self, page: ExtractedPage) -> List[QualityWarning]:
        """Perform automated quality evaluation on a single extracted page."""
        warnings: List[QualityWarning] = []
        raw_text = (page.raw_text or "").strip()
        struct_text = (page.structured_text or "").strip()
        raw_len = len(raw_text)
        struct_len = len(struct_text)

        # 1. Empty Page check
        if raw_len == 0 and struct_len == 0:
            warnings.append(
                QualityWarning(
                    category="empty_page",
                    message=f"Page {page.page_number} contains zero extractable text.",
                    severity="info",
                    page_number=page.page_number,
                )
            )
            return warnings

        # 2. Low-Text Page check
        if 0 < raw_len < self.config.low_text_threshold:
            warnings.append(
                QualityWarning(
                    category="low_text_page",
                    message=f"Page {page.page_number} has low text volume ({raw_len} characters).",
                    severity="info",
                    page_number=page.page_number,
                    details={"text_length": raw_len},
                )
            )

        # 3. OCR Candidate check
        if raw_len < self.config.ocr_low_text_threshold and len(page.figures) > 0:
            warnings.append(
                QualityWarning(
                    category="ocr_candidate",
                    message=(
                        f"Page {page.page_number} has low text ({raw_len} chars) but contains {len(page.figures)} "
                        "embedded images; candidate for OCR verification."
                    ),
                    severity="warning",
                    page_number=page.page_number,
                    details={"text_length": raw_len, "figure_count": len(page.figures)},
                )
            )

        # 4. Garbled Text / Font Encoding Failure check
        garbled_issues = self._detect_garbled_patterns(raw_text or struct_text)
        if garbled_issues:
            warnings.append(
                QualityWarning(
                    category="garbled_text",
                    message=f"Page {page.page_number} exhibited suspicious encoding signals: {'; '.join(garbled_issues)}.",
                    severity="warning",
                    page_number=page.page_number,
                    details={"issues": garbled_issues},
                )
            )

        # 5. Table Extraction Quality checks
        for table in page.tables:
            table_issues = self._validate_table_structure(table)
            for issue in table_issues:
                warnings.append(
                    QualityWarning(
                        category="table_irregularity",
                        message=f"Page {page.page_number} Table '{table.table_id}': {issue}",
                        severity="warning",
                        page_number=page.page_number,
                        details={"table_id": table.table_id, "issue": issue},
                    )
                )

        # 6. Reading Order Anomalies check
        reading_order_issues = self._check_reading_order(page)
        if reading_order_issues:
            for ro_issue in reading_order_issues:
                warnings.append(
                    QualityWarning(
                        category="reading_order_warning",
                        message=f"Page {page.page_number}: {ro_issue}",
                        severity="info",
                        page_number=page.page_number,
                    )
                )

        # 7. Representation Completeness (raw vs structured comparison)
        if raw_len > 0 and struct_len > 0:
            divergence = abs(raw_len - struct_len) / max(raw_len, struct_len)
            if divergence > 0.40 and raw_len > 200:
                warnings.append(
                    QualityWarning(
                        category="representation_divergence",
                        message=(
                            f"Page {page.page_number}: Significant volume divergence between raw ({raw_len} chars) "
                            f"and structured text ({struct_len} chars, divergence {divergence:.1%})."
                        ),
                        severity="warning",
                        page_number=page.page_number,
                        details={"raw_len": raw_len, "struct_len": struct_len, "divergence": round(divergence, 3)},
                    )
                )

        return warnings

    def assess_document(self, doc: ExtractedDocument) -> ExtractedDocument:
        """Evaluate entire document, attaching page-level and document-level quality warnings."""
        doc_warnings: List[QualityWarning] = []

        total_pages = len(doc.pages)
        empty_pages = 0
        ocr_candidates = 0
        garbled_pages = 0
        table_warning_count = 0

        for page in doc.pages:
            page_warnings = self.assess_page(page)
            # Combine without duplicating existing warnings
            existing_categories = {w.category for w in page.quality_warnings}
            for pw in page_warnings:
                if pw.category not in existing_categories:
                    page.quality_warnings.append(pw)

            # Accumulate metrics
            for w in page.quality_warnings:
                if w.category == "empty_page":
                    empty_pages += 1
                elif w.category == "ocr_candidate":
                    ocr_candidates += 1
                elif w.category == "garbled_text":
                    garbled_pages += 1
                elif w.category == "table_irregularity":
                    table_warning_count += 1

        # Document-level summaries
        if empty_pages > 0 and empty_pages == total_pages:
            doc_warnings.append(
                QualityWarning(
                    category="all_pages_empty",
                    message=f"Document '{doc.document_id}' has {total_pages} pages, all of which are empty.",
                    severity="critical",
                )
            )

        if ocr_candidates > 0:
            doc_warnings.append(
                QualityWarning(
                    category="document_has_ocr_candidates",
                    message=f"Document contains {ocr_candidates} page(s) flagged for OCR verification.",
                    severity="warning",
                    details={"count": ocr_candidates},
                )
            )

        if garbled_pages > 0:
            doc_warnings.append(
                QualityWarning(
                    category="document_has_garbled_pages",
                    message=f"Document contains {garbled_pages} page(s) with potential font encoding corruption.",
                    severity="warning",
                    details={"count": garbled_pages},
                )
            )

        doc.document_warnings.extend(doc_warnings)
        return doc

    def _detect_garbled_patterns(self, text: str) -> List[str]:
        """Check for font corruption, unicode replacement chars, or broken ligatures."""
        if not text or len(text.strip()) < 50:
            return []

        stripped = text.strip()
        total_chars = len(stripped)
        issues: List[str] = []

        # 1. Replacement character frequency (U+FFFD)
        replacement_count = stripped.count("\ufffd")
        if replacement_count / total_chars > self.config.garbled_replacement_ratio_threshold:
            issues.append(f"High replacement char ratio ({replacement_count}/{total_chars})")

        # 2. Control characters (excluding standard whitespace)
        control_count = sum(1 for c in stripped if ord(c) < 32 and c not in ("\n", "\r", "\t"))
        if control_count / total_chars > self.config.garbled_control_char_threshold:
            issues.append(f"Excessive control characters ({control_count}/{total_chars})")

        # 3. Low alphanumeric ratio (ignoring repetitive leader dots)
        clean_non_dots = "".join(c for c in stripped if c != ".")
        if len(clean_non_dots) >= 50:
            alnum_count = sum(1 for c in clean_non_dots if c.isalnum())
            if alnum_count / len(clean_non_dots) < self.config.garbled_min_alnum_ratio:
                issues.append(f"Low alphanumeric density ({alnum_count / len(clean_non_dots):.1%})")

        # 4. Genuinely garbled unbroken alphanumeric tokens (> 60 chars)
        for word in stripped.split():
            if word.startswith(("http://", "https://", "ftp://", "www.")) or "://" in word:
                continue
            core = "".join(c for c in word if c.isalnum())
            if len(core) > self.config.garbled_max_token_length:
                if self._is_exempt_long_token(word, core):
                    continue
                issues.append(f"Abnormally long unbroken token ({len(core)} chars)")
                break

        return issues

    @staticmethod
    def _is_exempt_long_token(word: str, core: Optional[str] = None) -> bool:
        """Exempt valid long numbers, hex constants, and legitimate URL/path slugs.

        Supports both (word, core) and legacy single-argument (core) signatures.
        """
        if core is None:
            core = "".join(c for c in word if c.isalnum())
            raw_token = word
        else:
            raw_token = word

        # 1. Pure numbers (e.g. 68-char prime modulus in NIST SP 800-186 p.21)
        if core.isdigit():
            return True

        # 2. Hexadecimal constants (e.g. 0x0123...)
        if (core.startswith("0x") or core.startswith("0X")) and len(core) > 2:
            return all(c in "0123456789abcdefABCDEF" for c in core[2:])

        # 3. URL slug, URI path, or hyphenated compound identifier
        clean_token = raw_token.strip("()[]{}'\"<>,;`")
        if re.fullmatch(r"[a-zA-Z0-9_\-\./\?=&%:]+", clean_token):
            parts = [p for p in re.split(r"[-_/\.:\?=&%]+", clean_token) if p]
            # Must consist of multiple punctuated parts, none exceeding 35 chars
            if len(parts) > 1 and all(len(p) <= 35 for p in parts):
                return True

        return False

    def _validate_table_structure(self, table: TableData) -> List[str]:
        """Verify structural consistency of extracted table headers and rows."""
        issues: List[str] = []
        if table.rows_count == 0:
            return ["Table has 0 data rows"]

        col_count = table.cols_count
        row_lengths = [len(r) for r in table.rows]

        # Column count consistency
        if any(l != col_count for l in row_lengths):
            issues.append(f"Inconsistent column counts across rows (expected {col_count}, observed {set(row_lengths)})")

        # Empty cell ratio
        total_cells = sum(row_lengths)
        empty_cells = sum(1 for r in table.rows for cell in r if not cell.strip())
        if total_cells > 0 and (empty_cells / total_cells) > 0.70:
            issues.append(f"High sparse/empty cell ratio ({empty_cells}/{total_cells} = {empty_cells/total_cells:.1%})")

        # Headers check
        if not table.headers or all(not h.strip() for h in table.headers):
            issues.append("Table lacks header titles")

        return issues

    def _check_reading_order(self, page: ExtractedPage) -> List[str]:
        """Detect erratic coordinate jumps that may signal reading order anomalies."""
        issues: List[str] = []
        blocks = [b for b in page.blocks if b.bbox is not None and b.block_type in (BlockType.PARAGRAPH, BlockType.HEADING)]
        if len(blocks) < 3:
            return issues

        # Check for sharp upward jumps within the same column
        for i in range(1, len(blocks)):
            prev_b = blocks[i - 1].bbox
            curr_b = blocks[i].bbox
            if prev_b and curr_b:
                # Same horizontal column (left alignment within 30 points)
                if abs(prev_b.left - curr_b.left) < 30:
                    # Current block is significantly higher up than previous block
                    if curr_b.bottom < prev_b.top - 80:
                        issues.append(
                            f"Potential reading order anomaly between block {blocks[i-1].block_id} and {blocks[i].block_id} "
                            f"(vertical jump of {prev_b.top - curr_b.bottom:.1f}pt)"
                        )
                        break

        return issues
