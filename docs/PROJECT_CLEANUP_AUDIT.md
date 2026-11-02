# Cybersecurity RAG — Repository Clean-Up and Architecture Audit Report

**File Path:** `docs/PROJECT_CLEANUP_AUDIT.md`  
**Repository Root:** `C:\Users\Computer\Desktop\cybersecurity-rag`  
**Audit Date:** October 21, 2026  
**Auditor:** Senior Python & AI Infrastructure Engineer  
**Audit Status:** Phase 1 Complete (Audit Only — Zero Files Deleted or Modified)  

---

## Executive Summary

An exhaustive repository inspection was conducted across all 4,654 files in the `cybersecurity-rag` project. The objective is to identify obsolete, duplicate, temporary, and unneeded assets, classify all files into 12 structured architectural tiers, and define a safe, non-destructive clean-up strategy that maintains the operational integrity of the live RAG pipeline (`BAAI/bge-m3` dense retrieval, BM25 keyword search, RRF hybrid fusion, confidence evaluation, adaptive query rewriting, cross-encoder reranking, context building, and Groq LLM generation).

> [!IMPORTANT]
> **Safety Guarantee:** In compliance with Phase 2 rules, **no files have been moved, deleted, renamed, or modified.** All production corpus chunks (13,084 records), embeddings (`BAAI/bge-m3`), Qdrant collections, ground-truth evaluations, application source code, and uncommitted Git changes are preserved in their current state.

---

## 1. High-Level Repository Structure

The current repository is organized into the following top-level directories:

```
cybersecurity-rag/
├── app/                          # Core application logic (Pipeline, Retrieval, Generation, Core, Ingestion)
│   ├── conversation/             # Conversation history memory and multi-turn query rewriting
│   ├── core/                     # Central configuration (Pydantic Settings), interfaces, models
│   ├── generation/               # LLM prompt context construction, generator, and Groq provider
│   ├── ingestion/                # Document extraction, text cleaning, chunking, and embedding logic
│   ├── pipeline/                 # High-level RAGEngine orchestrator and legacy pipeline wrappers
│   └── retrieval/                # Dense (BGE-M3/Qdrant), BM25, RRF, Confidence, QueryRewriter, Reranker
├── data/                         # Authoritative corpus data, embeddings, vectors, and evaluation sets
│   ├── chunks_corpus/            # Production corpus chunks (64 JSONL files, 9,909 chunks)
│   ├── chunks_pilot/             # Production pilot chunks (11 JSONL files, 3,175 chunks)
│   ├── cleaned_corpus/           # Checkpointed cleaned documents (697 files)
│   ├── cleaned_pilot/            # Cleaned pilot document text (187 files)
│   ├── document_inventory/       # CSV and JSON metadata manifests of all 73 NIST documents
│   ├── embeddings_bge_m3/        # 1024-dim numpy embeddings, manifest, and metadata jsonl
│   ├── evaluation/               # Official benchmark questions and ground-truth JSON files
│   ├── extraction_*/             # Milestone extraction directories from earlier pipeline phases
│   └── qdrant/                   # Embedded Qdrant SQLite vector database storage
├── docs/                         # Technical specifications, architecture docs, guides, and ADRs
├── documents/                    # 73 authoritative NIST Special Publication source PDFs
├── evaluation/                   # Formal retrieval benchmark evaluation scripts and CLI runners
├── reports/                      # Benchmark outputs, forensic error reports, and cleaning analytics
├── scratch/                      # Ad-hoc experimental scripts, page-by-page diagnostics, and OCR data
├── scripts/                      # Production runners (ingestion, cleaning, chunking) and ad-hoc scripts
├── tests/                        # Automated unit and integration test suites (167 passing tests)
├── .env                          # Secret-bearing environment configuration (Protected)
├── .gitignore                    # Version control exclusion rules
├── .python-version               # Python version pinning (3.12)
├── CHUNKING_IMPLEMENTATION_PLAN.md # Authoritative Stage 4 chunking specification
├── main.py                       # Primary CLI interactive application entry point
├── PROJECT_HANDOVER.md           # Engineering handover document
├── pyproject.toml                # Project metadata, dependencies, and build configuration
├── README.md                     # Project documentation and quickstart guide
├── uv.lock                       # Deterministic dependency lockfile
└── __pycache__/                  # Stale root-level Python bytecode cache
```

---

## 2. Comprehensive 12-Category Repository Classification

### Category 1: Core Application Code Required by the Active Pipeline
These files implement the active RAG system. They are actively imported and executed by `main.py`, `app.pipeline.engine.RAGEngine`, and the test suites. **Must be strictly preserved.**

