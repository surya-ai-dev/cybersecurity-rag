# Architecture Specification — Cybersecurity RAG

This document details the architectural design, layers, contracts, and data flows of the Cybersecurity RAG system.

---

## 1. High-Level Architecture

```text
+--------------------------------------------------------------------------+
|                                 USER CLI                                 |
|                                (main.py)                                 |
+--------------------------------------------------------------------------+
                                     |
                                     v
+--------------------------------------------------------------------------+
|                         RAGEngine (Orchestrator)                         |
|                         (app/pipeline/engine.py)                         |
+--------------------------------------------------------------------------+
       |                                                    |
       | 1. Get History                                     | 6. Generate Answer
       v                                                    v
+-----------------------------+           +--------------------------------+
|     ConversationMemory      |           |          GroqProvider          |
| (app/conversation/memory.py)|           |   (app/generation/providers)   |
+-----------------------------+           +--------------------------------+
       |                                                    ^
       | 2. Rewrite Query                                   | 5. Formatted Prompt
       v                                                    |
+-----------------------------+           +--------------------------------+
|        QueryRewriter        |           |         ContextBuilder         |
| (app/conversation/rewriter) |           |  (app/generation/build_ctx.py)  |
+-----------------------------+           +--------------------------------+
       |                                                    ^
       | 3. Standalone Query                                | 4. Top-5 Chunks
       v                                                    |
+--------------------------------------------------------------------------+
|                       HybridRetriever (Search Layer)                     |
|                         (app/retrieval/hybrid.py)                        |
|                                                                          |
|   +-----------------------+              +---------------------------+   |
|   |    DenseRetriever     |              |       BM25Retriever       |   |
|   | (app/retrieval/dense) |              |    (app/retrieval/bm25)   |   |
|   |   BGE-small + Qdrant  |              |      Rank-BM25 Index      |   |
|   +-----------------------+              +---------------------------+   |
|               \                              /                           |
|                \--[Top-20]            [Top-20]--/                        |
|                            \        /                                    |
|                             v      v                                     |
|                     +----------------------+                             |
|                     |      RRFFusion       |                             |
|                     | (app/retrieval/rrf)  |                             |
|                     +----------------------+                             |
|                                |                                         |
|                                v [Top-20 Fused]                          |
|                     +----------------------+                             |
|                     | CrossEncoderReranker |                             |
|                     | (app/retrieval/rerank|                             |
|                     +----------------------+                             |
+--------------------------------------------------------------------------+
```

---

## 2. Request Flow

The full request lifecycle follows these sequential steps:

1. **User Question Ingestion**: The user enters a question into `main.py` (or calls `engine.query(question)`).
2. **Conversation History Retrieval**: `RAGEngine` calls `self.memory.get_messages()` to fetch recent message exchanges.
3. **Query Rewriting**:
   - If conversation history exists, `RAGEngine` calls `self.query_rewriter(question, history, llm_provider=self.llm_provider)`.
   - The query rewriter invokes the LLM with `temperature=0.0` and a specialized prompt to resolve anaphoric references (e.g., *"Why is it important?"* becomes *"Why is the principle of least privilege important?"*).
   - If no history exists, the raw question is used directly.
4. **Hybrid Retrieval**:
   - `RAGEngine` passes the standalone query to `self.retriever.retrieve(query, top_k=20)`.
   - `HybridRetriever` queries `DenseRetriever` (Qdrant cosine search) for 20 candidates and `BM25Retriever` (BM25Okapi inverted index) for 20 candidates.
   - Both candidate lists are combined via `RRFFusion` ($K=60$), producing 20 fused candidates.
5. **Cross-Encoder Reranking**:
   - `RAGEngine` submits the 20 candidates to `self.reranker.rerank(query, candidates, top_n=5)`.
   - `CrossEncoderReranker` scores each `(query, chunk_text)` pair using `ms-marco-MiniLM-L-6-v2` and returns the Top-5 highest scoring chunks.
