# Forensic Investigation: Cross-Encoder Reranker Behavior for Q19 in Experiment D

**Document:** `reports/retrieval_evaluation/phase2_q19_reranker_investigation.md`  
**Project:** Cybersecurity RAG — Phase 2 Optimization  
**Target Question:** `Q19` (*"What challenges can organizations face when monitoring security in public cloud environments?"*)  
**Investigation Scope:** [`app/retrieval/reranker.py`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/app/retrieval/reranker.py), Experiment D Execution Data, and Cross-Encoder Scoring Mechanics  
**Baseline Freeze Commit:** `c6f2afb`  
**Evaluation Date:** 2026-11-03  
**Status:** Complete — Empirical Forensic Evidence  

---

## 1. Executive Summary

In **Experiment D**, chained query rewriting and domain expansion successfully resolved the **Candidate Pool Miss** for Question Q19 by placing **all three official ground-truth chunks** into the Top 20 candidate pool across both Dense (`BAAI/bge-m3`) and Sparse (`BM25Okapi`) channels, with all three surviving RRF fusion ($k=60$):
- `NIST_SP_800-146_txt_00134`: Fused **Rank #1** (RRF score: `0.032258`) $\rightarrow$ Final Top 5 **Rank #5** (Logit: `-0.3518`)
- `NIST_SP_800-144_txt_00087`: Fused **Rank #3** (RRF score: `0.031319`) $\rightarrow$ Final Top 5 **Rank #1** (Logit: `+2.7471`)
- `NIST_SP_800-144_txt_00065`: Fused **Rank #6** (RRF score: `0.025487`) $\rightarrow$ Final Top 5 **Excluded** (Logit: `-1.7067`)

While `txt_00087` and `txt_00134` reached the final Top 5, official ground-truth target `txt_00065` was suppressed from Rank 6 to Rank 6+ by the Cross-Encoder (`ms-marco-MiniLM-L-6-v2`), being overtaken by its direct sibling chunk `NIST_SP_800-144_txt_00088` (Logit: `+1.7882`), `NIST_SP_800-201_txt_00031` (Logit: `+0.7195`), and `NIST_SP_800-210_txt_00030` (Logit: `+0.5879`).

This investigation inspects the production reranker module, execution traces, tokenization limits, and chunk text contents to determine **why `txt_00065` received a negative score** and whether this behavior stems from an implementation bug or model relevance judgment.

---

## 2. Technical Inspection of `app/retrieval/reranker.py`

Inspection of [`app/retrieval/reranker.py`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/app/retrieval/reranker.py) confirms the exact mechanics governing candidate scoring and ranking:

### 2.1 Input Format Sent to the Cross-Encoder
- **Code Reference:** Lines 102–129 of [`app/retrieval/reranker.py`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/app/retrieval/reranker.py#L102-L129)
- **Data Structure:** The input passed to `self._model.predict(pairs)` is a Python `List[Tuple[str, str]]`, where each element is:
  ```python
  pairs.append((query, chunk.text))
  ```
- **Query Component:** The query string passed to `.rerank(query, documents)` is the standalone search query (in Experiment D, the 32-token expanded query).
- **Document Component:** Only the raw text content (`chunk.text`) is extracted from each `RetrievedChunk`. Metadata fields such as `document_id`, `section`, `category`, and `source_file` are **not** prepended or concatenated to the text sent into the Cross-Encoder.
- **Pair Construction:** The underlying `SentenceTransformer.CrossEncoder` tokenizes the tuple into standard BERT dual-sentence sequence format:
  $$\text{[CLS]} \circ \text{Tokens}(\text{Query}) \circ \text{[SEP]} \circ \text{Tokens}(\text{Chunk Text}) \circ \text{[SEP]}$$

### 2.2 Score Type: Raw Logits vs. Probabilities
- **Code Reference:** Lines 131–140 of [`app/retrieval/reranker.py`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/app/retrieval/reranker.py#L131-L140)
- **Model Type:** `cross-encoder/ms-marco-MiniLM-L-6-v2` is a sequence classification model trained on MS MARCO with `num_labels=1`.
- **Output:** `self._model.predict(pairs)` directly returns the output of the final linear regression head without applying a sigmoid transformation (`apply_softmax=False`).
- **Nature of Scores:** The scores are **unbounded real-valued logits** $(-\infty, +\infty)$:
  - Positive logits (e.g., `+2.7471`, `+1.7882`) signify high predicted relevance.
  - Negative logits (e.g., `-0.3518`, `-1.7067`, `-4.7790`, `-8.5259`) signify lower predicted relevance or irrelevance.
  - Scores are assigned directly to `chunk.score` and `chunk.reranker_score` as float values.

### 2.3 Candidate Sorting & Tie-Breaking
- **Code Reference:** Lines 142–155 of [`app/retrieval/reranker.py`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/app/retrieval/reranker.py#L142-L155)
- **Sorting Logic:**
  ```python
  doc_objects.sort(
      key=lambda c: (
          -(c.reranker_score if c.reranker_score is not None else float("-inf")),
          str(c.chunk_id),
      ),
  )
  ```
- Candidates are sorted strictly in **descending numerical order of reranker logit**.
- Ties are broken deterministically in **alphabetical ascending order of `chunk_id`**.
- The top $N$ candidates (`limit = top_n`, default: 5) are sliced and returned with assigned `reranker_rank` (1 through 5).

### 2.4 Truncation & Token Length Limits
- **Architecture Limit:** `cross-encoder/ms-marco-MiniLM-L-6-v2` has `max_position_embeddings = 512` tokens.
- **Truncation Behavior:** The HuggingFace tokenizer truncates the combined `[CLS] query [SEP] text [SEP]` sequence if total tokens exceed 512.
- **Empirical Measurement for Experiment D:**
  - Tokenizer: `AutoTokenizer.from_pretrained("cross-encoder/ms-marco-MiniLM-L-6-v2")`
  - Query Token Count: **32 tokens**
  - Special Tokens (`[CLS]`, `[SEP]`, `[SEP]`): **3 tokens**
  - Budget available for document text: $512 - 35 = \mathbf{477\text{ tokens}}$

---

## 3. Comparison of the Three Target & Sibling Chunks

The table below contrasts the three critical chunks from `NIST_SP_800-144`:

| Attribute | `NIST_SP_800-144_txt_00065` | `NIST_SP_800-144_txt_00087` | `NIST_SP_800-144_txt_00088` |
| :--- | :--- | :--- | :--- |
| **Ground-Truth Status** | **Official Target** | **Official Target** | **Sibling Chunk (Non-Target)** |
| **Section Header** | `### 4.3 Trust` | `### 4.9 Incident Response` | `### 4.9 Incident Response` |
| **Section Subheading** | `- Ancillary Data` | `- Data Availability` | `- Incident Analysis & Resolution` |
| **Page Range** | Pages 30–31 | Pages 43–44 | Page 44 |
| **Character Length** | 2,086 chars | 2,523 chars | 2,177 chars |
| **Standalone Tokens** | 395 tokens | 450 tokens | 408 tokens |
| **Total Pair Tokens** | **430 tokens** | **485 tokens** | **443 tokens** |
| **Truncated at 512?** | **False (0 overflow)** | **False (0 overflow)** | **False (0 overflow)** |
| **Dense Rank & Score** | Rank 17 (`0.6711`) | Rank 7 (`0.6921`) | Rank 3 (`0.7027`) |
| **BM25 Rank & Score** | Rank 20 (`35.4142`) | Rank 1 (`68.4748`) | Rank 3 (`57.8776`) |
| **RRF Fused Rank** | **Rank 6 (`0.025487`)** | **Rank 3 (`0.031319`)** | **Rank 2 (`0.031758`)** |
| **Cross-Encoder Logit** | **`-1.7067`** | **`+2.7471`** | **`+1.7882`** |
| **Final Top 5 Rank** | **Rank 6 (Suppressed)** | **Rank 1** | **Rank 2** |

---

## 4. Why Did `txt_00065` Receive a Lower Score?

Detailed textual and token-level analysis reveals three distinct factors driving the lower Cross-Encoder score:

### Factor 1: Lexical Term Density Mismatch
The Stage 2 query is dense with operational monitoring and logging terminology:
> `public cloud security monitoring challenges shared responsibility model event logs forensics limitations incident response cloud consumer visibility event log accessibility audit logs provider-controlled infrastructure PaaS SaaS logging`

Measuring exact term matches against the query vocabulary demonstrates a severe disparity:

| Query Concept Term | `txt_00065` (Sec 4.3) | `txt_00087` (Sec 4.9) | `txt_00088` (Sec 4.9) |
| :--- | :---: | :---: | :---: |
| `"public cloud"` | 0 | **1** | 0 |
| `"security"` | 3 | 2 | 0 |
| `"monitoring"` | 0 *(uses "monitor status")* | **1** | 0 |
| `"event logs" / "event log"` | 0 | **2** | 0 |
| `"incident response"` | 0 | **4** | **1** |
| `"incident"` | 1 *(past breach)* | **5** | **10** |
| `"forensic" / "forensics"` | 0 | 0 | **1** |
| `"visibility"` | **2** | 0 | 0 |
| `"audit"` | **1** | 0 | 0 |
| `"PaaS"` | 0 | **1** | **1** |
| `"SaaS"` | 1 | **1** | **2** |
| `"cloud consumer"` | 0 *(uses "cloud consumers")* | 0 | **2** |
| `"logging"` | 0 | **2** | **1** |
| **Total Query Concept Hits** | **5 / 21 terms** | **9 / 21 terms** | **7 / 21 terms** |

- `txt_00087` and `txt_00088` match 9 and 7 technical keywords, including exact phrases `"event logs"`, `"incident response"`, `"logging"`, `"PaaS"`, and `"SaaS"`.
- `txt_00065` matches only 5 terms and contains **zero occurrences** of `"event logs"`, `"event log"`, `"logging"`, `"incident response"`, or `"PaaS"`.

### Factor 2: Section Heading & Semantic Framing
- The Cross-Encoder processes the opening tokens of each chunk with high positional salience.
- `txt_00087` and `txt_00088` both begin with `### 4.9 Incident Response`. This header directly echoes `"incident response"`, immediately biasing the self-attention heads toward query-document relevance.
- `txt_00065` begins with `### 4.3 Trust`. The semantic topic of "Trust" is broader and perceived by the model as governance/policy-oriented rather than an operational answer to technical monitoring challenges.

### Factor 3: Text Dilution by Ancillary Data Anecdote
- In `txt_00065`, lines 46–48 discuss dashboards, visibility into cloud provider controls, and third-party audit rights (highly relevant to the question).
- However, lines 50–52 (over 40% of the chunk, ~160 tokens) shift into a narrative case study about a marketing contact database stolen via an employee phishing attack at a SaaS vendor:
  > *"...For example, a database of contact information stolen from a SaaS cloud provider, via a targeted phishing attack against one of its employees, was used in turn to launch successful targeted electronic mail attacks against consumers..."*
- Because the Cross-Encoder applies full bi-directional self-attention across all tokens in the concatenated pair, this phishing breach anecdote dilutes the chunk's overall relevance density for *security monitoring*, causing the global logit to drop to `-1.7067`.

---

## 5. Verified Findings vs. Hypotheses

### Verified Findings (Fact-Based & Empirically Confirmed)
1. **Zero Code Defects:**
   Inspection of [`app/retrieval/reranker.py`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/app/retrieval/reranker.py) confirms that input pair construction, score extraction, and descending sort logic operate correctly without bugs, index misalignments, or silent exceptions.
2. **Raw Logits, Not Probabilities:**
   The cross-encoder produces unbounded real-valued logits. Negative numbers do not represent errors or zero probabilities; they reflect positions below the model's decision boundary.
3. **No Truncation Occurred:**
   The concatenated token lengths for `txt_00065` (430 tokens), `txt_00087` (485 tokens), and `txt_00088` (443 tokens) are all well below the 512-token ceiling. The entire text of `txt_00065` was evaluated by the model.
4. **Lexical Disparity:**
   `txt_00065` contains zero occurrences of "event logs", "logging", or "incident response", whereas `txt_00087` contains 9 matches including specific mentions of PaaS/SaaS log unavailability.
5. **Cross-Query Score Trajectory of `txt_00065`:**
   Empirical logit progression across queries:
   - Baseline Query (*high-level question*): `+0.5867` (scored higher than `txt_00087`'s `-0.3854`)
   - Stage 1 Query (*rewritten with "forensics", "event logs"*): `-5.7189` (steep drop due to missing terms)
   - Stage 2 Query (*expanded with "visibility", "audit", "infrastructure"*): `-1.7067` (+4.01 logit recovery)

### Hypotheses (Supported by Model Architecture & Inductive Bias)
1. **Passage Dilution Penalty:**
   The ~160 tokens dedicated to employee phishing and stolen contact databases in `txt_00065` likely act as negative semantic signal for a query specifically seeking security monitoring challenges.
2. **MS MARCO Inductive Bias:**
   `ms-marco-MiniLM-L-6-v2` was trained on MS MARCO passage re-ranking, which heavily rewards passages containing direct, concrete operational explanations (such as `txt_00087` explaining that PaaS providers do not supply event logs) over passages prescribing high-level contract requirements (such as `txt_00065` suggesting third-party audit rights in service agreements).
3. **Sub-string / Exact Term Dependency:**
   Cross-encoders inherit dense lexical matching sensitivities from their transformer pretraining; the presence of exact sub-strings like `"event logs"` in `txt_00087` yields disproportionately larger logit gains compared to conceptual synonyms like `"monitor status"` or `"dashboards"` in `txt_00065`.

---

## 6. Code Issue vs. Model Relevance Judgment Conclusion

| Criterion | Evaluation | Supporting Evidence |
| :--- | :---: | :--- |
| **Code Bug in Reranker?** | **NO** | `app/retrieval/reranker.py` correctly passes `(query, text)`, extracts float predictions, and sorts descending. |
| **Truncation Issue?** | **NO** | 430 tokens evaluated vs. 512 max limit (0 tokens dropped). |
| **Data / Pipeline Corruption?** | **NO** | Chunk payload matches corpus 100%; point ID 64 present in Qdrant. |
| **Model Relevance Judgment?** | **YES** | The model evaluated the complete texts and legitimately rated `txt_00087` (+2.75) and `txt_00088` (+1.79) as significantly more relevant to cloud security monitoring and event logging than `txt_00065` (-1.71). |

**Conclusion:** The lower score assigned to `txt_00065` is **not a software defect**, but an authentic **model relevance judgment** reflecting `txt_00065`'s lower lexical keyword density and partial passage dilution by an unrelated phishing anecdote.

---

## 7. Architectural Implications for Phase 2 Retrieval Optimization

To prevent valid ground-truth chunks from being suppressed when candidate retrieval succeeds (Recall@20 = 100%), Phase 2 should explore the following non-breaking enhancements:

1. **Hybrid Score Interpolation (Rank Fusion + Reranker):**
   Instead of sorting purely by Cross-Encoder logit, blend normalized RRF scores with normalized reranker scores:
   $$S_{\text{final}} = \alpha \cdot S_{\text{norm}}(\text{RRF}) + (1 - \alpha) \cdot S_{\text{norm}}(\text{CrossEncoder})$$
   Because `txt_00065` placed **#6 in RRF**, a hybrid weighting ($\alpha \approx 0.3 - 0.4$) would keep `txt_00065` comfortably inside the Top 5.
2. **Metadata-Enriched Reranker Inputs:**
   Prepend section titles to chunk text when constructing reranker pairs:
   `f"Section: {chunk.metadata.section}\n\n{chunk.text}"`
   This provides cross-attention context for chunks whose bodies use generalized language.
3. **Ground-Truth Annotation Audit:**
   `txt_00088` (which placed #2 in reranking with `+1.7882`) directly continues `txt_00087` and contains vital technical details on SaaS event logs and cloud forensics. Auditing whether `txt_00088` should be recognized as an official ground-truth peer would align evaluation metrics with empirical relevance.

---

## 8. Safety & Compliance Verification

- [x] Unmodified production source code (`app/`).
- [x] Unmodified tests and configurations (`tests/`, `app/core/config.py`).
- [x] Unmodified ground-truth datasets (`data/evaluation/`).
- [x] No new experiments or benchmark reruns executed.
- [x] Analysis strictly derived from frozen baseline and Experiment D empirical artifacts.