| Relative File Path | Component | Functional Role & Active Pipeline Dependencies |
| :--- | :--- | :--- |
| `main.py` | Interactive CLI | Root entry point for terminal interaction; instantiates `RAGEngine`. |
| `app/pipeline/engine.py` | Orchestration | Core `RAGEngine` class unifying retrieval, confidence, rewriting, reranking, and generation. |
| `app/core/config.py` | Configuration | Pydantic `Settings` loading `.env`, vector dimensions, model names, and feature flags. |
| `app/core/models.py` | Domain Models | Pydantic data schemas: `RetrievedChunk`, `ChunkMetadata`, `QueryResponse`, `ConfidenceDecision`. |
| `app/core/interfaces.py` | Abstract Bases | `BaseRetriever`, `BaseLLMProvider`, and `BaseConversationMemory` protocols. |
| `app/retrieval/retriever.py` | Retrieval Facade | High-level `retrieve()` functional interface delegating to `HybridRetriever`. |
| `app/retrieval/hybrid.py` | Hybrid Retriever | `HybridRetriever` combining `DenseRetriever` and `BM25Retriever` via `RRFFusion`. |
| `app/retrieval/dense.py` | Dense Search | BGE-M3 query vector encoding and embedded Qdrant cosine similarity search. |
| `app/retrieval/bm25.py` | Sparse Search | `BM25Retriever` tokenization and BM25Okapi scoring over all 13,084 corpus chunks. |
| `app/retrieval/rrf.py` | Rank Fusion | `RRFFusion` implementing Reciprocal Rank Fusion ($k=60$) over multiple candidate lists. |
| `app/retrieval/confidence.py` | Confidence Logic | `ConfidenceEvaluator`, `extract_dense_score()`, and metric-aware `merge_candidate_pools()`. |
| `app/retrieval/query_rewriter.py` | Retrieval Rewriting | LLM-driven query rewriting and domain expansion using Groq API. |
| `app/retrieval/reranker.py` | Cross-Encoder | `CrossEncoderReranker` using `cross-encoder/ms-marco-MiniLM-L-6-v2`. |
| `app/generation/build_context.py` | Context Building | Assembles retrieved chunks into formatted LLM prompts with stage-aware score labeling. |
| `app/generation/llm.py` | Generation | `LLMGenerator` formatting prompts and managing stream responses. |
| `app/generation/providers/groq_provider.py` | LLM Provider | Groq client wrapper handling completions, streaming, and error fallbacks. |
| `app/conversation/conversation_memory.py` | Memory | Multi-turn message buffer maintaining user and assistant conversational history. |
| `app/conversation/query_rewriter.py` | Conversational Rewriter | Rewrites follow-up questions into standalone queries using prior dialogue turns. |

### Category 2: Configuration Files and Environment Templates
Critical project environment files and dependency declarations. **Must be strictly preserved.**

| Relative File Path | Role | Protection Notes |
| :--- | :--- | :--- |
| `.env` | Active Secrets & Environment | Contains `GROQ_API_KEY`, Qdrant paths, model names. **Never commit, delete, or log.** |
| `pyproject.toml` | Project Dependencies | Defines Python `>=3.12` and locked library versions (PyMuPDF, Qdrant, sentence-transformers, etc.). |
| `uv.lock` | Lockfile | Deterministic lockfile generated by `uv` for reproducible builds. |
| `.python-version` | Python Version | Specifies `3.12` runtime environment. |
| `.gitignore` | Git Rules | Excludes `.venv/`, `.env`, `data/*`, `documents/`, and `/scratch/`. |

### Category 3: Document Ingestion, Chunking, and Embedding Scripts
Modules that construct the corpus from raw PDFs to cleaned, chunked, and embedded representations. **Preserve for corpus lifecycle maintenance.**

| Relative File Path | Component | Functional Purpose |
| :--- | :--- | :--- |
| `app/ingestion/chunking/*` (8 files) | Chunking Subsystem | Structure-aware text, table, and figure chunkers (`runner.py`, `pipeline.py`, etc.). |
| `app/ingestion/cleaning/*` (6 files) | Cleaning Subsystem | Text sanitization, encoding repair, header/footer removal, and hyphenation stitching. |
| `app/ingestion/extraction/*` (11 files) | Extraction Subsystem | PyMuPDF/Docling layout extraction, table detection, OCR, and figure filtering. |
| `app/ingestion/extract_text.py` | Extraction Entry | High-level text extraction coordinator. |
| `app/ingestion/clean_text.py` | Cleaning Entry | High-level text cleaning coordinator. |
| `app/ingestion/chunk_documents.py` | Chunking Entry | Document chunking orchestrator. |
| `app/ingestion/embed_documents.py` | Embedding Entry | BGE-M3 embedding generator. |
| `app/ingestion/build_qdrant.py` | DB Construction | Vector collection initialization in Qdrant. |
| `scripts/run_corpus_extraction.py` | Production Runner | Batch-wise PDF extraction with checkpointing. |
| `scripts/run_corpus_cleaning.py` | Production Runner | Batch-wise corpus cleaning with checkpointing. |
| `scripts/run_corpus_chunking.py` | Production Runner | Production chunking over cleaned corpus. |
| `scripts/generate_full_corpus_embeddings.py` | Production Runner | Generates the 1024-dim BGE-M3 vectors in `data/embeddings_bge_m3/`. |
| `scripts/ingest_embeddings_qdrant.py` | Production Runner | Ingests vectors into Qdrant collection `cybersecurity_chunks_bge_m3`. |
| `scripts/scan_document_inventory.py` | Inventory Scanner | Generates document inventories and page counts across all 73 PDFs. |

