"""Figure-aware chunker producing searchable metadata records linked to on-disk image assets."""

from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple

from app.ingestion.chunking.config import ChunkingConfig
from app.ingestion.chunking.models import ChunkRecord, FigureChunkMetadata
from app.ingestion.chunking.tokenizer import TokenizerAdapter


class FigureChunker:
    """Creates dedicated, searchable figure records linked to validated image assets."""

    # Regex patterns to detect narrative captions embedded in Markdown text
    FIGURE_CAPTION_PATTERNS = [
        re.compile(r"(\*\*(?:Fig\.|Figure)\s*\d+[\.:][^\*\n]+\*\*)", re.IGNORECASE),
        re.compile(r"(?:^|\n)((?:Fig\.|Figure)\s*\d+[\.:][^\n]+)", re.IGNORECASE),
        re.compile(r"(\*\*(?:Diagram|Chart)\s*\d+[\.:][^\*\n]+\*\*)", re.IGNORECASE),
    ]

    def __init__(self, config: ChunkingConfig, tokenizer: TokenizerAdapter):
        self.config = config
        self.tokenizer = tokenizer

    def chunk_document_figures(
        self,
        document_id: str,
        category: str,
        source_file: str,
        pages: List[Dict[str, Any]],
        doc_dir: Path,
        duplicate_of: Optional[List[str]] = None,
    ) -> Tuple[List[ChunkRecord], List[str]]:
        """Create searchable figure ChunkRecords and collect any asset validation errors."""
        if duplicate_of is None:
            duplicate_of = []

        figure_chunks: List[ChunkRecord] = []
        validation_errors: List[str] = []
        fig_seq = 1

        for page in pages:
            page_num = page.get("page_number", 1)
            citation_label = page.get("citation_label", f"[{document_id} Page {page_num}]")
            page_figures = page.get("figures", [])
            page_text = page.get("cleaned_text", "") or ""
            raw_warnings = page.get("cleaning_metadata", {}).get("encoding_warnings", [])
            page_warnings: List[str] = []
            for w in raw_warnings:
                if isinstance(w, dict):
                    desc = w.get("desc") or w.get("warning") or w.get("message")
                    w_type = w.get("type", "ENCODING_WARNING")
                    page_warnings.append(f"{w_type}: {desc}" if desc else str(w))
                else:
                    page_warnings.append(str(w))

            for fig in page_figures:
                fig_id = fig.get("figure_id", f"fig_p{page_num}_{fig_seq}")
                image_rel_path = fig.get("image_path", "")
                raw_caption = (fig.get("caption", "") or "").strip()
                bbox = fig.get("bbox")
                width = int(fig.get("width", 0))
                height = int(fig.get("height", 0))

                # Step 1: Asset existence validation
                asset_full_path = doc_dir / image_rel_path if image_rel_path else None
                asset_exists = asset_full_path.exists() if (asset_full_path and image_rel_path) else False

                if not asset_exists:
                    validation_errors.append(
                        f"Missing figure asset for {document_id} ({fig_id}): path '{image_rel_path}' not found on disk."
                    )

                # Step 2: Narrative caption linkage
                caption, caption_linked = self._resolve_caption(raw_caption, page_text, page_num)

                # Step 3: Extract relevant surrounding context (1-2 sentences)
                surrounding_context = self._extract_surrounding_context(caption, page_text)

                # Step 4: Build searchable retrieval text
                context_line = f"Context: {surrounding_context}\n" if surrounding_context else ""
                text = (
                    f"### Figure: {caption}\n"
                    f"Source: {citation_label}\n"
                    f"Asset: {image_rel_path}\n"
                    f"{context_line}"
                ).strip()

                tokens = self.tokenizer.count_tokens(text)

                # Step 5: Warnings & Uncertainty
                has_warning = ("\ufffd" in text) or bool(page_warnings) or (not asset_exists)
                warnings_list = list(page_warnings)
                if "\ufffd" in text:
                    warnings_list.append(f"Contains \\ufffd in figure metadata on page {page_num}")
                if not asset_exists:
                    warnings_list.append(f"Figure asset '{image_rel_path}' is missing on disk")

                chunk_id = f"{document_id}_fig_{fig_seq:05d}"
                fig_meta = FigureChunkMetadata(
                    figure_id=fig_id,
                    asset_path=image_rel_path,
                    caption=caption,
                    status=self.config.figure_vlm_status,
                    dimensions={"width": width, "height": height},
                    surrounding_context=surrounding_context,
                    vlm_description=None,
                    caption_linked=caption_linked,
                )

                figure_chunks.append(
                    ChunkRecord(
                        chunk_id=chunk_id,
                        document_id=document_id,
                        category=category,
                        source_file=source_file,
                        content_type="figure",
                        page_start=page_num,
                        page_end=page_num,
                        citation_label=citation_label,
                        section_path=[caption],
                        section_heading=caption,
                        text=text,
                        token_count=tokens,
                        char_count=len(text),
                        figure_metadata=fig_meta.to_dict(),
                        has_encoding_warning=has_warning,
                        encoding_warnings=list(set(warnings_list)),
                        bbox_coordinates=[bbox] if bbox else [],
                        duplicate_of=duplicate_of,
                    )
                )
                fig_seq += 1

        return figure_chunks, validation_errors

    def _resolve_caption(
        self, raw_caption: str, page_text: str, page_num: int
    ) -> Tuple[str, bool]:
        """Link narrative caption if metadata contains technical fallback or is blank."""
        is_fallback = (
            not raw_caption
            or raw_caption.startswith("Embedded image (xref")
            or "xref" in raw_caption.lower()
        )

        if is_fallback and page_text:
            for pattern in self.FIGURE_CAPTION_PATTERNS:
                m = pattern.search(page_text)
                if m:
                    clean_caption = m.group(1).replace("**", "").strip()
                    return clean_caption, True

        if raw_caption:
            return raw_caption.replace("**", "").strip(), False

        return f"Figure on Page {page_num}", False

    def _extract_surrounding_context(self, caption: str, page_text: str) -> str:
        """Extract 1-2 focused sentences referencing the figure from narrative text."""
        if not page_text:
            return ""

        # Extract number if present in caption (e.g. "Fig. 7" -> "7")
        num_match = re.search(r"(?:Fig\.|Figure)\s*(\d+)", caption, re.IGNORECASE)
        fig_num = num_match.group(1) if num_match else None

        sentences = re.split(r"(?<=[.!?])\s+", page_text)
        relevant_sentences: List[str] = []

        for s in sentences:
            s_clean = s.strip()
            if not s_clean:
                continue

            # Skip the caption line itself
            if caption in s_clean:
                continue

            # Check if sentence references figure number or figure
            is_relevant = False
            if fig_num and (f"Figure {fig_num}" in s_clean or f"Fig. {fig_num}" in s_clean):
                is_relevant = True
            elif "figure" in s_clean.lower() or "diagram" in s_clean.lower() or "illustrates" in s_clean.lower():
                is_relevant = True

            if is_relevant:
                relevant_sentences.append(s_clean)
                if len(relevant_sentences) >= self.config.figure_context_sentences:
                    break

        if relevant_sentences:
            return " ".join(relevant_sentences)

        return ""
