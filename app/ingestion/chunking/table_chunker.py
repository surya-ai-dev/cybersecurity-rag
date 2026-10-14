"""Table-aware chunker preserving headers, rows, cells, and multi-page continuations."""

import re
from typing import Any, Dict, List, Optional, Tuple

from app.ingestion.chunking.config import ChunkingConfig
from app.ingestion.chunking.models import ChunkRecord, TableChunkMetadata
from app.ingestion.chunking.tokenizer import TokenizerAdapter


class TableChunker:
    """Processes structured tables into atomic units or row-partitioned chunks with repeated headers."""

    def __init__(self, config: ChunkingConfig, tokenizer: TokenizerAdapter):
        self.config = config
        self.tokenizer = tokenizer

    def chunk_document_tables(
        self,
        document_id: str,
        category: str,
        source_file: str,
        pages: List[Dict[str, Any]],
        duplicate_of: Optional[List[str]] = None,
    ) -> List[ChunkRecord]:
        """Process all structured tables across pages with multi-page continuation linking."""
        if duplicate_of is None:
            duplicate_of = []

        table_chunks: List[ChunkRecord] = []
        table_seq = 1

        # State tracking for multi-page continuation linking
        prev_table_state: Optional[Dict[str, Any]] = None

        for page in pages:
            page_num = page.get("page_number", 1)
            citation_label = page.get("citation_label", f"[{document_id} Page {page_num}]")
            page_tables = page.get("tables", [])
            raw_warnings = page.get("cleaning_metadata", {}).get("encoding_warnings", [])
            page_warnings: List[str] = []
            for w in raw_warnings:
                if isinstance(w, dict):
                    desc = w.get("desc") or w.get("warning") or w.get("message")
                    w_type = w.get("type", "ENCODING_WARNING")
                    page_warnings.append(f"{w_type}: {desc}" if desc else str(w))
                else:
                    page_warnings.append(str(w))

            for table in page_tables:
                table_id = table.get("table_id", f"table_p{page_num}_{table_seq}")
                headers = [str(h).strip() for h in table.get("headers", [])]
                rows = [[str(cell).strip() for cell in row] for row in table.get("rows", [])]
                raw_caption = (table.get("caption", "") or "").strip()
                bbox = table.get("bbox")

                # Multi-page continuation detection
                is_continuation = False
                continuation_of_table_id = None
                parent_table_id = table_id
                effective_caption = raw_caption

                if self.config.enable_multipage_table_linking and prev_table_state:
                    if self._is_continuation(
                        curr_page=page_num,
                        curr_headers=headers,
                        curr_caption=raw_caption,
                        curr_bbox=bbox,
                        prev_state=prev_table_state,
                    ):
                        is_continuation = True
                        continuation_of_table_id = prev_table_state["table_id"]
                        parent_table_id = prev_table_state["parent_table_id"]
                        if not effective_caption or "continued" in effective_caption.lower():
                            effective_caption = prev_table_state["caption"]

                if not effective_caption:
                    effective_caption = f"Table on Page {page_num}"

                # Update continuation tracking state
                prev_table_state = {
                    "table_id": table_id,
                    "parent_table_id": parent_table_id,
                    "page_number": page_num,
                    "headers": headers,
                    "caption": effective_caption,
                    "bbox": bbox,
                }

                # Chunk this table (atomic if fits, row-split if oversized)
                chunks = self._chunk_single_table(
                    document_id=document_id,
                    category=category,
                    source_file=source_file,
                    page_number=page_num,
                    citation_label=citation_label,
                    table_id=table_id,
                    parent_table_id=parent_table_id,
                    is_continuation=is_continuation,
                    continuation_of_table_id=continuation_of_table_id,
                    caption=effective_caption,
                    headers=headers,
                    rows=rows,
                    bbox=bbox,
                    table_seq=table_seq,
                    page_warnings=page_warnings,
                    duplicate_of=duplicate_of,
                )

                table_chunks.extend(chunks)
                table_seq += 1

        return table_chunks

    def _is_continuation(
        self,
        curr_page: int,
        curr_headers: List[str],
        curr_caption: str,
        curr_bbox: Optional[Dict[str, float]],
        prev_state: Dict[str, Any],
    ) -> bool:
        """Evaluate evidence to determine if current table continues the previous table."""
        # Condition 1: Must be consecutive pages
        if curr_page != prev_state["page_number"] + 1:
            return False

        # Condition 2: Column count must match and be > 0
        prev_headers = prev_state["headers"]
        if not curr_headers or len(curr_headers) != len(prev_headers):
            return False

        # Condition 3: Header similarity check
        normalized_curr = [h.lower().replace(" ", "").replace("_", "") for h in curr_headers]
        normalized_prev = [h.lower().replace(" ", "").replace("_", "") for h in prev_headers]
        matches = sum(1 for a, b in zip(normalized_curr, normalized_prev) if a == b)
        similarity = matches / len(curr_headers)

        if similarity < self.config.continuation_header_similarity_threshold:
            return False

        # Condition 4: Top of page heuristic or explicit continuation marker
        if "continued" in curr_caption.lower() or "(cont" in curr_caption.lower():
            return True

        if curr_bbox and curr_bbox.get("top", 999.0) <= 150.0:
            return True

        # If similarity is 1.0 (exact identical headers on consecutive pages), link with high confidence
        if similarity == 1.0:
            return True

        return False

    def _chunk_single_table(
        self,
        document_id: str,
        category: str,
        source_file: str,
        page_number: int,
        citation_label: str,
        table_id: str,
        parent_table_id: str,
        is_continuation: bool,
        continuation_of_table_id: Optional[str],
        caption: str,
        headers: List[str],
        rows: List[List[str]],
        bbox: Optional[Dict[str, float]],
        table_seq: int,
        page_warnings: List[str],
        duplicate_of: List[str],
    ) -> List[ChunkRecord]:
        """Partition a table into atomic unit or row-split chunks."""
        # Format full table markdown
        full_md = self._render_markdown_table(headers, rows)
        title_heading = f"### Table: {caption}\nSource: {citation_label}\n\n"
        full_text = f"{title_heading}{full_md}".strip()
        full_tokens = self.tokenizer.count_tokens(full_text)

        # Uncertainty detection
        has_warning = ("\ufffd" in full_text) or bool(page_warnings)
        warnings_list = list(page_warnings)
        if "\ufffd" in full_text:
            warnings_list.append(f"Contains \\ufffd in table on page {page_number}")

        # Check if table fits atomically
        if full_tokens <= self.config.max_table_tokens or not self.config.table_split_by_rows:
            chunk_id = f"{document_id}_tbl_{table_seq:05d}_p01"
            table_meta = TableChunkMetadata(
                parent_table_id=parent_table_id,
                part_index=1,
                total_parts=1,
                caption=caption,
                headers=headers,
                row_start=0,
                row_end=len(rows),
                rows_count=len(rows),
                cols_count=len(headers),
                is_continuation=is_continuation,
                continuation_of_table_id=continuation_of_table_id,
            )
            return [
                ChunkRecord(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    category=category,
                    source_file=source_file,
                    content_type="table",
                    page_start=page_number,
                    page_end=page_number,
                    citation_label=citation_label,
                    section_path=[caption],
                    section_heading=caption,
                    text=full_text,
                    token_count=full_tokens,
                    char_count=len(full_text),
                    table_metadata=table_meta.to_dict(),
                    has_encoding_warning=has_warning,
                    encoding_warnings=list(set(warnings_list)),
                    bbox_coordinates=[bbox] if bbox else [],
                    duplicate_of=duplicate_of,
                )
            ]

        # Oversized Table: Partition by rows
        row_batches: List[Tuple[int, int, List[List[str]]]] = []
        current_batch: List[List[str]] = []
        batch_start_idx = 0

        header_prefix = self._render_header_block(headers)

        for r_idx, row in enumerate(rows):
            test_batch = current_batch + [row]
            test_md = self._render_rows_block(headers, test_batch)
            test_text = f"### Table: {caption} (Part 99 of 99)\nSource: {citation_label}\n\n{test_md}"
            test_tokens = self.tokenizer.count_tokens(test_text)

            if test_tokens <= self.config.max_table_tokens:
                current_batch.append(row)
            else:
                if current_batch:
                    row_batches.append((batch_start_idx, r_idx, current_batch))
                    current_batch = []
                    batch_start_idx = r_idx

                # Check if this single row itself exceeds max_table_tokens
                test_single_md = self._render_rows_block(headers, [row])
                test_single_text = f"### Table: {caption} (Part 99 of 99)\nSource: {citation_label}\n\n{test_single_md}"
                if self.tokenizer.count_tokens(test_single_text) > self.config.max_table_tokens:
                    # Controlled fallback: partition monolithic row into sub-rows repeating context
                    sub_rows = self._split_oversized_row(headers, row, caption, citation_label)
                    for sub_row in sub_rows:
                        row_batches.append((r_idx, r_idx + 1, [sub_row]))
                    current_batch = []
                    batch_start_idx = r_idx + 1
                else:
                    current_batch = [row]
                    batch_start_idx = r_idx

        if current_batch:
            row_batches.append((batch_start_idx, len(rows), current_batch))

        total_parts = len(row_batches)
        chunks: List[ChunkRecord] = []

        for p_idx, (r_start, r_end, batch_rows) in enumerate(row_batches, 1):
            chunk_id = f"{document_id}_tbl_{table_seq:05d}_p{p_idx:02d}"
            part_caption = f"{caption} (Part {p_idx} of {total_parts})"
            part_md = self._render_rows_block(headers, batch_rows)
            part_text = f"### Table: {part_caption}\nSource: {citation_label}\n\n{part_md}".strip()
            part_tokens = self.tokenizer.count_tokens(part_text)

            part_warning = ("\ufffd" in part_text) or bool(page_warnings)
            part_warnings_list = list(page_warnings)
            if "\ufffd" in part_text:
                part_warnings_list.append(f"Contains \\ufffd in table on page {page_number}")

            table_meta = TableChunkMetadata(
                parent_table_id=parent_table_id,
                part_index=p_idx,
                total_parts=total_parts,
                caption=caption,
                headers=headers,
                row_start=r_start,
                row_end=r_end,
                rows_count=len(batch_rows),
                cols_count=len(headers),
                is_continuation=is_continuation,
                continuation_of_table_id=continuation_of_table_id,
            )

            chunks.append(
                ChunkRecord(
                    chunk_id=chunk_id,
                    document_id=document_id,
                    category=category,
                    source_file=source_file,
                    content_type="table",
                    page_start=page_number,
                    page_end=page_number,
                    citation_label=citation_label,
                    section_path=[caption],
                    section_heading=part_caption,
                    text=part_text,
                    token_count=part_tokens,
                    char_count=len(part_text),
                    table_metadata=table_meta.to_dict(),
                    has_encoding_warning=part_warning,
                    encoding_warnings=list(set(part_warnings_list)),
                    bbox_coordinates=[bbox] if bbox else [],
                    duplicate_of=duplicate_of,
                )
            )

        return chunks

    def _render_markdown_table(self, headers: List[str], rows: List[List[str]]) -> str:
        """Render complete Markdown pipe table."""
        if not headers and not rows:
            return ""
        return self._render_rows_block(headers, rows)

    def _render_header_block(self, headers: List[str]) -> str:
        """Render Markdown table header and delimiter rows."""
        if not headers:
            return ""
        header_line = "| " + " | ".join(h.replace("|", "\\|") for h in headers) + " |"
        sep_line = "| " + " | ".join(":---" for _ in headers) + " |"
        return f"{header_line}\n{sep_line}"

    def _render_rows_block(self, headers: List[str], rows: List[List[str]]) -> str:
        """Render Markdown table with repeated headers and specified subset of rows."""
        num_cols = len(headers) if headers else (max(len(r) for r in rows) if rows else 0)
        lines: List[str] = []

        if headers:
            lines.append("| " + " | ".join(h.replace("|", "\\|") for h in headers) + " |")
            lines.append("| " + " | ".join(":---" for _ in headers) + " |")
        elif rows:
            synthetic_headers = [f"Col_{i+1}" for i in range(num_cols)]
            lines.append("| " + " | ".join(synthetic_headers) + " |")
            lines.append("| " + " | ".join(":---" for _ in synthetic_headers) + " |")

        for row in rows:
            # Ensure row length matches num_cols
            padded_row = list(row) + [""] * (num_cols - len(row))
            row_cells = [c.replace("|", "\\|").replace("\n", " ").strip() for c in padded_row[:num_cols]]
            lines.append("| " + " | ".join(row_cells) + " |")

        return "\n".join(lines)

    def _split_cell_into_units(self, text: str) -> List[str]:
        """Split a large cell text into semantic units (lines, examples, bullets, reference groups)."""
        # 1. Newline / line boundaries
        if "\n" in text:
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            if len(lines) > 1:
                sub_units: List[str] = []
                for line in lines:
                    if self.tokenizer.count_tokens(line) > 250:
                        sub_units.extend(self._split_cell_into_units(line))
                    else:
                        sub_units.append(line)
                return sub_units

        # 2. Numbered examples: 'Example 1:', 'Example1:', etc.
        ex = re.split(r"(?=(?:Example\s*\d+:))", text, flags=re.IGNORECASE)
        items = [p.strip() for p in ex if p.strip()]
        if len(items) > 1:
            return items

        # 3. Bullets: , •, \u2022
        bullets = re.split(r"(?=[•\u2022])", text)
        items = [p.strip() for p in bullets if p.strip()]
        if len(items) > 1:
            return items

        # 4. Framework prefixes: 'BSAFSS:', 'BSIMM:', 'SP80053:', etc.
        refs = re.split(r"(?=(?:[A-Z0-9\[\]\-]+:))", text)
        items = [p.strip() for p in refs if p.strip()]
        if len(items) > 1:
            return items

        # 5. Semicolon-delimited lists
        if ";" in text:
            parts = text.split(";")
            items = [p.strip() + ";" for p in parts[:-1] if p.strip()]
            if parts[-1].strip():
                items.append(parts[-1].strip())
            if len(items) > 1:
                return items

        # 6. Sentence / period boundaries
        sentences = re.split(r"(?<=\.\s)", text)
        items = [s.strip() for s in sentences if s.strip()]
        if len(items) > 1:
            return items

        # 7. Dot leaders / dashes
        if re.search(r"[.\-_]{3,}", text):
            parts = re.split(r"([.\-_]{3,}\s*)", text)
            items = []
            curr = ""
            for p in parts:
                if not p:
                    continue
                curr += p
                if re.match(r"^[.\-_]{3,}\s*$", p):
                    items.append(curr.strip())
                    curr = ""
            if curr.strip():
                items.append(curr.strip())
            if len(items) > 1:
                return items

        # 8. Fallback: group by words
        words = text.split()
        if len(words) > 25:
            chunk_size = 20
            return [" ".join(words[i : i + chunk_size]) for i in range(0, len(words), chunk_size)]

        # 9. Fallback: character slicing if monolithic single string > 250 chars
        if len(text) > 250:
            return [text[i : i + 200] for i in range(0, len(text), 200)]

        return [text]

    def _split_oversized_row(
        self,
        headers: List[str],
        row: List[str],
        caption: str,
        citation_label: str,
    ) -> List[List[str]]:
        """Iteratively partition an oversized table row into sub-rows fitting max_table_tokens.
        Context columns (practices, tasks, versions) are repeated across all sub-rows while
        large content columns (examples, references, updates) are distributed semantically."""
        cell_tokens = [self.tokenizer.count_tokens(c) for c in row]
        max_tokens = min(self.config.max_table_tokens, 480)

        # Identify large columns (tokens > 100 or highest token column)
        large_indices = [i for i, t in enumerate(cell_tokens) if t > 100]
        if not large_indices:
            large_indices = [cell_tokens.index(max(cell_tokens))]

        # Gather units for each large column
        col_units = {i: self._split_cell_into_units(row[i]) for i in large_indices}

        header_block = f"| {' | '.join(headers)} |\n| {' | '.join([':---'] * len(headers))} |"

        # Incrementally find the minimum number of parts so all sub-rows fit under max_table_tokens
        max_units_count = max(len(u) for u in col_units.values())
        max_search_parts = max(max_units_count + 1, 30)

        candidate_sub_rows = [row]
        for num_parts in range(2, max_search_parts + 1):
            candidate_sub_rows = []
            for p in range(num_parts):
                sub_row = []
                for col_idx in range(len(row)):
                    if col_idx in large_indices and len(col_units[col_idx]) > 1:
                        units = col_units[col_idx]
                        k, m = divmod(len(units), num_parts)
                        start = p * k + min(p, m)
                        end = start + k + (1 if p < m else 0)
                        sub_row.append(" ".join(units[start:end]))
                    else:
                        # Replicate context column across all parts
                        sub_row.append(row[col_idx])
                candidate_sub_rows.append(sub_row)

            # Validate rendered token counts for each sub-row
            all_fit = True
            for s_idx, s_row in enumerate(candidate_sub_rows, 1):
                row_line = f"| {' | '.join(s_row)} |"
                rendered = f"### Table: {caption} (Part {s_idx} of {num_parts})\nSource: {citation_label}\n\n{header_block}\n{row_line}"
                toks = self.tokenizer.count_tokens(rendered)
                if toks > max_tokens:
                    all_fit = False
                    break

            if all_fit:
                return candidate_sub_rows

        return candidate_sub_rows