### Category 4: Existing Corpus, Embeddings, and Qdrant Database Artifacts
The underlying cybersecurity knowledge repository (**13,084 total chunks**). **Protected by Phase 2 rules — Do not delete or regenerate.**

| Relative Directory / File Path | Items | Size | Purpose & Integrity Status |
| :--- | :--- | :--- | :--- |
| `documents/` | 73 PDFs | ~250 MB | Authoritative NIST Special Publication source documents across 10 security domains. |
| `data/chunks_corpus/` | 64 files | 17.46 MB | Authoritative JSONL chunk files for 63 full corpus documents (9,909 chunks). |
| `data/chunks_pilot/` | 11 files | 5.77 MB | Authoritative JSONL chunk files for 10 pilot documents (3,175 chunks). |
| `data/embeddings_bge_m3/` | 109 files | 109.64 MB | `embeddings.npy` (53.59 MB, 13,084 vectors), `chunk_metadata.jsonl`, `manifest.json`. |
| `data/qdrant/` | 3 files | 150.27 MB | Embedded vector store: `collection/cybersecurity_chunks_bge_m3/storage.sqlite`. |
| `data/cleaned_corpus/` | 697 files | 107.85 MB | Checkpointed cleaned Markdown text and metadata manifests for corpus. |
| `data/cleaned_pilot/` | 187 files | 43.64 MB | Cleaned Markdown text and manifests for pilot documents. |
| `data/document_inventory/` | 3 files | 2.59 MB | `document_inventory.csv`, `document_inventory.json`, `page_inventory.csv`. |

### Category 5: Evaluation Scripts and Official Ground-Truth Datasets
The formal benchmark evaluation harness used to measure Hit@K, MRR, and Recall@K. **Must be strictly preserved.**

| Relative File Path | Component | Purpose |
| :--- | :--- | :--- |
| `data/evaluation/evaluation_questions.json` | Benchmark Questions | 40 official questions (Q1–Q40) covering public cloud, incident response, zero trust, etc. |
| `data/evaluation/retrieval_ground_truth_current.json` | Baseline Ground Truth | 20 entries (15 evaluation-eligible: Q1–Q13, Q16, Q17, Q19, Q20) mapped to verified chunk IDs. |
| `data/evaluation/retrieval_ground_truth_additional_20.json` | Additional Ground Truth | 20 entries (20 evaluation-eligible: Q21–Q40 across 20 distinct NIST publications). |
| `evaluation/evaluate_retrieval_metrics.py` | Primary Evaluator | Authoritative 50 KB benchmark script supporting `--eval-set baseline\|additional\|all`. |
| `evaluation/run_full_evaluation.py` | Unified Runner | Terminal UI running complete evaluation suites with tabular reporting. |
| `evaluation/evaluate_hybrid_retrieval.py` | Hybrid Evaluator | Evaluates dense vs. BM25 vs. hybrid fusion retrieval. |
| `evaluation/evaluate_reranked_retrieval.py` | Reranker Evaluator | Evaluates cross-encoder reranking quality and latency. |
| `evaluation/evaluate_bm25.py` | BM25 Evaluator | Dedicated evaluation for BM25 keyword retrieval. |
| `evaluation/evaluate_rrf.py` | RRF Evaluator | Dedicated benchmark evaluating RRF $k$ hyperparameter variations. |
| `evaluation/analyze_reranker.py` | Score Analyzer | Analyzes score distributions and rank movements under cross-encoder reranking. |

### Category 6: New `question_evaluvation/` Dataset
Status of the new 15-question evaluation suite:
- **Directory:** `question_evaluvation/`
- **Current Status:** Staged and fully verified in memory and scratch logs; 15 questions (`Q041` through `Q055`) covering the 15 requested topic areas with 100% verified chunk mappings to non-overlapping corpus records. Ready to be committed to disk as a dedicated evaluation directory upon user approval.

### Category 7: Unit Tests and Integration Tests
The active test suite ensuring zero regressions across all components. All 167 tests pass cleanly (`Ran 167 tests in 91.954s - OK`). **Must be strictly preserved.**

