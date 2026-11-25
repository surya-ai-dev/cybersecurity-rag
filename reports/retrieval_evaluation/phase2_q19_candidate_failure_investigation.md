# Q19 Candidate Retrieval Failure — Forensic Investigation Report

**Document:** `reports/retrieval_evaluation/phase2_q19_candidate_failure_investigation.md`  
**Project:** Cybersecurity RAG — Phase 2 Optimization  
**Target Question:** `Q19`  
**Baseline Freeze Commit:** `c6f2afb`  
**Date:** 2026-11-02  
**Investigation Type:** Empirical Forensic Diagnostic (Zero Code Changes, Zero Ground-Truth Changes)  

---

## 1. Executive Summary

In the frozen Phase 1 benchmark evaluation across 100 questions (`reports/retrieval_evaluation/benchmark_100q_results.json`), **Question Q19** was classified as a **Candidate Pool Miss**:
- **Question Text:** *"What challenges can organizations face when monitoring security in public cloud environments?"*
- **Target Documents:** [`NIST_SP_800-144`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/data/chunks_corpus/cloud_application_security/NIST_SP_800-144_chunks.jsonl) & [`NIST_SP_800-146`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/data/chunks_corpus/cloud_application_security/NIST_SP_800-146_chunks.jsonl)
- **Expected Ground-Truth Chunks:** `NIST_SP_800-144_txt_00065`, `NIST_SP_800-144_txt_00087`, `NIST_SP_800-146_txt_00134`
- **Observed Benchmark Results:**
  - Dense (`BAAI/bge-m3`, Top-20): `Hit@20 = 0.0`
  - Sparse (`BM25Okapi`, Top-20): `Hit@20 = 0.0`
  - Fusion (`RRFFusion`, $k=60$, Top-20): `Hit@20 = 0.0`
  - Final Production (`Cross-Encoder`, Top-5): `Hit@5 = 0.0` (0 expected chunks retrieved)

This forensic investigation analyzes the complete end-to-end retrieval stack to identify the exact technical root cause behind the failure of both dense and lexical search channels.

---

## 2. Expected Chunk Identification and Corpus Verification

All three target chunks were located in the authoritative JSONL corpus and their integrity verified:

### 2.1 Chunk Text and Metadata Specifications

| Chunk ID | Document ID | Section / Heading | Token Count | Page Range | Corpus File |
| :--- | :--- | :--- | :---: | :---: | :--- |
| **`NIST_SP_800-144_txt_00065`** | `NIST_SP_800-144` | `### 4.3 Trust` | 395 | 30–31 | `data/chunks_corpus/cloud_application_security/NIST_SP_800-144_chunks.jsonl` |
| **`NIST_SP_800-144_txt_00087`** | `NIST_SP_800-144` | `### 4.9 Incident Response` | 450 | 43–44 | `data/chunks_corpus/cloud_application_security/NIST_SP_800-144_chunks.jsonl` |
| **`NIST_SP_800-146_txt_00134`** | `NIST_SP_800-146` | `### 8.4.4 Support for Forensics` | 297 | 62–63 | `data/chunks_corpus/cloud_application_security/NIST_SP_800-146_chunks.jsonl` |

### 2.2 Complete Target Chunk Text

#### Target Chunk 1: `NIST_SP_800-144_txt_00065`
```markdown
### **4.3 Trust**

While notification tools and Webbased dashboards are typically made available to consumers to monitor status, they can lack sufficient detail and may themselves suffer disruption during a system outage [Goo09a, Ker11, Per11].

Transparency in the way the cloud provider operates, including the provisioning of composite services, is a vital ingredient for effective oversight over system security and privacy by an organization.  To ensure that policy and procedures are being enforced throughout the system lifecycle, service arrangements should include some means for the organization to gain visibility into the security controls and processes employed by the cloud provider and their performance over time.  For example, the service agreement could include the right to audit controls via a third party, as a way to validate control aspects that are not otherwise accessible or assessable by the consumer.  Ideally, the consumer would have control over aspects of the means of visibility to accommodate its needs, such as the threshold for alerts and notifications, and the level of detail and schedule of reports.

- **Ancillary Data.** While the focus of attention in cloud computing is mainly on protecting application data, cloud providers also hold significant details about the accounts of cloud consumers that could be compromised and used in subsequent attacks.  Payment information is one example; other, more subtle types of information, can also be involved.  For example, a database of contact information stolen from a SaaS cloud provider, via a targeted phishing attack against one of its employees, was used in turn to launch successful targeted electronic mail attacks against consumers of the cloud service [Kre07, Mcm07].  The incident illustrates the need for cloud providers to protect and report promptly security breaches occurring not only in the data the cloud provider holds for its consumers, but also in the data it holds about its consumers, regardless of whether the data is held within or separately from the cloud infrastructure.
```

