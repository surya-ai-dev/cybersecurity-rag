"""Main entry point for the Cybersecurity RAG CLI application."""

from typing import Any, Sequence

from app.core.interfaces import BaseMemoryManager
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


def handle_cli_command(raw_input: str, engine: RAGEngine) -> bool:
    """Handle interactive slash memory/session commands.

    Returns:
        True if the input was handled as a command; False if it is a normal query.
    """
    text = raw_input.strip()
    if not text.startswith("/"):
        return False

    parts = text.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""
    memory = engine.memory

    if cmd == "/new":
        if hasattr(memory, "new_session"):
            meta = memory.new_session(title=arg or None)  # type: ignore[attr-defined]
            print(f"Started new session: {meta.session_id} ({meta.title})")
        elif hasattr(memory, "clear"):
            memory.clear()  # type: ignore[attr-defined]
            print("Cleared in-memory conversation buffer.")
        else:
            print("Active memory backend does not support session creation.")
        return True

    if cmd == "/sessions":
        if hasattr(memory, "list_sessions"):
            sessions = memory.list_sessions()  # type: ignore[attr-defined]
            if not sessions:
                print("No saved sessions found.")
            else:
                print("\nSaved Sessions:")
                for sess in sessions:
                    active_mark = "*" if getattr(memory, "session_id", None) == sess.session_id else " "
                    print(
                        f" {active_mark} {sess.session_id} | turns={sess.turn_count} | "
                        f"title={sess.title} | updated={sess.updated_at}"
                    )
        else:
            print("Session listing requires MemoryManager (ENABLE_PERSISTENT_MEMORY=true).")
        return True

    if cmd == "/load":
        if not arg:
            print("Usage: /load <session_id>")
            return True
        if hasattr(memory, "switch_session"):
            meta = memory.switch_session(arg)  # type: ignore[attr-defined]
            print(
                f"Loaded session: {meta.session_id} | title={meta.title} | "
                f"turns={meta.turn_count}"
            )
            if meta.summary:
                print(f"Summary: {meta.summary}")
        else:
            print("Session loading requires MemoryManager (ENABLE_PERSISTENT_MEMORY=true).")
        return True

    if cmd == "/memory":
        if isinstance(memory, BaseMemoryManager):
            ctx = memory.get_context()
            print(f"\nSession ID : {ctx.session_id or 'N/A'}")
            print(f"Recent Turns: {len(ctx.recent_messages)} (tokens={ctx.total_tokens})")
            print(f"Summary    : {ctx.summary or '(none)'}")
            if ctx.active_facts:
                print("Active Facts:")
                for fact in ctx.active_facts:
                    print(f"  - [{fact.category}] {fact.key}: {fact.value}")
            else:
                print("Active Facts: (none)")
        else:
            print(f"In-memory turns stored: {len(memory.get_messages())}")
        return True

    if cmd == "/clear":
        if hasattr(memory, "clear"):
            memory.clear()  # type: ignore[attr-defined]
            print("Cleared active session memory.")
        else:
            print("Active memory backend does not support clearing.")
        return True

    print(
        "Unknown command. Available commands: /new, /sessions, /load <session_id>, /memory, /clear, exit"
    )
    return True


def main() -> None:
    """Run the interactive cybersecurity RAG command-line interface."""
    print("=" * 70)
    print("CYBERSECURITY RAG SYSTEM")
    print("=" * 70)
    print("Commands: /new | /sessions | /load <id> | /memory | /clear | exit")

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

            if handle_cli_command(question, engine):
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