| Relative Test File | Test Suite Scope | Test Count |
| :--- | :--- | :--- |
| `tests/test_pipeline_integration.py` | End-to-end RAGEngine retrieval, scoring, confidence, and generation | 11 tests |
| `tests/test_adaptive_query_rewriter.py` | Adaptive query rewriting, confidence triggers, and safe fallbacks | 8 tests |
| `tests/test_query_rewriter.py` | LLM query rewriter system prompt, Groq integration, and entity preservation | 8 tests |
| `tests/test_cross_encoder_reranker.py` | Reranker initialization, candidate pool combining, and top-N ranking | 5 tests |
| `tests/test_rrf_hybrid_retrieval.py` | Reciprocal Rank Fusion, $k$-factor weighting, and candidate ranking | 7 tests |
| `tests/test_modular_rag.py` | Modular component registration and interfaces | 6 tests |
| `tests/test_chunking_pipeline.py` | Table, figure, and text chunking structure-awareness | 32 tests |
| `tests/test_cleaning_pipeline.py` | Hyphenation, encoding, and header/footer cleaning rules | 14 tests |
| `tests/test_corpus_cleaning_runner.py` | Production cleaning runner, checkpointing, and error handling | 12 tests |
| `tests/test_corpus_extraction_runner.py` | Production extraction runner, process pool, and quality gate | 14 tests |
| `tests/test_document_corrections.py` | NIST SP document layout correction rules | 9 tests |
| `tests/test_extraction_quality.py` | Layout parser table structure and markdown export validation | 15 tests |
| `tests/test_figure_filter.py` | Uninformative figure filtering logic | 8 tests |
| `tests/test_hybrid_pipeline_integration.py` | Hybrid layout extraction pipeline end-to-end | 7 tests |
| `tests/test_llm.py` | Groq LLM provider instantiation and generation | 3 tests |
| `tests/test_models_markdown_export.py` | Document model markdown serialization and deduplication | 8 tests |

### Category 8: Temporary Debugging Scripts and One-Off Diagnostic Files
Scripts created during specific debugging sessions, manual investigations, or micro-benchmarks that are not part of the active pipeline or regular test suites. **Candidates for clean-up or archiving.**

| Relative File Path | Size | Reason It Is Classified as Temporary / Diagnostic |
| :--- | :--- | :--- |
| `scripts/inspect_q6.py` | 1.9 KB | Ad-hoc script querying obsolete collection `"cybersecurity_chunks"` with `bge-small` specifically for Q6. |
| `scripts/evaluate_q10_q13_q19.py` | 8.2 KB | One-off diagnostic evaluating only Q10, Q13, and Q19 during pipeline integration. |
| `scripts/test_three_reranker_questions.py` | 3.6 KB | One-off script testing cross-encoder reranker latency on Q10, Q13, Q19. |
| `scripts/inspect_bge_reranking.py` | 26.1 KB | Interactive CLI tool written to manually inspect BGE reranking outputs. |
| `scripts/search_qdrant.py` | 6.7 KB | Ad-hoc CLI vector search utility. |
| `tests/embed_test.py` | 2.7 KB | Ad-hoc manual script with `def main():` attempting to load non-existent `data/chunks/`. Not a unit test. |
| `tests/embed_small_test.py` | 2.1 KB | Ad-hoc manual script testing `bge-small` on non-existent `data/chunks/`. Not a unit test. |
| `scratch/` (Entire folder — 79 files, 23 dirs) | 31.25 MB | Contains ad-hoc page tests (`test_p60_line_by_line.py`), OCR models (`.traineddata`), test images, and log files. |

### Category 9: Duplicate, Obsolete, or Superseded Files
Files that have been superseded by newer implementations, are identical duplicates, or are empty (0 bytes). **Safe to remove.**

| Relative File Path | Size | Exact Evidence of Redundancy |
| :--- | :--- | :--- |
| `evaluation/evaluate_hybrid_weights.py` | **0 bytes** | Completely empty 0-byte file created during hybrid weight tuning; never implemented. |
| `docs/CURRENT_RAG_ARCHITECTURE_1.md` | 34.6 KB | Byte-for-byte identical duplicate of `docs/CURRENT_RAG_ARCHITECTURE.md`. |
| `data/evaluation/ground_truth.json` | 533 bytes | Legacy 5-question pilot ground truth (Q1–Q5). Fully superseded by `retrieval_ground_truth_current.json`. |
| `app/retrieval/hybrid_reranker.py` | 6.9 KB | Early standalone script combining BGE vector weights with cross-encoder; superseded by modular `app/retrieval/reranker.py`. |
| `scripts/benchmark_embeddings_pilot.py` | 11.7 KB | Early pilot benchmark comparing `bge-small` vs `bge-m3`. Superseded by finalized BGE-M3 pipeline. |
| `scripts/benchmark_lightweight_embeddings.py` | 25.7 KB | Early lightweight embedding benchmark. Superseded by full corpus ingestion. |

### Category 10: Logs, Caches, Generated Reports, Temporary Outputs, and Unnecessary Artifacts
Temporary runtime artifacts, backup files, and historical run data.

