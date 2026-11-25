# Phase 2 Investigation: Topic Coverage Verification for Confidence Assessment

**Document:** `reports/retrieval_evaluation/phase2_topic_coverage_investigation.md`  
**Project:** Cybersecurity RAG — Phase 2 Optimization  
**Focus:** Diagnostic Analysis of Q10 False-Confidence and Architectural Design of an Isolated Topic Coverage Checker  
**Evidence Source:** Experiment F Execution Logs (`scratch/experiment_f_20q_results.json`) & Corpus Data (`data/chunks_corpus/`)  
**Baseline Freeze Commit:** `c6f2afb`  
**Status:** Code and Evidence Inspection Complete — Design and Test Plan Formulated  

---

## 1. Existing ConfidenceEvaluator Logic and Stopping Conditions

The current confidence assessment logic is implemented in [`app/retrieval/confidence.py`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/app/retrieval/confidence.py) within the [`ConfidenceEvaluator`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/app/retrieval/confidence.py#L180-L522) class. It determines whether the current candidate pool is sufficiently relevant and grounded to terminate retrieval, or if the pipeline must escalate to query rewriting / expansion.

### 1.1 Input Interface and Signatures

The primary evaluation entry point is:
```python
def evaluate(
    self,
    candidates: Sequence[RetrievedChunk],
    query: Optional[str] = None,
) -> ConfidenceResult:
```

- `candidates`: A sequence of [`RetrievedChunk`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/app/core/models.py#L38-L58) objects (typically 20 candidates from reciprocal rank fusion or previous stage merges). Each candidate exposes:
  - `chunk.text`: Complete raw text of the chunk.
  - `chunk.dense_score`: Float cosine similarity $\in [0, 1]$ (or `None`).
  - `chunk.bm25_score`: Unbounded BM25 lexical score (or `None`).
  - `chunk.rrf_score`: Reciprocal Rank Fusion score $\le 0.035$ (or `None`).
  - `chunk.metadata`: [`ChunkMetadata`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/app/core/models.py#L26-L36) containing `document_id`, `section`, `source_file`, `token_count`.
- `query`: The search query string (used to test for exact technical publication identifiers).

### 1.2 Configured Signals and Default Thresholds

The evaluator computes multi-view signals and checks them against calibrated thresholds:

| Signal Name | Source | Default Threshold | Description |
| :--- | :--- | :---: | :--- |
| `top1` | Dense cosine similarity | `0.725` (HIGH) / `0.705` (Med Generic) / `0.680` (Med Lower) | Highest dense score among deduplicated candidates. |
| `mean3` | Dense cosine similarity | `0.700` (HIGH) / `0.685` (Med Generic) / `0.660` (Med Lower) | Average dense score across top 3 dense candidates. |
| `top_bm25` | BM25Okapi score | `25.0` | Maximum lexical match score across candidate pool. |
| `overlap_count` | Cross-modal intersection | `6` | Number of chunks present in both dense and BM25 candidate lists. |
| `has_exact_match` | Regex on query | Boolean | Whether an explicit standard/control identifier (e.g., `NIST SP 800-53`, `AC-2`) appears in the top `identifier_search_depth` (5) candidates. |

### 1.3 Decision Rules and Stopping Conditions

The decision follows an evidence-based three-tier ladder:

1. **Tier 1 — HIGH Confidence (Dense Semantic Dominance):**
   - Condition: `top1 >= 0.725` AND `mean3 >= 0.700`.
   - Action: `SKIP_REWRITE` (`is_confident = True`).
   - Reason: `confident_high_dense(...)`.
2. **Tier 2 — MEDIUM Confidence (Hybrid Consensus):**
   Requires `top1 >= 0.680` AND `mean3 >= 0.660`.
   - **Subcase A (Exact Identifier Grounding):**
     - Condition: `has_exact_match == True` AND `top_bm25 >= 25.0` AND `mean3 >= 0.660`.
     - Action: `SKIP_REWRITE` (`is_confident = True`).
   - **Subcase B (Cross-Modal Consensus on Generic Query):**
     - Condition: `top1 >= 0.705` AND `mean3 >= 0.685` AND `overlap_count >= 6` AND `top_bm25 >= 25.0`.
     - Action: `SKIP_REWRITE` (`is_confident = True`).
     - Reason: `confident_medium_resolved_sufficient(cross_modal_consensus: ...)`.
   - **Subcase C (Insufficient Hybrid Grounding):**
     - Condition: Dense scores meet medium lower bounds, but fail Subcase A and Subcase B.
     - Action: `TRIGGER_REWRITE` (`is_confident = False`).
3. **Tier 3 — LOW Confidence:**
   - Condition: `top1 < 0.680` OR `mean3 < 0.660` OR missing scores.
   - Action: `TRIGGER_REWRITE` (`is_confident = False`).

---

## 2. Exact Q10 Evaluation Path and Evidence from Experiment F

In Experiment F, question **Q10** demonstrated an empirical false-confidence stopping failure.

### 2.1 Benchmark Definition
- **Question ID:** `Q10`
- **Original Question:** *"What are the security implications of storing organizational data in the public cloud?"*
- **Target Document:** `NIST_SP_800-144` (*Guidelines on Security and Privacy in Public Cloud Computing*)
- **Official Ground Truth Chunks:**
  1. `NIST_SP_800-144_txt_00080` (Section 4.7 "Data Protection" — Value Concentration, Cloud Storage as Bank Vault)
  2. `NIST_SP_800-144_txt_00081` (Section 4.7 "Data Protection" — Data Isolation, Multi-Tenancy vs. Multi-Instance, Encryption)
  3. `NIST_SP_800-144_txt_00082` (Section 4.7 "Data Protection" — Multi-Tenant Databases, Cryptographic Key Management, Data at Rest/in Transit/in Use)

### 2.2 Stage 1 Execution (Original Query)
- **Input Query:** *"What are the security implications of storing organizational data in the public cloud?"*
- **Signals Observed:**
  - `dense_top1`: `0.6928` (< 0.7050 threshold)
  - `dense_mean3`: `0.6822` (< 0.6850 threshold)
  - `overlap_count`: `9` ($\ge 6$)
  - `top_bm25`: `33.2` ($\ge 25.0$)
  - `query_identifiers`: `[]` (`has_exact_match = False`)
- **Evaluator Decision:** `is_confident = False` (Level: `MEDIUM`)
- **Reason:** `low_confidence_medium_evidence(top1=0.6928<0.7050, mean3=0.6822<0.6850)`
- **Pipeline Action:** Correctly identified insufficient confidence and escalated to **Stage 2 (Query Rewriter Alone)**.
- **Stage 1 Candidate Pool:** Contained `0 / 3` ground-truth chunks in the Top-20 RRF pool.

### 2.3 Stage 2 Execution (Query Rewriter Alone) — The Failure Point
- **Rewritten Query:** `"public cloud data storage security implications organizational data confidentiality integrity availability"`
- **Retrieval Output (Merged Top-20 Pool):**
  - None of the 3 ground-truth chunks were retrieved into the Top-20 pool (`txt_00080`, `txt_00081`, `txt_00082` all missing).
  - Ground Truth Recall in Pool: **0.0% (0 / 3)**.
- **Evaluator Signals Observed:**
  - `dense_top1`: **`0.7162`** ($\ge 0.7050$ threshold) $\rightarrow$ **PASS**
  - `dense_mean3`: **`0.7136`** ($\ge 0.6850$ threshold) $\rightarrow$ **PASS**
  - `overlap_count`: **`14`** ($\ge 6$ threshold) $\rightarrow$ **PASS** (14 chunks retrieved by both dense and BM25)
  - `top_bm25`: **`33.2`** ($\ge 25.0$ threshold) $\rightarrow$ **PASS**
- **Evaluator Decision:** **`is_confident = True`** (Level: `MEDIUM`, Action: `skip_rewrite`)
- **Stopping Reason:**  
  `confident_medium_resolved_sufficient(cross_modal_consensus: top1=0.7162>=0.7050, mean3=0.7136>=0.6850, overlap=14>=6, bm25=33.2>=25.0)`
- **Pipeline Consequence:**  
  The sequential ladder concluded that retrieval was "sufficient" and **terminated immediately**, completely skipping Stage 3 (Domain Expansion) and Stage 4 (Combined).
- **Final Top-5 Output:** **0 / 3 relevant chunks** (`Hit@5 = 0.0`, `Recall@5 = 0.0`).
- **Audit Classification:** **`FALSE_CONFIDENT`**.

---

## 3. Candidate Chunks Inspection and Topic Coverage Breakdown

A forensic inspection of the 20 candidate chunks in Q10's final pool reveals why dense and BM25 retrievers agreed, and why the content failed to address the question:

### 3.1 Content of Top Candidates in Q10 Pool

| Candidate ID | Source Doc & Section Heading | Content Summary | Storage Concept? | Protection Concept? |
| :--- | :--- | :--- | :---: | :---: |
| `NIST_SP_800-144_txt_00028` | NIST SP 800-144: **Section 1. Introduction** | General intro to cloud computing growth, cost benefits, and high-level security/privacy impetus. | **NO** | **NO** |
| `NIST_SP_800-144_txt_00040` | NIST SP 800-144: **Section 3. Public Cloud Services** | Definitions of cloud service models (SaaS, PaaS, IaaS) and deployment models. | **NO** | **NO** |
| `NIST_SP_800-144_txt_00094` | NIST SP 800-144: **Section 5. Public Cloud Outsourcing** | General outsourcing considerations, service agreements, and maintaining accountability. | **NO** | **NO** |
| `NIST_SP_800-144_txt_00043` | NIST SP 800-144: **Section 3.2 The Security and Privacy Upside** | Staff specialization in large cloud providers and economies of scale. | **NO** | Partial (CIA mention) |
| `NIST_SP_800-144_txt_00021` | NIST SP 800-144: **Exec Summary: Planning** | High-level advice to plan security/privacy before engaging cloud solutions. | **NO** | **NO** |
| `NIST_SP_800-144_txt_00038` | NIST SP 800-144: **Section 2.3 Outsourcing and Accountability** | Discusses 3 classes of public clouds (free/ad-supported, non-negotiable fee, negotiated fee). | **NO** | Partial (encryption mention) |
| `NIST_SP_800-144_txt_00120` | NIST SP 800-144: **Section 6. Conclusion** | Concluding remarks on balancing cloud benefits, risk analysis, and privacy objectives. | **NO** | **NO** |
| `NIST_SP_800-144_txt_00099` | NIST SP 800-144: **Section 5.1 General Concerns** | Service contract risks: inadequate policies, weak confidentiality/integrity sureties. | **NO** | Partial (CIA sureties) |
| `NIST_SP_800-146_txt_00135` | NIST SP 800-146: **Section 8.5 Information Security** | General cloud info sec: physical controls, encryption at rest/in transit, provider assurance. | Yes (tangential) | Yes |
| `NIST_SP_800-223_txt_00046` | NIST SP 800-223: **Section 3.2.4 Data Storage Zone Threats** | Discusses High-Performance Computing (HPC) file systems and cluster hard disk failures. | Yes (HPC, not Cloud) | Yes |

### 3.2 Forensic Finding: "Executive Overview" Hall of Mirrors

8 of the top candidates from NIST SP 800-144 were **high-level introductory, executive summary, or concluding overviews** (Sections 1, 2.3, 3, 3.2, 5, 6). 
- None of the top 8 candidates originated from **Section 4.7 "Data Protection"** (the dedicated 5-page section on data storage and protection in public clouds).
- In the top 8 chunks, **0 chunks contain the words `storage`, `storing`, or `stored`**.
- Both the dense retriever and BM25 retriever scored these chunks highly because the rewritten query injected the broad security triad keywords (`confidentiality`, `integrity`, `availability`) along with broad terms (`public cloud`, `organizational data`). The introductory sections mention all these general words repeatedly, yielding strong lexical matches (BM25 = 33.2) and generalized dense semantic alignment (dense = 0.716).

---

## 4. Specific Missing Concepts

To answer Q10, a retrieved candidate set must address the specific risks and technical controls associated with **storing data** in public multi-tenant environments.

The official ground-truth chunks (`NIST_SP_800-144_txt_00080`, `00081`, `00082`) delineate 6 core technical concepts that were **100% missing** from the top candidates:

1. **Value Concentration & High Payoff Ratio (`txt_00080`):**
   - Cloud data stores serve as the 21st-century "bank vault" where high collective value is concentrated, creating a disproportionately high payoff ratio for adversaries targeting public cloud databases.
2. **Collocation & Shared Environment Risks (`txt_00080`, `txt_00081`):**
   - Customer data is physically collocated on shared hardware with data from other organizations, exposing data to collateral damage, resource starvation, or targeted Denial of Service (DoS) directed at neighboring high-threat tenants.
3. **Data Isolation Models (`txt_00081`, `txt_00082`):**
   - Multi-tenant shared database models (using customer identifier tagging enforced by provider logic) versus multi-instance isolated models (separate virtual machines/database management systems).
4. **Data Protection Across System States (`txt_00081`, `txt_00082`):**
   - Lacking physical control over the underlying media, encryption is the only mechanism to guarantee data protection.
   - Requirements to protect data *at rest*, *in transit*, and *in use*.
5. **Cryptographic Key Management Bottleneck (`txt_00082`):**
   - Cloud consumer responsibility for key management, and the failure of traditional Hardware Security Modules (HSMs) to scale effectively to dynamic cloud environments.
6. **Data Sanitization and Media Remanence (`txt_00082`):**
   - Challenges of securely erasing, shredding, and zeroing deallocated storage blocks on shared multi-tenant infrastructure.

---

## 5. Architectural Design for an Isolated Topic Coverage Checker

The root cause of false confidence is that dense similarity and BM25 lexical consensus measure **aggregate keyword/embedding overlap**, but cannot detect **facet dropout** (where an essential semantic dimension of the query is completely omitted from the retrieved chunks).

### 5.1 Architectural Role and Positioning

The `TopicCoverageChecker` is designed as an **isolated, modular component** that acts as a quality gatekeeper for the `ConfidenceEvaluator`.

```
                    [Retrieved Candidates (Top 20)]
                                 │
                                 ▼
                     [ConfidenceEvaluator.evaluate]
                                 │
                   (Candidate passed score thresholds)
                                 │
                                 ▼
                    ┌───────────────────────────┐
                    │ TopicCoverageChecker.check│
                    │   - Extract Query Facets  │
                    │   - Scan Top-K Chunks     │
                    │   - Measure Facet Coverage│
                    └─────────────┬─────────────┘
                                  │
                  ┌───────────────┴───────────────┐
                  ▼                               ▼
       [All Facets Covered]              [Missing Core Facet]
                  │                               │
                  ▼                               ▼
       is_confident = True               is_confident = False
        (Permit STOP)                     (Trigger Next Stage)
                                          reason: "facet_dropout(storage)"
```

### 5.2 Component Interface

```python
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence
from app.core.models import RetrievedChunk


@dataclass
class TopicCoverageResult:
    """Diagnostic outcome of topic facet coverage evaluation."""

    is_covered: bool
    coverage_score: float  # Percentage of required facets covered [0.0 - 1.0]
    required_facets: List[str]
    missing_facets: List[str]
    facet_match_details: Dict[str, List[str]] = field(default_factory=dict)
    reason: str = ""


class TopicCoverageChecker:
    """Verifies that all essential conceptual facets of a query are present in candidates."""

    def __init__(
        self,
        min_coverage_ratio: float = 1.0,
        eval_depth: int = 5,
    ) -> None:
        """
        Args:
            min_coverage_ratio: Minimum ratio of query facets that must be satisfied.
            eval_depth: Number of top candidate chunks to inspect for topic coverage.
        """
        self.min_coverage_ratio = min_coverage_ratio
        self.eval_depth = eval_depth

    def extract_facets(self, query: str) -> List[Dict[str, Any]]:
        """Extract conceptual facets (domain, asset/action, security aspect) from the query."""
        ...

    def check(
        self,
        query: str,
        candidates: Sequence[RetrievedChunk],
    ) -> TopicCoverageResult:
        """Evaluate whether top candidates collectively cover all extracted query facets."""
        ...
```

### 5.3 Deterministic Facet Extraction and Matching Strategy

Rather than adding an expensive LLM call (which adds 500–1,500 ms latency), the checker can employ a fast, deterministic **Facet Extractor** based on cybersecurity query grammar:

1. **Query Decomposition into Semantic Facets:**
   - **Facet A (Environment / Domain):** e.g., `cloud`, `public cloud`, `saas`, `iaas`, `paas`, `network`.
   - **Facet B (Target Asset / Operation):** e.g., `data storage`, `storing data`, `backup`, `log`, `monitoring`, `source code`.
   - **Facet C (Security Aspect / Requirement):** e.g., `security implications`, `risks`, `protection`, `access control`, `incident response`.
2. **Facet Presence Verification in Candidate Pool:**
   - Evaluates the top $K$ candidates (default $K=5$).
   - A facet is considered **covered** if at least one candidate in the top $K$ substantively mentions the facet (or its standard synonym family).
   - If a multi-facet query has Facet B (`storing data` / `storage`) with **0 occurrences** across all top candidates, `TopicCoverageResult.is_covered` is set to `False`.

### 5.4 Integration Mechanics with `ConfidenceEvaluator`

In `ConfidenceEvaluator.evaluate()`:
- When a candidate set meets the score conditions for Subcase B (cross-modal consensus):
  ```python
  if top1 >= self.medium_generic_top1 and mean3 >= self.medium_generic_mean3 ...:
      if self.topic_coverage_checker is not None and query:
          coverage = self.topic_coverage_checker.check(query, unique_candidates[:5])
          if not coverage.is_covered:
              return ConfidenceResult(
                  is_confident=False,
                  level=ConfidenceLevel.MEDIUM.value,
                  action=ConfidenceAction.TRIGGER_REWRITE.value,
                  reason=f"low_confidence_topic_dropout(missing_facets={coverage.missing_facets})",
                  ...
              )
  ```
- This directly overrides false consensus, demoting the result to `is_confident = False` and forcing the sequential ladder to escalate to the next stage.

---

## 6. Test Plan: Comparing Existing and Updated Decisions

To validate the `TopicCoverageChecker` without modifying production code or touching benchmark ground truth, the following test plan is established:

### 6.1 Objectives
1. **Primary Objective:** Verify that for **Q10**, the checker successfully detects the absence of the `data_storage` facet at Stage 2, overturns the premature stop, and escalates to Stage 3 / Stage 4.
2. **Ground-Truth Retrieval Verification:** Verify that upon escalating to Stage 3 or Stage 4, the candidate pool captures `NIST_SP_800-144_txt_00081` and `txt_00082` (as proven by Experiment E).
3. **Safety / Non-Regression Objective:** Verify that for the **7 Stage 1 stopping questions** (Q1, Q7, Q9, Q12, Q20, Q22, Q24) and **Q19**, the checker correctly confirms topic coverage and does **not** cause unnecessary stage escalations.

### 6.2 Test Matrix across Benchmark Questions

| Question | Stage Stopped (Exp F) | Facets in Query | Coverage in Candidates | Expected Outcome with Checker |
| :--- | :---: | :--- | :--- | :--- |
| **Q10** | **Stage 2 (False Stop)** | `[cloud, data_storage, protection]` | `data_storage`: 0% in Top 8 | **Overturn Stop $\rightarrow$ Escalate to Stage 3/4 (Rescue GT Chunks)** |
| **Q19** | Stage 2 (True Confident) | `[cloud, monitoring, incident_challenges]` | All 3 facets: 100% in Rank 2, 3, 5 | **Confirm Stop at Stage 2 (No change, Preserve efficiency)** |
| **Q1** | Stage 1 (True Confident) | `[sp 800-144, cloud_computing, target_audience]` | Exact identifier + target audience | **Confirm Stop at Stage 1 (Preserve efficiency)** |
| **Q7** | Stage 1 (True Confident) | `[iaas, security_responsibility, provider_vs_consumer]` | Covered in Top Candidates | **Confirm Stop at Stage 1 (Preserve efficiency)** |
| **Q9** | Stage 1 (True Confident) | `[public_cloud, client_side_security, browser]` | Covered in Top Candidates | **Confirm Stop at Stage 1 (Preserve efficiency)** |
| **Q12** | Stage 1 (True Confident) | `[saas, access_control, consumer_challenges]` | Covered in Top Candidates | **Confirm Stop at Stage 1 (Preserve efficiency)** |
| **Q20** | Stage 1 (True Confident) | `[cloud, forensic_investigations, challenges]` | Covered in Top Candidates | **Confirm Stop at Stage 1 (Preserve efficiency)** |

### 6.3 Test Execution Strategy (Shadow Mode)
- Implement `TopicCoverageChecker` in a dedicated standalone test script in `scratch/test_topic_coverage_shadow.py`.
- Run all 20 questions through the shadow pipeline:
  - Record the existing decision from `ConfidenceEvaluator`.
  - Record the `TopicCoverageResult` from the checker.
  - Record the simulated new stopping stage and resulting candidate pool recall.
- Generate a formal comparison artifact verifying:
  - Total False-Confident decisions reduced (from 1 to 0 on Q10).
  - True-Confident retention rate (must remain 100% for Q1, Q7, Q9, Q12, Q19, Q20, Q22, Q24).
  - Overall 20-question Candidate Pool Recall improvement.

---

## 7. Immutability Confirmation

- **Production Code (`app/`):** Untouched (0 bytes modified).
- **Configurations & Settings (`app/core/config.py`):** Untouched (0 bytes modified).
- **Ground Truth (`retrieval_ground_truth_100q_refined.json`):** Untouched (0 bytes modified).
- **Benchmark Artifacts (Phase 1, Exp E, Exp F):** Untouched.
- **Git Status:** Working directory remains strictly clean on frozen commit `c6f2afb`.
