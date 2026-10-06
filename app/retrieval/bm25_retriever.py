"""Compatibility wrapper for BM25Retriever.

Exposes the modularized BM25Retriever from app.retrieval.bm25.
"""

from app.retrieval.bm25 import BM25Retriever, load_documents, main, tokenize

__all__ = ["BM25Retriever", "load_documents", "tokenize", "main"]

if __name__ == "__main__":
    main()