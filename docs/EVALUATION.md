# Evaluation & Benchmarking Baseline — Cybersecurity RAG

This document records the official, verified evaluation metrics and baseline performance of the Cybersecurity RAG system following the modular refactoring (Step 8).

---

## 1. Evaluation Dataset Setup

The benchmark suite consists of two evaluation datasets located in `data/evaluation/`:
- **`evaluation_questions.json`**: Contains 20 curated cybersecurity questions based on NIST Special Publications. Questions Q1 through Q15 are used for standardized retrieval and reranking benchmarks.
- **`retrieval_ground_truth.json`**: Ground truth mapping for Q1–Q15 listing the verified relevant chunk IDs for each question.
- **`ground_truth.json`**: Benchmark mapping for Q1–Q5 used by the BM25 keyword evaluation.

---

## 2. Dense Retrieval Baseline

Evaluated via `evaluation/evaluate_retrieval_metrics.py`:
- **Model**: `BAAI/bge-small-en-v1.5`
- **Vector DB**: Qdrant (Cosine Similarity)
- **Candidate Limit**: Top-20
- **Scope**: 15 Questions (Q1–Q15)

| Metric | Pre-Refactor Baseline | Current Modular System | Parity Status |
| :--- | :---: | :---: | :---: |
| **Hit@1** | 73.33% | 73.33% | Exact Match (0.00%) |
| **Hit@3** | 86.67% | 86.67% | Exact Match (0.00%) |
| **Hit@5** | 93.33% | 93.33% | Exact Match (0.00%) |
| **Precision@5** | 44.00% | 44.00% | Exact Match (0.00%) |
| **MRR** | 0.8022 | 0.8022 | Exact Match (0.00%) |

---

## 3. BM25 Retrieval Baseline

Evaluated via `evaluation/evaluate_bm25.py`:
- **Algorithm**: Rank-BM25 (BM25Okapi)
- **Corpus**: 7,703 chunks
- **Candidate Limit**: Top-20
- **Scope**: Questions Q1–Q5

| Metric | Current System |
| :--- | :---: |
| **Hit@1** | 5.00% |
| **Hit@3** | 20.00% |
| **Hit@5** | 25.00% |
| **Precision@5** | 7.00% |
| **MRR** | 0.1292 |

*Note: Keyword search alone exhibits low standalone recall for conceptual questions, but provides essential exact-token retrieval for hybrid fusion.*

---

## 4. RRF / Hybrid Retrieval Baseline

Evaluated via `evaluation/evaluate_rrf.py`:
- **Fusion Algorithm**: Reciprocal Rank Fusion ($K=60$)
- **Inputs**: Dense Top-20 + BM25 Top-20
- **Candidate Limit**: Top-20
- **Scope**: 15 Questions (Q1–Q15)

| Metric | Pre-Refactor Baseline | Current Modular System | Parity Status |
| :--- | :---: | :---: | :---: |
| **Hit@1** | 86.67% | 86.67% | Exact Match (0.00%) |
| **Hit@3** | 100.00% | 100.00% | Exact Match (0.00%) |
| **Hit@5** | 100.00% | 100.00% | Exact Match (0.00%) |
| **Precision@5** | 51.00% | 51.00% | Exact Match (0.00%) |
| **MRR** | 0.9333 | 0.9333 | Exact Match (0.00%) |

---

## 5. Cross-Encoder Reranking Baseline

Evaluated via `evaluation/evaluate_reranked_retrieval.py`:
- **Model**: `cross-encoder/ms-marco-MiniLM-L-6-v2`
- **Input Candidates**: RRF Top-20
- **Final Top-N**: Top-5
- **Scope**: 15 Questions (Q1–Q15)

| Metric | Pre-Refactor Baseline | Current Modular System | Parity Status |
| :--- | :---: | :---: | :---: |
| **Hit@1** | 73.33% | 73.33% | Exact Match (0.00%) |
| **Hit@3** | 100.00% | 100.00% | Exact Match (0.00%) |
| **Hit@5** | 100.00% | 100.00% | Exact Match (0.00%) |
| **Precision@5** | 46.67% | 46.67% | Exact Match (0.00%) |
| **MRR** | 0.8556 | 0.8556 | Exact Match (0.00%) |

---

## 6. End-to-End Evaluation Results

Tested through `RAGEngine` across diverse cybersecurity queries:

