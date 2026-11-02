# Stage 2 — Embedding Model Pilot Benchmark Report

**Project**: Cybersecurity RAG  
**Location**: `C:\Users\Computer\Desktop\cybersecurity-rag`  
**Date**: October 15, 2026  
**Auditor / Agent**: Antigravity  
**Models Evaluated**:
1. `BAAI/bge-small-en-v1.5` (Baseline: 384 dimensions, 33.4M parameters)
2. `BAAI/bge-m3` (Candidate: 1024 dimensions, 560M parameters)  
**Corpus Cohort**: 396 structure-aware chunks (NIST SP 800-144 & NIST SP 800-146)  
**Evaluation Ground Truth**: 15 verified questions from [`data/evaluation/retrieval_ground_truth_current.json`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/data/evaluation/retrieval_ground_truth_current.json)  

---

## 1. Executive Summary

This report delivers empirical benchmark results comparing `BAAI/bge-small-en-v1.5` against `BAAI/bge-m3` on the active structure-aware NIST Cybersecurity corpus.

### High-Level Verdict
- **Retrieval Accuracy: `BAAI/bge-m3` is the clear winner across all quality metrics**.
  - **Hit@1**: **46.67%** vs 33.33% (**+13.34%** absolute improvement).
  - **Hit@3**: **73.33%** vs 60.00% (**+13.33%** absolute improvement).
  - **Hit@5**: **73.33%** vs 66.67% (**+6.66%** absolute improvement).
  - **Precision@5**: **21.33%** vs 16.00% (**+5.33%** absolute improvement).
  - **MRR (Mean Reciprocal Rank)**: **0.6000** vs 0.4578 (**+31.1%** relative improvement).
- **Compute & Latency: `BAAI/bge-small-en-v1.5` is ~10.6x faster at corpus encoding on CPU**.
  - **Corpus Encoding Throughput**: BGE-Small achieved **2.54 chunks/sec** vs BGE-M3's **0.24 chunks/sec**.
  - **Query Latency**: BGE-Small averaged **116.1 ms** vs BGE-M3's **484.1 ms**.
  - **Working RAM**: BGE-Small peaked at **~421 MB** (+21.1 MB delta) vs BGE-M3 at **~1,189 MB** (+338.0 MB model delta). Both fit comfortably in the 16 GB laptop RAM.
- **Strategic Recommendation**:
  - For **production query retrieval**, BGE-M3's 484 ms query latency is well within standard interactive SLA (< 1.0 s) and provides substantially superior recall and precision.
  - For **offline full-corpus indexing** (13,084 chunks), BGE-M3 will require approximately **~15.1 hours** on CPU vs BGE-Small's **~1.4 hours**. Batching strategies, overnight indexing, or GPU offload (if available) should be factored into full-corpus ingestion planning.

---

## 2. Test Environment & Methodology

The benchmark was executed using [`scripts/benchmark_embeddings_pilot.py`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/scripts/benchmark_embeddings_pilot.py) under strictly controlled, identical conditions:

- **Host Hardware**: AMD64 Laptop, 16.0 GB Physical RAM.
- **Compute Execution**: PyTorch `2.13.0+cpu` (**CPU-only execution, 0 GPU acceleration**).
- **Disk Footprint**: In-memory cosine similarity (**0 bytes written to disk**; vector databases bypassed).
- **Safety Controls**:
  - `local_files_only=True`: 0 network calls; executed purely from local cache.
  - Sequential model execution: BGE-Small completed and fully unallocated with `gc.collect()` before BGE-M3 loaded.
  - Active corpus files and project configs were untouched.
- **Corpus Cohort (396 Chunks Total)**:
  - NIST SP 800-144 (Cloud Security & Privacy): 164 chunks.
  - NIST SP 800-146 (Cloud Computing Synopsis): 232 chunks.
- **Ground Truth Suite**:
  - 15 human-verified, evaluation-eligible queries: Q1, Q3, Q4, Q5, Q7, Q8, Q9, Q10, Q11, Q12, Q13, Q16, Q17, Q19, Q20.

---

## 3. Head-to-Head Comparative Metric Matrix