#### Target Chunk 2: `NIST_SP_800-144_txt_00087`
```markdown
### **4.9 Incident Response**

As the name implies, incident response involves an organized method for dealing with the consequences of an attack against the security of a computer system.  The cloud provider's role is vital in performing incident response activities, including incident verification, attack analysis, containment, data collection and preservation, problem remediation, and service restoration. Each layer in a cloud application stack, including the application, operating system, network, and database, generates event logs, as do other cloud components, such as load balancers and intrusion detection systems; many such event sources and the means of accessing them are under the control of the cloud provider.

The complexity of a cloud service can obscure recognition and analysis of incidents.  For example, it reportedly took one IaaS provider approximately eight hours to recognize and begin taking action on an apparent denial of service attack against its cloud infrastructure, after the issue was reported by a consumer of the service [Bro09, Met09].  Revising an organization's incident response plan to address differences between the organizational computing environment and a cloud computing environment is an important, but easy-to-overlook prerequisite to transitioning applications and data.

- **Data Availability.** The availability of relevant data from event monitoring is essential for timely detection of security incidents.  Cloud consumers are often confronted with extremely limited capabilities for detection of incidents in public cloud environments [Gro10].  Prominent issues include insufficient access to event sources and vulnerability information under the control of the cloud provider, inadequate interfaces for accessing and processing event data automatically, inability to add detection points within the cloud infrastructure, and difficulty directing third-party reported abuses and incidents effectively back to the correct consumer or the cloud provider for handling.  The situation varies among cloud service models and cloud providers [Gro10].  For example, PaaS providers typically do not make event logs available to consumers, who are then left mainly with event data from self-deployed applications (e.g., via application logging). Similarly, SaaS consumers are completely dependent upon the cloud provider to provide event data such as activity logging, while IaaS consumers control more of the information stack and have access to associated event sources.
```

#### Target Chunk 3: `NIST_SP_800-146_txt_00134`
```markdown
### **8.4.4 Support for Forensics**

As part of an incident response effort, the goal of digital forensics is to: (1) discern what happened, (2) understand what portions of the system were affected, (3) learn how to prevent such incidents from happening again, and (4) collect information for possible future legal actions. Forensics in the cloud, however, raises a number of new issues, such as:

- How are incident handling responsibilities defined in service agreements? (see Appendix A)

- How are clocks synchronized across data centers to help reconstruct a chain of events?

- How are data breach notifications laws handled in different countries?

- What data can a cloud provider look at when capturing an image of a shared hard drive?

- What is the consumer allowed to see in an audit log, e.g., is information related to other cloud consumers protected?

- What is the responsibility of a consumer to report an incident in a PaaS model?

- Can a provider legally intervene in stopping an attack on an application in its cloud if it is only an indirect contractual relationship (e.g., three tiers of customers)?

Forensic analysis in a SaaS model may be the sole responsibility of a provider while forensic analysis in an IaaS model may be the primary responsibility of the consumer (with some collaboration with the provider). The PaaS model appears to split responsibilities between consumers and providers.
```

---

## 3. Indexed Vector Database Verification (Qdrant)

Direct inspection of the embedded Qdrant vector database (`data/qdrant`, collection `cybersecurity_chunks_bge_m3`) confirms:

1. **Existence:** All three target chunks are indexed and present in the collection:
   - `NIST_SP_800-144_txt_00065`: Point ID `64`
   - `NIST_SP_800-144_txt_00087`: Point ID `86`
   - `NIST_SP_800-146_txt_00134`: Point ID `313`
