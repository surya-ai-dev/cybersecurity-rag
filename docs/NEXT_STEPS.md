# Next Steps & Advanced RAG Roadmap — Cybersecurity RAG

This document defines the roadmap and engineering protocol for subsequent development phases following the architecture modularization.

---

## 1. Completed Work

The architectural foundation is complete and verified:
- [x] Package modularization (`app/core`, `app/retrieval`, `app/generation`, `app/conversation`, `app/pipeline`, `app/ingestion`).
- [x] Protocol contracts (`BaseRetriever`, `BaseReranker`, `BaseLLMProvider`, `BaseConversationMemory`).
- [x] Provider abstraction for LLMs (`GroqProvider`).
- [x] Pure context builder decoupled from retrieval.
- [x] Sliding-window conversation memory.
- [x] Modular retrieval components (`DenseRetriever`, `BM25Retriever`, `RRFFusion`, `CrossEncoderReranker`, `HybridRetriever`).
- [x] Centralized orchestrator (`RAGEngine`).
- [x] Backward-compatibility wrappers maintained for existing evaluation scripts.
- [x] Verification of 100% parity against baseline metrics.
- [x] Full architectural documentation in `docs/`.

---

## 2. Current Phase: Advanced RAG Improvements

With the architecture stabilized, modularized, and tested, the project enters the **Advanced RAG Improvement Phase**. 

The goal of this phase is to iteratively boost retrieval accuracy, precision, and generation grounding on difficult cybersecurity questions without sacrificing the modular foundation.

---

## 3. Candidate Improvements (Planned / Conceptual Only)

The following areas represent candidate improvements for future engineering cycles. **None of these are currently implemented:**

1. **Metadata Filtering**:
   - Filter chunks in Qdrant by document ID (e.g., `NIST_SP_800-53`), publication series, or control families (e.g., `AC`, `IA`, `SC`) when specified by user queries.
2. **Query Routing**:
   - Classify incoming queries to determine whether they require definition lookups, multi-document control comparisons, or procedural implementation steps.
3. **Retrieval Routing**:
   - Dynamically route queries between dense-only, sparse-only, or full hybrid retrieval based on presence of specific tokens (e.g., CVE codes, NIST control identifiers).
4. **Contextual Retrieval / Contextual Embeddings**:
   - Prepend document/section titles to chunk text before embedding to reduce ambiguity in isolated passages.
5. **Adaptive Retrieval (Dynamic K)**:
   - Adjust retrieval Top-K based on reranker score confidence or query complexity.
6. **Corrective RAG (CRAG)**:
   - Introduce an evaluator step after reranking to trigger query refinement or web search fallback if retrieved document confidence falls below a threshold.
7. **Self-RAG / Self-Reflection**:
   - Assess generated answers for faithfulness, citation alignment, and answer completeness before returning them to the user.
8. **Advanced Generation Grounding Metrics**:
   - Integrate automated evaluation for answer faithfulness, groundedness, and citation fidelity against retrieved contexts.

> [!IMPORTANT]
> The items above are strictly **candidate ideas**. Do not implement them simultaneously or without following the development protocol below.

---

## 4. Engineering & Development Protocol

Every future improvement **MUST** follow this rigorous, incremental process:

1. **Select ONE improvement**: Work on exactly one isolated feature at a time.
2. **Understand the current architecture**: Review `docs/ARCHITECTURE.md` and related modules before writing code.
3. **Define the problem**: Clearly articulate what limitation or bottleneck is being addressed.
4. **Define the expected benefit**: Specify the metric or capability expected to improve (e.g., improve Hit@1 from 73.33% to 80.00%).
5. **Implement the smallest possible change**: Maintain strict inward dependency flow and protocol interfaces.
6. **Run existing unit tests**: Ensure `python -m unittest discover -s tests` passes.
7. **Run retrieval benchmarks**: Execute `evaluation/evaluate_retrieval_metrics.py`, `evaluate_rrf.py`, and `evaluate_reranked_retrieval.py`.
8. **Compare with baseline**: Benchmark results directly against `docs/EVALUATION.md`.
9. **Analyze differences**: Investigate any regressions or metric shifts.
10. **Document the result**: Update `docs/DEVELOPMENT_LOG.md` and `docs/EVALUATION.md`.
11. **Seek approval**: Complete the cycle and await user approval before moving to the next improvement.

---

## 5. Git Status

The working tree changes resulting from Steps 1–9 and documentation Step 9C are **intentionally uncommitted**. Development continues in this clean state pending user instruction to stage and commit.
