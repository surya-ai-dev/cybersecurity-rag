# Controlled Candidate-Depth Retrieval Experiment on Question Q10

- **Timestamp:** `2026-10-21T04:55:06.790611`
- **Question ID:** `Q10`
- **Question:** *"What are the security implications of storing organizational data in the public cloud?"*
- **Target Ground-Truth Chunks:** `NIST_SP_800-144_txt_00080`, `NIST_SP_800-144_txt_00081`, `NIST_SP_800-144_txt_00082`

---

## 1. Overall Performance Comparison Table

| Configuration | Dense / BM25 / RRF Pool | Reranker | Hit@5 | Recall@5 | MRR@5 | NDCG@5 | Retrieval Latency | Rerank Latency | Total Latency |
|---|---|---|---|---|---|---|---|---|---|
| **A. Baseline (Dense 20 / BM25 20 / RRF 20 -> Reranker)** | 20 / 20 / 20 | Enabled | **0.0%** | **0.0%** | **0.0000** | **0.0000** | 5034.0 ms | 7190.7 ms | 12224.7 ms |
| **B. Expanded Retrieval (Dense 30 / BM25 30 / RRF 30 -> Reranker)** | 30 / 30 / 30 | Enabled | **0.0%** | **0.0%** | **0.0000** | **0.0000** | 1150.5 ms | 7712.7 ms | 8863.2 ms |
| **C. Larger Candidate Pool (Dense 50 / BM25 50 / RRF 50 -> Reranker)** | 50 / 50 / 50 | Enabled | **0.0%** | **0.0%** | **0.0000** | **0.0000** | 768.1 ms | 8794.4 ms | 9562.5 ms |
| **D. Larger Candidate Pool Without Reranking (Dense 50 / BM25 50 / RRF 50)** | 50 / 50 / 50 | Disabled | **0.0%** | **0.0%** | **0.0000** | **0.0000** | 519.8 ms | 0.0 ms | 519.8 ms |

---

## 2. Target Ground-Truth Chunk Journey Across Pipeline Stages

### A. Baseline (Dense 20 / BM25 20 / RRF 20 -> Reranker -> Top 5)

| Target Chunk ID | In Dense (Rank / Score) | In BM25 (Rank / Score) | In RRF Pool (Rank / Score) | In Reranker (Rank / Score) | In Final Top 5? |
|---|---|---|---|---|---|
| `NIST_SP_800-144_txt_00080` | Rank 19 (0.6492) | ❌ Outside 20 | ❌ Truncated (< 20) | Rank None (N/A) | ❌ No |
| `NIST_SP_800-144_txt_00081` | Rank 18 (0.6493) | ❌ Outside 20 | ❌ Truncated (< 20) | Rank None (N/A) | ❌ No |
| `NIST_SP_800-144_txt_00082` | ❌ Outside 20 | ❌ Outside 20 | ❌ Truncated (< 20) | Rank None (N/A) | ❌ No |

### B. Expanded Retrieval (Dense 30 / BM25 30 / RRF 30 -> Reranker -> Top 5)

| Target Chunk ID | In Dense (Rank / Score) | In BM25 (Rank / Score) | In RRF Pool (Rank / Score) | In Reranker (Rank / Score) | In Final Top 5? |
|---|---|---|---|---|---|
| `NIST_SP_800-144_txt_00080` | Rank 19 (0.6492) | Rank 30 (28.2844) | Rank 14 (0.023769) | Rank 8 (2.5924) | ❌ No |
| `NIST_SP_800-144_txt_00081` | Rank 18 (0.6493) | ❌ Outside 30 | Rank 29 (0.012821) | Rank 26 (-0.3122) | ❌ No |
| `NIST_SP_800-144_txt_00082` | ❌ Outside 30 | ❌ Outside 30 | ❌ Truncated (< 30) | Rank None (N/A) | ❌ No |

### C. Larger Candidate Pool (Dense 50 / BM25 50 / RRF 50 -> Reranker -> Top 5)

| Target Chunk ID | In Dense (Rank / Score) | In BM25 (Rank / Score) | In RRF Pool (Rank / Score) | In Reranker (Rank / Score) | In Final Top 5? |
|---|---|---|---|---|---|
| `NIST_SP_800-144_txt_00080` | Rank 19 (0.6492) | Rank 30 (28.2844) | Rank 16 (0.023769) | Rank 8 (2.5924) | ❌ No |
| `NIST_SP_800-144_txt_00081` | Rank 18 (0.6493) | ❌ Outside 50 | Rank 36 (0.012821) | Rank 38 (-0.3122) | ❌ No |
| `NIST_SP_800-144_txt_00082` | ❌ Outside 50 | ❌ Outside 50 | ❌ Truncated (< 50) | Rank None (N/A) | ❌ No |

### D. Larger Candidate Pool Without Reranking (Dense 50 / BM25 50 / RRF 50 -> Top 5 Direct)

