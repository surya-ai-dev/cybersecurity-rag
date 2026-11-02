# Controlled Benchmark: Adaptive Query Rewriting Evaluation (36 Questions)

**Date:** 2026-10-21 05:48:03  
**Corpus:** Full Cybersecurity Corpus (13,084 chunks)  
**Ground Truth:** `data/evaluation/retrieval_ground_truth_v2.json` (36 verified questions, 63 target chunks)  
**LLM Rewriter Model:** `qwen/qwen3.8-27b` (domain-expanded system prompt)  
**Confidence Evaluator:** `ConfidenceEvaluator(score_threshold=0.735, mean_threshold=0.7)`  

## Executive Summary

- **Confident Questions (Skipped Rewrite):** 6 / 36 (16.7%)
- **Low Confidence Questions (Triggered Rewrite):** 30 / 36 (83.3%)
- **Config A (Baseline):** Hit@5 = **83.33%**, Recall@5 = **59.03%**, Mean Latency = **4511.5 ms**
- **Config B (Always-On Rewriter):** Hit@5 = **77.78%** (-5.55%), Recall@5 = **57.41%**, Mean Latency = **4408.1 ms**
- **Config C (Adaptive without Merging):** Hit@5 = **80.56%** (-2.77%), Recall@5 = **58.33%**, Mean Latency = **4996.6 ms**
- **Config D (Adaptive with Candidate Merging):** Hit@5 = **80.56%** (-2.77%), Recall@5 = **59.72%** (+0.69%), Mean Latency = **5041.6 ms**

### Key Verdict

Config D does not fully recover baseline performance (80.56% vs 83.33%).

## Comparative Benchmark Metrics Table

| Metric | Config A: Baseline | Config B: Always-On | Config C: Adaptive (No Merge) | Config D: Adaptive (Merged) | Delta (D vs A) | Delta (D vs B) |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Hit Rate@1** | 50.00% | 38.89% | 41.67% | 41.67% | -8.33% | +2.78% |
| **Hit Rate@5** | **83.33%** | 77.78% | 80.56% | **80.56%** | **-2.77%** | **+2.78%** |
| **Recall@1** | 35.18% | 29.17% | 30.09% | 30.09% | -5.09% | +0.92% |
| **Recall@5** | **59.03%** | 57.41% | 58.33% | **59.72%** | **+0.69%** | **+2.31%** |
| **Precision@5** | 18.89% | 16.67% | 17.22% | 17.78% | -1.11% | +1.11% |
| **MRR@5** | 0.6222 | 0.5245 | 0.5523 | 0.5523 | -0.0699 | +0.0278 |
| **NDCG@5** | 0.5262 | 0.4717 | 0.4848 | 0.4914 | -0.0348 | +0.0197 |
| **Mean Latency** | 4511.5 ms | 4408.1 ms | 4996.6 ms | 5041.6 ms | +530.1 ms | +633.5 ms |
| **Latency p50** | 4465.7 ms | 4396.6 ms | 5024.8 ms | 4997.9 ms | +532.2 ms | +601.2 ms |
| **Latency p95** | 6182.1 ms | 5814.1 ms | 6573.1 ms | 6829.0 ms | +646.9 ms | +1014.9 ms |
| **Improved / Neutral / Regressed** | N/A (Baseline) | 5 / 16 / 15 | 5 / 17 / 14 | **5 / 17 / 14** | N/A | N/A |

## Detailed Analysis of Target Questions

### Analysis of the Five Questions Improved by Rewriting (Q10, Q19, Q25, Q38, Q40)

| QID | Confidence Decision | Top1 Dense | Mean3 Dense | Conf A Hit@5 | Conf B Hit@5 | Conf C Hit@5 | Conf D Hit@5 | In Pre-Rerank Pool (D) | Reranker Retained (D) |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Q10** | **LOW** | 0.6928 | 0.6768 | 0 | 1 | 1 | 1 | Yes | Yes |
| **Q19** | **LOW** | 0.7106 | 0.6888 | 0 | 1 | 1 | 1 | Yes | Yes |
| **Q25** | **LOW** | 0.7095 | 0.6905 | 0 | 1 | 1 | 1 | Yes | Yes |
| **Q38** | **LOW** | 0.7337 | 0.6773 | 0 | 1 | 1 | 1 | Yes | Yes |
| **Q40** | **LOW** | 0.6933 | 0.6874 | 1 | 1 | 1 | 1 | Yes | Yes |


### Analysis of the Eight Questions Regressed by Always-On Rewriting (Q1, Q4, Q9, Q11, Q12, Q14, Q17, Q30)

