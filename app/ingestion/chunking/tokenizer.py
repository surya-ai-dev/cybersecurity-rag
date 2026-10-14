"""Pluggable tokenizer adapters for model-independent document chunking."""

from abc import ABC, abstractmethod
from typing import List, Optional
import warnings

from app.ingestion.chunking.config import ChunkingConfig


class TokenizerAdapter(ABC):
    """Abstract interface defining required token budgeting capabilities."""

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Return the exact or estimated token count for text."""
        pass

    @abstractmethod
    def tokenize(self, text: str) -> List[str]:
        """Convert text into token string fragments."""
        pass

    @abstractmethod
    def truncate_tokens(self, text: str, max_tokens: int) -> str:
        """Safely truncate text so its token representation does not exceed max_tokens."""
        pass

    @property
    @abstractmethod
    def is_exact(self) -> bool:
        """Return True if this adapter uses an authoritative model tokenizer."""
        pass


class HuggingFaceTokenizerAdapter(TokenizerAdapter):
    """Authoritative tokenizer adapter using local offline Hugging Face tokenizers."""

    def __init__(self, model_name_or_path: str = "BAAI/bge-small-en-v1.5"):
        self.model_name_or_path = model_name_or_path
        try:
            from transformers import AutoTokenizer

            # Strictly local_files_only to prevent unapproved network downloads
            self._tokenizer = AutoTokenizer.from_pretrained(
                model_name_or_path,
                local_files_only=True,
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to load local HuggingFace tokenizer '{model_name_or_path}' offline: {e}. "
                "Ensure model weights/tokenizer files reside in the local cache or use a supported adapter."
            ) from e

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        return len(self._tokenizer.encode(text, add_special_tokens=False, verbose=False))

    def tokenize(self, text: str) -> List[str]:
        if not text:
            return []
        return self._tokenizer.tokenize(text)

    def truncate_tokens(self, text: str, max_tokens: int) -> str:
        if not text or max_tokens <= 0:
            return ""
        tokens = self._tokenizer.encode(text, add_special_tokens=False, verbose=False)
        if len(tokens) <= max_tokens:
            return text
        truncated_ids = tokens[:max_tokens]
        return self._tokenizer.decode(truncated_ids, skip_special_tokens=True).strip()

    @property
    def is_exact(self) -> bool:
        return True


class TiktokenAdapter(TokenizerAdapter):
    """Tokenizer adapter using OpenAI tiktoken encoding (e.g. cl100k_base)."""

    def __init__(self, encoding_name: str = "cl100k_base"):
        self.encoding_name = encoding_name
        try:
            import tiktoken

            self._encoding = tiktoken.get_encoding(encoding_name)
        except Exception as e:
            raise RuntimeError(f"Failed to load tiktoken encoding '{encoding_name}': {e}") from e

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        return len(self._encoding.encode(text, disallowed_special=()))

    def tokenize(self, text: str) -> List[str]:
        if not text:
            return []
        tokens = self._encoding.encode(text, disallowed_special=())
        return [self._encoding.decode([t]) for t in tokens]

    def truncate_tokens(self, text: str, max_tokens: int) -> str:
        if not text or max_tokens <= 0:
            return ""
        tokens = self._encoding.encode(text, disallowed_special=())
        if len(tokens) <= max_tokens:
            return text
        return self._encoding.decode(tokens[:max_tokens]).strip()

    @property
    def is_exact(self) -> bool:
        return True


class CharEstimatorAdapter(TokenizerAdapter):
    """Zero-dependency heuristic character estimator (1 token ~ 4.0 chars).

    WARNING: Only intended as an offline diagnostic fallback. Not exact.
    """

    CHARS_PER_TOKEN = 4.0

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        return max(1, int(len(text) / self.CHARS_PER_TOKEN))

    def tokenize(self, text: str) -> List[str]:
        if not text:
            return []
        # Rough whitespace tokenization
        return text.split()

    def truncate_tokens(self, text: str, max_tokens: int) -> str:
        if not text or max_tokens <= 0:
            return ""
        char_limit = int(max_tokens * self.CHARS_PER_TOKEN)
        if len(text) <= char_limit:
            return text
        # Truncate at last word boundary before char_limit
        truncated = text[:char_limit]
        last_space = truncated.rfind(" ")
        if last_space > 0:
            truncated = truncated[:last_space]
        return truncated.strip()

    @property
    def is_exact(self) -> bool:
        return False


def get_tokenizer_adapter(config: ChunkingConfig) -> TokenizerAdapter:
    """Factory creating the configured TokenizerAdapter instance."""
    backend = config.tokenizer_backend.lower().strip()
    if backend == "hf_tokenizer":
        return HuggingFaceTokenizerAdapter(model_name_or_path=config.model_name_or_path)
    elif backend == "tiktoken":
        return TiktokenAdapter()
    elif backend == "char_estimate":
        warnings.warn(
            "Using CharEstimatorAdapter: token counts are heuristic approximations only.",
            UserWarning,
            stacklevel=2,
        )
        return CharEstimatorAdapter()
    else:
        raise ValueError(
            f"Unsupported tokenizer backend: '{config.tokenizer_backend}'. "
            "Supported backends: 'hf_tokenizer', 'tiktoken', 'char_estimate'."
        )
