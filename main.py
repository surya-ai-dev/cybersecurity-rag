"""Main entry point for the Cybersecurity RAG CLI application."""

from typing import Any, Sequence

from app.pipeline.engine import RAGEngine


def display_sources(sources: Sequence[Any]) -> None:
    """Format and display retrieved source citations."""
    print("\n" + "=" * 70)
    print("SOURCES")
    print("=" * 70)

    for index, result in enumerate(sources, start=1):
        metadata = getattr(result, "metadata", None)
        if metadata is not None:
            doc_id = getattr(metadata, "document_id", "Unknown")
            source_file = getattr(metadata, "source_file", "Unknown")
            section = getattr(metadata, "section", "Unknown")
        elif isinstance(result, dict):
            raw_meta = result.get("metadata", {})
            doc_id = raw_meta.get("document_id", "Unknown")
            source_file = raw_meta.get("source_file", "Unknown")
            section = raw_meta.get("section", "Unknown")
        else:
            doc_id, source_file, section = "Unknown", "Unknown", "Unknown"

        score = getattr(result, "reranker_score", None)
        if score is None and isinstance(result, dict):
            score = result.get("reranker_score", 0.0)
        score_val = float(score) if score is not None else 0.0

        print(f"[{index}] {doc_id} | {source_file}")
        print(f"    Section: {section}")
        print(f"    Reranker score: {score_val:.4f}")


def main() -> None:
    """Run the interactive cybersecurity RAG command-line interface."""
    print("=" * 70)
    print("CYBERSECURITY RAG SYSTEM")
    print("=" * 70)

    engine = RAGEngine()

    try:
        while True:
            question = input(
                "\nEnter cybersecurity question (type 'exit' to quit): "
            )

            if question.strip().lower() == "exit":
                break

            if not question.strip():
                print("❌ Question cannot be empty.")
                continue

            # Query the orchestrator with real-time streaming
            response = engine.query(question, stream=True)

            print(
                f"\nDEBUG: Stored conversations = "
                f"{len(engine.memory.get_messages())}"
            )

            display_sources(response.sources)

    finally:
        engine.close()


if __name__ == "__main__":
    main()
