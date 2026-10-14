"""Detection and metadata tagging of standardized NIST legal and administrative boilerplate."""

import re
from typing import List, Dict, Any, Tuple
from app.ingestion.cleaning.config import CleaningConfig

BOILERPLATE_PATTERNS = [
    ("NIST_COMMERCIAL_DISCLAIMER", re.compile(r'certain commercial entities,?\s+equipment,?\s+or materials', re.IGNORECASE)),
    ("NIST_STATUTORY_RESPONSIBILITIES", re.compile(r'developed by nist in accordance with its statutory responsibilities', re.IGNORECASE)),
    ("NIST_SERIES_NOTICE", re.compile(r'reports on computer systems technology', re.IGNORECASE)),
    ("NIST_NON_CONTRADICTION", re.compile(r'nothing in this publication should be taken to contradict', re.IGNORECASE)),
    ("NIST_CSD_CONTACT", re.compile(r'national institute of standards and technology\s+attn:\s+computer security division', re.IGNORECASE)),
    ("NIST_PATENT_POLICY", re.compile(r'nist\s+collaborates\s+with\s+industry\s+on\s+standards.*patent', re.IGNORECASE))
]


class BoilerplateDetector:
    """Identifies and tags standard NIST administrative boilerplate without deleting technical content."""

    def __init__(self, config: CleaningConfig):
        self.config = config

    def tag_page_boilerplate(self, text: str) -> List[Dict[str, Any]]:
        """Scan text and return detected boilerplate blocks and metadata tags."""
        tags = []
        if not self.config.tag_boilerplate or not text:
            return tags

        paragraphs = text.split("\n\n")
        for para in paragraphs:
            para_clean = para.strip()
            if len(para_clean) < 60:
                continue

            for tag_name, pattern in BOILERPLATE_PATTERNS:
                if pattern.search(para_clean):
                    tags.append({
                        "type": tag_name,
                        "snippet": para_clean[:120].replace("\n", " "),
                        "char_count": len(para_clean)
                    })
                    break

        return tags