| Relative File Path / Directory | Items / Size | Nature of Artifact |
| :--- | :--- | :--- |
| `__pycache__/` (at repository root) | 12 files (44 KB) | Stale `.pyc` files compiled from an earlier flat project structure before modules were moved to `app/`. |
| Module-level `__pycache__/` (15 dirs) | 89 files (~350 KB) | Python bytecode cache (`*.pyc`) generated during test execution. Automatically regenerated by Python. |
| `data/evaluation/*.bak` (2 files) | 24.2 KB | Backup copies: `retrieval_ground_truth_current.json.bak` and `retrieval_ground_truth_additional_20.json.bak`. |
| `scratch/diagnostics/NIST_SP_800-116/regression.log` | 1 file (12 KB) | Text log file from a historical extraction regression run. |
| `reports/benchmark_lightweight_results.json` | 17.7 KB | Generated JSON output from the historical lightweight embedding benchmark. |
| `reports/evaluation_q10_q13_q19_summary.json` | 9.0 KB | Generated JSON output from the Q10/Q13/Q19 diagnostic evaluation run. |
| `reports/*.csv` (5 files) | 143.8 KB | Generated quality analytics CSVs (`corpus_quality_issues.csv`, `corpus_duplicate_candidates.csv`, etc.). |
| `data/extraction_*` (10 directories) | 3,149 files (254 MB) | Intermediate extraction output folders from earlier development stages (see Section 6). |

### Category 11: Documentation and Architecture Diagrams
Architectural documentation, developer logs, and guidelines. **Preserve for project continuity.**

| Relative File Path | Document Title & Purpose |
| :--- | :--- |
| `docs/CURRENT_RAG_ARCHITECTURE.md` | Authoritative end-to-end architecture documentation for the live pipeline. |
| `docs/ARCHITECTURE.md` | Modular architecture and subsystem design specification. |
| `docs/AI_CONTEXT.md` | System context and architectural overview for AI engineering assistants. |
| `docs/PROJECT_OVERVIEW.md` | High-level system overview, motivation, and technology stack. |
| `docs/DEVELOPMENT_LOG.md` | Chronological development log tracking phases, bugs, and fixes. |
| `docs/DECISIONS.md` | Architectural Decision Records (ADRs). |
| `docs/EVALUATION.md` | Formal evaluation methodology and metrics definitions. |
| `docs/NEXT_STEPS.md` | Engineering roadmap, future enhancements, and pending work. |
| `docs/FULL_CORPUS_EMBEDDING_PIPELINE.md` | Operational runbook for running the full-corpus BGE-M3 embedding pipeline. |
| `docs/LIGHTWEIGHT_BENCHMARK_GUIDE.md` | Operational guide for lightweight embedding benchmark execution. |
| `docs/chunking_stage0_discovery.md` | Technical discovery findings for document chunking. |
| `docs/chunking_stage1_design.md` | Detailed architectural design for structure-aware chunking. |
| `README.md` | Project introduction, architecture diagram, and usage commands. |
| `PROJECT_HANDOVER.md` | Complete engineering handover document. |
| `CHUNKING_IMPLEMENTATION_PLAN.md` | Stage 4 chunking single source-of-truth implementation plan. |

### Category 12: Dependencies, Git Files, and Development-Tool Configuration
Tooling, dependency management, and version control configuration. **Must be strictly preserved.**

| Relative File Path | Role |
| :--- | :--- |
| `pyproject.toml` | Build system and runtime dependency definitions. |
| `uv.lock` | Exact package hashes and resolved versions. |
| `.python-version` | Python interpreter version specification (3.12). |
| `.gitignore` | Exclusion patterns preventing secrets and bloated artifacts from entering Git. |
| `.git/` | Git version control repository history. |

---

## 3. Files Required by the Active Pipeline and Why

The production RAG pipeline operates along a strict query execution path:

```
User Query (main.py)
   │
   ▼
RAGEngine.query() / .stream() (app/pipeline/engine.py)
   │
   ├──▶ Multi-Turn Resolution: rewrite_question() (app/conversation/query_rewriter.py)
   │
   ├──▶ Candidate Retrieval: HybridRetriever.retrieve() (app/retrieval/hybrid.py)
   │       ├── Dense Vector Search: DenseRetriever (app/retrieval/dense.py) -> Qdrant (data/qdrant/)
   │       ├── Keyword BM25 Search: BM25Retriever (app/retrieval/bm25.py) -> Chunks (data/chunks_*)
   │       └── Reciprocal Rank Fusion: RRFFusion (app/retrieval/rrf.py)
   │
   ├──▶ Confidence Evaluation: ConfidenceEvaluator (app/retrieval/confidence.py)
   │       └── If Low Confidence: QueryRewriter (app/retrieval/query_rewriter.py) -> Groq API
   │
   ├──▶ Candidate Pool Merging: merge_candidate_pools() (app/retrieval/confidence.py)
   │
   ├──▶ Optional Cross-Encoder Reranking: CrossEncoderReranker (app/retrieval/reranker.py)
   │
   ├──▶ Context Assembly: build_rag_context() (app/generation/build_context.py)
   │
   └──▶ Grounded Answer Generation: LLMGenerator (app/generation/llm.py) -> GroqProvider
```

