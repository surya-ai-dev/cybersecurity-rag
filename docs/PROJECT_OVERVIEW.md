# Project Overview — Cybersecurity RAG

## 1. Executive Summary & Problem Statement

General-purpose Large Language Models (LLMs) often hallucinate factual details or lack deep, authoritative knowledge on specialized cybersecurity frameworks, standards, and guidelines. In enterprise and high-assurance security environments, generating incorrect guidance (e.g., inaccurate access control recommendations, fabricated compliance requirements, or flawed cryptographic parameters) introduces severe operational and security risks.

This project implements a production-oriented, specialized **Retrieval-Augmented Generation (RAG)** system designed specifically for the cybersecurity domain. By constraining generation exclusively to authoritative National Institute of Standards and Technology (NIST) Special Publications, the system provides grounded, citation-backed answers while preventing hallucinations and speculative extensions.

---

## 2. Project Goals

1. **High Factual Accuracy**: Guarantee that every generated claim is directly supported by authoritative source documents.
2. **Transparent Citations**: Map every answer statement to traceable citations (`[Source X]`) detailing document titles, sections, and IDs.
3. **Advanced Hybrid Retrieval**: Overcome the vocabulary mismatch of dense embeddings and the semantic blindness of keyword search by fusing dense vector search and BM25 using Reciprocal Rank Fusion (RRF).
4. **Precision Reranking**: Utilize a cross-encoder model to re-score candidate chunks based on deep query-document cross-attention before generation.
5. **Clean Modular Architecture**: Provide decoupled, protocol-based components that support testing, independent scaling, and zero-downtime component swaps without framework bloat.

---

## 3. Domain & Corpus

The knowledge base is built from foundational NIST Special Publications:
- **NIST SP 800-53 Rev. 5**: Security and Privacy Controls for Information Systems and Organizations.
- **NIST SP 800-144**: Guidelines on Security and Privacy in Public Cloud Computing.
- **NIST SP 800-146**: Cloud Computing Synopsis and Recommendations.
- **NIST SP 800-46 Rev. 2**: Guide to Enterprise Telework, Remote Access, and BYOD Security.
- **NIST SP 800-125**: Guide to Security in Full Virtualization Technologies.
- **NIST SP 800-205 / SP 800-215 / SP 800-223 / SP 800-111**: Cryptographic key management, microsegmentation, security baselines, and storage encryption.

The indexed corpus consists of **7,703 chunks** extracted, cleaned, and chunked with token-aware sliding windows and rich metadata (document ID, section heading, token count, source file).

---

## 4. Technology Stack

- **Language & Runtime**: Python 3.12 (managed via `uv`)
- **Dense Vector Search**: Qdrant (embedded local database at `data/qdrant`)
- **Dense Embeddings**: `BAAI/bge-small-en-v1.5` (SentenceTransformers, 384 dimensions)
- **Sparse / Keyword Search**: Rank-BM25 (`rank_bm25` Okapi implementation)
- **Fusion**: Reciprocal Rank Fusion (RRF, $K=60$)
- **Reranker**: Cross-Encoder `cross-encoder/ms-marco-MiniLM-L-6-v2`
- **LLM Provider**: Groq Cloud API (`openai/gpt-oss-20b`, temperature = 0.0)
- **Configuration & Environment**: Centralized dataclass (`app/core/config.py`) via `python-dotenv`
- **Testing**: Python standard library `unittest`

---

## 5. Core Pipeline Overview

The request lifecycle executes through seven modular steps:

1. **User Question**: Input accepted via interactive CLI (`main.py`) or programmatic API (`RAGEngine.query()`).
2. **Conversation Context**: Recent conversation history fetched from `ConversationMemory`.
3. **Query Rewriting**: Context-dependent queries (e.g., *"Why is it important?"*) rewritten by `QueryRewriter` into standalone queries using the LLM.
4. **Hybrid Retrieval**:
   - Dense vector retrieval returns Top-20 chunks from Qdrant.
   - BM25 keyword search returns Top-20 chunks from the in-memory inverted index.
   - Reciprocal Rank Fusion combines the ranked lists into Top-20 fused candidates.