| Metric Category | Evaluation Metric | `BAAI/bge-small-en-v1.5` | `BAAI/bge-m3` | Delta / Advantage |
| :--- | :--- | :---: | :---: | :---: |
| **Model Characteristics** | **Architecture** | BERT-based (12 layers) | XLM-RoBERTa (24 layers) | BGE-M3 has 16.8x more parameters |
| | **Parameters** | 33.4 Million | 560 Million | — |
| | **Vector Dimension** | 384 dimensions | 1024 dimensions | BGE-M3 vectors are 2.67x larger |
| | **Context Window** | 512 tokens | 8,192 tokens | BGE-M3 handles long contexts |
| **Retrieval Accuracy** | **Hit@1** | 33.33% | **46.67%** | **+13.34%** (BGE-M3) |
| | **Hit@3** | 60.00% | **73.33%** | **+13.33%** (BGE-M3) |
| | **Hit@5** | 66.67% | **73.33%** | **+6.66%** (BGE-M3) |
| | **Precision@5** | 16.00% | **21.33%** | **+5.33%** (BGE-M3) |
| | **MRR (Mean Reciprocal Rank)** | 0.4578 | **0.6000** | **+0.1422 (+31.1%)** (BGE-M3) |
| **Computational Efficiency** | **Model Load Time** | **1.24 s** | 7.00 s | BGE-Small is 5.6x faster to load |
| | **Corpus Encoding Time (396 chunks)** | **156.02 s (2.6 min)** | 1679.30 s (28.0 min) | BGE-Small is 10.8x faster |
| | **Corpus Throughput (CPU)** | **2.54 chunks/s** | 0.24 chunks/s | BGE-Small processes ~10.6x more chunks/s |
| | **Average Query Latency** | **116.06 ms** | 484.09 ms | BGE-Small is 4.2x faster per query |
| **Memory Footprint** | **Model RAM Delta** | **+21.06 MB** | +338.04 MB | BGE-Small uses 16x less RAM |
| | **Peak Process RAM** | **421.69 MB** | 1,189.16 MB (~1.19 GB) | Both fit in 16 GB RAM |
| | **Post-Unload RAM** | 298.45 MB | 270.57 MB | Clean garbage collection verified |

---

## 4. Deep-Dive Analysis

### 1. Retrieval Accuracy Performance
- **Substantial Quality Leap**: `BGE-M3` achieved a **0.6000 MRR**, placing the first relevant chunk at rank 1 or 2 on average across queries, whereas `BGE-Small` (MRR 0.4578) placed the first relevant chunk between rank 2 and 3.
- **Top-1 Precision**: In nearly half of the queries (46.67%), `BGE-M3` returned the exact target NIST chunk as the single top result, compared to only one-third (33.33%) for `BGE-Small`.
- **Semantic Differentiation**: `BGE-M3` demonstrated superior semantic separation on highly nuanced cloud queries (e.g. separating Q1 "risks", Q4 "governance", Q5 "responsibility", and Q10 "data storage").

### 2. Computational and Latency Trade-Offs
- **Query Latency (Runtime User Impact)**:
  - `BGE-Small`: 116 ms
  - `BGE-M3`: 484 ms
  - *Analysis*: In a production RAG pipeline, the generation step (LLM response via Groq API) typically consumes 800–2,500 ms. An embedding latency of 484 ms is completely acceptable and will not cause perceptible user lag.
- **Corpus Ingestion Throughput (One-Time Indexing Impact)**:
  - On CPU-only PyTorch, encoding 396 chunks took 2.6 minutes with BGE-Small, versus 28.0 minutes with BGE-M3.
  - This 10.8x throughput gap is the primary operational trade-off.

---

## 5. Full-Corpus Projections (13,084 Chunks)

Based on the measured throughput and vector memory metrics, the projections for indexing the full 73-document NIST corpus (13,084 chunks) are as follows:

| Dimension | `BAAI/bge-small-en-v1.5` | `BAAI/bge-m3` | Feasibility Assessment |
| :--- | :---: | :---: | :--- |
| **Projected CPU Ingestion Time** | **~1.43 hours** (~86 mins) | **~15.14 hours** (~908 mins) | BGE-Small can be indexed in a single lunch break; BGE-M3 requires an overnight batch job or GPU acceleration. |
| **Raw Vector Storage Size** | **~20.1 MB** (384 $\times$ 4 bytes) | **~53.6 MB** (1024 $\times$ 4 bytes) | Both easily fit in our ~1,535 MB free disk headroom. |
| **Estimated Qdrant Index Size** | **~60–90 MB** | **~160–220 MB** | Both comfortably fit within disk limits (> 500 MB reserve preserved). |
| **Peak Ingestion Working RAM** | **~600–800 MB** | **~2.2–3.0 GB** | Safe on 16 GB laptop RAM with batching. |

---

## 6. Strategic Decision Matrix & Final Recommendation

| Deployment Strategy | Recommended Model | Rationale & Trade-Off |
| :--- | :---: | :--- |
| **Maximum Retrieval Accuracy (Recommended)** | **`BAAI/bge-m3`** | **Best RAG accuracy**: +13.3% Hit@1/Hit@3, +31% MRR. Query latency (484 ms) is fully interactive. Full ingestion can be run as a one-time overnight task. |
| **Rapid Iteration / Low CPU Resource** | **`BAAI/bge-small-en-v1.5`** | **Fastest turnaround**: Full corpus indexes in ~1.4 hours on CPU. Lower dimensional index (384 vs 1024). Acceptable baseline accuracy (66.7% Hit@5). |

### Summary Recommendation
`BAAI/bge-m3` provides a significant and decisive improvement in retrieval quality (+13.3% Hit@1, 0.6000 MRR) without violating laptop RAM or disk constraints. Its higher one-time ingestion cost (~15 hours on CPU) is a worthwhile trade-off for substantially better factual grounding and precision in the Cybersecurity RAG system.