6. **Context Building**:
   - `RAGEngine` calls `self.context_builder(top_5_chunks)`.
   - `build_context()` formats each chunk into a structured, labeled text block (`SOURCE 1`, `Document: ...`, `Section: ...`, `Content: ...`).
7. **Prompt Construction**:
   - `RAGEngine` injects the standalone question and formatted context into `RAG_PROMPT_TEMPLATE`.
   - Strict constraints mandate: only context facts, no hallucinations, concise definitions, and mandatory `[Source X]` citations.
8. **LLM Generation**:
   - `self.llm_provider.stream(prompt)` (or `.generate()`) calls the Groq Cloud API with `temperature=0.0`, streaming tokens in real time.
9. **Memory Update**:
   - The user question and full assistant answer are appended to `self.memory.add_message(question, answer)`.
10. **Structured Response**:
    - A `RAGResponse` dataclass is returned containing `question`, `standalone_question`, `answer`, and `sources` (list of `RetrievedChunk`).

---

## 3. Core Layer (`app/core/`)

The Core layer contains foundation components with zero dependencies on other `app.*` subpackages:

- **`config.py`**:
  - Encapsulates application-wide configuration in a `Settings` dataclass.
  - Automatically derives filesystem paths (`data_dir`, `qdrant_path`, `evaluation_dir`).
  - Manages hyperparameters (`dense_top_k=20`, `bm25_top_k=20`, `rrf_k=60`, `final_top_n=5`, `conversation_history_limit=6`).
  - Resolves environment variables (`GROQ_API_KEY`, `GROQ_MODEL`) safely using `python-dotenv`.
- **`models.py`**:
  - `ChunkMetadata`: Structured metadata (document ID, section title, source file, token count). Supports dict-style access for backwards compatibility.
  - `RetrievedChunk`: Standard domain representation of a chunk during retrieval, reranking, and generation. Tracks `score`, `dense_score`, `bm25_score`, `rrf_score`, and `reranker_score`.
  - `Message`: Represents an interaction turn (`user`, `assistant`).
  - `RAGResponse`: Standard response object encapsulating query, rewritten query, answer, and retrieved source chunks.
- **`interfaces.py`**:
  - Python `typing.Protocol` definitions specifying the public contracts for all architectural components:
    - `BaseRetriever`: Defines `retrieve(query: str, top_k: int) -> List[RetrievedChunk]`.
    - `BaseReranker`: Defines `rerank(query: str, documents: Sequence[Any], top_n: int) -> List[RetrievedChunk]`.
    - `BaseLLMProvider`: Defines `generate(...) -> str` and `stream(...) -> Iterator[str]`.
    - `BaseConversationMemory`: Defines `add_message(...)`, `get_messages() -> List[Message]`, and `clear()`.

---

## 4. Retrieval Layer (`app/retrieval/`)

- **`DenseRetriever` (`dense.py`)**:
  - **Responsibility**: Semantic vector search.
  - **Input**: Query string, `top_k: int`.
  - **Output**: `List[RetrievedChunk]`.
  - **Rationale**: Captures conceptual meaning even when vocabulary does not match exact document words.
  - **Implementation**: BGE-small embedding model (`BAAI/bge-small-en-v1.5`, 384 dimensions) and embedded Qdrant vector store.
- **`BM25Retriever` (`bm25.py`)**:
  - **Responsibility**: Exact term matching and keyword search.
  - **Input**: Query string, `top_k: int`.
  - **Output**: `List[RetrievedChunk]`.
  - **Rationale**: Captures exact cybersecurity codes (e.g. `AC-6`, `SP 800-53`, `BYOD`) that dense embeddings may blur.
  - **Implementation**: `rank_bm25.BM25Okapi` over 7,703 tokenized chunks.
