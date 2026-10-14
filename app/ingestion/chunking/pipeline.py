"""Document chunking pipeline orchestrator."""

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from app.ingestion.chunking.config import ChunkingConfig
from app.ingestion.chunking.figure_chunker import FigureChunker
from app.ingestion.chunking.models import ChunkRecord
from app.ingestion.chunking.table_chunker import TableChunker
from app.ingestion.chunking.text_chunker import StructureAwareTextChunker
from app.ingestion.chunking.tokenizer import TokenizerAdapter, get_tokenizer_adapter


@dataclass
class DocumentChunkResult:
    """Outcome and audit metrics from chunking a single document."""

    document_id: str
    category: str
    source_file: str
    pages_processed: int
    chunks: List[ChunkRecord] = field(default_factory=list)
    chunks_text: int = 0
    chunks_table: int = 0
    chunks_figure: int = 0
    encoding_warnings_count: int = 0
    missing_assets_count: int = 0
    oversized_chunks_count: int = 0
    validation_errors: List[str] = field(default_factory=list)

    @property
    def total_chunks(self) -> int:
        return len(self.chunks)


class DocumentChunkingPipeline:
    """Orchestrates structure-aware, table-aware, and figure-aware chunking for a document."""

    # Known duplicate document registry across the corpus
    KNOWN_DUPLICATE_MAP = {
        "NIST.SP.800-61r3": ["NIST_SP_800-61"],
        "NIST_SP_800-61": ["NIST.SP.800-61r3"],
    }

    def __init__(self, config: ChunkingConfig, tokenizer: Optional[TokenizerAdapter] = None):
        self.config = config
        self.tokenizer = tokenizer or get_tokenizer_adapter(config)
        self.text_chunker = StructureAwareTextChunker(config=config, tokenizer=self.tokenizer)
        self.table_chunker = TableChunker(config=config, tokenizer=self.tokenizer)
        self.figure_chunker = FigureChunker(config=config, tokenizer=self.tokenizer)

    def process_document(self, doc_dir: Path) -> DocumentChunkResult:
        """Process one cleaned publication directory containing structured JSON and assets."""
        if not doc_dir.is_dir():
            raise FileNotFoundError(f"Document directory does not exist: {doc_dir}")

        doc_id = doc_dir.name
        json_path = doc_dir / f"{doc_id}_structured.json"
        if not json_path.exists():
            raise FileNotFoundError(f"Missing structured JSON file: {json_path}")

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Standardize category metadata for root-level documents to 'root'
        parent_dir_cat = doc_dir.parent.name
        raw_category = data.get("category", parent_dir_cat)
        if raw_category in ("documents", "root") or parent_dir_cat == "root":
            category = "root"
        else:
            category = raw_category

        source_file = data.get("file_path", f"documents/{category}/{doc_id}.pdf")
        pages = data.get("pages", [])
        page_count = len(pages)

        # Detect duplicate relationships
        duplicate_of = self.KNOWN_DUPLICATE_MAP.get(doc_id, [])

        # Step 1: Collect table markdown blocks to prevent duplicate narrative text indexing
        table_markdown_set: Set[str] = set()
        for page in pages:
            for table in page.get("tables", []):
                md = table.get("markdown", "")
                if md and md.strip():
                    table_markdown_set.add(md.strip())

        # Step 2: Chunk normal text
        text_chunks = self.text_chunker.chunk_document_text(
            document_id=doc_id,
            category=category,
            source_file=source_file,
            pages=pages,
            table_markdown_set=table_markdown_set,
            duplicate_of=duplicate_of,
        )

        # Step 3: Chunk tables
        table_chunks = self.table_chunker.chunk_document_tables(
            document_id=doc_id,
            category=category,
            source_file=source_file,
            pages=pages,
            duplicate_of=duplicate_of,
        )

        # Step 4: Chunk figures
        figure_chunks, asset_errors = self.figure_chunker.chunk_document_figures(
            document_id=doc_id,
            category=category,
            source_file=source_file,
            pages=pages,
            doc_dir=doc_dir,
            duplicate_of=duplicate_of,
        )

        # Combine all chunks
        all_chunks: List[ChunkRecord] = text_chunks + table_chunks + figure_chunks

        # Validation & Metrics Audit
        validation_errors: List[str] = list(asset_errors)
        encoding_warnings_count = 0
        oversized_chunks_count = 0

        for chunk in all_chunks:
            if not chunk.text or not chunk.text.strip():
                validation_errors.append(f"Empty text in chunk: {chunk.chunk_id}")

            if chunk.token_count <= 0:
                validation_errors.append(f"Zero token count in chunk: {chunk.chunk_id}")

            if chunk.page_start > chunk.page_end:
                validation_errors.append(
                    f"Invalid page range in {chunk.chunk_id}: {chunk.page_start} > {chunk.page_end}"
                )

            if chunk.has_encoding_warning:
                encoding_warnings_count += 1

            # Ordinary text chunks must not exceed max_chunk_tokens
            if chunk.content_type == "text" and chunk.token_count > self.config.max_chunk_tokens:
                oversized_chunks_count += 1

        return DocumentChunkResult(
            document_id=doc_id,
            category=category,
            source_file=source_file,
            pages_processed=page_count,
            chunks=all_chunks,
            chunks_text=len(text_chunks),
            chunks_table=len(table_chunks),
            chunks_figure=len(figure_chunks),
            encoding_warnings_count=encoding_warnings_count,
            missing_assets_count=len(asset_errors),
            oversized_chunks_count=oversized_chunks_count,
            validation_errors=validation_errors,
        )
