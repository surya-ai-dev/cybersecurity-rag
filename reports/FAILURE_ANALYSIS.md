# Cybersecurity RAG — Retrieval Failure Analysis

## 1. Purpose

This document tracks retrieval failures identified during the
baseline evaluation of the Cybersecurity RAG pipeline.

The objectives are to:

- Identify questions where relevant chunks are not retrieved.
- Compare Dense, BM25, Hybrid, and Reranker retrieval results.
- Investigate possible root causes using evidence.
- Separate confirmed findings from hypotheses.
- Track decisions and proposed improvements.
- Re-evaluate the system after approved changes.

IMPORTANT:
- Do not modify ground-truth labels based only on retrieval results.
- Do not change production code before investigating the failure.
- Do not change the baseline evaluation results.
- Every proposed improvement must be supported by evidence.
- Record all changes and evaluate their impact separately.

---

## 2. Baseline Evaluation Information

| Property | Value |
|---|---|
| Project | Cybersecurity RAG |
| Evaluation date | 2026-10-21 |
| Evaluation questions | 36 |
| Evaluation type | Retrieval evaluation |
| Dense retrieval | BGE-M3 + Qdrant |
| Sparse retrieval | BM25 |
| Fusion method | Reciprocal Rank Fusion (RRF) |
| RRF parameter | k = 60 |
| Reranker | Cross-Encoder |
| Reranker model | cross-encoder/ms-marco-MiniLM-L-6-v2 |
| Dense top-K | 20 |
| BM25 top-K | 20 |
| Final retrieved chunks | 5 |
| Query rewriting | Disabled |
| Adaptive retrieval | Disabled |
| LLM answer generation | Excluded from this evaluation |

### Baseline Evaluation Reports

- JSON:
  `retrieval_evaluation_20261021_041958.json`

- Markdown:
  `retrieval_evaluation_20261021_041958.md`

### Ground-Truth Dataset

`data/evaluation/retrieval_ground_truth_v2.json`

### Evaluation Script

`scripts/evaluate_retrieval.py`

Root-level wrapper:

`evaluate_retrieval.py`

---

## 3. Baseline Results

| Configuration | Hit@1 | Hit@5 | Recall@5 | MRR@20 | NDCG@5 |
|---|---:|---:|---:|---:|---:|
| A. Dense Retrieval | 47.22% | 83.33% | 59.49% | 0.6447 | 0.5288 |
| B. BM25 | 25.00% | 58.33% | 44.44% | 0.3858 | 0.3382 |
| C. Hybrid + RRF | 41.67% | 72.22% | 51.85% | 0.5608 | 0.4542 |
| D. Hybrid + RRF + Reranker | 50.00% | 83.33% | 59.03% | 0.6305 | 0.5262 |

Note:
These results are the original baseline and must remain unchanged.

Dense retrieval and Hybrid + RRF + Reranker both achieved 83.33%
Hit@5. The reranker configuration achieved better Hit@1.

We must investigate the individual rankings and other metrics before
deciding which configuration is best overall.

---

## 4. Questions Requiring Investigation

### 4.1 Questions Where All Configurations Failed

The baseline Hit@5 results indicate that none of the four configurations
retrieved a relevant ground-truth chunk within the top five for these
questions:

- [ ] Q10
- [ ] Q19
- [ ] Q25
- [ ] Q38

These questions are the first priority for investigation.

### 4.2 Questions Where Retrieval Configurations Disagree

The following questions are useful for understanding the differences
between retrieval strategies:

- [ ] Q5
- [ ] Q7
- [ ] Q8
- [ ] Q13
- [ ] Q30
- [ ] Q33
- [ ] Q35
- [ ] Q39
- [ ] Q40

The baseline results suggest that the reranker or hybrid retrieval
changes the Hit@5 outcome for some of these questions.

The exact rankings must be checked before drawing conclusions.

---

## 5. Failure Investigation Template

Copy this section for every question investigated.

### Question ID: QXX

#### A. Question Information

**Original question:**

[Paste the exact question from the evaluation dataset.]

**Expected relevant chunk IDs:**

[List all ground-truth chunk IDs.]

**Expected information:**

[Describe the information that the retrieved chunks should contain.]

#### B. Retrieval Results

| Configuration | Relevant chunk found in top 5? | Relevant chunk rank | Notes |
|---|---|---|---|
| A. Dense | Unknown | Unknown | |
| B. BM25 | Unknown | Unknown | |
| C. Hybrid + RRF | Unknown | Unknown | |
| D. Hybrid + RRF + Reranker | Unknown | Unknown | |

**Important:** A relevant chunk may be different from the exact
ground-truth chunk ID. Record both exact ID matches and any
semantically relevant alternative chunks.

#### C. Retrieved Chunk Inspection

| Configuration | Rank | Chunk ID | Source document | Relevance assessment |
|---|---:|---|---|---|
| Dense | 1 | | | |
| Dense | 2 | | | |
| Dense | 3 | | | |
| Dense | 4 | | | |
| Dense | 5 | | | |
| BM25 | 1 | | | |
| BM25 | 2 | | | |
| BM25 | 3 | | | |
| BM25 | 4 | | | |
| BM25 | 5 | | | |
| Hybrid + RRF + Reranker | 1 | | | |
| Hybrid + RRF + Reranker | 2 | | | |
| Hybrid + RRF + Reranker | 3 | | | |
| Hybrid + RRF + Reranker | 4 | | | |
| Hybrid + RRF + Reranker | 5 | | | |