Every file participating in this chain is **critical**. Removing any of these files will immediately break interactive queries, evaluation benchmarks, or unit tests.

### Compatibility Wrappers in `app/`
The following files act as backward-compatibility wrappers for legacy code:
- `app/retrieval/bm25_retriever.py` (exports `BM25Retriever` from `app.retrieval.bm25`)
- `app/retrieval/rrf_fusion.py` (exports `RRFFusion` from `app.retrieval.rrf`)
- `app/pipeline/rag_pipeline.py` (exports `RAGEngine` functional delegates from `app.pipeline.engine`)
- `app/retrieval/retriever.py` (exports functional `retrieve()` from `app.retrieval.hybrid`)

> [!NOTE]
> While these 4 compatibility files are technically redundant with their modern counterparts, they currently protect external scripts and legacy tests from `ImportError`. They should be preserved or deprecated gracefully after verifying all call sites.

---

## 4. Duplicate, Obsolete, and Redundant Files (With Evidence)

1. **`evaluation/evaluate_hybrid_weights.py`**
   - **Evidence:** File size is exactly **0 bytes**. Contains no code, classes, or imports.
   - **Status:** Obsolete / Abandoned stub.

2. **`docs/CURRENT_RAG_ARCHITECTURE_1.md`**
   - **Evidence:** Created as an identical mirror of `docs/CURRENT_RAG_ARCHITECTURE.md` (34,611 bytes vs 34,611 bytes).
   - **Status:** Redundant duplicate.

3. **`data/evaluation/ground_truth.json`**
   - **Evidence:** Contains only 5 pilot questions (`Q1`–`Q5`) evaluated against outdated chunk identifiers. The official benchmark uses `retrieval_ground_truth_current.json` (Q1–Q20) and `retrieval_ground_truth_additional_20.json` (Q21–Q40).
   - **Status:** Obsolete legacy file.

4. **`data/evaluation/retrieval_ground_truth_current.json.bak` and `*.additional_20.json.bak`**
   - **Evidence:** Created as editor/script backup copies during ground truth refinement. Git tracks all previous versions in version history.
   - **Status:** Redundant backups.

5. **`tests/embed_test.py` and `tests/embed_small_test.py`**
   - **Evidence:** These files define standalone `def main():` scripts that attempt to read from `data/chunks/` (a directory that no longer exists; chunks are stored in `data/chunks_corpus` and `data/chunks_pilot`). Neither contains `unittest.TestCase` or `pytest` assertions.
   - **Status:** Broken, obsolete manual test scripts.

6. **`scripts/inspect_q6.py`**
   - **Evidence:** Queries collection `"cybersecurity_chunks"` (the old collection, whereas the active collection is `cybersecurity_chunks_bge_m3`) and uses `bge-small-en-v1.5`.
   - **Status:** Obsolete ad-hoc script.

7. **Root `__pycache__/`**
   - **Evidence:** Contains `.pyc` files for `bm25_retriever.py`, `rag_pipeline.py`, `reranker.py`, and `retriever.py` compiled at the root level before modularization into `app/`.
   - **Status:** Stale orphaned bytecode.

---

## 5. Files That Appear Safe to Remove Immediately

The following candidates can be removed without breaking the active RAG pipeline, the 167 unit tests, the official benchmark evaluation, or any data dependencies:

| Exact Relative Path | Type | Justification for Safe Removal | Risk Level |
| :--- | :--- | :--- | :--- |
| `evaluation/evaluate_hybrid_weights.py` | Empty File | 0 bytes; contains no code or imports. | **None** |
| `docs/CURRENT_RAG_ARCHITECTURE_1.md` | Duplicate | Exact copy of `docs/CURRENT_RAG_ARCHITECTURE.md`. | **None** |
| `data/evaluation/retrieval_ground_truth_current.json.bak` | Backup | Redundant editor backup; canonical version is active. | **None** |
| `data/evaluation/retrieval_ground_truth_additional_20.json.bak` | Backup | Redundant editor backup; canonical version is active. | **None** |
| `tests/embed_test.py` | Broken Script | References non-existent `data/chunks/`; not a unit test. | **Low** |
| `tests/embed_small_test.py` | Broken Script | References non-existent `data/chunks/`; not a unit test. | **Low** |
| `scripts/inspect_q6.py` | Obsolete Script | Hardcoded to obsolete Qdrant collection and obsolete model. | **Low** |
| `__pycache__/` (at repository root) | Stale Bytecode | Orphaned bytecode from pre-modular flat repository layout. | **None** |
| `scratch/` (entire repository directory) | Diagnostic Scratch | 79 temporary diagnostic files, test images, and logs; ignored by git. | **Low** |