2. **Vector Integrity:** All three records contain 1024-dimensional normalized float32 vectors generated by `BAAI/bge-m3`.
3. **Payload Text Integrity:** A character-by-character comparison verifies an **exact 100% match** between the Qdrant payload text and the original JSONL corpus text:
   - `txt_00065`: 2,086 characters (Exact match: `True`)
   - `txt_00087`: 2,523 characters (Exact match: `True`)
   - `txt_00134`: 1,420 characters (Exact match: `True`)
4. **Conclusion:** The failure is **not caused by indexing errors, missing chunks, database corruption, or corrupted payload text**.

---

## 4. Dense Retrieval Diagnostic Findings

A diagnostic dense search was executed using the production `DenseRetriever` (`BAAI/bge-m3`) against the full 13,084 Qdrant vectors with query:
*"What challenges can organizations face when monitoring security in public cloud environments?"*

### 4.1 Target Chunk Positions and Scores

| Target Chunk ID | Source Document | Dense Rank | Cosine Similarity Score | Cutoff Rank 20 Score | Distance to Top-20 Cutoff ($\Delta$) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **`NIST_SP_800-144_txt_00065`** | `NIST_SP_800-144` | **#30** | `0.6472` | `0.6573` | **`-0.0101`** |
| **`NIST_SP_800-144_txt_00087`** | `NIST_SP_800-144` | **#90** | `0.6119` | `0.6573` | `-0.0454` |
| **`NIST_SP_800-146_txt_00134`** | `NIST_SP_800-146` | **#102** | `0.6062` | `0.6573` | `-0.0511` |

### 4.2 Analysis of Chunks Occupying Dense Top-20

The Dense Top 20 is heavily monopolized by **19 chunks from `NIST_SP_800-144`** and 1 chunk from `NIST_SP_800-210`:

```
Rank  1: NIST_SP_800-144_txt_00047 (0.7106) — Section: 3.3 The Security and Privacy Downside
Rank  2: NIST_SP_800-144_txt_00120 (0.6895) — Section: 6. Conclusion
Rank  3: NIST_SP_800-144_txt_00026 (0.6887) — Section: Maintain accountability over privacy and security...
Rank  4: NIST_SP_800-144_txt_00048 (0.6854) — Section: 3.3 The Security and Privacy Downside
Rank  5: NIST_SP_800-144_txt_00054 (0.6822) — Section: 4. Key Security and Privacy Issues
Rank  6: NIST_SP_800-144_txt_00050 (0.6812) — Section: 3.3 The Security and Privacy Downside
Rank  7: NIST_SP_800-144_txt_00056 (0.6759) — Section: 4.1 Governance
Rank  8: NIST_SP_800-144_txt_00022 (0.6733) — Section: Understand the public cloud computing environment...
Rank  9: NIST_SP_800-144_txt_00099 (0.6687) — Section: 5.1 General Concerns
Rank 10: NIST_SP_800-144_txt_00021 (0.6686) — Section: Carefully plan the security and privacy aspects...
...
Rank 19: NIST_SP_800-144_txt_00062 (0.6574) — Section: 4.3 Trust
Rank 20: NIST_SP_800-210_txt_00032 (0.6573) — Section: 2 Cloud Access Control Characteristics
```

### 4.3 Dense Semantic Drift Mechanism
- The user query uses high-level, overarching vocabulary: *"security in public cloud environments"*, *"challenges can organizations face"*.
- In BGE-M3's semantic latent space, these broad conceptual phrases align most strongly with **macro-level introductory and conclusion chunks** (such as Section 3.3 "The Security and Privacy Downside" and Section 6 "Conclusion").
- Target chunk `txt_00065` (Trust and Dashboard Visibility) ranked at **#30**, missing the Top-20 candidate pool by a razor-thin cosine delta of **`0.0101`**.
- Target chunks `txt_00087` (Incident Response event logs) and `txt_00134` (Cloud digital forensics) discuss operational mechanics (hypervisors, event logs, clock sync) and drift to ranks 90 and 102.

---

## 5. BM25 Lexical Retrieval Diagnostic Findings

