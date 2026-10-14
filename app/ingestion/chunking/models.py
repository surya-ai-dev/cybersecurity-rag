"""Data models for structure-aware, model-independent document chunking."""

from dataclasses import asdict, dataclass, field
import hashlib
from typing import Any, Dict, List, Optional


@dataclass
class TableChunkMetadata:
    """Relational metadata associated with an atomic or row-partitioned table chunk."""

    parent_table_id: str
    part_index: int = 1
    total_parts: int = 1
    caption: str = ""
    headers: List[str] = field(default_factory=list)
    row_start: int = 0
    row_end: int = 0
    rows_count: int = 0
    cols_count: int = 0
    is_continuation: bool = False
    continuation_of_table_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert table metadata to serializable dict."""
        return {
            "parent_table_id": self.parent_table_id,
            "part_index": self.part_index,
            "total_parts": self.total_parts,
            "caption": self.caption,
            "headers": list(self.headers),
            "row_start": self.row_start,
            "row_end": self.row_end,
            "rows_count": self.rows_count,
            "cols_count": self.cols_count,
            "is_continuation": self.is_continuation,
            "continuation_of_table_id": self.continuation_of_table_id,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["TableChunkMetadata"]:
        if not data:
            return None
        return cls(
            parent_table_id=data.get("parent_table_id", "unknown"),
            part_index=data.get("part_index", 1),
            total_parts=data.get("total_parts", 1),
            caption=data.get("caption", ""),
            headers=list(data.get("headers", [])),
            row_start=data.get("row_start", 0),
            row_end=data.get("row_end", 0),
            rows_count=data.get("rows_count", 0),
            cols_count=data.get("cols_count", 0),
            is_continuation=data.get("is_continuation", False),
            continuation_of_table_id=data.get("continuation_of_table_id"),
        )


@dataclass
class FigureChunkMetadata:
    """Metadata associated with an extracted figure asset and its contextual link."""

    figure_id: str
    asset_path: str
    caption: str = ""
    status: str = "EXTRACTED_VLM_PENDING"
    dimensions: Dict[str, int] = field(default_factory=dict)
    surrounding_context: str = ""
    vlm_description: Optional[str] = None
    caption_linked: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert figure metadata to serializable dict."""
        return {
            "figure_id": self.figure_id,
            "asset_path": self.asset_path,
            "caption": self.caption,
            "status": self.status,
            "dimensions": dict(self.dimensions),
            "surrounding_context": self.surrounding_context,
            "vlm_description": self.vlm_description,
            "caption_linked": self.caption_linked,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["FigureChunkMetadata"]:
        if not data:
            return None
        return cls(
            figure_id=data.get("figure_id", "unknown"),
            asset_path=data.get("asset_path", ""),
            caption=data.get("caption", ""),
            status=data.get("status", "EXTRACTED_VLM_PENDING"),
            dimensions=dict(data.get("dimensions", {})),
            surrounding_context=data.get("surrounding_context", ""),
            vlm_description=data.get("vlm_description"),
            caption_linked=data.get("caption_linked", True),
        )


@dataclass
class ChunkRecord:
    """Standardized, normalized chunk record representing a retrieval unit."""

    chunk_id: str
    document_id: str
    category: str
    source_file: str
    content_type: str  # "text" | "table" | "figure" | "mixed"
    page_start: int
    page_end: int
    citation_label: str
    section_path: List[str] = field(default_factory=list)
    section_heading: str = ""
    text: str = ""
    token_count: int = 0
    char_count: int = 0
    table_metadata: Optional[Dict[str, Any]] = None
    figure_metadata: Optional[Dict[str, Any]] = None
    has_encoding_warning: bool = False
    encoding_warnings: List[str] = field(default_factory=list)
    bbox_coordinates: List[Dict[str, float]] = field(default_factory=list)
    content_hash: str = ""
    duplicate_of: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.char_count and self.text:
            self.char_count = len(self.text)
        if not self.content_hash and self.text:
            self.content_hash = self.compute_hash(self.text)

    @staticmethod
    def compute_hash(text: str) -> str:
        """Compute deterministic SHA-256 hash of canonical text."""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """Convert chunk record to JSON-serializable dictionary."""
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "category": self.category,
            "source_file": self.source_file,
            "content_type": self.content_type,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "citation_label": self.citation_label,
            "section_path": list(self.section_path),
            "section_heading": self.section_heading,
            "text": self.text,
            "token_count": self.token_count,
            "char_count": self.char_count,
            "table_metadata": self.table_metadata,
            "figure_metadata": self.figure_metadata,
            "has_encoding_warning": self.has_encoding_warning,
            "encoding_warnings": list(self.encoding_warnings),
            "bbox_coordinates": [dict(b) for b in self.bbox_coordinates],
            "content_hash": self.content_hash,
            "duplicate_of": list(self.duplicate_of),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChunkRecord":
        """Instantiate ChunkRecord from dictionary."""
        return cls(
            chunk_id=data["chunk_id"],
            document_id=data["document_id"],
            category=data["category"],
            source_file=data["source_file"],
            content_type=data["content_type"],
            page_start=data["page_start"],
            page_end=data["page_end"],
            citation_label=data["citation_label"],
            section_path=list(data.get("section_path", [])),
            section_heading=data.get("section_heading", ""),
            text=data.get("text", ""),
            token_count=data.get("token_count", 0),
            char_count=data.get("char_count", 0),
            table_metadata=data.get("table_metadata"),
            figure_metadata=data.get("figure_metadata"),
            has_encoding_warning=data.get("has_encoding_warning", False),
            encoding_warnings=list(data.get("encoding_warnings", [])),
            bbox_coordinates=list(data.get("bbox_coordinates", [])),
            content_hash=data.get("content_hash", ""),
            duplicate_of=list(data.get("duplicate_of", [])),
        )
