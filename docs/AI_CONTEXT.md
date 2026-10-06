# AI Agent Context & Operational Manual

This document provides essential context and instructions for AI coding assistants working on the **Cybersecurity RAG** codebase. Read this document before making any changes.

---

## 1. Project Summary & Purpose

- **Domain**: Cybersecurity question answering grounded exclusively in National Institute of Standards and Technology (NIST) Special Publications.
- **Goal**: Deliver precise, factual, citation-backed answers while preventing hallucinations, unsupported claims, or speculative extensions.
- **Core Technology Stack**:
  - **Vector Database**: Embedded Qdrant (local filesystem at `data/qdrant`)
  - **Dense Embedding Model**: `BAAI/bge-small-en-v1.5` (384-dimensional cosine similarity)
  - **Keyword Retriever**: Rank-BM25 over 7,703 indexed chunk documents
  - **Fusion Algorithm**: Reciprocal Rank Fusion (RRF) with constant $K=60$
  - **Reranker Model**: Cross-Encoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`)
  - **LLM Provider**: Groq Cloud API running `openai/gpt-oss-20b` (temperature = 0.0)
  - **Orchestration**: Custom lightweight orchestrator (`RAGEngine`), zero external agent framework dependencies.

---

## 2. Invariant Architectural Rules

When modifying or extending this repository, you **MUST** adhere to the following architectural rules:

1. **Strict Layered Dependencies**:
   - `main.py` $\rightarrow$ `app.pipeline` $\rightarrow$ (`app.conversation`, `app.retrieval`, `app.generation`) $\rightarrow$ `app.core`
   - `app.core` must **NEVER** import from retrieval, generation, conversation, or pipeline.
   - `app.retrieval` must **NEVER** import from generation, conversation, or pipeline.
   - `app.generation` must **NEVER** import from retrieval or pipeline.
   - Circular imports are strictly forbidden.

2. **Public Protocol Compliance**:
   - All retrieval modules must implement `app.core.interfaces.BaseRetriever`.
   - All reranker modules must implement `app.core.interfaces.BaseReranker`.
   - All LLM providers must implement `app.core.interfaces.BaseLLMProvider`.
   - All memory buffers must implement `app.core.interfaces.BaseConversationMemory`.
   - Consumers must depend on these abstract protocols, not concrete classes.

3. **Centralized Configuration**:
   - Never hardcode model identifiers, paths, Top-K limits, or constants in components.
   - Access all configuration through `from app.core.config import settings`.
   - Never print, log, or hardcode API keys.

4. **Lazy Resource Loading**:
   - Heavy dependencies (PyTorch weights, HuggingFace models, Qdrant client, BM25 indices) must **NOT** be initialized at import time.
   - Defer all heavy initialization until the first `retrieve()`, `rerank()`, or `generate()` call.

5. **Pure Context Builder**:
   - `app/generation/build_context.py` has exactly one responsibility: formatting retrieved/reranked documents into a prompt context string.
   - It must **never** perform retrieval, search, or ranking.

6. **Single Source of Truth**:
   - `RAGEngine` in `app/pipeline/engine.py` is the single authoritative orchestrator. Do not replicate pipeline orchestration across other scripts.

---

## 3. Key Entry Points & Public API

- **CLI Application**: `python main.py`
  - Interactive CLI using streaming output and conversational memory.
- **Orchestrator Instance**:
  ```python
  from app.pipeline.engine import RAGEngine
  engine = RAGEngine()
  response = engine.query("What is least privilege?", stream=False)
  print(response.answer)
  for source in response.sources:
      print(source.chunk_id, source.reranker_score)
  ```
- **Domain Models** (`app.core.models`):
  - `RetrievedChunk`: Holds chunk text, metadata, scores (`score`, `dense_score`, `bm25_score`, `rrf_score`, `reranker_score`). Supports dict-style access for backwards compatibility.
  - `ChunkMetadata`: Holds document ID, category, source file, section, and token count.
  - `Message`: Represents a conversation turn (`user`, `assistant`).
  - `RAGResponse`: Standardized output with `question`, `standalone_question`, `answer`, and `sources`.

---

## 4. Verification & Testing Commands

Before submitting any work, run these tests to verify zero regressions:

```powershell
# 1. Run unit test suite
$env:PYTHONUTF8=1; python -m unittest discover -s tests

# 2. Run retrieval benchmarks
$env:PYTHONUTF8=1; python evaluation/evaluate_retrieval_metrics.py
$env:PYTHONUTF8=1; python evaluation/evaluate_rrf.py
$env:PYTHONUTF8=1; python evaluation/evaluate_reranked_retrieval.py

# 3. Test LLM connectivity
$env:PYTHONUTF8=1; python tests/test_llm.py

# 4. Test Embedding model
$env:PYTHONUTF8=1; python tests/embed_small_test.py
```

---

## 5. Established Performance Baselines

The modular architecture matches the verified pre-modularization baseline with 100% parity:

| Stage | Metric | Baseline Target |
| :--- | :--- | :--- |
| **Dense (BGE-small)** | Hit@1 / Hit@3 / Hit@5 / MRR | 73.33% / 86.67% / 93.33% / 0.8022 |
| **Hybrid (Dense + BM25 + RRF)** | Hit@1 / Hit@3 / Hit@5 / MRR | 86.67% / 100.00% / 100.00% / 0.9333 |
| **Cross-Encoder Reranker** | Hit@1 / Hit@3 / Hit@5 / MRR | 73.33% / 100.00% / 100.00% / 0.8556 |

**Ground-Truth Limitation Rule**:
Some benchmark questions have exact chunk-ID annotations. In rare cases (e.g. Q2), the Cross-Encoder ranks a semantically valid chunk higher than the designated annotation. **Never** silently modify `data/evaluation/*.json` to inflate metrics. Always preserve the baseline.

---

## 6. What NOT To Do

- **DO NOT** install or introduce heavy orchestration frameworks (LangChain, LlamaIndex, Haystack, AutoGen).
- **DO NOT** introduce external observability frameworks without explicit approval.
- **DO NOT** delete compatibility wrappers (`bm25_retriever.py`, `rrf_fusion.py`, `retriever.py`, `hybrid_reranker.py`, `rag_pipeline.py`, `llm.py`). Existing benchmark scripts and tools rely on them.
- **DO NOT** commit `.env`, `data/qdrant/`, `data/chunks/`, or model caches to Git.
- **DO NOT** run `git commit` or `git push` unless explicitly asked by the user.