A full corpus diagnostic scoring was run using the production `BM25Retriever` (`BM25Okapi`, tokenization: `[a-zA-Z0-9]+`).

### 5.1 Query Tokenization
- Raw Question: *"What challenges can organizations face when monitoring security in public cloud environments?"*
- Tokenized Query (12 tokens):
  `['what', 'challenges', 'can', 'organizations', 'face', 'when', 'monitoring', 'security', 'in', 'public', 'cloud', 'environments']`

### 5.2 Target Chunk Positions and BM25 Scores

| Target Chunk ID | Source Document | BM25 Rank | BM25 Score | Cutoff Rank 20 Score | Distance to Top-20 Cutoff ($\Delta$) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **`NIST_SP_800-146_txt_00134`** | `NIST_SP_800-146` | **#44** | `17.0660` | `19.1523` | `-2.0863` |
| **`NIST_SP_800-144_txt_00087`** | `NIST_SP_800-144` | **#84** | `14.9942` | `19.1523` | `-4.1581` |
| **`NIST_SP_800-144_txt_00065`** | `NIST_SP_800-144` | **#399** | `11.3289` | `19.1523` | `-7.8234` |

### 5.3 Token Matching Forensic Breakdown

#### Target 1: `NIST_SP_800-144_txt_00087` (BM25 Rank 84, Score 14.9942)
- **Matched Query Tokens (7):** `'can'` (1), `'monitoring'` (1), `'security'` (2), `'in'` (3), `'public'` (1), `'cloud'` (15), `'environments'` (1).
- **Missing High-IDF Query Tokens (5):** `'challenges'` (0), `'organizations'` (0), `'face'` (0), `'when'` (0), `'what'` (0).
- **Forensic Reason:** While the chunk discusses monitoring challenges (*"Cloud consumers are often confronted with extremely limited capabilities for detection of incidents in public cloud environments..."*), it uses the words **"consumers"** instead of **"organizations"**, and **"limited capabilities / prominent issues"** instead of **"challenges"**. The absence of the rare, high-IDF keyword **"challenges"** severely penalized its BM25 ranking.

#### Target 2: `NIST_SP_800-146_txt_00134` (BM25 Rank 44, Score 17.0660)
- **Matched Query Tokens (5):** `'what'` (5), `'can'` (2), `'when'` (1), `'in'` (9), `'cloud'` (4).
- **Missing Query Tokens (7):** `'challenges'` (0), `'organizations'` (0), `'face'` (0), `'monitoring'` (0), `'security'` (0), `'public'` (0), `'environments'` (0).
- **Forensic Reason:** The chunk achieves a high BM25 score solely through repeated questions (*"what is the responsibility...", "what data can a provider..."*) and high frequency of common prepositions. It completely lacks domain tokens like "security", "monitoring", and "public".

#### Target 3: `NIST_SP_800-144_txt_00065` (BM25 Rank 399, Score 11.3289)
- **Matched Query Tokens (4):** `'can'` (2), `'security'` (3), `'in'` (6), `'cloud'` (10).
- **Missing Query Tokens (8):** `'challenges'`, `'organizations'`, `'face'`, `'when'`, `'what'`, `'monitoring'`, `'public'`, `'environments'`.
- **Forensic Reason:** The text uses the phrase *"monitor status"* rather than *"monitoring"*, so the simple word-boundary tokenizer failed to stem or match the term.

---

## 6. Metadata, Filters, and Candidate Pool Fusion Dynamics

### 6.1 Filter Verification
- Code inspection of `DenseRetriever` (`app/retrieval/dense.py`), `BM25Retriever` (`app/retrieval/bm25.py`), and `HybridRetriever` (`app/retrieval/hybrid.py`) confirms that **no metadata, document, or category filters were active** (`filter=None`).
- All 13,084 corpus chunks were available for evaluation.

### 6.2 Reciprocal Rank Fusion ($k=60$) Dynamics
In Phase 1, `dense_top_k=20` and `bm25_top_k=20`.
- Because none of the three target chunks reached the Top 20 of either Dense or BM25, their RRF fusion scores were deterministically $0.0$.
- None of the target chunks entered the Top-20 fused candidate pool delivered to the reranker.