---

## 6. Files That Require User Decision

The following files contain historical, exploratory, or milestone data. They are not used by the live RAG pipeline, but their removal requires explicit user confirmation:

| Relative Path | Size | Description & User Decision Required |
| :--- | :--- | :--- |
| `data/extraction_baseline/` | 2.00 MB | Early baseline extraction outputs for 5 pilot PDFs. Safe to archive or delete if baseline comparisons are complete. |
| `data/extraction_benchmark_pymupdf4llm/` | 1.15 MB | Benchmark outputs comparing PyMuPDF vs PyMuPDF4LLM. Safe to archive if benchmark report in `reports/` is sufficient. |
| `data/extraction_corpus_68/` | 114.73 MB | Raw Markdown and JSON extraction outputs for the 68 non-pilot documents prior to cleaning and chunking. |
| `data/extraction_pilot/` | 25.77 MB | Stage 1 raw pilot extraction outputs. |
| `data/extraction_pilot_v2/` | 25.24 MB | Stage 2 pilot extraction outputs. |
| `data/extraction_pilot_v3/` | 23.05 MB | Stage 3 pilot extraction outputs. |
| `data/extraction_poc_hybrid_nist_800_53/` | 13.47 MB | Proof-of-concept hybrid extraction for NIST SP 800-53. |
| `data/extraction_poc_hybrid_nist_800_53_filtered/` | 12.95 MB | Filtered POC extraction outputs for SP 800-53. |
| `data/extraction_poc_hybrid_nist_800_53_qualityfix/` | 12.97 MB | Quality-fixed POC extraction outputs for SP 800-53. |
| `data/extraction_regression_pilot_5docs/` | 23.22 MB | Regression test outputs for the 5-PDF pilot. |
| `data/evaluation/ground_truth.json` | 533 bytes | Legacy 5-question pilot ground truth. Safe to delete if legacy pilot benchmark is permanently retired. |
| `app/retrieval/hybrid_reranker.py` | 6.94 KB | Standalone reranker script. Can be removed if confirmed no external caller uses it instead of `app/retrieval/reranker.py`. |
| `scripts/evaluate_q10_q13_q19.py` | 8.21 KB | Diagnostic script evaluating Q10, Q13, Q19. Useful for focused testing, but redundant with `evaluation/evaluate_retrieval_metrics.py`. |
| `scripts/test_three_reranker_questions.py` | 3.64 KB | Diagnostic script testing reranking on Q10, Q13, Q19. |
| `scripts/inspect_bge_reranking.py` | 26.06 KB | Interactive BGE reranker diagnostic tool. Useful for manual debugging, but not part of production. |
| `reports/benchmark_lightweight_results.json` | 17.69 KB | Raw JSON results from lightweight embedding benchmark. |
| `reports/evaluation_q10_q13_q19_summary.json` | 8.99 KB | Raw JSON results from Q10/Q13/Q19 diagnostic run. |

> [!TIP]
> **Storage Optimization Opportunity:** The historical extraction directories in `data/` account for **254 MB across 3,149 files**. Since the production pipeline runs entirely from `data/chunks_corpus/`, `data/chunks_pilot/`, and `data/qdrant/`, these intermediate directories can be archived into a single compressed backup or removed after user verification.

---

## 7. Dependencies and Configuration That Must Be Preserved

1. **Python Dependencies (`pyproject.toml` / `uv.lock`):**
   - Core Vector & Retrieval: `sentence-transformers>=6.0.0`, `qdrant-client>=1.19.0`, `rank-bm25>=0.2.2`.
   - LLM & Generation: `groq>=1.6.0`, `python-dotenv>=1.2.3`.
   - Document Processing: `pymupdf>=1.28.2`, `pypdf>=6.16.2`, `beautifulsoup4>=4.15.0`, `pandas>=3.0.5`, `tiktoken>=0.14.0`, `requests>=2.34.2`.
2. **Environment Variables (`.env`):**
   - `GROQ_API_KEY`: Required for query rewriting and answer generation.
   - `QDRANT_COLLECTION`: Must remain `cybersecurity_chunks_bge_m3`.
   - `EMBEDDING_MODEL`: Must remain `BAAI/bge-m3`.
   - `RERANKER_MODEL`: Must remain `cross-encoder/ms-marco-MiniLM-L-6-v2`.
3. **Authoritative Data Directories:**
   - `data/chunks_corpus/` and `data/chunks_pilot/`: The 13,084 source chunks for BM25 and context generation.
   - `data/embeddings_bge_m3/`: Precomputed 1024-dim BGE-M3 embeddings.
   - `data/qdrant/`: Embedded vector storage.
   - `documents/`: Raw NIST source PDFs.

---

## 8. Proposed Clean Folder Structure

