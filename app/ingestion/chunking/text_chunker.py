"""Structure-aware normal text chunker for NIST cybersecurity publications."""

from dataclasses import dataclass
import re
from typing import Any, Dict, List, Optional, Tuple

from app.ingestion.chunking.config import ChunkingConfig
from app.ingestion.chunking.models import ChunkRecord
from app.ingestion.chunking.tokenizer import TokenizerAdapter


@dataclass
class TextSegment:
    """An atomic text unit (paragraph, heading, or list item) with source provenance."""

    text: str
    page_number: int
    citation_label: str
    section_path: List[str]
    section_heading: str
    is_heading: bool = False
    bbox: Optional[Dict[str, float]] = None
    encoding_warnings: List[str] = None

    def __post_init__(self):
        if self.encoding_warnings is None:
            self.encoding_warnings = []


class StructureAwareTextChunker:
    """Chunks cleaned narrative text while preserving headings, section boundaries, and lists."""

    # Sentence splitting regex protecting common cybersecurity and English abbreviations
    SENTENCE_SPLIT_REGEX = re.compile(
        r"(?<!\be\.g)(?<!\bi\.e)(?<!\bet al)(?<!\bvs)(?<!\bRev)(?<!\bNo)(?<!\bFig)(?<!\bTab)"
        r"(?<!\bNIST)(?<!\bSP)(?<!\bFIPS)(?<!\bp)(?<!\bpp)"
        r"(?<=[.!?])\s+(?=[A-Z0-9\(\[\"\'])"
    )

    def __init__(self, config: ChunkingConfig, tokenizer: TokenizerAdapter):
        self.config = config
        self.tokenizer = tokenizer

    def chunk_document_text(
        self,
        document_id: str,
        category: str,
        source_file: str,
        pages: List[Dict[str, Any]],
        table_markdown_set: Optional[set] = None,
        duplicate_of: Optional[List[str]] = None,
    ) -> List[ChunkRecord]:
        """Convert page text streams into normalized, structure-aware text ChunkRecords."""
        if table_markdown_set is None:
            table_markdown_set = set()
        if duplicate_of is None:
            duplicate_of = []

        segments = self._extract_segments(pages, table_markdown_set)
        if not segments:
            return []

        # Group segments by top-level or immediate section to enforce section boundaries
        chunks: List[ChunkRecord] = []
        seq_num = 1

        # We partition segments into section groups
        section_groups = self._group_by_section(segments)

        for section_heading, group_segments in section_groups:
            section_chunks = self._chunk_section_group(
                document_id=document_id,
                category=category,
                source_file=source_file,
                section_heading=section_heading,
                segments=group_segments,
                seq_start=seq_num,
                duplicate_of=duplicate_of,
            )
            chunks.extend(section_chunks)
            seq_num += len(section_chunks)

        return chunks

    def _extract_segments(
        self,
        pages: List[Dict[str, Any]],
        table_markdown_set: set,
    ) -> List[TextSegment]:
        """Parse pages into ordered TextSegments, stripping embedded tables and tracking headings."""
        segments: List[TextSegment] = []
        current_section_path: List[str] = ["Introduction"]
        current_heading: str = "Introduction"

        for page in pages:
            page_num = page.get("page_number", 1)
            citation_label = page.get("citation_label", f"[Page {page_num}]")
            page_text = page.get("cleaned_text", "") or ""
            page_warnings = []

            # Collect encoding warnings for page if present
            cleaning_meta = page.get("cleaning_metadata", {})
            for w in cleaning_meta.get("encoding_warnings", []):
                if isinstance(w, dict):
                    desc = w.get("desc") or w.get("warning") or w.get("message")
                    w_type = w.get("type", "ENCODING_WARNING")
                    page_warnings.append(f"{w_type}: {desc}" if desc else str(w))
                else:
                    page_warnings.append(str(w))
            if "\ufffd" in page_text:
                page_warnings.append(f"Contains \\ufffd on page {page_num}")

            # Strip embedded pipe tables from page_text so they are not indexed twice
            cleaned_narrative = page_text
            for tbl_md in table_markdown_set:
                if tbl_md and tbl_md in cleaned_narrative:
                    cleaned_narrative = cleaned_narrative.replace(tbl_md, "\n\n")

            # Split into paragraph blocks
            raw_paragraphs = [p.strip() for p in cleaned_narrative.split("\n\n") if p.strip()]

            for para in raw_paragraphs:
                # Skip standalone draft line numbers / page numbers that are solely digits (<= 4 digits)
                clean_digits = para.lstrip("#").strip("*_ \t")
                if clean_digits.isdigit() and len(clean_digits) <= 4:
                    continue

                # Check if this paragraph is a section heading
                detected_heading, heading_level = self._detect_heading(para)
                if detected_heading:
                    current_heading = detected_heading
                    # Update hierarchy
                    if heading_level == 1:
                        current_section_path = [detected_heading]
                    elif heading_level == 2:
                        current_section_path = current_section_path[:1] + [detected_heading]
                    else:
                        current_section_path = current_section_path[:2] + [detected_heading]

                    segments.append(
                        TextSegment(
                            text=detected_heading,
                            page_number=page_num,
                            citation_label=citation_label,
                            section_path=list(current_section_path),
                            section_heading=current_heading,
                            is_heading=True,
                            encoding_warnings=page_warnings,
                        )
                    )
                else:
                    segments.append(
                        TextSegment(
                            text=para,
                            page_number=page_num,
                            citation_label=citation_label,
                            section_path=list(current_section_path),
                            section_heading=current_heading,
                            is_heading=False,
                            encoding_warnings=page_warnings,
                        )
                    )

        return segments

    def _detect_heading(self, text: str) -> Tuple[Optional[str], int]:
        """Detect Markdown headings (#, ##, ###) or numbered section titles."""
        stripped = text.strip()
        if not stripped or len(stripped) > 200:
            return None, 0

        # Markdown headings (#, ##, ###, ####, etc.)
        if stripped.startswith("#"):
            h_level = 0
            while h_level < len(stripped) and stripped[h_level] == "#":
                h_level += 1
            heading_content = stripped[h_level:].strip()
            clean_title = heading_content.strip("*_ \t")
            # Bare draft line numbers like '### 13' or '### 17' must NOT become headings
            if not clean_title or clean_title.isdigit():
                return None, 0
            return heading_content, min(4, max(1, h_level))

        # NIST Special Headings: "APPENDIX A ...", "CHAPTER ONE ..."
        if re.match(r"^APPENDIX\s+[A-Z0-9]+", stripped, re.IGNORECASE):
            return stripped, 1
        if re.match(r"^CHAPTER\s+(?:[A-Z]+|\d+)", stripped, re.IGNORECASE):
            return stripped, 1

        # NIST Control pattern: "AC-2 ACCOUNT MANAGEMENT"
        if re.match(r"^[A-Z]{2}-\d+(?:\(\d+\))?\s+[A-Z\s]+$", stripped):
            return stripped, 2

        # Numbered section titles (must have dot-delimited numbering, e.g. "1. Introduction", "2.1 Purpose")
        # Must not be a full sentence (ending in punctuation) or bare draft margin line ("481 Institute...")
        m = re.match(r"^(\d+(?:\.\d+)+|\d+\.)\s+([A-Z][^\n]+)$", stripped)
        if m:
            num_part = m.group(1)
            title_part = m.group(2).strip()
            if len(title_part) <= 120 and not title_part.endswith((".", ";", ":", ",")):
                if num_part.endswith("."):
                    base_num = num_part[:-1]
                    if base_num.isdigit() and int(base_num) > 25:
                        return None, 0
                dots = num_part.count(".")
                level = min(3, max(1, dots))
                return stripped, level

        return None, 0

    def _group_by_section(
        self, segments: List[TextSegment]
    ) -> List[Tuple[str, List[TextSegment]]]:
        """Group contiguous segments by section heading so sections are never merged.
        Consecutive headings with no intervening body text are accumulated into a single
        hierarchical group rather than emitting empty standalone heading chunks."""
        groups: List[Tuple[str, List[TextSegment]]] = []
        current_heading: Optional[str] = None
        current_group: List[TextSegment] = []

        for seg in segments:
            if seg.is_heading:
                # If current_group already contains non-heading body segments, flush the group
                has_body = any(not s.is_heading for s in current_group)
                if has_body:
                    groups.append((current_heading or "Introduction", current_group))
                    current_heading = seg.text
                    current_group = [seg]
                else:
                    # Current group has only headings or preamble (no body text)
                    # Accumulate consecutive headings together
                    current_heading = seg.text
                    current_group.append(seg)
            else:
                if current_heading is None:
                    current_heading = seg.section_heading
                current_group.append(seg)

        if current_group:
            has_body = any(not s.is_heading for s in current_group)
            if has_body or not groups:
                groups.append((current_heading or "Introduction", current_group))
            else:
                # Trailing lone heading with no body: attach to previous group
                prev_heading, prev_segments = groups[-1]
                prev_segments.extend(current_group)

        return groups

    def _chunk_section_group(
        self,
        document_id: str,
        category: str,
        source_file: str,
        section_heading: str,
        segments: List[TextSegment],
        seq_start: int,
        duplicate_of: List[str],
    ) -> List[ChunkRecord]:
        """Accumulate paragraphs within a section, splitting oversizes and applying overlap."""
        chunks: List[ChunkRecord] = []
        current_paragraphs: List[str] = []
        current_pages: List[int] = []
        current_warnings: List[str] = []
        section_path = segments[0].section_path if segments else [section_heading]

        # Extract heading text if present (accumulating all consecutive headings in the group)
        heading_lines = []
        body_segments: List[TextSegment] = []
        for seg in segments:
            if seg.is_heading:
                heading_lines.append(f"### {seg.text}")
            else:
                body_segments.append(seg)

        heading_prefix = ("\n\n".join(heading_lines) + "\n\n") if heading_lines else ""

        if not body_segments:
            # Genuinely empty section or lone heading
            if heading_prefix.strip():
                chunk_id = f"{document_id}_txt_{seq_start:05d}"
                text = heading_prefix.strip()
                chunks.append(
                    ChunkRecord(
                        chunk_id=chunk_id,
                        document_id=document_id,
                        category=category,
                        source_file=source_file,
                        content_type="text",
                        page_start=segments[0].page_number,
                        page_end=segments[0].page_number,
                        citation_label=segments[0].citation_label,
                        section_path=section_path,
                        section_heading=section_heading,
                        text=text,
                        token_count=self.tokenizer.count_tokens(text),
                        char_count=len(text),
                        duplicate_of=duplicate_of,
                    )
                )
            return chunks

        # Process body segments
        seq_num = seq_start
        accumulated_text = ""
        prev_chunk_overlap = ""

        i = 0
        while i < len(body_segments):
            seg = body_segments[i]
            para_text = seg.text.strip()
            if not para_text:
                i += 1
                continue

            para_tokens = self.tokenizer.count_tokens(para_text)
            heading_tokens = self.tokenizer.count_tokens(heading_prefix) if heading_prefix else 0
            max_body_tokens = max(20, self.config.max_chunk_tokens - heading_tokens)

            # Case A: Monolithic paragraph exceeding available body budget
            if para_tokens > max_body_tokens:
                # Flush existing accumulated text first if non-empty
                if accumulated_text:
                    full_chunk_text = f"{heading_prefix}{prev_chunk_overlap}{accumulated_text}".strip()
                    tokens = self.tokenizer.count_tokens(full_chunk_text)
                    if tokens > self.config.max_chunk_tokens and prev_chunk_overlap:
                        full_chunk_text = f"{heading_prefix}{accumulated_text}".strip()
                        tokens = self.tokenizer.count_tokens(full_chunk_text)
                    chunk_id = f"{document_id}_txt_{seq_num:05d}"
                    p_min = min(current_pages) if current_pages else seg.page_number
                    p_max = max(current_pages) if current_pages else seg.page_number
                    cit = f"[{document_id} Page {p_min}]" if p_min == p_max else f"[{document_id} Pages {p_min}-{p_max}]"

                    chunks.append(
                        ChunkRecord(
                            chunk_id=chunk_id,
                            document_id=document_id,
                            category=category,
                            source_file=source_file,
                            content_type="text",
                            page_start=p_min,
                            page_end=p_max,
                            citation_label=cit,
                            section_path=section_path,
                            section_heading=section_heading,
                            text=full_chunk_text,
                            token_count=tokens,
                            char_count=len(full_chunk_text),
                            has_encoding_warning=bool(current_warnings),
                            encoding_warnings=list(set(current_warnings)),
                            duplicate_of=duplicate_of,
                        )
                    )
                    seq_num += 1
                    prev_chunk_overlap = self._compute_overlap_text(accumulated_text)
                    accumulated_text = ""
                    current_pages = []
                    current_warnings = []

                # Recursively split the oversized paragraph
                sub_parts = self._recursive_split(para_text, max_body_tokens)
                for part in sub_parts:
                    full_part_text = f"{heading_prefix}{part}".strip()
                    tokens = self.tokenizer.count_tokens(full_part_text)
                    chunk_id = f"{document_id}_txt_{seq_num:05d}"
                    cit = f"[{document_id} Page {seg.page_number}]"

                    chunks.append(
                        ChunkRecord(
                            chunk_id=chunk_id,
                            document_id=document_id,
                            category=category,
                            source_file=source_file,
                            content_type="text",
                            page_start=seg.page_number,
                            page_end=seg.page_number,
                            citation_label=cit,
                            section_path=section_path,
                            section_heading=section_heading,
                            text=full_part_text,
                            token_count=tokens,
                            char_count=len(full_part_text),
                            has_encoding_warning=bool(seg.encoding_warnings),
                            encoding_warnings=list(set(seg.encoding_warnings)),
                            duplicate_of=duplicate_of,
                        )
                    )
                    seq_num += 1
                    prev_chunk_overlap = self._compute_overlap_text(part)

                i += 1
                continue

            # Case B: Paragraph fits into accumulator
            candidate = f"{accumulated_text}\n\n{para_text}".strip() if accumulated_text else para_text
            candidate_full = f"{heading_prefix}{prev_chunk_overlap}{candidate}".strip()
            candidate_tokens = self.tokenizer.count_tokens(candidate_full)

            if candidate_tokens <= self.config.max_chunk_tokens:
                accumulated_text = candidate
                current_pages.append(seg.page_number)
                current_warnings.extend(seg.encoding_warnings)
                i += 1
            else:
                # Chunk is full, emit current accumulator
                if accumulated_text:
                    full_chunk_text = f"{heading_prefix}{prev_chunk_overlap}{accumulated_text}".strip()
                    tokens = self.tokenizer.count_tokens(full_chunk_text)
                    if tokens > self.config.max_chunk_tokens and prev_chunk_overlap:
                        full_chunk_text = f"{heading_prefix}{accumulated_text}".strip()
                        tokens = self.tokenizer.count_tokens(full_chunk_text)
                    chunk_id = f"{document_id}_txt_{seq_num:05d}"
                    p_min = min(current_pages) if current_pages else seg.page_number
                    p_max = max(current_pages) if current_pages else seg.page_number
                    cit = f"[{document_id} Page {p_min}]" if p_min == p_max else f"[{document_id} Pages {p_min}-{p_max}]"

                    chunks.append(
                        ChunkRecord(
                            chunk_id=chunk_id,
                            document_id=document_id,
                            category=category,
                            source_file=source_file,
                            content_type="text",
                            page_start=p_min,
                            page_end=p_max,
                            citation_label=cit,
                            section_path=section_path,
                            section_heading=section_heading,
                            text=full_chunk_text,
                            token_count=tokens,
                            char_count=len(full_chunk_text),
                            has_encoding_warning=bool(current_warnings),
                            encoding_warnings=list(set(current_warnings)),
                            duplicate_of=duplicate_of,
                        )
                    )
                    seq_num += 1
                    prev_chunk_overlap = self._compute_overlap_text(accumulated_text)

                accumulated_text = para_text
                current_pages = [seg.page_number]
                current_warnings = list(seg.encoding_warnings)
                i += 1

        # Emit trailing remaining accumulated text
        if accumulated_text:
            full_chunk_text = f"{heading_prefix}{prev_chunk_overlap}{accumulated_text}".strip()
            tokens = self.tokenizer.count_tokens(full_chunk_text)
            if tokens > self.config.max_chunk_tokens and prev_chunk_overlap:
                full_chunk_text = f"{heading_prefix}{accumulated_text}".strip()
                tokens = self.tokenizer.count_tokens(full_chunk_text)
            chunk_id = f"{document_id}_txt_{seq_num:05d}"
            p_min = min(current_pages) if current_pages else segments[-1].page_number
            p_max = max(current_pages) if current_pages else segments[-1].page_number
            cit = f"[{document_id} Page {p_min}]" if p_min == p_max else f"[{document_id} Pages {p_min}-{p_max}]"

            chunks.append(
                ChunkRecord(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    category=category,
                    source_file=source_file,
                    content_type="text",
                    page_start=p_min,
                    page_end=p_max,
                    citation_label=cit,
                    section_path=section_path,
                    section_heading=section_heading,
                    text=full_chunk_text,
                    token_count=tokens,
                    char_count=len(full_chunk_text),
                    has_encoding_warning=bool(current_warnings),
                    encoding_warnings=list(set(current_warnings)),
                    duplicate_of=duplicate_of,
                )
            )

        return chunks

    def _compute_overlap_text(self, text: str) -> str:
        """Extract a short sliding-window overlap (e.g. 50 tokens) from the tail of text."""
        if not text or self.config.chunk_overlap_tokens <= 0:
            return ""

        # Split into sentences from tail
        sentences = self.SENTENCE_SPLIT_REGEX.split(text)
        overlap_sentences: List[str] = []
        overlap_tokens = 0

        for s in reversed(sentences):
            s_clean = s.strip()
            if not s_clean:
                continue
            toks = self.tokenizer.count_tokens(s_clean)
            if overlap_tokens + toks <= self.config.chunk_overlap_tokens:
                overlap_sentences.insert(0, s_clean)
                overlap_tokens += toks
            else:
                break

        if overlap_sentences:
            return " ".join(overlap_sentences) + "\n\n"
        return ""

    def _recursive_split(self, text: str, max_tokens: int) -> List[str]:
        """Recursively divide oversized text into sentences, clauses, then tokens."""
        # Step 1: Sentence splitting
        sentences = self.SENTENCE_SPLIT_REGEX.split(text)
        parts: List[str] = []
        current = ""

        for s in sentences:
            s_clean = s.strip()
            if not s_clean:
                continue

            # If an individual sentence itself exceeds max_tokens, split by clauses
            if self.tokenizer.count_tokens(s_clean) > max_tokens:
                if current:
                    parts.append(current.strip())
                    current = ""
                clause_parts = self._split_by_clauses(s_clean, max_tokens)
                parts.extend(clause_parts)
                continue

            candidate = f"{current} {s_clean}".strip() if current else s_clean
            if self.tokenizer.count_tokens(candidate) <= max_tokens:
                current = candidate
            else:
                if current:
                    parts.append(current.strip())
                current = s_clean

        if current:
            parts.append(current.strip())

        return parts

    def _split_by_clauses(self, text: str, max_tokens: int) -> List[str]:
        """Split a long sentence on semicolons, colons, or safe word boundaries."""
        clauses = re.split(r"(?<=[;:])\s+", text)
        parts: List[str] = []
        current = ""

        for c in clauses:
            c_clean = c.strip()
            if not c_clean:
                continue

            if self.tokenizer.count_tokens(c_clean) > max_tokens:
                if current:
                    parts.append(current.strip())
                    current = ""
                # Word-level fallback
                word_parts = self._split_by_words(c_clean, max_tokens)
                parts.extend(word_parts)
                continue

            candidate = f"{current} {c_clean}".strip() if current else c_clean
            if self.tokenizer.count_tokens(candidate) <= max_tokens:
                current = candidate
            else:
                if current:
                    parts.append(current.strip())
                current = c_clean

        if current:
            parts.append(current.strip())
        return parts

    def _split_by_words(self, text: str, max_tokens: int) -> List[str]:
        """Final fallback: split safely along whitespace word boundaries."""
        words = text.split()
        parts: List[str] = []
        current_words: List[str] = []

        for w in words:
            candidate = " ".join(current_words + [w])
            if self.tokenizer.count_tokens(candidate) <= max_tokens:
                current_words.append(w)
            else:
                if current_words:
                    parts.append(" ".join(current_words))
                current_words = [w]

        if current_words:
            parts.append(" ".join(current_words))
        return parts
