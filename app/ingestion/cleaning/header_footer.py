"""Detection and conservative removal of running headers and page-number footers."""

import re
from typing import List, Dict, Set, Tuple, Any
from collections import Counter
from app.ingestion.cleaning.config import CleaningConfig

PAGE_NUM_FOOTER_RE = re.compile(r'^(?:page\s+)?(?:\d+|[ivxlcdm]+|\d+-\d+)$', re.IGNORECASE)
SECTION_HEADING_RE = re.compile(r'^(?:#+|\d+(?:\.\d+)*\s+[A-Z]|[A-Z][A-Za-z0-9\s]{2,}:)')


class HeaderFooterDetector:
    """Discovers and strips verified running headers and footers across document pages."""

    def __init__(self, config: CleaningConfig):
        self.config = config

    def discover_document_headers_footers(self, pages: List[Dict[str, Any]]) -> Tuple[Set[str], Set[str]]:
        """Scan all pages of a document to find recurring top and bottom lines."""
        top_line_counter = Counter()
        bottom_line_counter = Counter()

        for p in pages:
            text = p.get("structured_text", "").strip()
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            if lines:
                top_line_counter[lines[0]] += 1
                if len(lines) > 1:
                    bottom_line_counter[lines[-1]] += 1

        total_pages = max(len(pages), 1)
        verified_headers = set()
        verified_text_footers = set()

        # Discover headers: line appears on >= min_header_frequency AND >= min_header_ratio
        for line, cnt in top_line_counter.items():
            if cnt >= self.config.min_header_frequency or (cnt >= 3 and cnt / total_pages >= self.config.min_header_ratio):
                # Ensure line is not a section heading or very short common word
                if len(line) >= 4 and not SECTION_HEADING_RE.match(line):
                    verified_headers.add(line)

        # Discover recurring textual footers (e.g. "CHAPTER THREE")
        for line, cnt in bottom_line_counter.items():
            if cnt >= self.config.min_footer_frequency:
                if len(line) >= 4 and not PAGE_NUM_FOOTER_RE.match(line):
                    verified_text_footers.add(line)

        return verified_headers, verified_text_footers

    def clean_page(
        self,
        text: str,
        verified_headers: Set[str],
        verified_text_footers: Set[str]
    ) -> Tuple[str, List[str], List[str]]:
        """
        Strip verified running headers from the top and page-number/text footers from the bottom.
        Returns: (cleaned_text, headers_removed, footers_removed)
        """
        if not text.strip():
            return text, [], []

        lines = text.splitlines()
        headers_removed = []
        footers_removed = []

        # Find first non-empty line
        start_idx = 0
        while start_idx < len(lines) and not lines[start_idx].strip():
            start_idx += 1

        if start_idx < len(lines):
            first_line = lines[start_idx].strip()
            if self.config.remove_running_headers and first_line in verified_headers:
                headers_removed.append(first_line)
                lines[start_idx] = ""

        # Find last non-empty line
        end_idx = len(lines) - 1
        while end_idx >= 0 and not lines[end_idx].strip():
            end_idx -= 1

        if end_idx >= 0:
            last_line = lines[end_idx].strip()
            # Check for isolated page number or verified textual footer
            if self.config.remove_running_footers:
                if PAGE_NUM_FOOTER_RE.match(last_line) or last_line in verified_text_footers:
                    footers_removed.append(last_line)
                    lines[end_idx] = ""

        cleaned = "\n".join(lines).strip("\n")
        return cleaned, headers_removed, footers_removed