- **`RRFFusion` (`rrf.py`)**:
  - **Responsibility**: Non-parametric rank combination.
  - **Input**: Multiple ranked lists of documents, constant $K$ (default 60), `top_k: int`.
  - **Output**: Fused, sorted `List[RetrievedChunk]`.
  - **Rationale**: Combines disparate score distributions (cosine vs BM25) purely based on rank order without fragile score normalization.
- **`HybridRetriever` (`hybrid.py`)**:
  - **Responsibility**: Retrieval orchestration.
  - **Input**: Query string, `top_k: int`.
  - **Output**: Fused candidate `List[RetrievedChunk]`.
  - **Rationale**: Implements `BaseRetriever` so high-level consumers interact with a unified search interface.
- **`CrossEncoderReranker` (`reranker.py`)**:
  - **Responsibility**: Deep query-document relevance scoring.
  - **Input**: Query string, sequence of candidate chunks, `top_n: int`.
  - **Output**: Top-N reranked `List[RetrievedChunk]`.
  - **Rationale**: Bi-encoders compute independent embeddings; Cross-Encoders evaluate full cross-attention over `(query, document)` tokens, yielding superior precision.

---

## 5. Generation Layer (`app/generation/`)

- **`build_context.py`**:
  - **Responsibility**: Pure formatting component.
  - **Input**: Sequence of `RetrievedChunk` instances.
  - **Output**: Formatted prompt context string.
  - **Rationale**: Decouples retrieval from prompt formatting. Context builder contains zero retrieval or database logic.
- **`GroqProvider` (`providers/groq_provider.py`)**:
  - **Responsibility**: Concrete LLM provider for Groq Cloud.
  - **Input**: Prompt string, sampling parameters (`temperature`, `max_tokens`).
  - **Output**: Complete string or token stream iterator.
  - **Rationale**: Isolates the third-party Groq SDK. Switching LLM providers (e.g. Ollama, OpenAI, Anthropic) requires only adding a new class implementing `BaseLLMProvider`.
- **`llm.py`**:
  - **Responsibility**: Backward-compatibility wrapper for legacy callers.
  - **Rationale**: Preserves `generate_answer()` signature while delegating internally to `GroqProvider`.

---

## 6. Conversation Layer (`app/conversation/`)

- **`ConversationMemory` (`conversation_memory.py`)**:
  - **Responsibility**: In-memory sliding history window.
  - **Capacity**: Configurable (default 6 recent messages from `settings.conversation_history_limit`).
  - **Rationale**: Prevents context bloat while keeping recent dialogue accessible for pronoun resolution.
- **`QueryRewriter` (`query_rewriter.py`)**:
  - **Responsibility**: Context-aware query disambiguation.
  - **Input**: User follow-up query, recent `Message` history, optional `BaseLLMProvider`.
  - **Output**: Standalone question string.
  - **Rationale**: Resolves ambiguous references (*"Why is it important?"* $\rightarrow$ *"Why is the principle of least privilege important?"*) before sending queries to retrieval.

---

## 7. Pipeline Layer (`app/pipeline/`)

- **`RAGEngine` (`engine.py`)**:
  - Central orchestrator coordinating all subsystems.
  - Follows Dependency Injection: accepts `retriever`, `reranker`, `query_rewriter`, `context_builder`, `llm_provider`, and `memory` via its constructor.
  - Provides default concrete implementations if none are injected.
  - Exposes `query()`, `run()`, `stream()`, and `close()` lifecycle methods.
  - Manages context manager support (`with RAGEngine() as engine:`).

---

## 8. Ingestion Layer (`app/ingestion/`)

The offline document ingestion pipeline transforms raw NIST PDFs into an embedded vector database:

