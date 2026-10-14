"""Encoding sanitization and replacement character handling."""

import re
from typing import Tuple, List, Dict
from app.ingestion.cleaning.config import CleaningConfig


class EncodingCleaner:
    """Sanitizes text encodings, handles replacement characters, and normalizes whitespace."""

    def __init__(self, config: CleaningConfig):
        self.config = config

    def clean_text(self, text: str) -> Tuple[str, List[Dict[str, str]], List[Dict[str, str]]]:
        """
        Sanitize character encoding, whitespace, and U+FFFD instances.
        Returns: (cleaned_text, transformations, warnings)
        """
        transformations = []
        warnings = []

        if not text:
            return text, transformations, warnings

        # 1. Normalize non-breaking spaces and typography
        if self.config.normalize_whitespace:
            if "\u00a0" in text:
                text = text.replace("\u00a0", " ")
                transformations.append({"type": "NON_BREAKING_SPACE", "desc": "Replaced non-breaking spaces with standard spaces"})

            # Normalize quotes and dashes
            replacements = [
                ("“", '"'), ("”", '"'),
                ("‘", "'"), ("’", "'"),
                ("—", " - "), ("–", "-")
            ]
            for orig, target in replacements:
                if orig in text:
                    text = text.replace(orig, target)
                    transformations.append({"type": "TYPOGRAPHY_NORMALIZED", "desc": f"Normalized '{orig}' to '{target}'"})

        # 2. Inspect and handle U+FFFD
        if self.config.handle_replacement_chars and "\ufffd" in text:
            lines = text.splitlines()
            cleaned_lines = []
            for ln in lines:
                if "\ufffd" in ln:
                    # Check if bullet list marker at line start
                    bullet_match = re.match(r'^(\s*)\ufffd\s+(.*)$', ln)
                    if bullet_match:
                        indent = bullet_match.group(1)
                        rest = bullet_match.group(2)
                        ln = f"{indent}* {rest}"
                        transformations.append({
                            "type": "REPLACEMENT_CHAR_RESOLVED",
                            "desc": "Resolved U+FFFD as list bullet marker '* '"
                        })
                    elif re.search(r'[+\-=*/<>|()]\s*\ufffd', ln) or re.search(r'\ufffd\s*[a-zA-Z]\b', ln):
                        # Mathematical context (e.g. NIST SP 800-186) -> Preserve and warn!
                        warnings.append({
                            "type": "UNCERTAIN_REPLACEMENT_CHAR_PRESERVED",
                            "desc": f"Preserved U+FFFD in mathematical/technical expression: '{ln[:80]}'"
                        })
                    else:
                        # Intra-word ligature or separator (e.g. "Option\ufffdA")
                        if re.search(r'[A-Za-z]\ufffd[A-Za-z]', ln):
                            ln = re.sub(r'([A-Za-z])\ufffd([A-Za-z])', r'\1 \2', ln)
                            transformations.append({
                                "type": "REPLACEMENT_CHAR_SPACED",
                                "desc": "Replaced intra-word U+FFFD separator with space"
                            })
                        else:
                            warnings.append({
                                "type": "UNCERTAIN_REPLACEMENT_CHAR_PRESERVED",
                                "desc": f"Preserved ambiguous U+FFFD: '{ln[:80]}'"
                            })
                cleaned_lines.append(ln)
            text = "\n".join(cleaned_lines)

        # 3. Collapse excessive blank lines and trailing whitespace
        if self.config.normalize_whitespace:
            lines = [ln.rstrip() for ln in text.splitlines()]
            text = "\n".join(lines)
            # Collapse 3+ newlines to 2
            old_len = len(text)
            text = re.sub(r'\n{3,}', '\n\n', text)
            if len(text) < old_len:
                transformations.append({
                    "type": "EXCESSIVE_BLANK_LINES_COLLAPSED",
                    "desc": f"Collapsed excessive newlines (-{old_len - len(text)} chars)"
                })
            text = text.strip("\n")

        return text, transformations, warnings
