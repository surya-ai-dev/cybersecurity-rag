# ConfidenceEvaluator Improvement and Calibration Report

**Date:** 2026-11-01 15:52:23 UTC  
**Status:** Completed — All 4 Part A Issues Resolved & Verified  

## 1. Executive Summary & Verification Findings

This report presents the implementation and empirical validation of the enhanced `ConfidenceEvaluator`. All four Part A issues have been resolved:

1. **Issue 1 (Threshold Calibration):** Calibrated static thresholds from `0.735/0.700` down to `0.725/0.700` based on empirical BGE-M3 distribution quartiles.
2. **Issue 2 (Three-Way Decision Logic):** Replaced rigid binary AND logic with an evidence-based **HIGH / MEDIUM / LOW** decision model that evaluates multi-view lexical signals before deciding to rewrite.
3. **Issue 3 (RRF vs Dense Ranking Mismatch):** Separated confidence statistical evaluation from candidate pool ordering; extracts and independently sorts dense scores without disturbing RRF candidate ordering.
4. **Issue 4 (BM25 Evidence & Exact Identifier Matching):** Integrated BM25 max scores, cross-modal candidate overlap counts, and regex-based exact publication/control identifier verification (`NIST SP`, `SSDF`, `ABAC`, `AC-2`, etc.).

## 2. 36-Question Benchmark Aggregate Comparison

| Metric | Config A: Baseline (No Rewrite) | Config B: Old Adaptive (0.735/0.700) | Config C: Improved Adaptive (Calibrated 3-Way) | Delta vs Old Adaptive |
| :--- | :---: | :---: | :---: | :---: |
| **Hit@1** | 50.0% | 50.0% | **50.0%** | +0.00% |
| **Hit@5** | 83.33% | 83.33% | **83.33%** | **Maintained (83.33%)** |
| **Recall@5** | 59.03% | 59.03% | **59.03%** | **Maintained (59.03%)** |
| **Precision@5** | 18.89% | 18.89% | **18.89%** | +0.00% |
| **MRR@5** | 0.6222 | 0.6199 | **0.6199** | +0.0000 |
| **NDCG@5** | 0.5262 | 0.5243 | **0.5243** | +0.0000 |
| **Mean Latency** | 5636.6 ms | 6264.5 ms | **6125.2 ms** | **-139.3 ms reduction** |
| **Rewriting Triggers** | 0 / 36 (0.0%) | 30 / 36 (83.3%) | **16 / 36 (44.4%)** | **-14 rewrites (-46.7%)** |
| **Unnecessary Rewrites** | 0 | 24 / 36 | **13 / 36** | **Reduced by 11 queries** |
| **False Confidence** | 0 | 0 | **3 (Q25, Q33, Q38)** | **3 false-confidence cases** |

> [!NOTE]
> **False-Confidence Analysis:** Three questions (**Q25**, **Q33**, and **Q38**) were classified as confident and skipped query rewriting despite having an initial retrieval `Hit@5 = 0`:
> - **Q25:** Classified as **MEDIUM** and skipped rewriting due to exact identifier match (`SSDF`) and high BM25 score (40.90).
> - **Q33:** Classified as **HIGH** (`top1=0.7289 >= 0.7250`, `mean3=0.7282 >= 0.7000`) and skipped rewriting based on dense score criteria.
> - **Q38:** Classified as **MEDIUM** and skipped rewriting due to exact identifier match (`NIST SP 800-145`, `SP 800-145`), high BM25 score (`49.74 >= 25.0`), and sufficient mean top-3 dense similarity (`0.6792 >= 0.6600`).
> In these three cases, initial retrieval retrieved high-scoring distractor chunks from the target publications that satisfied confidence criteria, causing the evaluator to skip query rewriting even though the true ground-truth chunks were missed at rank 5.

## 3. Decision Level Distribution

- **HIGH Confidence (Rewrite Skipped):** 12 / 36 (33.3%)
- **MEDIUM Confidence (Evidence-Evaluated):** 17 / 36 (47.2%)
  - Resolved as Sufficient (Rewrite Skipped): 8
  - Resolved as Insufficient (Rewrite Triggered): 9
- **LOW Confidence (Rewrite Triggered):** 7 / 36 (19.4%)

## 4. Per-Question Decision Breakdown