| Target Chunk ID | In Dense (Rank / Score) | In BM25 (Rank / Score) | In RRF Pool (Rank / Score) | In Reranker | In Final Top 5? |
|---|---|---|---|---|---|
| `NIST_SP_800-144_txt_00080` | Rank 19 (0.6492) | Rank 30 (28.2844) | Rank 16 (0.023769) | Disabled | ❌ No |
| `NIST_SP_800-144_txt_00081` | Rank 18 (0.6493) | ❌ Outside 50 | Rank 36 (0.012821) | Disabled | ❌ No |
| `NIST_SP_800-144_txt_00082` | ❌ Outside 50 | ❌ Outside 50 | ❌ Truncated (< 50) | Disabled | ❌ No |

---

## 3. Actual Delivered Top-5 Chunks by Configuration

### Configuration A: Baseline (Dense 20 / BM25 20 / RRF 20 -> Reranker)
1. ⚪ `NIST_SP_800-144_txt_00021` (NIST_SP_800-144) — *Reranker Score: 3.7604* — Section: `**Carefully plan the security and privacy aspects of cloud computing solutions before engaging them.**`
2. ⚪ `NIST_SP_800-144_txt_00043` (NIST_SP_800-144) — *Reranker Score: 3.7304* — Section: `**3.2 The Security and Privacy Upside**`
3. ⚪ `NIST_SP_800-144_txt_00038` (NIST_SP_800-144) — *Reranker Score: 3.5729* — Section: `**2.3 Outsourcing and Accountability**`
4. ⚪ `NIST_SP_800-146_txt_00135` (NIST_SP_800-146) — *Reranker Score: 3.046* — Section: `Unknown`
5. ⚪ `NIST_SP_800-144_txt_00024` (NIST_SP_800-144) — *Reranker Score: 2.7044* — Section: `**Ensure that a cloud computing solution satisfies organizational security and privacy requirements.**`

### Configuration B: Expanded Retrieval (Dense 30 / BM25 30 / RRF 30 -> Reranker)
1. ⚪ `NIST_SP_800-144_txt_00021` (NIST_SP_800-144) — *Reranker Score: 3.7604* — Section: `**Carefully plan the security and privacy aspects of cloud computing solutions before engaging them.**`
2. ⚪ `NIST_SP_800-144_txt_00043` (NIST_SP_800-144) — *Reranker Score: 3.7304* — Section: `**3.2 The Security and Privacy Upside**`
3. ⚪ `NIST_SP_800-144_txt_00038` (NIST_SP_800-144) — *Reranker Score: 3.5729* — Section: `**2.3 Outsourcing and Accountability**`
4. ⚪ `NIST_SP_800-146_txt_00135` (NIST_SP_800-146) — *Reranker Score: 3.046* — Section: `**8.5 Information Security**`
5. ⚪ `NIST_SP_800-144_txt_00024` (NIST_SP_800-144) — *Reranker Score: 2.7044* — Section: `**Ensure that a cloud computing solution satisfies organizational security and privacy requirements.**`

### Configuration C: Larger Candidate Pool (Dense 50 / BM25 50 / RRF 50 -> Reranker)
1. ⚪ `NIST_SP_800-144_txt_00021` (NIST_SP_800-144) — *Reranker Score: 3.7604* — Section: `**Carefully plan the security and privacy aspects of cloud computing solutions before engaging them.**`
2. ⚪ `NIST_SP_800-144_txt_00043` (NIST_SP_800-144) — *Reranker Score: 3.7304* — Section: `**3.2 The Security and Privacy Upside**`
3. ⚪ `NIST_SP_800-144_txt_00038` (NIST_SP_800-144) — *Reranker Score: 3.5729* — Section: `**2.3 Outsourcing and Accountability**`
4. ⚪ `NIST_SP_800-146_txt_00135` (NIST_SP_800-146) — *Reranker Score: 3.046* — Section: `**8.5 Information Security**`
5. ⚪ `NIST_SP_800-144_txt_00024` (NIST_SP_800-144) — *Reranker Score: 2.7044* — Section: `**Ensure that a cloud computing solution satisfies organizational security and privacy requirements.**`

### Configuration D: Larger Candidate Pool Without Reranking (Dense 50 / BM25 50 / RRF 50)
1. ⚪ `NIST_SP_800-144_txt_00040` (NIST_SP_800-144) — *RRF Score: 0.0325* — Section: `**<mark>3. Public Cloud Services</mark>**`
2. ⚪ `NIST_SP_800-144_txt_00094` (NIST_SP_800-144) — *RRF Score: 0.0311* — Section: `**<mark>5. Public Cloud Outsourcing</mark>**`
3. ⚪ `NIST_SP_800-144_txt_00024` (NIST_SP_800-144) — *RRF Score: 0.0302* — Section: `**Ensure that a cloud computing solution satisfies organizational security and privacy requirements.**`
4. ⚪ `NIST_SP_800-144_txt_00043` (NIST_SP_800-144) — *RRF Score: 0.0302* — Section: `**3.2 The Security and Privacy Upside**`
5. ⚪ `NIST_SP_800-144_txt_00021` (NIST_SP_800-144) — *RRF Score: 0.0292* — Section: `**Carefully plan the security and privacy aspects of cloud computing solutions before engaging them.**`
