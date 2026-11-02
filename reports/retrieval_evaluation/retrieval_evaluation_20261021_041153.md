# Cybersecurity RAG: Retrieval Pipeline Benchmark Report

- **Timestamp:** `2026-10-21T04:11:53.212803`
- **Questions Evaluated:** `1`
- **Dense Embedding Model:** `BAAI/bge-m3`
- **Cross-Encoder Reranker:** `cross-encoder/ms-marco-MiniLM-L-6-v2`
- **Initial Candidate Top-K:** `20`
- **Production Cutoff:** `Top 5`

---

## 1. Executive Summary & Configuration Comparison

| Configuration | Hit@1 | Hit@5 | Hit@20 | Recall@5 | Recall@20 | Precision@5 | MRR@20 | NDCG@5 | NDCG@20 | Avg Latency |
|---|---|---|---|---|---|---|---|---|---|---|
| **Dense Retrieval Only (BGE-M3)** | 100.00% | **100.00%** | 100.00% | **66.67%** | 100.00% | 40.00% | **1.0000** | **0.7654** | 0.8886 | 44483.8 ms |
| **BM25 Retrieval Only (Okapi)** | 0.00% | **100.00%** | 100.00% | **33.33%** | 100.00% | 20.00% | **0.2000** | **0.1815** | 0.4121 | 579.8 ms |
| **Hybrid Retrieval (Dense + BM25 + RRF)** | 0.00% | **100.00%** | 100.00% | **33.33%** | 100.00% | 20.00% | **0.5000** | **0.2961** | 0.5989 | 45065.0 ms |
| **Hybrid + Cross-Encoder Reranker** | 100.00% | **100.00%** | 100.00% | **66.67%** | 100.00% | 40.00% | **1.0000** | **0.7039** | 0.8212 | 50721.3 ms |

> [!NOTE]
> **Production Impact:** Configuration D evaluates the actual candidate stream delivered into the context builder. Top-5 metrics represent the exact context injected into prompt generation, while Top-20 metrics reflect the underlying candidate pool ceiling.

---

## 2. Per-Question Detailed Performance Matrix

| QID | Question Preview | Expected Chunks | Dense Hit@5 | BM25 Hit@5 | Hybrid Hit@5 | Reranked Hit@5 | Reranked Recall@5 | Reranked MRR@20 |
|---|---|---|---|---|---|---|---|---|
| **Q1** | What are the security risks of public cloud c... | 3 | ✅ | ✅ | ✅ | ✅ | 66.7% | 1.000 |

---

## 3. Top Missing or Suboptimal Queries (Config D Hit@5 = 0)

🎉 **Zero misses! All 36 evaluation questions achieved 100% Hit@5 in the reranked pipeline.**