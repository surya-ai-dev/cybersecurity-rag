# Lightweight Embedding Benchmark Report

**Date**: 2026-10-16 12:40:45  
**Evaluation Corpus**: 396 structure-aware chunks (NIST SP 800-144 & SP 800-146)  
**Evaluation Queries**: 15 verified questions from `retrieval_ground_truth_current.json`  
**Hardware Environment**: CPU-only PyTorch execution on 16 GB RAM  

---

## 1. Executive Summary

This benchmark evaluates lightweight embedding models (384-dimensional) on CPU for the Cybersecurity RAG project.
It compares their retrieval accuracy (Hit@K, Precision@5, MRR) and runtime efficiency (load time, throughput, query latency)
against the recorded historical baseline for `BAAI/bge-m3`.

### Evaluated & Reference Models

| Model Alias | Repository ID | Dimension | Evaluation Status | Role |
| :--- | :--- | :---: | :---: | :--- |
| **BGE-Small-en-v1.5** | `BAAI/bge-small-en-v1.5` | 384 | **EVALUATED** | Baseline |
| **MiniLM-L6-v2** | `sentence-transformers/all-MiniLM-L6-v2` | 384 | **EVALUATED** | Candidate |
| **E5-Small-v2** | `intfloat/e5-small-v2` | 384 | **SKIPPED (Not cached locally)** | Candidate |
| **BGE-M3 [Historical Reference]** | `BAAI/bge-m3` | 1024 | **HISTORICAL REFERENCE** | Historical Reference (Heavyweight) |

---

## 2. Comparative Metric Table

> [!NOTE]
> BGE-M3 results are strictly **historical reference numbers** recorded during the Stage 2 pilot benchmark and were not re-evaluated during this run.

| Metric Category | Metric | BGE-Small-en-v1.5 | MiniLM-L6-v2 | BGE-M3 [Historical Reference] |
| :--- | :--- | :---: | :---: | :---: |
| **Architecture** | Parameters | 33.4M | 22.7M | 560M |
| **Architecture** | Vector Dimension | 384 | 384 | 1024 |
| **Retrieval Accuracy** | Hit@1 | 33.33% | 26.67% | 46.67% |
| **Retrieval Accuracy** | Hit@3 | 60.00% | 60.00% | 73.33% |
| **Retrieval Accuracy** | Hit@5 | 66.67% | 66.67% | 73.33% |
| **Retrieval Accuracy** | Precision@5 | 16.00% | 14.67% | 21.33% |
| **Retrieval Accuracy** | MRR | 0.4578 | 0.4467 | 0.6000 |
| **Computational Speed** | Model Load Time | 3.05 s | 1.10 s | 7.00 s |
| **Computational Speed** | Corpus Encoding (396 chunks) | 131.16 s | 33.34 s | 1600.02 s |
| **Computational Speed** | CPU Throughput | 3.02 chunks/s | 11.88 chunks/s | 0.25 chunks/s |
| **Computational Speed** | Avg Query Latency | 53.7 ms | 26.8 ms | 564.6 ms |
| **Memory Footprint** | Model RAM Delta | +27.4 MB | +12.1 MB | +338.0 MB |

---

## 3. Methodology & Measurement Limitations

1. **Ranking Methodology**: All embeddings are $L_2$-normalized; cosine similarity is computed directly via in-memory dot product `corpus_embeddings @ query_embedding`.
2. **Prefix Rules**: E5 models require `query: ` for questions and `passage: ` for documents; BGE-small and MiniLM use direct text encoding without prefixes.
3. **RAM Tracking**: Process Resident Set Size (RSS) is sampled using `psutil`. Notice that Python runtime garbage collection and OS paging can introduce slight non-linear fluctuations in RSS delta.
4. **CPU Latency**: Timings are measured on CPU with single-process PyTorch execution. Background OS tasks may introduce modest run-to-run jitter ($\pm 5\%$).