| QID | Query | Dense Top-1 | Mean-3 | BM25 Top | Overlap | Level | Action | Reason |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Q1** | What are the security risks of public cl... | 0.734 | 0.7022 | 29.15 | 10 | **HIGH** | `skip_rewrite` | confident_high_dense(top1=0.7340>=0.7250, mean3=0.7022>=0.70... |
| **Q3** | How can client-side malware affect publi... | 0.6652 | 0.6559 | 27.17 | 4 | **LOW** | `trigger_rewrite` | low_dense_confidence(top1=0.6652<0.6800 or mean3=0.6559<0.66... |
| **Q4** | Why is governance important for public c... | 0.6638 | 0.6573 | 17.7 | 5 | **LOW** | `trigger_rewrite` | low_dense_confidence(top1=0.6638<0.6800 or mean3=0.6573<0.66... |
| **Q5** | Who is responsible for security and priv... | 0.6634 | 0.6615 | 32.41 | 7 | **LOW** | `trigger_rewrite` | low_dense_confidence(top1=0.6634<0.6800 or mean3=0.6615<0.66... |
| **Q7** | What privacy risks can arise when organi... | 0.7388 | 0.7297 | 23.79 | 6 | **HIGH** | `skip_rewrite` | confident_high_dense(top1=0.7388>=0.7250, mean3=0.7297>=0.70... |
| **Q8** | How does loss of control affect security... | 0.6712 | 0.6533 | 28.52 | 7 | **LOW** | `trigger_rewrite` | low_dense_confidence(top1=0.6712<0.6800 or mean3=0.6533<0.66... |
| **Q9** | What security issues can result from out... | 0.7765 | 0.7333 | 33.54 | 10 | **HIGH** | `skip_rewrite` | confident_high_dense(top1=0.7765>=0.7250, mean3=0.7333>=0.70... |
| **Q10** | What are the security implications of st... | 0.6928 | 0.6822 | 33.2 | 9 | **MEDIUM** | `trigger_rewrite` | low_confidence_medium_evidence(top1=0.6928<0.7050, mean3=0.6... |
| **Q11** | What responsibilities does an organizati... | 0.7008 | 0.6852 | 26.31 | 10 | **MEDIUM** | `trigger_rewrite` | low_confidence_medium_evidence(top1=0.7008<0.7050)... |
| **Q12** | What security responsibilities are share... | 0.7257 | 0.7097 | 39.82 | 6 | **HIGH** | `skip_rewrite` | confident_high_dense(top1=0.7257>=0.7250, mean3=0.7097>=0.70... |
| **Q13** | What risks are associated with relying o... | 0.6678 | 0.6647 | 26.68 | 4 | **LOW** | `trigger_rewrite` | low_dense_confidence(top1=0.6678<0.6800 or mean3=0.6647<0.66... |
| **Q14** | How can social engineering attacks affec... | 0.6835 | 0.6416 | 22.1 | 4 | **LOW** | `trigger_rewrite` | low_dense_confidence(top1=0.6835<0.6800 or mean3=0.6416<0.66... |
| **Q16** | Why are security and privacy considerati... | 0.6829 | 0.6786 | 29.34 | 7 | **MEDIUM** | `trigger_rewrite` | low_confidence_medium_evidence(top1=0.6829<0.7050, mean3=0.6... |
| **Q17** | What governance practices are important ... | 0.6862 | 0.67 | 18.96 | 7 | **MEDIUM** | `trigger_rewrite` | low_confidence_medium_evidence(top1=0.6862<0.7050, mean3=0.6... |
| **Q19** | What challenges can organizations face w... | 0.7106 | 0.6963 | 23.47 | 6 | **MEDIUM** | `trigger_rewrite` | low_confidence_medium_evidence(bm25=23.5<25.0)... |
| **Q20** | What factors should organizations consid... | 0.7262 | 0.7227 | 32.18 | 6 | **HIGH** | `skip_rewrite` | confident_high_dense(top1=0.7262>=0.7250, mean3=0.7227>=0.70... |
| **Q21** | What are the core phases of the incident... | 0.6862 | 0.6841 | 51.6 | 12 | **MEDIUM** | `trigger_rewrite` | low_confidence_medium_evidence(top1=0.6862<0.7050, mean3=0.6... |
| **Q22** | What key considerations and trade-offs s... | 0.7185 | 0.703 | 35.0 | 8 | **MEDIUM** | `skip_rewrite` | confident_medium_resolved_sufficient(cross_modal_consensus: ... |
| **Q23** | What fundamental paradigm shift does Zer... | 0.7099 | 0.6768 | 48.69 | 12 | **MEDIUM** | `trigger_rewrite` | low_confidence_medium_evidence(mean3=0.6768<0.6850)... |
| **Q24** | What security recommendations should org... | 0.7435 | 0.7324 | 35.18 | 10 | **HIGH** | `skip_rewrite` | confident_high_dense(top1=0.7435>=0.7250, mean3=0.7324>=0.70... |
| **Q25** | What are the core practice groups that c... | 0.7095 | 0.6955 | 40.9 | 15 | **MEDIUM** | `skip_rewrite` | confident_medium_resolved_sufficient(exact_identifier=['SSDF... |
| **Q26** | How should organizations leverage action... | 0.7435 | 0.7168 | 41.67 | 11 | **HIGH** | `skip_rewrite` | confident_high_dense(top1=0.7435>=0.7250, mean3=0.7168>=0.70... |
| **Q27** | What are the three tiers in the multitie... | 0.7686 | 0.7005 | 45.41 | 8 | **HIGH** | `skip_rewrite` | confident_high_dense(top1=0.7686>=0.7250, mean3=0.7005>=0.70... |
| **Q28** | How does the security control tailoring ... | 0.7214 | 0.6953 | 36.97 | 5 | **MEDIUM** | `trigger_rewrite` | low_confidence_medium_evidence(overlap=5<6)... |
| **Q29** | What are the core requirements and authe... | 0.7254 | 0.6844 | 40.01 | 5 | **MEDIUM** | `trigger_rewrite` | low_confidence_medium_evidence(mean3=0.6844<0.6850, overlap=... |
| **Q30** | What are the fundamental attribute types... | 0.7005 | 0.6991 | 39.42 | 8 | **MEDIUM** | `skip_rewrite` | confident_medium_resolved_sufficient(exact_identifier=['ABAC... |
| **Q31** | What are the primary operational charact... | 0.7105 | 0.6956 | 53.31 | 12 | **MEDIUM** | `skip_rewrite` | confident_medium_resolved_sufficient(cross_modal_consensus: ... |
| **Q32** | How do application-proxy gateways differ... | 0.7428 | 0.7303 | 48.81 | 12 | **HIGH** | `skip_rewrite` | confident_high_dense(top1=0.7428>=0.7250, mean3=0.7303>=0.70... |
| **Q33** | What security controls and client softwa... | 0.7289 | 0.7282 | 40.82 | 12 | **HIGH** | `skip_rewrite` | confident_high_dense(top1=0.7289>=0.7250, mean3=0.7282>=0.70... |
| **Q34** | What strategic benefits and operational ... | 0.74 | 0.7386 | 47.96 | 13 | **HIGH** | `skip_rewrite` | confident_high_dense(top1=0.7400>=0.7250, mean3=0.7386>=0.70... |
| **Q35** | How does technical penetration testing d... | 0.7273 | 0.6859 | 34.44 | 9 | **MEDIUM** | `skip_rewrite` | confident_medium_resolved_sufficient(cross_modal_consensus: ... |
| **Q36** | What are the four phases of the digital ... | 0.6658 | 0.6529 | 55.93 | 8 | **LOW** | `trigger_rewrite` | low_dense_confidence(top1=0.6658<0.6800 or mean3=0.6529<0.66... |
| **Q37** | What distinguishes foundational practice... | 0.7537 | 0.7311 | 53.45 | 10 | **HIGH** | `skip_rewrite` | confident_high_dense(top1=0.7537>=0.7250, mean3=0.7311>=0.70... |
| **Q38** | What are the five essential characterist... | 0.7337 | 0.6792 | 49.74 | 12 | **MEDIUM** | `skip_rewrite` | confident_medium_resolved_sufficient(exact_identifier=['NIST... |
| **Q39** | What is the procedure for characterizing... | 0.7262 | 0.6967 | 57.74 | 16 | **MEDIUM** | `skip_rewrite` | confident_medium_resolved_sufficient(cross_modal_consensus: ... |
| **Q40** | What core security assurances does a ser... | 0.7073 | 0.6972 | 47.43 | 10 | **MEDIUM** | `skip_rewrite` | confident_medium_resolved_sufficient(cross_modal_consensus: ... |
