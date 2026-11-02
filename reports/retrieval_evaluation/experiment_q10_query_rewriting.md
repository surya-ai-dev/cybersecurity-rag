# Controlled Query Rewriting Experiment on Question Q10

- **Timestamp:** `2026-10-21T05:05:17.418512`
- **Question ID:** `Q10`
- **Original Question:** *"What are the security implications of storing organizational data in the public cloud?"*
- **Target Ground-Truth Chunks:** `NIST_SP_800-144_txt_00080`, `NIST_SP_800-144_txt_00081`, `NIST_SP_800-144_txt_00082`
- **Fixed Candidate Depth Settings:** `Dense=50, BM25=50, RRF=50, Cross-Encoder=ms-marco-MiniLM-L-6-v2, Top=5`

---

## 1. Overall Performance Comparison Matrix

| Experiment | Search Query Sent to Retrievers | Hit@5 | Recall@5 | MRR@5 | NDCG@5 | Rewriter Latency | Retrieval Latency | Rerank Latency | Total Latency |
|---|---|---|---|---|---|---|---|---|---|
| **A. Baseline (Original Question)** | *"What are the security implications of storing organizational data in the public cloud?"* | **0.0%** | **0.0%** | **0.0000** | **0.0000** | 0.0 ms | 9499.7 ms | 14040.6 ms | 23540.3 ms |
| **B1. Automated LLM Rewriter (qwen/qwen3.8-27b)** | *"public cloud data storage security implications organizational data confidentiality integrity availability"* | **0.0%** | **0.0%** | **0.0000** | **0.0000** | 910.1 ms | 1841.9 ms | 11265.1 ms | 14017.1 ms |
| **B2. Domain-Expanded Technical Query** | *"public cloud data storage security implications data protection shared environment multi-tenant isolation data at rest encryption"* | **100.0%** | **66.7%** | **1.0000** | **0.7654** | 0.0 ms | 1367.0 ms | 9999.4 ms | 11366.4 ms |

---

## 2. Stage-by-Stage Target Chunk Tracking

### Experiment A: Baseline (Original Question)
- **Query Used:** *"What are the security implications of storing organizational data in the public cloud?"*

| Target Chunk ID | Dense (Rank / Score) | BM25 (Rank / Score) | RRF Pool (Rank / Score) | Reranker (Rank / Score) | In Top 5? | Status / Fate |
|---|---|---|---|---|---|---|
| `NIST_SP_800-144_txt_00080` | Rank 19 (0.6492) | Rank 30 (28.2844) | Rank 16 (0.023769) | Rank 8 (2.5924) | ❌ No | Retrieved in candidate pool but ranked outside Top 5 by Reranker (Rank 8) |
| `NIST_SP_800-144_txt_00081` | Rank 18 (0.6493) | ❌ > 50 | Rank 36 (0.012821) | Rank 38 (-0.3122) | ❌ No | Retrieved in candidate pool but ranked outside Top 5 by Reranker (Rank 38) |
| `NIST_SP_800-144_txt_00082` | ❌ > 50 | ❌ > 50 | ❌ Discarded | ❌ Not seen | ❌ No | Absent from both Dense and BM25 top 50 |

### Experiment B1: Automated LLM Rewriter (qwen/qwen3.8-27b)
- **Query Used:** *"public cloud data storage security implications organizational data confidentiality integrity availability"*

| Target Chunk ID | Dense (Rank / Score) | BM25 (Rank / Score) | RRF Pool (Rank / Score) | Reranker (Rank / Score) | In Top 5? | Status / Fate |
|---|---|---|---|---|---|---|
| `NIST_SP_800-144_txt_00080` | ❌ > 50 | ❌ > 50 | ❌ Discarded | ❌ Not seen | ❌ No | Absent from both Dense and BM25 top 50 |
| `NIST_SP_800-144_txt_00081` | Rank 34 (0.657) | ❌ > 50 | ❌ Discarded | ❌ Not seen | ❌ No | Discarded during RRF top-50 pool cutoff |
| `NIST_SP_800-144_txt_00082` | ❌ > 50 | ❌ > 50 | ❌ Discarded | ❌ Not seen | ❌ No | Absent from both Dense and BM25 top 50 |