1. **"What is least privilege?"**:
   - Status: PASS
   - Sources Retrieved: 5 chunks (`NIST_SP_800-53_00693` top-ranked)
   - Citations Generated: `[Source 1]`, `[Source 3]`
   - Grounding: Answer strictly confined to defining least privilege at the interface and module levels.
2. **"What is network segmentation?"**:
   - Status: PASS
   - Sources Retrieved: 5 chunks (`NIST_SP_800-125_00030` top-ranked)
   - Citations Generated: `[Source 3]`
   - Grounding: Explains logical traffic isolation, PCI DSS requirements, and isolation methods (virtual switches, firewalls).
3. **"What is encryption at rest?"**:
   - Status: PASS
   - Sources Retrieved: 5 chunks (`NIST_SP_800-46_00076` top-ranked)
   - Citations Generated: `[Source 1]`
   - Grounding: Defines cryptographic data protection for stored/inactive data against physical theft or unauthorized access.
4. **"What is a security baseline?"**:
   - Status: PASS
   - Sources Retrieved: 5 chunks (`NIST_SP_800-223_00036` top-ranked)
   - Citations Generated: `[Source 1]`, `[Source 4]`
   - Grounding: Defines predefined set of controls acting as starting protection points.
5. **"What are risks of public cloud infrastructure?"**:
   - Status: PASS
   - Sources Retrieved: 5 chunks (`NIST_SP_800-146_00101` top-ranked)
   - Citations Generated: `[Source 1]`, `[Source 2]`, `[Source 3]`, `[Source 5]`
   - Grounding: Outlines network dependency, multi-tenancy risks, and workload location opacity.

---

## 7. Conversational RAG Regression Results

Verified across a 3-turn multi-turn dialogue session:
- **Turn 1**: *"What is least privilege?"*
  - Standalone: *"What is least privilege?"*
  - Citations: `[Source 1]`, `[Source 3]`
- **Turn 2**: *"Why is it important?"*
  - Standalone Rewrite: *"Why is the principle of least privilege important?"*
  - Citations: `[Source 1]`, `[Source 5]`
- **Turn 3**: *"How can it be implemented?"*
  - Standalone Rewrite: *"How can the principle of least privilege be implemented?"*
  - Citations: `[Source 1, Source 5]`, `[Source 3]`, `[Source 2]`
- **Result**: Zero loss of context; pronoun resolution succeeded on turns 2 and 3; answers remained grounded in NIST sources.

---

## 8. Automated Unit & Integration Tests

Command:
```powershell
python -m unittest discover -s tests
```

Result:
- **10 Tests Passed** in 0.001s (`OK`).
- Test coverage includes:
  - `ChunkMetadata` serialization, dictionary access, and backward compatibility.
  - `RetrievedChunk` score preservation and shallow copying.
  - `Message` and `RAGResponse` serialization.
  - Concrete class inheritance under protocols (`BaseRetriever`, `BaseReranker`, `BaseLLMProvider`, `BaseConversationMemory`).
  - `ConversationMemory` sliding-window truncation.
  - `build_context` pure formatting assertions.
  - `RAGEngine` dependency injection and mock query lifecycle.

---

## 9. Important Evaluation Limitations

### Exact-ID Annotation Limitation
The ground-truth files (`retrieval_ground_truth.json` and `ground_truth.json`) evaluate matches by exact chunk ID strings. 

In cybersecurity standards (such as NIST SP 800-144, SP 800-53, SP 800-146), multiple chunks from different sections often discuss the same security concept with equal semantic validity. 
- For example, in Q2 (*"What security challenges are associated with public cloud environments?"*), chunk `NIST_SP_800-144_00004` is semantically relevant and scored highest by the Cross-Encoder, but the ground-truth file designated an alternative chunk from the same publication.
- This causes Hit@1 to drop from 86.67% under RRF to 73.33% under the Cross-Encoder.
- **Rule**: Do not alter ground-truth files to artificially inflate metrics. When an exact-ID limitation occurs, verify whether the retrieved candidate is semantically valid from the text content.

---

## 10. Baseline Rule for Future Development

All future RAG enhancements (e.g. metadata filtering, contextual embeddings, adaptive routing) **MUST** be measured against this established baseline table.

- **Never** silently modify evaluation questions or ground-truth annotations to make metrics look higher.
- Enhancements should aim to improve upon Hit@1 (currently 73.33% reranked, 86.67% RRF) and Precision@5 (currently 46.67% reranked, 51.00% RRF) while maintaining 100.00% Hit@3 and Hit@5.
