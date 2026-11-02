# Embedding Model Benchmark — Stage 0 Preflight Report

**Project**: Cybersecurity RAG  
**Location**: `C:\Users\Computer\Desktop\cybersecurity-rag`  
**Date**: October 15, 2026  
**Auditor / Agent**: Antigravity  
**Target Models**:
1. `BAAI/bge-small-en-v1.5` (Baseline: 384 dimensions, 33.4M parameters)
2. `BAAI/bge-m3` (Candidate: 1024 dimensions, 560M parameters)

---

## 1. Executive Summary

This report delivers the read-only Stage 0 Preflight findings for comparing `BAAI/bge-small-en-v1.5` and `BAAI/bge-m3` across the newly completed Cybersecurity RAG corpus (73 NIST publications, 4,649 physical pages, 13,084 structure-aware chunks).

### High-Level Verdict: CONDITIONAL GO
- **Model Cache Readiness: GO (100% Verified)**. Both models are already fully downloaded and intact in the local Hugging Face cache (`C:\Users\Computer\.cache\huggingface\hub`). **Zero downloads are required.**
- **Hardware & Environment Readiness: GO**. The laptop possesses 16 GB physical RAM, 1,599 MB free disk space (~1,100 MB headroom above the 500 MB mandatory reserve), and an operational Python 3.12 environment with `torch 2.13.0+cpu` and `sentence_transformers 6.0.0`.
- **Existing Evaluation Data Readiness: NO-GO FOR IMMEDIATE RUN**. The existing retrieval ground truth (`data/evaluation/retrieval_ground_truth.json`) references **legacy chunk IDs** (e.g. `NIST_SP_800-144_00080`) from the early 7,703-chunk prototype. Exactly **0 out of 33 ground truth chunk IDs** match the current 13,084 structure-aware chunk IDs (`_txt_`, `_tbl_`, `_fig_`). Evaluating against the existing files unmodified would erroneously yield 0.0% retrieval scores for both models.
- **Recommendation**: Align the ground truth chunk IDs on a representative pilot benchmark subset (e.g., 200–500 chunks across cloud security, cryptography, and risk management) before executing the comparative benchmark.

---

## 2. Existing Files and Scripts Inspected

A comprehensive survey of the repository's embedding, retrieval, evaluation, and vector database assets was conducted:

| Category | File Path | Current Role / Configuration |
| :--- | :--- | :--- |
| **Core Configuration** | [`app/core/config.py`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/app/core/config.py) | Central `Settings` class: specifies `embedding_model = "BAAI/bge-small-en-v1.5"`, `embedding_dim = 384`, `qdrant_collection = "cybersecurity_chunks"`, `qdrant_path = data/qdrant`, `dense_top_k = 20`. |
| **Dense Retrieval** | [`app/retrieval/dense.py`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/app/retrieval/dense.py) | Implements `DenseRetriever` using `sentence_transformers.SentenceTransformer(self.embedding_model_name, local_files_only=True)` and local `QdrantClient(path=str(self.qdrant_path))`. |
| **Retrieval Architecture** | [`app/retrieval/`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/app/retrieval/) | Modular retrieval modules: `bm25.py`, `rrf.py` (Reciprocal Rank Fusion $K=60$), `hybrid.py`, `reranker.py` (`cross-encoder/ms-marco-MiniLM-L-6-v2`). |
| **Ingestion (Legacy)** | [`app/ingestion/embed_documents.py`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/app/ingestion/embed_documents.py) | Legacy script configured for `BAAI/bge-m3`, batch size 4, 4 CPU threads, targeting obsolete `data/chunks/*.json` into `data/embeddings/`. |
| **Ingestion (Legacy)** | [`app/ingestion/embed_documents_safe.py`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/app/ingestion/embed_documents_safe.py) | Legacy script configured for `BAAI/bge-small-en-v1.5`, batch size 2, 2 CPU threads, targeting obsolete `data/chunks/*.json` into `data/embeddings_small/`. |
| **Vector DB Setup** | [`app/ingestion/build_qdrant.py`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/app/ingestion/build_qdrant.py) | Script to populate local Qdrant collection with 384-dim vectors from `.npy` files. |
| **Evaluation Suite** | [`evaluation/run_full_evaluation.py`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/evaluation/run_full_evaluation.py) | Unified 3-level evaluation runner (Retrieval, Generation, End-to-End). |
| **Evaluation Suite** | [`evaluation/evaluate_retrieval_metrics.py`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/evaluation/evaluate_retrieval_metrics.py) | Standalone evaluation computing Hit@K, Precision@K, and MRR. |
| **Evaluation Suite** | [`evaluation/evaluate_retrieval.py`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/evaluation/evaluate_retrieval.py) | Direct query retrieval against Qdrant collection. |
| **Benchmark Documentation** | [`docs/EVALUATION.md`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/docs/EVALUATION.md) | Historical benchmark record documenting baseline metrics on the legacy 7,703-chunk corpus. |
| **Evaluation Datasets** | [`data/evaluation/evaluation_questions.json`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/data/evaluation/evaluation_questions.json) | 20 questions (`Q1` to `Q20`), strictly cloud computing security. |
| **Evaluation Ground Truth** | [`data/evaluation/retrieval_ground_truth.json`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/data/evaluation/retrieval_ground_truth.json) | Relevant chunk IDs for Q1–Q15 (uses legacy IDs; Q16–Q20 unmapped). |
| **Evaluation Ground Truth** | [`data/evaluation/ground_truth.json`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/data/evaluation/ground_truth.json) | Subset for BM25 keyword evaluation (Q1–Q5 only; uses legacy IDs). |
| **Test Scripts** | [`tests/embed_test.py`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/tests/embed_test.py) | Standalone BGE-M3 test (currently broken due to path dependency on `data/chunks/`). |
| **Test Scripts** | [`tests/embed_small_test.py`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/tests/embed_small_test.py) | Standalone BGE-small test (currently broken due to path dependency on `data/chunks/`). |

---

## 3. Model Cache Verification (Local Disk)