| QID | Confidence Decision | Top1 Dense | Mean3 Dense | Conf A Hit@5 | Conf B Hit@5 | Conf C Hit@5 | Conf D Hit@5 | In Pre-Rerank Pool (D) | Reranker Retained (D) | Status D vs A |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Q1** | LOW | 0.6750 | 0.6912 | 1 | 1 | 1 | 1 | Yes | Yes | REGRESSED |
| **Q4** | LOW | 0.6338 | 0.6474 | 1 | 0 | 0 | 0 | Yes | No | REGRESSED |
| **Q9** | **CONFIDENT** | 0.7765 | 0.7333 | 1 | 0 | 1 | 1 | Yes | Yes | NEUTRAL |
| **Q11** | LOW | 0.6826 | 0.6852 | 1 | 0 | 0 | 0 | Yes | No | REGRESSED |
| **Q12** | LOW | 0.7257 | 0.7045 | 1 | 0 | 0 | 0 | Yes | No | REGRESSED |
| **Q14** | LOW | 0.6835 | 0.6306 | 1 | 1 | 1 | 1 | Yes | Yes | REGRESSED |
| **Q17** | LOW | 0.6862 | 0.6654 | 1 | 0 | 0 | 0 | Yes | No | REGRESSED |
| **Q30** | LOW | 0.7005 | 0.6919 | 1 | 0 | 0 | 0 | Yes | No | REGRESSED |


## Full 36-Question Evaluation Results

| QID | Decision | Hit@5 (A) | Hit@5 (B) | Hit@5 (C) | Hit@5 (D) | Recall@5 (A) | Recall@5 (D) | MRR@5 (A) | MRR@5 (D) | Status (D vs A) |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Q1 | LOW | 1 | 1 | 1 | 1 | 0.67 | 0.33 | 1.00 | 0.50 | REGRESSED |
| Q3 | LOW | 1 | 1 | 1 | 1 | 0.33 | 0.33 | 1.00 | 0.50 | REGRESSED |
| Q4 | LOW | 1 | 0 | 0 | 0 | 0.50 | 0.00 | 0.33 | 0.00 | REGRESSED |
| Q5 | LOW | 1 | 1 | 1 | 1 | 0.25 | 0.25 | 0.50 | 1.00 | NEUTRAL |
| Q7 | LOW | 1 | 1 | 1 | 1 | 0.33 | 0.33 | 1.00 | 0.25 | REGRESSED |
| Q8 | LOW | 0 | 0 | 0 | 0 | 0.00 | 0.00 | 0.00 | 0.00 | NEUTRAL |
| Q9 | CONF | 1 | 0 | 1 | 1 | 0.33 | 0.33 | 1.00 | 1.00 | NEUTRAL |
| Q10 | LOW | 0 | 1 | 1 | 1 | 0.00 | 0.67 | 0.00 | 1.00 | IMPROVED |
| Q11 | LOW | 1 | 0 | 0 | 0 | 0.25 | 0.00 | 1.00 | 0.00 | REGRESSED |
| Q12 | LOW | 1 | 0 | 0 | 0 | 0.50 | 0.00 | 1.00 | 0.00 | REGRESSED |
| Q13 | LOW | 1 | 1 | 1 | 1 | 0.33 | 0.33 | 0.50 | 0.20 | REGRESSED |
| Q14 | LOW | 1 | 1 | 1 | 1 | 1.00 | 1.00 | 1.00 | 0.33 | REGRESSED |
| Q16 | LOW | 1 | 1 | 1 | 1 | 0.33 | 0.33 | 0.25 | 0.20 | NEUTRAL |
| Q17 | LOW | 1 | 0 | 0 | 0 | 1.00 | 0.00 | 0.25 | 0.00 | REGRESSED |
| Q19 | LOW | 0 | 1 | 1 | 1 | 0.00 | 0.33 | 0.00 | 1.00 | IMPROVED |
| Q20 | LOW | 1 | 1 | 1 | 1 | 0.25 | 0.25 | 0.33 | 1.00 | NEUTRAL |
| Q21 | LOW | 1 | 1 | 1 | 1 | 1.00 | 1.00 | 1.00 | 1.00 | NEUTRAL |
| Q22 | LOW | 1 | 1 | 1 | 1 | 1.00 | 1.00 | 0.50 | 0.20 | REGRESSED |
| Q23 | LOW | 1 | 1 | 1 | 1 | 1.00 | 1.00 | 1.00 | 0.50 | REGRESSED |
| Q24 | CONF | 1 | 1 | 1 | 1 | 1.00 | 1.00 | 1.00 | 1.00 | NEUTRAL |
| Q25 | LOW | 0 | 1 | 1 | 1 | 0.00 | 1.00 | 0.00 | 1.00 | IMPROVED |
| Q26 | CONF | 1 | 1 | 1 | 1 | 1.00 | 1.00 | 1.00 | 1.00 | NEUTRAL |
| Q27 | LOW | 1 | 1 | 1 | 1 | 0.33 | 0.33 | 1.00 | 1.00 | NEUTRAL |
| Q28 | LOW | 1 | 1 | 1 | 1 | 1.00 | 1.00 | 1.00 | 0.33 | REGRESSED |
| Q29 | LOW | 1 | 1 | 1 | 1 | 1.00 | 1.00 | 1.00 | 1.00 | NEUTRAL |
| Q30 | LOW | 1 | 0 | 0 | 0 | 0.50 | 0.00 | 0.20 | 0.00 | REGRESSED |
| Q31 | LOW | 1 | 1 | 1 | 1 | 1.00 | 1.00 | 1.00 | 1.00 | NEUTRAL |
| Q32 | CONF | 1 | 1 | 1 | 1 | 1.00 | 1.00 | 1.00 | 1.00 | NEUTRAL |
| Q33 | LOW | 0 | 0 | 0 | 0 | 0.00 | 0.00 | 0.00 | 0.00 | NEUTRAL |
| Q34 | CONF | 1 | 1 | 1 | 1 | 1.00 | 1.00 | 1.00 | 1.00 | NEUTRAL |
| Q35 | LOW | 1 | 1 | 1 | 1 | 1.00 | 1.00 | 0.20 | 0.33 | NEUTRAL |
| Q36 | LOW | 1 | 1 | 1 | 1 | 1.00 | 1.00 | 0.33 | 0.20 | REGRESSED |
| Q37 | CONF | 1 | 1 | 1 | 1 | 1.00 | 1.00 | 1.00 | 1.00 | NEUTRAL |
| Q38 | LOW | 0 | 1 | 1 | 1 | 0.00 | 1.00 | 0.00 | 0.33 | IMPROVED |
| Q39 | LOW | 1 | 1 | 1 | 1 | 1.00 | 1.00 | 0.50 | 0.50 | NEUTRAL |
| Q40 | LOW | 1 | 1 | 1 | 1 | 0.33 | 0.67 | 0.50 | 0.50 | IMPROVED |


