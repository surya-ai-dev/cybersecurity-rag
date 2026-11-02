# Cross-Encoder Query Alignment Benchmark Report

Generated at: 2026-10-31T17:01:35.927708

## 1. Aggregate Comparison

| Configuration | Hit@1 (%) | Hit@5 (%) | Recall@5 (%) | Precision@5 (%) | MRR@5 | NDCG@5 | Latency (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Config A: Baseline (No Rewrite)** | 50.0% | 83.33% | 59.03% | 18.89% | 0.6222 | 0.5262 | 5170.3 ms |
| **Config D-Coupled (Previous Phase 4B)** | 41.67% | 80.56% | 59.72% | 17.78% | 0.5523 | 0.4914 | 5748.9 ms |
| **Config D-Decoupled (Phase 4B Fixed)** | 50.0% | 83.33% | 59.03% | 18.89% | 0.6199 | 0.5243 | 5785.2 ms |

## 2. Target Regressed & Improved Questions Focus

| QID | Original Question | Baseline Hit@5 | Coupled Hit@5 | Decoupled Hit@5 | Status |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **Q4** | Why is governance important for public cloud secur... | 1 | 0 | 1 | RESTORED |
| **Q10** | What are the security implications of storing orga... | 0 | 1 | 0 | UNCHANGED |
| **Q11** | What responsibilities does an organization retain ... | 1 | 0 | 1 | RESTORED |
| **Q12** | What security responsibilities are shared between ... | 1 | 0 | 1 | RESTORED |
| **Q17** | What governance practices are important when using... | 1 | 0 | 1 | RESTORED |
| **Q19** | What challenges can organizations face when monito... | 0 | 1 | 0 | UNCHANGED |
| **Q25** | What are the core practice groups that comprise th... | 0 | 1 | 0 | UNCHANGED |
| **Q30** | What are the fundamental attribute types evaluated... | 1 | 0 | 1 | RESTORED |
| **Q38** | What are the five essential characteristics of clo... | 0 | 1 | 0 | UNCHANGED |
| **Q40** | What core security assurances does a service mesh ... | 1 | 1 | 1 | UNCHANGED |
