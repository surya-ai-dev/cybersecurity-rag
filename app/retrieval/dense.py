"""Dense vector retriever using BGE embeddings and Qdrant."""

from pathlib import Path
from typing import List, Optional, Union

from app.core.config import settings
from app.core.interfaces import BaseRetriever
from app.core.models import ChunkMetadata, RetrievedChunk


class DenseRetriever(BaseRetriever):
    """Dense retriever using BGE sentence embeddings and embedded Qdrant vector database."""

    def __init__(
        self,
        embedding_model_name: Optional[str] = None,
        qdrant_path: Optional[Union[str, Path]] = None,
        collection_name: Optional[str] = None,
        top_k: Optional[int] = None,
        lazy_load: bool = True,
    ) -> None:
        """Initialize the Dense retriever.

        Args:
            embedding_model_name: Name or path of the embedding model.
            qdrant_path: Local filesystem path to the embedded Qdrant directory.
            collection_name: Qdrant collection name.
            top_k: Default retrieval limit.
            lazy_load: If True, defer model and client loading until first query.
        """
        self.embedding_model_name = embedding_model_name or settings.embedding_model
        self.qdrant_path = Path(qdrant_path) if qdrant_path else settings.qdrant_path
        self.collection_name = collection_name or settings.qdrant_collection
        self.default_top_k = top_k or settings.dense_top_k

        self._embedding_model = None
        self._qdrant_client = None

        if not lazy_load:
            self._ensure_initialized()

    def _ensure_initialized(self) -> None:
        """Lazily initialize the embedding model and Qdrant client."""
        if self._embedding_model is None:
            from sentence_transformers import SentenceTransformer

            self._embedding_model = SentenceTransformer(
                self.embedding_model_name,
                local_files_only=True,
            )

        if self._qdrant_client is None:
            from qdrant_client import QdrantClient

            self._qdrant_client = QdrantClient(
                path=str(self.qdrant_path),
            )

    @property
    def embedding_model(self):
        """Access the underlying SentenceTransformer embedding model."""
        self._ensure_initialized()
        return self._embedding_model

    @property
    def client(self):
        """Access the underlying Qdrant client."""
        self._ensure_initialized()
        return self._qdrant_client

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
    ) -> List[RetrievedChunk]:
        """Retrieve candidate chunks for a query using dense semantic search.

        Args:
            query: The search query text.
            top_k: Number of candidate chunks to return. Defaults to self.default_top_k.

        Returns:
            List of RetrievedChunk instances ranked by vector similarity score.
        """
        if not query or not query.strip():
            return []

        limit = top_k if top_k is not None else self.default_top_k
        self._ensure_initialized()

        query_embedding = self._embedding_model.encode(
            query,
            normalize_embeddings=True,
        )

        results = self._qdrant_client.query_points(
            collection_name=self.collection_name,
            query=query_embedding.tolist(),
            limit=limit,
            with_payload=True,
        ).points

        documents: List[RetrievedChunk] = []

        for point in results:
            payload = point.payload or {}
            chunk_id = payload.get("chunk_id")

            if chunk_id is None:
                continue

            score = float(point.score)

            metadata = ChunkMetadata(
                document_id=payload.get("document_id", "Unknown"),
                category=payload.get("category", "Unknown"),
                source_file=payload.get("source_file", "Unknown"),
                section=payload.get("section", "Unknown"),
                token_count=int(payload.get("token_count", 0)),
                extra={
                    k: v
                    for k, v in payload.items()
                    if k not in {"chunk_id", "text", "document_id", "category", "source_file", "section", "token_count"}
                },
            )

            documents.append(
                RetrievedChunk(
                    chunk_id=str(chunk_id),
                    text=str(payload.get("text", "")),
                    score=score,
                    dense_score=score,
                    metadata=metadata,
                )
            )

        return documents

    def close(self) -> None:
        """Close the Qdrant client connection and release resources."""
        if self._qdrant_client is not None:
            self._qdrant_client.close()
            self._qdrant_client = None

    def __enter__(self) -> "DenseRetriever":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


def main():
    """CLI test for DenseRetriever."""
    print("=" * 70)
    print("DENSE RETRIEVER TEST")
    print("=" * 70)

    with DenseRetriever() as retriever:
        question = input("\nEnter cybersecurity question: ").strip()
        if not question:
            print("Question cannot be empty.")
            return

        print(f"\nRetrieving top {retriever.default_top_k} dense results...")
        results = retriever.retrieve(question)

        print(f"Retrieved {len(results)} chunks.")
        for rank, chunk in enumerate(results[:5], start=1):
            print(f"\n[{rank}] Score: {chunk.score:.4f} | Chunk ID: {chunk.chunk_id}")
            print(f"    Document: {chunk.metadata.document_id} | File: {chunk.metadata.source_file}")
            print(f"    Section: {chunk.metadata.section}")
            print(f"    Text: {chunk.text[:150]}...")


if __name__ == "__main__":
    main()
