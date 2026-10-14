"""Structure-aware, content-aware document chunking package."""

from app.ingestion.chunking.config import ChunkingConfig
from app.ingestion.chunking.figure_chunker import FigureChunker
from app.ingestion.chunking.models import (
    ChunkRecord,
    FigureChunkMetadata,
    TableChunkMetadata,
)
from app.ingestion.chunking.pipeline import (
    DocumentChunkResult,
    DocumentChunkingPipeline,
)
from app.ingestion.chunking.runner import (
    CorpusChunkingRunner,
    PilotRunnerReport,
)
from app.ingestion.chunking.table_chunker import TableChunker
from app.ingestion.chunking.text_chunker import StructureAwareTextChunker
from app.ingestion.chunking.tokenizer import (
    CharEstimatorAdapter,
    HuggingFaceTokenizerAdapter,
    TiktokenAdapter,
    TokenizerAdapter,
    get_tokenizer_adapter,
)

__all__ = [
    "ChunkingConfig",
    "ChunkRecord",
    "TableChunkMetadata",
    "FigureChunkMetadata",
    "TokenizerAdapter",
    "HuggingFaceTokenizerAdapter",
    "TiktokenAdapter",
    "CharEstimatorAdapter",
    "get_tokenizer_adapter",
    "StructureAwareTextChunker",
    "TableChunker",
    "FigureChunker",
    "DocumentChunkingPipeline",
    "DocumentChunkResult",
    "CorpusChunkingRunner",
    "PilotRunnerReport",
]
