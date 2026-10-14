"""Configuration for structure-aware, model-independent document chunking."""

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict


@dataclass
class ChunkingConfig:
    """Settings controlling structure-aware document chunking operations."""

    # Tokenizer & Model Independence
    tokenizer_backend: str = "hf_tokenizer"  # "hf_tokenizer" | "tiktoken" | "char_estimate"
    model_name_or_path: str = "BAAI/bge-small-en-v1.5"
    max_model_context: int = 512

    # Normal Text Budgeting (Tokens)
    target_chunk_tokens: int = 400  # Nominal target chunk size
    max_chunk_tokens: int = 500  # Strict ceiling (bounded below 512 context limit)
    chunk_overlap_tokens: int = 50  # Overlap between contiguous chunks within same section
    min_chunk_tokens: int = 80  # Lower threshold to avoid micro-chunks

    # Table Sizing & Splitting
    max_table_tokens: int = 500  # Budget for atomic table chunks
    table_split_by_rows: bool = True  # Split oversized tables by row blocks
    repeat_table_headers: bool = True  # Repeat title and headers in every row chunk
    enable_multipage_table_linking: bool = True  # Detect and link continuation tables
    continuation_header_similarity_threshold: float = 0.90  # Required match ratio

    # Figure Records
    enable_figure_records: bool = True  # Emit dedicated searchable figure records
    figure_context_sentences: int = 2  # Sentences of surrounding narrative context
    figure_vlm_status: str = "EXTRACTED_VLM_PENDING"

    # Uncertainty & Security Content
    preserve_ambiguous_chars: bool = True  # Retain \ufffd verbatim without guessing
    propagate_warnings: bool = True  # Expose encoding warnings in chunk metadata

    # Directories & Guardrails
    input_dir: Path = field(default_factory=lambda: Path("data/cleaned_pilot"))
    output_dir: Path = field(default_factory=lambda: Path("data/chunks_pilot"))
    min_free_disk_mb: float = 500.0  # Mandatory free space safety reserve
    fail_fast: bool = False  # Halt immediately on document error if True
    dry_run: bool = False
    overwrite_existing: bool = False  # Overwrite existing files in output directory if True

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to JSON-serializable dictionary."""
        d = asdict(self)
        d["input_dir"] = str(self.input_dir)
        d["output_dir"] = str(self.output_dir)
        return d
