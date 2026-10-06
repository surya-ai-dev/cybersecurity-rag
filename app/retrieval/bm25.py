"""BM25 keyword-based retriever for the Cybersecurity RAG system."""

import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Union

from rank_bm25 import BM25Okapi

from app.core.config import settings
from app.core.interfaces import BaseRetriever
from app.core.models import ChunkMetadata, RetrievedChunk


# ============================================================
# TOKENIZATION
# ============================================================

def tokenize(text: str) -> List[str]:
    """Tokenize input text for BM25 matching, preserving words and digits."""
    text = text.lower()
    return re.findall(r"\b[a-zA-Z0-9]+\b", text)


# ============================================================
# DOCUMENT LOADER
# ============================================================

def load_documents(metadata_dir: Optional[Union[str, Path]] = None) -> List[Dict[str, Any]]:
    """Scan and load chunk metadata JSON files from the data directory.

    Args:
        metadata_dir: Directory containing chunk JSON files. Defaults to settings.data_dir.

    Returns:
        Deduplicated list of chunk dictionaries with 'chunk_id', 'text', and 'metadata'.
    """
    search_dir = Path(metadata_dir) if metadata_dir else settings.data_dir

    json_files = list(search_dir.rglob("*.json"))

    if not json_files:
        raise FileNotFoundError(
            f"No JSON metadata files found inside: {search_dir}"
        )

    documents: List[Dict[str, Any]] = []

    for file_path in json_files:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        # Case 1: JSON contains a list of chunks
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                chunk_id = item.get("chunk_id") or item.get("id") or item.get("chunkId")
                text = item.get("text") or item.get("content") or item.get("chunk")
                if chunk_id and text:
                    documents.append({
                        "chunk_id": str(chunk_id),
                        "text": str(text),
                        "metadata": item,
                    })

        # Case 2: JSON contains {"chunks": [...]}
        elif isinstance(data, dict):
            chunks = data.get("chunks")
            if isinstance(chunks, list):
                for item in chunks:
                    if not isinstance(item, dict):
                        continue
                    chunk_id = item.get("chunk_id") or item.get("id") or item.get("chunkId")
                    text = item.get("text") or item.get("content") or item.get("chunk")
                    if chunk_id and text:
                        documents.append({
                            "chunk_id": str(chunk_id),
                            "text": str(text),
                            "metadata": item,
                        })

    # Deduplicate chunk IDs
    unique_documents: Dict[str, Dict[str, Any]] = {}
    for doc in documents:
        unique_documents[doc["chunk_id"]] = doc

    result = list(unique_documents.values())

    if not result:
        raise RuntimeError(
            f"JSON files were found in {search_dir}, but no valid chunks could be loaded."
        )

    return result


# ============================================================
# BM25 RETRIEVER CLASS
# ============================================================

class BM25Retriever(BaseRetriever):
    """Keyword-based retriever using BM25Okapi conforming to BaseRetriever."""

    def __init__(
        self,
        documents: Optional[List[Dict[str, Any]]] = None,
        data_dir: Optional[Union[str, Path]] = None,
        top_k: Optional[int] = None,
        lazy_load: bool = True,
    ) -> None:
        """Initialize the BM25 retriever.

        Args:
            documents: Pre-loaded list of chunk dictionaries. If None, loaded from disk.
            data_dir: Path to directory containing chunk JSON files.
            top_k: Default number of top results to return.
            lazy_load: If True, defer disk loading and index building until first retrieve call.
        """
        self.data_dir = Path(data_dir) if data_dir else settings.data_dir
        self.default_top_k = top_k or settings.bm25_top_k
        self._documents: Optional[List[Dict[str, Any]]] = documents
        self._bm25: Optional[BM25Okapi] = None

        if not lazy_load:
            self._ensure_initialized()

    def _ensure_initialized(self) -> None:
        """Lazily load documents and build the BM25 index if not already built."""
        if self._documents is None:
            self._documents = load_documents(self.data_dir)

        if self._bm25 is None:
            tokenized_documents = [
                tokenize(doc["text"])
                for doc in self._documents
            ]
            self._bm25 = BM25Okapi(tokenized_documents)

    @property
    def documents(self) -> List[Dict[str, Any]]:
        """Access the underlying document collection."""
        self._ensure_initialized()
        return self._documents  # type: ignore

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
    ) -> List[RetrievedChunk]:
        """Retrieve candidate chunks matching the keyword query.

        Args:
            query: The search query string.
            top_k: Number of candidate chunks to return. Defaults to self.default_top_k.

        Returns:
            List of RetrievedChunk instances ranked by BM25 score.
        """
        if not query or not query.strip():
            return []

        limit = top_k if top_k is not None else self.default_top_k
        self._ensure_initialized()

        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        scores = self._bm25.get_scores(query_tokens)  # type: ignore

        ranked_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True,
        )

        results: List[RetrievedChunk] = []

        for index in ranked_indices[:limit]:
            doc = self._documents[index]  # type: ignore
            raw_meta = doc.get("metadata", {})
            metadata = ChunkMetadata.from_dict(raw_meta if isinstance(raw_meta, dict) else {})
            score = float(scores[index])

            results.append(
                RetrievedChunk(
                    chunk_id=doc["chunk_id"],
                    text=doc["text"],
                    score=score,
                    bm25_score=score,
                    metadata=metadata,
                )
            )

        return results

    def close(self) -> None:
        """Release index memory if needed."""
        self._bm25 = None

    def __enter__(self) -> "BM25Retriever":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


# ============================================================
# CLI TEST ENTRY POINT
# ============================================================

def main():
    """CLI test for BM25Retriever."""
    print("=" * 70)
    print("BM25 RETRIEVER TEST")
    print("=" * 70)

    retriever = BM25Retriever()
    question = input("\nEnter cybersecurity question: ").strip()

    if not question:
        print("Question cannot be empty.")
        return

    results = retriever.retrieve(question)
    print(f"\nRetrieved {len(results)} chunks:")

    for rank, chunk in enumerate(results[:5], start=1):
        print(f"\n[{rank}] BM25 Score: {chunk.score:.4f} | Chunk ID: {chunk.chunk_id}")
        print(f"    Document: {chunk.metadata.document_id} | Section: {chunk.metadata.section}")
        print(f"    Text: {chunk.text[:150]}...")


if __name__ == "__main__":
    main()