### Experiment B2: Domain-Expanded Technical Query
- **Query Used:** *"public cloud data storage security implications data protection shared environment multi-tenant isolation data at rest encryption"*

| Target Chunk ID | Dense (Rank / Score) | BM25 (Rank / Score) | RRF Pool (Rank / Score) | Reranker (Rank / Score) | In Top 5? | Status / Fate |
|---|---|---|---|---|---|---|
| `NIST_SP_800-144_txt_00080` | ❌ > 50 | Rank 28 (21.758) | Rank 49 (0.011364) | Rank 6 (1.0779) | ❌ No | Retrieved in candidate pool but ranked outside Top 5 by Reranker (Rank 6) |
| `NIST_SP_800-144_txt_00081` | Rank 1 (0.7217) | Rank 4 (35.3593) | Rank 2 (0.032018) | Rank 2 (3.4488) | ✅ Rank 2 | Retained in Final Top 5 (Rank 2) |
| `NIST_SP_800-144_txt_00082` | Rank 2 (0.7187) | Rank 1 (38.4477) | Rank 1 (0.032522) | Rank 1 (4.1853) | ✅ Rank 1 | Retained in Final Top 5 (Rank 1) |

---

## 3. Actual Delivered Top-5 Chunks by Experiment

### Experiment A: Baseline (Original Question)
1. ⚪ `NIST_SP_800-144_txt_00021` (NIST_SP_800-144) — *Score: 3.7604* — Section: `**Carefully plan the security and privacy aspects of cloud computing solutions before engaging them.**`
2. ⚪ `NIST_SP_800-144_txt_00043` (NIST_SP_800-144) — *Score: 3.7304* — Section: `**3.2 The Security and Privacy Upside**`
3. ⚪ `NIST_SP_800-144_txt_00038` (NIST_SP_800-144) — *Score: 3.5729* — Section: `**2.3 Outsourcing and Accountability**`
4. ⚪ `NIST_SP_800-146_txt_00135` (NIST_SP_800-146) — *Score: 3.046* — Section: `**8.5 Information Security**`
5. ⚪ `NIST_SP_800-144_txt_00024` (NIST_SP_800-144) — *Score: 2.7044* — Section: `**Ensure that a cloud computing solution satisfies organizational security and privacy requirements.**`

### Experiment B1: Automated LLM Rewriter (qwen/qwen3.8-27b)
1. ⚪ `NIST_SP_800-146_txt_00135` (NIST_SP_800-146) — *Score: 4.7013* — Section: `**8.5 Information Security**`
2. ⚪ `NIST_SP_800-144_txt_00043` (NIST_SP_800-144) — *Score: 3.5722* — Section: `**3.2 The Security and Privacy Upside**`
3. ⚪ `NIST_SP_800-144_txt_00099` (NIST_SP_800-144) — *Score: 3.4454* — Section: `**5.1 General Concerns**`
4. ⚪ `NIST_SP_800-144_txt_00026` (NIST_SP_800-144) — *Score: 3.2616* — Section: `**Maintain accountability over the privacy and security of data and applications implemented and deployed in public cloud computing environments.**`
5. ⚪ `NIST_SP_800-223_txt_00046` (NIST_SP_800-223) — *Score: 2.1926* — Section: `**3.2.4. Data Storage Zone Threats**`

### Experiment B2: Domain-Expanded Technical Query
1. 🎯 **[TARGET CHUNK]** `NIST_SP_800-144_txt_00082` (NIST_SP_800-144) — *Score: 4.1853* — Section: `**4.7 Data Protection**`
2. 🎯 **[TARGET CHUNK]** `NIST_SP_800-144_txt_00081` (NIST_SP_800-144) — *Score: 3.4488* — Section: `**4.7 Data Protection**`
3. ⚪ `NIST_SP_800-144_txt_00111` (NIST_SP_800-144) — *Score: 2.4045* — Section: `**5.2 Preliminary Activities**`
4. ⚪ `NIST_SP_800-144_txt_00048` (NIST_SP_800-144) — *Score: 2.3935* — Section: `**3.3 The Security and Privacy Downside**`
5. ⚪ `NIST_SP_800-146_txt_00135` (NIST_SP_800-146) — *Score: 1.9821* — Section: `**8.5 Information Security**`