### 6.3 Empirical Simulation: Candidate Pool Depth Expansion
An empirical simulation was run testing candidate pool limits $N \in \{30, 50, 100\}$ on Q19:

| Candidate Pool Limit ($N$) | `NIST_SP_800-144_txt_00065` | `NIST_SP_800-144_txt_00087` | `NIST_SP_800-146_txt_00134` |
| :---: | :---: | :---: | :---: |
| **$N = 20$ (Phase 1 Baseline)** | Excluded (Dense #30, BM25 #399) | Excluded (Dense #90, BM25 #84) | Excluded (Dense #102, BM25 #44) |
| **$N = 30$** | In Dense (#30), **Excluded from Fused Top-30** | Excluded | Excluded |
| **$N = 50$** | In Dense (#30), **Excluded from Fused Top-50** | Excluded | In BM25 (#44), **Excluded from Fused Top-50** |
| **$N = 100$** | **Retrieved in Fused Pool (Rank #64)** | **Retrieved in Fused Pool (Rank #44)** | **Retrieved in Fused Pool (Rank #84)** |

> [!IMPORTANT]
> Because RRF scores decay rapidly ($1 / (60 + 	ext{rank})$), single-retriever candidates ranked between 25 and 50 are consistently overtaken by chunks that appear in both retrievers. Expanding candidate pools to **$N=30$ or $N=50$ is insufficient to rescue Q19** into the fused candidate pool; only $N=100$ brings all three chunks into the fusion window.

---

## 7. Downstream Cross-Encoder Assessment

To determine whether candidate pool expansion alone would resolve Q19, the production Cross-Encoder (`cross-encoder/ms-marco-MiniLM-L-6-v2`) was evaluated on the 3 target chunks alongside the 5 competitor chunks actually retrieved in Phase 1:

| Rank | Chunk ID | Chunk Type / Status | Cross-Encoder Logit Score | Content Summary |
| :---: | :--- | :---: | :---: | :--- |
| **1** | `NIST_SP_800-144_txt_00030` | Competitor (Phase 1 Rank 1) | **`+5.1375`** | Section 1.2 Purpose & Scope: Overview of public cloud security and privacy challenges. |
| **2** | `NIST_SP_800-144_txt_00008` | Competitor (Phase 1 Rank 2) | **`+4.9504`** | Abstract: Overview of security and privacy challenges pertinent to public cloud. |
| **3** | `NIST_SP_800-144_txt_00120` | Competitor (Phase 1 Rank 3) | **`+4.7616`** | Section 6 Conclusion: Continuous monitoring of system security state is challenging. |
| **4** | `NIST_SP_800-144_txt_00026` | Competitor (Phase 1 Rank 4) | **`+4.7335`** | Executive Summary: Maintain accountability over privacy and security in public cloud. |
| **5** | `NIST_SP_800-144_txt_00050` | Competitor (Phase 1 Rank 5) | **`+4.0500`** | Section 3.3 Security & Privacy Downside: Multi-tenancy and lack of physical boundaries. |
| **6** | `NIST_SP_800-144_txt_00065` | **TARGET CHUNK** | **`+0.5867`** | Section 4.3 Trust: Web dashboards lack detail; audit rights needed for visibility. |
| **7** | `NIST_SP_800-144_txt_00087` | **TARGET CHUNK** | **`-0.3854`** | Section 4.9 Incident Response: Limited capabilities for incident detection and event logs. |
| **8** | `NIST_SP_800-146_txt_00134` | **TARGET CHUNK** | **`-8.5259`** | Section 8.4.4 Forensics: Cloud forensic issues, clock synchronization, legal barriers. |

### Critical Discovery:
Even if all three target chunks are forced into the reranker candidate pool, **the Cross-Encoder scores all three targets below the top 5 competitors**:
- Top 5 competitors score between `+4.05` and `+5.14`.
- Best target chunk (`txt_00065`) scores `+0.5867` ($\Delta = -3.46$ below Rank 5).
- Target chunk `txt_00087` scores `-0.3854` ($\Delta = -4.43$ below Rank 5).
- Target chunk `txt_00134` receives an extreme negative logit (`-8.5259`).

**Conclusion:** Expanding candidate pool depth ($N$) without query transformation will **not** solve Q19. The Cross-Encoder itself strongly favors the broad conversational abstracts and conclusions of SP 800-144 over the specific technical subsections.

---

## 8. Corpus Ground-Truth Nuance: The Chunk 120 Finding

During content inspection of the retrieved competitor chunks, an important observation emerged regarding **`NIST_SP_800-144_txt_00120`** (retrieved at Rank 3 in Phase 1):

```markdown
### 6. Conclusion
...
Assessing and managing risk in cloud computing systems requires continuous monitoring of the security state of the system, and can prove challenging, since significant portions of the computing environment are under the control of the cloud provider and likely beyond the organization's purview.
...
```

1. Chunk `txt_00120` is the **authoritative synthesis paragraph** in NIST SP 800-144 that summarizes the exact monitoring challenges detailed across sections 4.3 and 4.9.
2. It contains the exact question phrase: *"continuous monitoring of the security state... can prove challenging... under the control of the cloud provider and likely beyond the organization's purview"*.
3. Because this chunk synthesizes the exact answer to Q19 in a single passage, all three retrieval models (Dense, BM25, and Cross-Encoder) naturally and legitimately prioritized it.
4. However, the Phase 1 ground truth for Q19 only designated the granular operational subsections (`txt_00065`, `txt_00087`, `txt_00134`), omitting the summary conclusion chunk `txt_00120`.

---

## 9. Evidence-Based Root Cause Summary

The candidate retrieval failure for Q19 is caused by the combination of three technical factors:

1. **Semantic Drift & Summary Magnet Effect (Dense):**  
   BGE-M3 dense embeddings of the broad query gravitate to macro-level sections (Conclusion, Downside, Purpose) which repeat global cloud security terms, pushing target operational chunks (`txt_00065`, `txt_00087`, `txt_00134`) down to ranks 30, 90, and 102.
2. **Vocabulary and Synonym Mismatch (BM25):**  
   Target chunks use formal technical descriptions (*"confronted with limited capabilities"*, *"cloud consumers"*, *"event sources"*, *"monitor status"*) rather than the user's phrasing (*"challenges"*, *"organizations"*, *"monitoring"*). BM25 penalized the chunks due to missing high-IDF terms, dropping them to ranks 44, 84, and 399.
3. **Cross-Attention Prose Preference (Cross-Encoder):**  
   The Cross-Encoder model (`ms-marco-MiniLM-L-6-v2`) assigns significantly higher relevance logits (`4.05` to `5.14`) to fluent introductory prose (`txt_00030`, `txt_00008`, `txt_00120`) than to technical operational lists (`+0.58` to `-8.52`).

---

## 10. Recommended Next Experiments (Phase 2)

Without modifying production code or benchmark ground truth, the following experiments are recommended for Phase 2:

### Experiment 1: Domain-Specific Query Expansion for Q19
- Test rewriting Q19 with domain terms:  
  *Original:* "What challenges can organizations face when monitoring security in public cloud environments?"  
  *Rewritten:* "NIST SP 800-144 SP 800-146 cloud monitoring challenges visibility web dashboards event logs audit logs access incident response detection forensics"
- Evaluate whether this elevates `txt_00065`, `txt_00087`, and `txt_00134` into the Dense and BM25 Top 20.

### Experiment 2: Candidate Pool Depth & Weighted RRF Fusion
- Evaluate increasing candidate limits ($N=50$ or $N=100$) in conjunction with weighted RRF ($w_{	ext{dense}}=0.7, w_{	ext{bm25}}=0.3$) to prevent single-channel dense hits like `txt_00065` (Rank 30) from being displaced by low-quality lexical matches.

### Experiment 3: Ground-Truth Annotation Review for Q19
- Conduct a formal review to determine whether `NIST_SP_800-144_txt_00120` should be recognized as a valid relevant ground-truth chunk for Q19 alongside the granular operational sections, given that it directly answers the question with authoritative NIST text.

---

**Report Complete.** File generated at `reports/retrieval_evaluation/phase2_q19_candidate_failure_investigation.md`.