Following approval and execution of the proposed clean-up, the repository structure will be organized cleanly as follows:

```
cybersecurity-rag/
├── app/                          # Core application logic
│   ├── conversation/             # Memory and conversational rewriting
│   ├── core/                     # Config, models, and interfaces
│   ├── generation/               # Context building and LLM generation
│   ├── ingestion/                # Document extraction, cleaning, and chunking modules
│   ├── pipeline/                 # High-level RAGEngine orchestrator
│   └── retrieval/                # Dense, BM25, RRF, Confidence, Rewriter, Reranker
├── data/                         # Authoritative data stores
│   ├── chunks_corpus/            # Production corpus chunks (9,909 chunks)
│   ├── chunks_pilot/             # Production pilot chunks (3,175 chunks)
│   ├── cleaned_corpus/           # Checkpointed cleaned documents
│   ├── cleaned_pilot/            # Cleaned pilot document text
│   ├── document_inventory/       # Document inventory CSV/JSON
│   ├── embeddings_bge_m3/        # 1024-dim embeddings & manifest
│   ├── evaluation/               # Official benchmark questions & ground truth
│   └── qdrant/                   # Embedded Qdrant database (cybersecurity_chunks_bge_m3)
├── docs/                         # Technical documentation, architecture, and ADRs
│   ├── CURRENT_RAG_ARCHITECTURE.md
│   ├── PROJECT_CLEANUP_AUDIT.md  # (This audit report)
│   └── ...
├── documents/                    # 73 authoritative NIST PDFs
├── evaluation/                   # Formal benchmark scripts
│   ├── evaluate_retrieval_metrics.py
│   ├── run_full_evaluation.py
│   └── ...
├── reports/                      # Formal evaluation and forensic reports
├── scripts/                      # Production ingestion & maintenance runners
│   ├── run_corpus_extraction.py
│   ├── run_corpus_cleaning.py
│   ├── run_corpus_chunking.py
│   ├── generate_full_corpus_embeddings.py
│   ├── ingest_embeddings_qdrant.py
│   └── scan_document_inventory.py
├── tests/                        # Comprehensive automated test suite
├── .env                          # Secret-bearing environment config
├── .gitignore                    # Version control rules
├── .python-version               # Python 3.12 pinning
├── main.py                       # CLI interactive entry point
├── pyproject.toml                # Project metadata and dependencies
├── README.md                     # Project README
└── uv.lock                       # Dependency lockfile
```

---

## 9. Risk Assessment and Migration Plan

| Category | Clean-up Action | Associated Risk | Mitigation Strategy |
| :--- | :--- | :--- | :--- |
| **0-byte / Duplicate files** | Delete `evaluate_hybrid_weights.py` and `CURRENT_RAG_ARCHITECTURE_1.md`. | **None.** No code references exist for the empty file; the duplicate is identical to `CURRENT_RAG_ARCHITECTURE.md`. | Verify git diff and ensure primary document is intact before deletion. |
| **Editor `.bak` files** | Delete `retrieval_ground_truth_*.bak`. | **None.** Active JSON files are fully tracked in Git history. | Confirm active JSON files are valid and pass schema validation. |
| **Broken test scripts** | Remove `tests/embed_test.py` and `tests/embed_small_test.py`. | **Very Low.** These scripts fail immediately on execution due to pointing to non-existent `data/chunks/`. | Validated: neither script is run by `unittest` discover or CI. |
| **Obsolete scripts** | Remove `scripts/inspect_q6.py`. | **Very Low.** Hardcoded to non-existent collection `"cybersecurity_chunks"`. | Production Q6 retrieval is already covered by `evaluate_retrieval_metrics.py`. |
| **Repo-level `scratch/`** | Delete or archive `scratch/`. | **Low.** Contains ad-hoc page tests and local OCR models; ignored by Git. | Confirm no active test or pipeline component imports from `scratch/` (verified: 0 imports). |
| **Root `__pycache__/`** | Remove orphaned root `.pyc` files. | **None.** Python will regenerate valid `.pyc` files in module subdirectories as needed. | Safe standard Python housekeeping. |
| **Historical `data/extraction_*`** | Archive to compressed tarball or keep untouched pending user approval. | **Low.** 254 MB of intermediate data from early development. Not loaded by live RAG. | Keep in place until explicit user sign-off. |

---

## 10. Audit Conclusion and Next Steps

The repository is structurally sound, highly capable, and fully verified:
- All 167 unit and integration tests pass cleanly.
- The 13,084-chunk corpus and BGE-M3 Qdrant database are intact.
- The clean-up candidates identified above represent **~32 MB of loose scratch/cache files** and **254 MB of historical intermediate extraction data** that can be safely reorganized or retired without impacting the live system.

In accordance with Phase 4 instructions:
- **No changes have been made to repository files.**
- Antigravity has stopped and is awaiting your explicit review and approval before proceeding with any file deletions, moves, or cleanup operations.
