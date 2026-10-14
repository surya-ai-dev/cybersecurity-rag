"""Conservative hyphenation repair with strict cybersecurity domain protections."""

import re
from typing import Tuple, List, Dict, Set
from app.ingestion.cleaning.config import CleaningConfig

# Common English prefixes/words frequently broken in NIST publication margins
COMMON_COMPOUND_WORDS: Set[str] = {
    "authentication", "authorization", "implementation", "organization", "organizational",
    "management", "cryptographic", "cryptography", "cryptosystem", "vulnerability", "vulnerabilities",
    "continuous", "monitoring", "recommendation", "recommendations", "operational",
    "interoperability", "infrastructure", "configuration", "capabilities", "information",
    "verification", "identification", "responsibilities", "considerations", "assurance",
    "establishment", "environment", "environments", "administrator", "administrators",
    "transmission", "protection", "assessment", "assessments", "requirement", "requirements",
    "architecture", "architectures", "guidelines", "publication", "publications",
    "reproducibility", "classification", "confidentiality", "integrity", "availability",
    "specification", "specifications", "accreditation", "certification", "compliance"
}

NIST_CONTROL_RE = re.compile(r'^[A-Z]{2}-\d+(?:\(\d+\))?$')
CVE_RE = re.compile(r'^CVE-\d{4}-\d{4,7}$')


class HyphenationCleaner:
    """Repairs soft hyphens broken across lines while strictly preserving technical identifiers."""

    def __init__(self, config: CleaningConfig):
        self.config = config

    def is_protected_term(self, word1: str, word2: str) -> bool:
        """Return True if word1-word2 must never be joined."""
        combined_hyphen = f"{word1}-{word2}".lower()
        if combined_hyphen in self.config.protected_hyphen_terms:
            return True
        if NIST_CONTROL_RE.match(f"{word1}-{word2}"):
            return True
        if CVE_RE.match(f"{word1}-{word2}"):
            return True
        # Cryptographic algorithms or hexadecimal (contains digits or uppercase acronyms)
        if re.search(r'\d', word1) or re.search(r'\d', word2):
            return True
        if word1.isupper() and len(word1) >= 2:
            return True
        if word2.isupper() and len(word2) >= 2:
            return True
        return False

    def clean_text(self, text: str) -> Tuple[str, List[Dict[str, str]], List[Dict[str, str]]]:
        """
        Scan text for line-break and wrapped hyphens.
        Returns: (cleaned_text, repairs_made, warnings_logged)
        """
        repairs_made = []
        warnings_logged = []

        if not self.config.repair_line_end_hyphens or not text:
            return text, repairs_made, warnings_logged

        def replace_line_break_hyphen(match: re.Match) -> str:
            w1 = match.group(1)
            w2 = match.group(2)
            joined = f"{w1}{w2}"
            hyphenated = f"{w1}-{w2}"

            # Check protected
            if self.is_protected_term(w1, w2):
                return match.group(0)

            # Check if joined word is in common vocabulary or ends with common suffix
            is_valid_word = (
                joined.lower() in COMMON_COMPOUND_WORDS or
                joined.lower().endswith(("tion", "tions", "ment", "ments", "ity", "ities", "able", "ing", "ed"))
            )

            if is_valid_word and not self.is_protected_term(w1, w2):
                repairs_made.append({
                    "original": match.group(0).replace("\n", "\\n"),
                    "repaired": joined,
                    "reason": "Confirmed soft-hyphen word break"
                })
                return joined
            else:
                # Ambiguous: leave intact to prevent accidental corruptions, but log warning
                warnings_logged.append({
                    "original": match.group(0).replace("\n", "\\n"),
                    "action": "PRESERVED_AS_IS",
                    "reason": f"Ambiguous hyphenation: '{w1}-{w2}' vs '{joined}'"
                })
                return match.group(0)

        # 1. Match word-\nword (across newlines)
        pattern_nl = re.compile(r'(\b[a-zA-Z]{3,})-\s*\n\s*([a-zA-Z]{3,}\b)')
        text = pattern_nl.sub(replace_line_break_hyphen, text)

        # 2. Match word- word (wrapped space artifacts within lines)
        pattern_sp = re.compile(r'(\b[a-zA-Z]{3,})-\s+([a-zA-Z]{3,}\b)')
        def replace_space_hyphen(match: re.Match) -> str:
            w1 = match.group(1)
            w2 = match.group(2)
            joined = f"{w1}{w2}"
            hyphenated = f"{w1}-{w2}"

            if self.is_protected_term(w1, w2):
                return hyphenated

            if joined.lower() in COMMON_COMPOUND_WORDS:
                repairs_made.append({
                    "original": match.group(0),
                    "repaired": joined,
                    "reason": "Normalized spaced hyphen word break"
                })
                return joined
            elif hyphenated.lower() in self.config.protected_hyphen_terms:
                return hyphenated
            else:
                return match.group(0)

        text = pattern_sp.sub(replace_space_hyphen, text)

        return text, repairs_made, warnings_logged