1. **`collect_nist.py`**: Downloads official NIST Special Publications PDFs into `documents/`.
2. **`extract_text.py`**: Extracts text from PDFs into `data/extracted_text/` with page metadata.
3. **`clean_text.py`**: Strips headers, footers, page numbers, and formatting artifacts into `data/cleaned_text/`.
4. **`chunk_documents.py`**: Splits cleaned text into token-aware chunks (target 250–400 tokens, 50-token overlap) and saves structured JSON files into `data/chunks/`.
5. **`embed_documents_safe.py` / `embed_documents.py`**: Batches chunk texts through `BAAI/bge-small-en-v1.5` to generate 384-dimensional dense vectors.
6. **`build_qdrant.py`**: Creates the `cybersecurity_chunks` Qdrant collection, creates payload indices, and inserts embeddings alongside chunk text and metadata.

---

## 9. Compatibility Wrappers

To ensure backward compatibility without breaking existing evaluation benchmarks or operational scripts, six compatibility wrappers are maintained:

1. **`app/retrieval/retriever.py`**: Exposes legacy functions (`dense_retrieval`, `close_retriever`) delegating to `DenseRetriever`.
2. **`app/retrieval/bm25_retriever.py`**: Exposes `load_documents` and legacy `BM25Retriever` delegating to `app/retrieval/bm25.py`.
3. **`app/retrieval/rrf_fusion.py`**: Exposes `reciprocal_rank_fusion` delegating to `app/retrieval/rrf.py`.
4. **`app/retrieval/hybrid_reranker.py`**: Exposes legacy `hybrid_retrieve` delegating to `HybridRetriever`.
5. **`app/pipeline/rag_pipeline.py`**: Exposes legacy `run_rag_pipeline` delegating to `RAGEngine`.
6. **`app/generation/llm.py`**: Exposes `generate_answer` delegating to `GroqProvider`.

These wrappers are intentionally maintained and are actively consumed by benchmark scripts in `evaluation/`.

---

## 10. Dependency Direction

Dependencies strictly flow inward toward `app.core`:

```text
main.py
  |
  v
app.pipeline
  |
  +---> app.conversation
  +---> app.retrieval
  +---> app.generation
          |
          v
       app.core (config, models, interfaces)
```

- **`app.core`** has zero internal dependencies.
- **`app.retrieval`** depends only on `app.core`.
- **`app.generation`** depends only on `app.core`.
- **`app.conversation`** depends only on `app.core`.
- **`app.pipeline`** connects the layers via public interfaces.

---

## 11. Lazy Initialization

All heavyweight components utilize lazy initialization to ensure near-instant startup time:

- **`DenseRetriever`**: Embedding model (`SentenceTransformer`) and `QdrantClient` are initialized only when `_ensure_initialized()` is triggered during the first retrieval call.
- **`BM25Retriever`**: Chunk JSON files and tokenized inverted index are built only on first query.
- **`CrossEncoderReranker`**: `CrossEncoder` weights are loaded only on first rerank invocation.
- **`RAGEngine`**: Instantiating `RAGEngine()` takes under 2 milliseconds.

---

## 12. Data Flow Summary

```text
NIST PDFs (documents/)
    | (extract_text.py)
Raw Text (data/extracted_text/)
    | (clean_text.py)
Cleaned Text (data/cleaned_text/)
    | (chunk_documents.py)
Tokenized Chunks (data/chunks/ -> 7,703 chunks)
    | (embed_documents_safe.py)
Vector Embeddings (384-dim BGE-small)
    | (build_qdrant.py)
Qdrant Vector DB (data/qdrant/)
    |
==================== RUNTIME QUERY ====================
    |
User Query -> Standalone Query
    |
    +---> Dense Search (Qdrant)  ---> Top-20
    +---> BM25 Search (Inverted) ---> Top-20
    |
    v
RRF Fusion (K=60)                ---> Top-20
    |
Cross-Encoder Reranker           ---> Top-5
    |
Context Builder (SOURCE 1..5)
    |
Groq LLM (Prompt + Context)
    |
Answer + Citations [Source X] -> RAGResponse
```
