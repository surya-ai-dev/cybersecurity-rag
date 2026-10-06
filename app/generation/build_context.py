"""Context builder for the Cybersecurity RAG system.

Formats retrieved and reranked document chunks into structured context
blocks for LLM consumption.
"""

from typing import Any, Dict, List, Sequence, Union

from app.core.models import ChunkMetadata, RetrievedChunk


# ============================================================
# CONTEXT BUILDER
# ============================================================

def build_context(
    results: Sequence[Union[RetrievedChunk, Dict[str, Any]]],
) -> str:
    """Format retrieved/reranked chunks into a prompt-ready context string.

    Args:
        results: Sequence of retrieved document chunks, either as RetrievedChunk
            instances or dictionaries with 'text', 'metadata', and 'rrf_score'.

    Returns:
        Formatted context string containing all sources with metadata and content.
    """
    if not results:
        return ""

    context_parts: List[str] = []

    for index, result in enumerate(results, start=1):
        if isinstance(result, RetrievedChunk):
            metadata = result.metadata
            if isinstance(metadata, ChunkMetadata):
                document = metadata.document_id or "Unknown"
                source = metadata.source_file or "Unknown"
                section = metadata.section or "Unknown"
            elif isinstance(metadata, dict):
                document = metadata.get("document_id") or metadata.get("document") or "Unknown"
                source = metadata.get("source_file", "Unknown")
                section = metadata.get("section", "Unknown")
            else:
                document, source, section = "Unknown", "Unknown", "Unknown"

            text = result.text or ""
            rrf_score = result.rrf_score if result.rrf_score is not None else 0.0

        elif isinstance(result, dict):
            metadata = result.get("metadata", {})
            if isinstance(metadata, ChunkMetadata):
                document = metadata.document_id or "Unknown"
                source = metadata.source_file or "Unknown"
                section = metadata.section or "Unknown"
            elif isinstance(metadata, dict):
                document = metadata.get("document_id") or metadata.get("document") or "Unknown"
                source = metadata.get("source_file", "Unknown")
                section = metadata.get("section", "Unknown")
            else:
                document, source, section = "Unknown", "Unknown", "Unknown"

            text = result.get("text", "") or ""
            rrf_val = result.get("rrf_score")
            rrf_score = float(rrf_val) if rrf_val is not None else 0.0

        else:
            document, source, section, rrf_score, text = "Unknown", "Unknown", "Unknown", 0.0, str(result)

        context = f"""
SOURCE {index}

Document: {document}
Source File: {source}
Section: {section}
RRF Score: {rrf_score:.6f}

Content:
{text}
"""
        context_parts.append(context.strip())

    return "\n\n".join(context_parts)


# ============================================================
# DEMO / TEST ENTRY POINT
# ============================================================

def main():
    """Demonstrate context building with sample chunks."""
    sample_results = [
        {
            "chunk_id": "chunk_001",
            "text": "Access control policy enforcing principle of least privilege.",
            "metadata": {
                "document_id": "NIST_SP_800_53",
                "source_file": "sp800-53r5.pdf",
                "section": "AC-6 Least Privilege",
            },
            "rrf_score": 0.032258,
        },
        RetrievedChunk(
            chunk_id="chunk_002",
            text="The organization employs the principle of least privilege for all user accounts.",
            metadata=ChunkMetadata(
                document_id="NIST_SP_800_53",
                source_file="sp800-53r5.pdf",
                section="AC-6(1) Authorize Access to Security Functions",
            ),
            rrf_score=0.016393,
        ),
    ]

    print("=" * 70)
    print("RAG CONTEXT BUILDER (Sample Demo)")
    print("=" * 70)
    print(f"\nBuilding context from {len(sample_results)} sample chunks...")
    context = build_context(sample_results)

    print("\n" + "=" * 70)
    print("RETRIEVED CONTEXT")
    print("=" * 70)
    print(context)
    print("\n" + "=" * 70)
    print("CONTEXT BUILD COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()