Add the complete chunk text or a concise evidence-based summary
when necessary.

#### D. Root-Cause Investigation

Investigate the following possibilities without assuming any of them
is the cause.

- [ ] Relevant information is missing from the corpus.
- [ ] Relevant information exists but is split across chunks.
- [ ] Chunk boundaries separate important context.
- [ ] Dense retrieval fails to find the relevant information.
- [ ] BM25 fails because of keyword or terminology mismatch.
- [ ] RRF fusion changes the ranking unfavorably.
- [ ] The Cross-Encoder reranker demotes relevant chunks.
- [ ] The question is ambiguous or uses different terminology.
- [ ] The ground-truth labels may need manual review.
- [ ] Another cause identified during investigation.

**Evidence collected:**

[Record the chunk IDs, text, scores, rankings, and source documents
that support the investigation.]

**Confirmed findings:**

[Record only conclusions supported by evidence.]

**Hypotheses requiring further testing:**

[Record possible explanations that have not yet been confirmed.]

**Ground-truth review required?**

[Yes / No / Undetermined]

**Recommended next investigation:**

[Describe the next test without implementing it.]

#### E. Decision

**Decision status:** Pending

**Approved action:**

[None until the investigation has been reviewed.]

**Reason for decision:**

[Explain the evidence supporting the decision.]

**Code or configuration changed:** No

**Ground truth changed:** No

**Re-evaluation required:** Yes, if a change is eventually approved.

---

## 6. Individual Failure Records

### Failure 1: Q10

**Status:** Pending investigation

**Initial observation:**

All four retrieval configurations failed to achieve Hit@5.

**Investigation findings:**

[To be completed after inspecting the evaluation artifacts and corpus.]

**Confirmed root cause:**

Not yet determined.

**Decision:**

Pending manual review.

---

### Failure 2: Q19

**Status:** Pending investigation

**Initial observation:**

All four retrieval configurations failed to achieve Hit@5.

**Investigation findings:**

[Not investigated yet.]

**Confirmed root cause:**

Not yet determined.

**Decision:**

Pending manual review.

---

### Failure 3: Q25

**Status:** Pending investigation

**Initial observation:**

All four retrieval configurations failed to achieve Hit@5.

**Investigation findings:**

[Not investigated yet.]

**Confirmed root cause:**

Not yet determined.

**Decision:**

Pending manual review.

---

### Failure 4: Q38

**Status:** Pending investigation

**Initial observation:**

All four retrieval configurations failed to achieve Hit@5.

**Investigation findings:**

[Not investigated yet.]

**Confirmed root cause:**

Not yet determined.

**Decision:**

Pending manual review.

---

## 7. Future Experiments

These experiments must be performed separately from the baseline.

### Experiment 1: Query Rewriting

**Objective:**

Determine whether rewriting the original question improves retrieval.

**Test A:**

Original question
→ Hybrid retrieval
→ RRF
→ Cross-Encoder reranker

**Test B:**

Original question
→ Query rewriting
→ Hybrid retrieval
→ RRF
→ Cross-Encoder reranker

**Keep constant:**

- Evaluation questions
- Ground-truth labels
- Corpus and chunk IDs
- Embedding model
- Retrieval parameters
- Reranker model
- Evaluation metrics

**Metrics to compare:**

- Hit@1
- Hit@5
- Recall@5
- MRR
- NDCG@5
- Latency

**Status:** Not started.

### Experiment 2: Adaptive Retrieval

**Objective:**

Determine whether a second retrieval attempt improves results
for questions where the initial retrieval is insufficient.

**Test A:** Baseline retrieval.

**Test B:** Adaptive retrieval enabled with a defined confidence
criterion and an additional retrieval attempt when triggered.

**Metrics to compare:**

- Hit@5
- Recall@5
- MRR
- NDCG@5
- Additional retrieval frequency
- Latency

**Status:** Not started.

### Experiment 3: Answer Generation Evaluation

**Objective:**

Evaluate the quality of the generated answer separately from
retrieval performance.

**Metrics:**

- Answer correctness
- Faithfulness
- Groundedness
- Citation accuracy
- Answer relevance

**Status:** Not started.

---

## 8. Change History

| Date | Question / Experiment | Change | Reason | Evaluation result |
|---|---|---|---|---|
| 2026-10-21 | Baseline | Initial retrieval evaluation completed | Establish baseline | Recorded in baseline reports |

Add a new row whenever an approved change is implemented.

Never overwrite the original baseline results.

---

## 9. Current Project Status

- [x] Baseline retrieval evaluation completed.
- [x] Four retrieval configurations compared.
- [ ] Q10 manually investigated.
- [ ] Q19 manually investigated.
- [ ] Q25 manually investigated.
- [ ] Q38 manually investigated.
- [ ] Disagreement cases investigated.
- [ ] Query rewriting evaluated.
- [ ] Adaptive retrieval evaluated.
- [ ] Answer generation evaluated.

**Current priority:**

Investigate Q10 using the original evaluation artifacts and corpus.
Record the evidence before proposing any changes.

**Project rule:**

Understand the failure first. Decide on a fix second.
Implement only after review. Re-evaluate after implementation.