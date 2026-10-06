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
    qdrant_collection: str = "cybersecurity_chunks"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dim: int = 384

    # --------------------------------------------------------
    # Reranker Configuration
    # --------------------------------------------------------
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

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
    query_rewrite_max_tokens: int = 512

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
