"""Centralized configuration management for the Cybersecurity RAG system."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load environment variables from .env file if present
load_dotenv(override=True)


@dataclass
class Settings:
    """Application-wide settings and hyperparameters."""

    # --------------------------------------------------------
    # Filesystem Paths
    # --------------------------------------------------------
    project_root: Path = field(
        default_factory=lambda: Path(__file__).resolve().parent.parent.parent
    )

    @property
    def data_dir(self) -> Path:
        """Root data directory."""
        return self.project_root / "data"

    @property
    def documents_dir(self) -> Path:
        """Raw PDF documents directory."""
        return self.project_root / "documents"

    @property
    def extracted_text_dir(self) -> Path:
        """Directory for extracted raw text from PDFs."""
        return self.data_dir / "extracted_text"

    @property
    def cleaned_text_dir(self) -> Path:
        """Directory for normalized and cleaned text files."""
        return self.data_dir / "cleaned_text"

    @property
    def chunks_dir(self) -> Path:
        """Directory for tokenized chunk JSON files."""
        return self.data_dir / "chunks"

    @property
    def embeddings_dir(self) -> Path:
        """Default embeddings and chunk metadata directory (BGE-small)."""
        return self.data_dir / "embeddings_small"

    @property
    def embeddings_bge_m3_dir(self) -> Path:
        """BGE-M3 embeddings directory."""
        return self.data_dir / "embeddings"

    @property
    def qdrant_path(self) -> Path:
        """Path to local embedded Qdrant vector database."""
        return self.data_dir / "qdrant"

    @property
    def evaluation_dir(self) -> Path:
        """Directory containing benchmark datasets and ground truth."""
        return self.data_dir / "evaluation"

    # --------------------------------------------------------
    # Vector Database & Embeddings Configuration
    # --------------------------------------------------------
    qdrant_collection: str = field(
        default_factory=lambda: os.getenv("QDRANT_COLLECTION", "cybersecurity_chunks_bge_m3")
    )
    embedding_model: str = field(
        default_factory=lambda: os.getenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    )
    embedding_dim: int = field(
        default_factory=lambda: int(os.getenv("EMBEDDING_DIM", "1024"))
    )

    # --------------------------------------------------------
    # Reranker Configuration
    # --------------------------------------------------------
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    enable_reranking: bool = field(
        default_factory=lambda: os.getenv("ENABLE_RERANKING", "true").lower() in ("true", "1", "yes")
    )

    # --------------------------------------------------------
    # LLM Provider Configuration (Groq)
    # --------------------------------------------------------
    groq_api_key: str = field(
        default_factory=lambda: os.getenv("GROQ_API_KEY", "")
    )
    llm_model: str = field(
        default_factory=lambda: os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    )
    llm_temperature: float = 0.0
    llm_max_tokens: int = 8192
    query_rewrite_max_tokens: int = 1024

    # --------------------------------------------------------
    # Query Rewriter Configuration
    # --------------------------------------------------------
    enable_query_rewriting: bool = field(
        default_factory=lambda: os.getenv("ENABLE_QUERY_REWRITING", "false").lower() in ("true", "1", "yes")
    )
    enable_adaptive_query_rewriting: bool = field(
        default_factory=lambda: os.getenv("ENABLE_ADAPTIVE_QUERY_REWRITING", "false").lower() in ("true", "1", "yes")
    )
    adaptive_confidence_threshold: float = field(
        default_factory=lambda: float(os.getenv("ADAPTIVE_CONFIDENCE_THRESHOLD", "0.725"))
    )
    adaptive_confidence_mean_threshold: float = field(
        default_factory=lambda: float(os.getenv("ADAPTIVE_CONFIDENCE_MEAN_THRESHOLD", "0.700"))
    )
    adaptive_confidence_med_threshold: float = field(
        default_factory=lambda: float(os.getenv("ADAPTIVE_CONFIDENCE_MED_THRESHOLD", "0.680"))
    )
    adaptive_confidence_med_mean_threshold: float = field(
        default_factory=lambda: float(os.getenv("ADAPTIVE_CONFIDENCE_MED_MEAN_THRESHOLD", "0.660"))
    )
    adaptive_confidence_med_generic_top1: float = field(
        default_factory=lambda: float(os.getenv("ADAPTIVE_CONFIDENCE_MED_GENERIC_TOP1", "0.705"))
    )
    adaptive_confidence_med_generic_mean3: float = field(
        default_factory=lambda: float(os.getenv("ADAPTIVE_CONFIDENCE_MED_GENERIC_MEAN3", "0.685"))
    )
    adaptive_confidence_min_overlap: int = field(
        default_factory=lambda: int(os.getenv("ADAPTIVE_CONFIDENCE_MIN_OVERLAP", "6"))
    )
    adaptive_confidence_min_bm25: float = field(
        default_factory=lambda: float(os.getenv("ADAPTIVE_CONFIDENCE_MIN_BM25", "25.0"))
    )
    identifier_search_depth: int = field(
        default_factory=lambda: int(os.getenv("IDENTIFIER_SEARCH_DEPTH", "5"))
    )
    query_rewriter_model: str = field(
        default_factory=lambda: os.getenv("QUERY_REWRITER_MODEL", os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b"))
    )
    query_rewriter_timeout: float = 10.0
    query_rewriter_max_retries: int = 2

    # --------------------------------------------------------
    # Retrieval Hyperparameters
    # --------------------------------------------------------
    dense_top_k: int = 20
    bm25_top_k: int = 20
    rrf_k: int = 60
    final_top_n: int = 5

    # --------------------------------------------------------
    # Conversation Configuration
    # --------------------------------------------------------
    conversation_history_limit: int = 6

    def require_groq_api_key(self) -> str:
        """Validate and return the Groq API key, raising ValueError if missing."""
        key = self.groq_api_key or os.getenv("GROQ_API_KEY", "")
        if not key:
            raise ValueError(
                "GROQ_API_KEY not found in environment or .env file."
            )
        return key


# Global default settings instance
settings = Settings()


def get_settings() -> Settings:
    """Return the global Settings instance."""
    return settings