5. **Cross-Encoder Reranking**: Re-scores candidate pairs `(query, chunk_text)` using cross-attention, returning the Top-5 most relevant chunks.
6. **Context Building**: Formats Top-5 chunks into structured `SOURCE [X]` blocks without performing retrieval.
7. **LLM Generation**: Streams grounded answers from Groq, enforces strict anti-hallucination prompt rules, records turns to memory, and outputs structured `RAGResponse`.

---

## 6. System Capabilities

- **Multi-Turn Continuity**: Maintains sliding conversation window (last 6 messages) and resolves pronouns across turns.
- **Real-Time Streaming**: Delivers low-latency token streaming to terminal or UI.
- **Source Transparency**: Outputs document IDs, file origins, section titles, and reranker scores alongside answers.
- **Lazy Resource Loading**: Fast startup with zero model weights or database locks initialized until first query execution.
- **100% Interface Driven**: All components adhere to abstract protocols (`BaseRetriever`, `BaseReranker`, `BaseLLMProvider`, `BaseConversationMemory`).

---

## 7. Current Architecture

```text
main.py
  │
  ▼
RAGEngine (app/pipeline/engine.py)
  ├── ConversationMemory (app/conversation/conversation_memory.py)
  ├── QueryRewriter (app/conversation/query_rewriter.py)
  ├── HybridRetriever (app/retrieval/hybrid.py)
  │     ├── DenseRetriever (app/retrieval/dense.py)
  │     ├── BM25Retriever (app/retrieval/bm25.py)
  │     └── RRFFusion (app/retrieval/rrf.py)
  ├── CrossEncoderReranker (app/retrieval/reranker.py)
  ├── ContextBuilder (app/generation/build_context.py)
  └── GroqProvider (app/generation/providers/groq_provider.py)
```

---

## 8. Project Structure

```text
cybersecurity-rag/
├── app/                  # Modular application package
│   ├── core/             # Configuration, domain models, interfaces
│   ├── retrieval/        # Dense, BM25, RRF, Hybrid, and Reranker
│   ├── generation/       # Context builder and Groq LLM provider
│   ├── conversation/     # Memory buffer and query rewriter
│   ├── pipeline/         # RAGEngine orchestrator
│   └── ingestion/        # Document extraction and Qdrant ingestion
├── evaluation/           # Retrieval & reranker benchmark suite
├── tests/                # Unit and integration test suite
├── scripts/              # Diagnostic utilities
├── data/                 # Datasets and local databases (ignored by git except evaluation/)
│   └── evaluation/       # Version-controlled ground-truth benchmarks
├── docs/                 # Architectural documentation & project knowledge
├── main.py               # Interactive CLI entry point
├── pyproject.toml        # Dependencies and packaging
└── README.md             # Project quickstart
```

---

## 9. Current Development Status

- **Status**: Steps 1–9 Complete and fully verified.
- **Audit State**: Architectural modularization completed with zero functional regressions against previous baselines.
- **Git Status**: Working tree contains all refactored files unstaged/uncommitted, waiting for explicit user approval before final commit.

---

## 10. Known Limitations

1. **Exact-ID Annotation Sensitivity**: The benchmark evaluation penalizes alternate chunks that discuss the same topic if they do not match the single designated chunk ID in ground truth.
2. **Context Window & Top-N Constraint**: Reranking currently selects Top-5 chunks (approx. 1,500–2,000 tokens) to minimize latency and context overflow. Very broad queries spanning dozens of topics may require broader context.
3. **No Metadata Filtering Yet**: Search currently operates across all documents without user-specified filters for publication year or specific NIST publication number.

---

## 11. Future Direction

Future iterations will focus on advancing RAG quality:
- Metadata filtering by NIST publication number and security control families.
- Adaptive query routing and corrective retrieval (CRAG).
- Contextual chunk embeddings to capture broader chapter context.
- Automated generation grounding metrics (faithfulness and citation accuracy).
