# Architecture Decision Records (ADRs) — Cybersecurity RAG

This document records the foundational architectural decisions established in the Cybersecurity RAG codebase.

---

## Decision: Dense + BM25 Hybrid Retrieval

### Decision
Combine dense vector search (`BAAI/bge-small-en-v1.5` over embedded Qdrant) with sparse keyword search (`rank_bm25.BM25Okapi` over tokenized chunks).

### Reason
Cybersecurity queries frequently feature technical acronyms, control identifiers (e.g., `AC-6`, `SP 800-53`), and specific terminology where pure dense embeddings suffer from vocabulary blur. Conversely, pure keyword search fails on semantic phrasing (*"limiting privileges to minimum"* vs *"principle of least privilege"*). Hybrid retrieval combines semantic comprehension with lexical precision.

### Consequence
Candidate retrieval achieves superior recall (Hit@5 = 100.00% under fusion) compared to dense-only (93.33%) or BM25-only (25.00%). The system requires maintaining both a vector store and a tokenized corpus.

---

## Decision: Reciprocal Rank Fusion (RRF) with K=60

### Decision
Fuse dense and BM25 candidate lists using Reciprocal Rank Fusion (RRF) with constant parameter $K=60$:
$$\text{Score}(d) = \sum_{m \in M} \frac{1}{K + r_m(d)}$$

### Reason
Dense cosine similarities and BM25 scores operate on entirely different scales and distributions. Weighted linear combination ($\alpha \cdot \text{dense} + (1-\alpha) \cdot \text{bm25}$) requires fragile score normalization and extensive hyperparameter tuning across varying queries. RRF is non-parametric and relies solely on rank position.

### Consequence
Retrieval fusion is robust, stable across diverse question types, and requires zero dynamic score calibration. Hit@1 reached 86.67% and MRR reached 0.9333.

---

## Decision: Cross-Encoder Reranking

### Decision
Apply a Cross-Encoder transformer model (`cross-encoder/ms-marco-MiniLM-L-6-v2`) to rerank the Top-20 fused candidates down to Top-5 before generation.

### Reason
Bi-encoders evaluate queries and documents as independent embedding vectors, missing token-level interactions. A Cross-Encoder feeds query and document tokens simultaneously through cross-attention layers, capturing deep contextual relevance.

### Consequence
Only the highest-quality, most relevant 5 chunks are passed into the LLM context window, minimizing prompt token consumption and reducing distraction for the generative model.

---

## Decision: RAGEngine Centralized Orchestration

### Decision
Consolidate the complete end-to-end RAG lifecycle into a single orchestrator class, `RAGEngine` (`app/pipeline/engine.py`), with dependency injection.

### Reason
*Architectural rationale inferred from the current design.*
Prior to modularization, pipeline stages were coupled across `rag_pipeline.py`, `llm.py`, and `main.py`, making testing and configuration management difficult. Centralizing orchestration enables programmatic usage, streaming support, and context manager resource cleanup (`with RAGEngine() as engine:`).

### Consequence
CLI applications, scripts, tests, and future API endpoints can instantiate or inject `RAGEngine` with full control over mock or real components.

---

## Decision: LLM Provider Abstraction (`BaseLLMProvider`)

### Decision
Decouple text generation behind a `BaseLLMProvider` protocol, implementing `GroqProvider` as the concrete driver for the Groq Cloud SDK.

### Reason
Prevent vendor lock-in. Direct imports of `groq.Groq` throughout query rewriters and pipeline modules created tight coupling to a single cloud provider.

### Consequence
Switching or adding LLM backends (e.g., local Ollama, vLLM, OpenAI, Anthropic) requires only writing a new class conforming to `BaseLLMProvider` without touching pipeline orchestration or query rewriting.

---

## Decision: Domain Data Models (`models.py`)

### Decision
Standardize all data passing between components into typed dataclasses: `RetrievedChunk`, `ChunkMetadata`, `Message`, and `RAGResponse`.

### Reason
Passing raw unstructured dictionaries (`{"chunk_id": ..., "score": ...}`) resulted in key inconsistencies (`score` vs `dense_score` vs `rrf_score`) and runtime errors.

### Consequence
Strong typing and autocomplete for developers, with built-in backward compatibility via `__getitem__` and `.get()` to ensure legacy scripts continue functioning without disruption.

---

## Decision: Abstract Protocols / Interfaces (`interfaces.py`)

### Decision
Define architectural boundaries using Python `typing.Protocol` (`BaseRetriever`, `BaseReranker`, `BaseLLMProvider`, `BaseConversationMemory`) marked with `@runtime_checkable`.

### Reason
Protocols enable structural subtyping (duck typing with static checking) without requiring rigid inheritance hierarchies from a third-party framework.

### Consequence
Components can be tested in total isolation using lightweight mocks without spinning up PyTorch models or network connections.

---

## Decision: Sliding Window Conversation Memory

### Decision
Implement in-memory sliding conversation buffer (`ConversationMemory`) capped at recent interaction turns (default 6 messages).

### Reason
*Architectural rationale inferred from the current design.*
Full multi-turn history grows indefinitely and overflows prompt token limits. A sliding window of 6 messages provides sufficient dialogue context for resolving follow-up questions while bounding token consumption.

### Consequence
Conversation state remains lean, fast, and does not require an external session database for CLI usage.

---

## Decision: Standalone Multi-Turn Query Rewriting

### Decision
Rewrite conversational follow-up questions (e.g., *"Why is it important?"*) into standalone search queries before executing retrieval.

### Reason
Retrieval algorithms (both dense vectors and BM25) perform poorly on pronouns, ellipses, and context-dependent questions. Resolving context at the query stage ensures optimal retrieval performance.

### Consequence
Retrieval precision remains high throughout multi-turn dialogues without polluting vector representations with conversational dialogue history.

---

## Decision: Lazy Resource Loading

### Decision
Defer all heavyweight resource initializations (BGE SentenceTransformer, CrossEncoder weights, Qdrant client connection, BM25 corpus parsing) until first invocation.

### Reason
Loading multiple gigabytes of transformer weights at import time slows down test suites, CLI startup, and simple administrative tasks.

### Consequence
Importing `app` or running unit tests executes in milliseconds. Resources are allocated only when a search or generation task is actually performed.

---

## Decision: Intentional Compatibility Wrappers

### Decision
Retain legacy module files (`retriever.py`, `bm25_retriever.py`, `rrf_fusion.py`, `hybrid_reranker.py`, `rag_pipeline.py`, `llm.py`) as thin wrappers delegating to the new modular classes.

### Reason
The project includes existing evaluation benchmarks and diagnostic scripts developed across earlier project phases. Deleting legacy modules would break these tools.

### Consequence
Complete backward compatibility is preserved. Legacy benchmarks continue to run cleanly while the core application runs on the new modular architecture.

---

## Decision: Centralized Settings Management

### Decision
Centralize all paths, model identifiers, hyperparameters, and credentials in `app.core.config.Settings`.

### Reason
Hardcoded Top-K values, collection names, and model paths scattered across multiple scripts lead to configuration drift and subtle regression bugs.

### Consequence
Any hyperparameter adjustment (e.g., tuning $K$, altering temperature, or changing collection names) is managed in one central file and propagates across all modules.