Both models were inspected in the local user cache directory:  
`C:\Users\Computer\.cache\huggingface\hub\`

Neither model requires downloading. Both are 100% complete and verified offline:

### Model 1: `BAAI/bge-small-en-v1.5`
- **Cache Directory**: `models--BAAI--bge-small-en-v1.5`
- **Size on Disk**: **128.28 MB**
- **Snapshot ID**: `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`
- **Key Files Verified**:
  - `model.safetensors` (127.28 MB)
  - `tokenizer.json` (0.68 MB)
  - `vocab.txt` (0.22 MB)
  - `config.json`, `config_sentence_transformers.json`, `sentence_bert_config.json`, `modules.json`
- **Offline Loading**: Verified functional with `SentenceTransformer(..., local_files_only=True)`.

### Model 2: `BAAI/bge-m3`
- **Cache Directory**: `models--BAAI--bge-m3`
- **Size on Disk**: **4,352.9 MB (~4.35 GB)**
- **Snapshot IDs**:
  - `5617a9f61b028005a4858fdac845db406aefb181` (Contains `pytorch_model.bin` [2,165.93 MB], `sentencepiece.bpe.model` [4.83 MB], `tokenizer.json` [16.31 MB], configs).
  - `9a0624b896d81da7492a910ffa53731274b6cf3d` (Contains `model.safetensors` [2,165.86 MB]).
- **Offline Loading**: Verified functional with `SentenceTransformer(..., local_files_only=True)`.

---

## 4. Hardware Profile and Resource Constraints

### System Environment
- **Host OS**: Microsoft Windows (AMD64)
- **Physical RAM**: **16.0 GB**
- **Python Environment**: Python 3.12.13 virtual environment (`.venv`)
- **PyTorch Installation**: `torch 2.13.0+cpu` (**CPU-only execution; CUDA unavailable**)
- **Key Libraries**: `transformers 5.15.1`, `sentence_transformers 6.0.0`, `qdrant_client`, `psutil 7.2.2`, `numpy 2.5.2`, `scipy 1.18.1`. `fastembed` is **not installed**.

### Disk Space Budget
- **Current Used Space**: 259,187,138,560 bytes (~259.2 GB)
- **Current Free Space**: 1,676,759,040 bytes = **1,599.08 MB (~1.60 GB)**
- **Mandatory Safety Reserve**: **500.0 MB**
- **Usable Disk Headroom**: **~1,099 MB (~1.10 GB)**

### Active Vector Database Status
- `data/qdrant` (default configured path in `Settings`): **Does NOT exist**.
- `qdrant_data/` and `qdrant_db/` (root-level directories): Both contain empty metadata files (`{"collections": {}, "aliases": {}}`) with zero stored points.
- `data/embeddings/` and `data/embeddings_small/`: **Do NOT exist**.
- **Conclusion**: There are currently no pre-existing vector embeddings or populated Qdrant collections on disk.

### Model Resource Comparison Matrix

| Property | `BAAI/bge-small-en-v1.5` | `BAAI/bge-m3` | Resource Implications |
| :--- | :---: | :---: | :--- |
| **Model Architecture** | BERT-based (12 layers, 384 hidden) | XLM-RoBERTa (24 layers, 1024 hidden) | BGE-M3 is ~16.8x larger in parameter count |
| **Parameters** | 33.4 Million | 560 Million | BGE-M3 requires significantly more CPU compute |
| **Embedding Dimension** | 384 floats (1,536 bytes/vector) | 1024 floats (4,096 bytes/vector) | BGE-M3 vectors consume 2.67x more RAM/disk |
| **Context Window** | 512 tokens | 8,192 tokens | BGE-small fits our $\le 500$-token chunk ceiling |
| **Weights on Disk** | 127.3 MB | 2,165.9 MB | Both already cached; 0 MB disk delta to load |
| **Estimated Working RAM (CPU)** | **~400–600 MB** | **~2.8–3.5 GB** | **Do not load simultaneously** to avoid paging |
| **CPU Throughput (Est.)** | **~40–70 chunks/sec** | **~3–7 chunks/sec** | BGE-M3 will take ~10–15x longer per chunk on CPU |
| **Full Corpus (13,084 chunks) Time** | ~3.5–5.5 minutes | ~35–70 minutes | Full corpus BGE-M3 run is too heavy for pilot |
| **Full Corpus Raw Vector Size** | ~20.1 MB | ~53.6 MB | Fits in disk headroom, but Qdrant index adds ~150 MB |

---

## 5. Evaluation Data Inventory & Disconnect Analysis

A critical inspection of the evaluation data revealed three major limitations that prevent an immediate benchmark run:

```
+-------------------------------------------------------------------------------+
|                        EVALUATION DATA DISCONNECT                             |
+-------------------------------------------------------------------------------+
|  retrieval_ground_truth.json (33 Chunk IDs)                                   |
|    "NIST_SP_800-144_00080", "NIST_SP_800-146_00131", "NIST_SP_800-53_00285"  |
|                                     |                                         |
|                                     v  (0% ID MATCH)                          |
|                                                                               |
|  Active Chunk Corpus (13,084 Chunk IDs across chunks_pilot & chunks_corpus)   |
|    "NIST_SP_800-144_txt_00059", "NIST_SP_800-146_tbl_00001_p01", etc.        |
+-------------------------------------------------------------------------------+
```

### Limitation 1: Zero Overlap with Current Chunk IDs
- In `data/evaluation/retrieval_ground_truth.json`, there are 33 unique relevant chunk IDs mapped to questions Q1–Q15.
- Every ID uses the legacy schema (`<doc_id>_<5-digit-seq>`), generated during an earlier uncleaned prototype.
- In Stage 2 and Stage 3, the chunking pipeline was rebuilt to produce structure-aware, typed IDs (`<doc_id>_<type>_<5-digit-seq>`).
- **Exact Matches Found**: **0 / 33 (0.00%)**.
- If any retrieval evaluation script (`evaluate_retrieval_metrics.py` or `run_full_evaluation.py`) is executed today, it will record Hit@1 = 0.0%, Hit@3 = 0.0%, Hit@5 = 0.0%, MRR = 0.0000 for both models.

### Limitation 2: Incomplete Question Mapping
- `evaluation_questions.json` contains 20 questions (`Q1` to `Q20`).
- `retrieval_ground_truth.json` only provides relevance annotations for `Q1` through `Q15`.
- Questions `Q16`, `Q17`, `Q18`, `Q19`, and `Q20` have **zero ground truth annotations**.

### Limitation 3: Domain Skew (Cloud Security Only)
- All 20 evaluation questions focus exclusively on public cloud computing risks, governance, and shared responsibility (`NIST_SP_800-144` and `NIST_SP_800-146`).
- The production corpus covers 10 diverse cybersecurity domains (cryptography, zero trust, identity management, vulnerability management, firmware/supply chain, incident handling).
- Benchmarking solely on cloud security will fail to reveal how each model handles cryptographic identifiers, control tags (`AC-2(1)`), or protocol tables.

---

## 6. Proposed Pilot Benchmark Methodology

To ensure a fair, safe, and rigorous comparison without running a slow full-corpus CPU generation or risking out-of-memory/disk exhaustion, we propose the following pilot benchmark:

### 1. Controlled Corpus Subset (Pilot Evaluation Pool)
Instead of indexing all 13,084 chunks across 73 publications (which would take ~1 hour on CPU for BGE-M3 and consume ~200 MB), select a focused, representative evaluation pool:
- **Pool Size**: ~300 to 500 chunks.
- **Documents Included**:
  - `NIST_SP_800-144` (Cloud Security Guidelines, 164 chunks): Directly corresponds to the questions in `evaluation_questions.json`.
  - `NIST_SP_800-146` (Cloud Architecture, 232 chunks): Directly corresponds to questions Q10, Q12, Q13.
  - (Optional) `NIST_SP_800-53` (Security Controls subset, ~100 chunks): Tests NIST control code retrieval (`AC-`, `IA-`).

### 2. Ground Truth Alignment (Mandatory Prerequisite)
Before scoring, map the 15 evaluation questions to the new chunk IDs in `NIST_SP_800-144` and `NIST_SP_800-146`.
- *Method*: Identify the exact section and paragraph in `NIST_SP_800-144` that answers each question (e.g., Section 3.1 for public cloud governance, Section 4.1 for data security). Match those sections to the corresponding `NIST_SP_800-144_txt_*` chunk IDs.
- *Strict Rule*: Do not invent synthetic relevance; only map questions to chunks that genuinely contain the verified answers.

### 3. Sequential In-Memory Execution Protocol
To adhere strictly to memory and disk constraints:
1. **Never load both models simultaneously**:
   - Run Model A (`bge-small-en-v1.5`) $\rightarrow$ Record all metrics $\rightarrow$ Unload Model A $\rightarrow$ Run `gc.collect()` $\rightarrow$ Verify RAM returns to baseline.
   - Run Model B (`bge-m3`) $\rightarrow$ Record all metrics $\rightarrow$ Unload Model B $\rightarrow$ Run `gc.collect()`.
2. **In-Memory Vector Search**:
   - Compute embeddings in float32 numpy arrays in memory.
   - Perform exact cosine similarity retrieval without writing temporary Qdrant disk collections.
   - Disk consumption: **0 MB** (pure in-memory).

---

## 7. Metrics Definition and Consistency Standards

Both models must be evaluated against the exact same evaluation set, corpus subset, and metric equations:

### 1. Retrieval Accuracy Metrics

- **Hit@K ($K \in \{1, 3, 5\}$)**:
  $$\text{Hit@K}(q) = \begin{cases} 1 & \text{if } \exists i \le K \text{ such that } c_i \in R_q \\ 0 & \text{otherwise} \end{cases}$$
  Corpus-level metric: $\text{Hit@K} = \frac{1}{|Q|} \sum_{q \in Q} \text{Hit@K}(q)$. Measures whether at least one relevant passage is retrieved within the top $K$ candidates.

- **Precision@5**:
  $$\text{Precision@5}(q) = \frac{|\{c_i \in Top_5(q) : c_i \in R_q\}|}{5}$$
  Corpus-level metric: $\text{Precision@5} = \frac{1}{|Q|} \sum_{q \in Q} \text{Precision@5}(q)$. Measures the density of relevant information within the top 5 retrieved chunks.

- **Mean Reciprocal Rank (MRR)**:
  $$\text{RR}(q) = \begin{cases} \frac{1}{\min \{i : c_i \in R_q\}} & \text{if } \exists c_i \in R_q \\ 0 & \text{otherwise} \end{cases}$$
  Corpus-level metric: $\text{MRR} = \frac{1}{|Q|} \sum_{q \in Q} \text{RR}(q)$. Heavily rewards models that place the first relevant passage at rank 1.

### 2. Operational & Efficiency Metrics

- **Cold Model Loading Time ($s$)**:
  Wall-clock time to instantiate `SentenceTransformer(model_name, local_files_only=True, device="cpu")`.
- **Query Encoding Latency ($ms$)**:
  Mean and median latency to encode a single query string across the 15 evaluation questions.
- **Corpus Encoding Throughput ($\text{chunks}/s$)**:
  Number of corpus chunks encoded divided by total elapsed encoding time on identical batch sizes (Batch Size = 4, CPU threads = 4).
- **Peak RAM Delta ($\Delta \text{RSS MB}$)**:
  Measured via `psutil.Process().memory_info().rss`:
  $$\Delta \text{RSS} = \text{RSS}_{\text{encoding}} - \text{RSS}_{\text{baseline}}$$
  Quantifies the active memory footprint overhead attributable to each model.

---

## 8. Risk Management Matrix

| Risk Factor | Probability | Impact | Mitigation Strategy |
| :--- | :---: | :---: | :--- |
| **Disk Exhaustion** (Free space < 500 MB) | Low | High | Use in-memory numpy cosine similarity for the pilot benchmark; do not write duplicate Qdrant collections to disk. |
| **RAM Exhaustion / Thrashing** | Medium | High | Enforce strict sequential execution: unload Model A and call `gc.collect()` before instantiating Model B. Cap batch size at 4 on CPU. |
| **CPU Saturation / Long Hangs** | High (if full corpus) | Medium | Restrict benchmark to the representative pilot pool (~300–400 chunks) rather than the full 13,084 chunks. |
| **False 0% Benchmark Results** | Certain (if unmitigated) | High | Reconcile the 33 legacy ground truth chunk IDs to current chunk IDs prior to scoring. |
| **API Secret Leakage** | Low | Critical | Ensure `.env` and Groq API keys are excluded from benchmark scripts, logs, and artifacts. |

---

## 9. Recommendation and Next Steps

### Recommendation: CONDITIONAL GO
We recommend proceeding to **Stage 1: Benchmark Design and Ground Truth Alignment**, with the following prerequisites:

1. **Do NOT run the benchmark against the unmapped legacy ground truth**.
2. **Reconcile Ground Truth IDs**: Create a verified mapping from the 15 evaluation questions to the corresponding current chunk IDs in `data/chunks_corpus/cloud_application_security/NIST_SP_800-144_chunks.jsonl` and `NIST_SP_800-146_chunks.jsonl`.
3. **Execute the Pilot Benchmark**:
   - Compare `BAAI/bge-small-en-v1.5` vs `BAAI/bge-m3` on the aligned pilot subset.
   - Record Hit@1, Hit@3, Hit@5, Precision@5, MRR, latency, throughput, and memory.
   - Present the empirical trade-off between retrieval quality and CPU/RAM cost to select the final embedding model.

*Awaiting user approval before proceeding to implementation.*