## Architectural & Engineering Insights

1. **Confidence Threshold Calibration:**
   - The existing thresholds (`score_threshold=0.735`, `mean_threshold=0.700`) were calibrated on pilot embeddings.
   - In our full 13,084-chunk corpus, cosine similarities for specialized technical questions cluster between `0.65` and `0.73`. Consequently, **30 out of 36 questions (83.3%)** are classified as `low_confidence`.
   - Only 6 questions passed the threshold as `CONFIDENT` (Q9, Q24, Q26, Q32, Q34, Q37).
   - For **Q9**, this decision was highly beneficial: it prevented the regression observed in always-on rewriting (preserving Hit@5 = 100%).
   - However, for Q4, Q11, Q12, Q17, and Q30, the low confidence classification triggered rewriting unnecessarily, subjecting them to reranking regressions.

2. **The Mechanism of Regressions in Candidate Merging (Config D):**
   - For all 5 regressed questions with Hit@5 = 0 (Q4, Q11, Q12, Q17, Q30), `merge_candidate_pools` **successfully preserved the ground-truth target chunks in the pre-reranking pool** (20 candidates).
   - In fact, `targets_in_pre_rerank_pool` contained the expected target chunks for all 5 questions.
   - **The single point of failure was the cross-encoder reranking query:** In `app/pipeline/engine.py`, lines 186 & 217, when query rewriting triggers, `search_query` is reassigned to `rewrite_res.rewritten_query`, and the cross-encoder reranks the merged candidates using this rewritten query.
   - **Diagnostic Proof:** When we reranked the *identical* merged candidate pool using the **original user question**, Hit@5 returned to **100% (1, 1, 1, 1, 1)** for Q4, Q11, Q12, Q17, and Q30! Conversely, reranking with the **rewritten query** produced **0% Hit@5** because the rewritten keyword expansions ('shared responsibility model', 'compliance', 'risk management') caused the cross-encoder to promote generic distractors over the specific answering chunks.

3. **The Dual Query Paradox:**
   - For queries needing domain expansion (Q10, Q19, Q25, Q38), the ground-truth chunks are only surfaced and prioritized by the cross-encoder when scored against the **technical expanded query** (Hit@5 = 100% with rewritten query vs 0% with original question).
   - For queries with precise technical intent (Q4, Q11, Q12, Q17, Q30), the cross-encoder performs optimally when scored against the **original user question** (Hit@5 = 100% with original query vs 0% with rewritten query).

## Production Recommendations

1. **Do NOT Enable Current Adaptive Query Rewriting in Production:** With current thresholds, Config C achieves Hit@5 of 80.56% and Config D achieves 80.56%, both falling short of the Baseline's 83.33% (-2.77% net regression). Furthermore, adaptive retrieval increases average query latency by **+530 ms** (+11.7%) due to the dual retrieval passes.
2. **Decouple Candidate Retrieval Query from Reranker Query:** Use the rewritten query *strictly* to broaden candidate recall in dense and BM25 retrievals. When reranking the merged candidate pool, evaluate candidates using the **original user question** or an ensemble score combining both `reranker(orig_query, chunk)` and `reranker(rewritten_query, chunk)`.
3. **Recalibrate Confidence Evaluator Signals:** A single cosine similarity cutoff is insufficient across varying technical query granularities. Incorporate **lexical BM25 score dispersion** and **entropy/margin between top-1 and top-5 dense scores** rather than relying solely on raw cosine similarity thresholds.
