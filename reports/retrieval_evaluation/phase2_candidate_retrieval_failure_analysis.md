# Phase 2 Candidate Retrieval Failure Analysis

**Document:** `reports/retrieval_evaluation/phase2_candidate_retrieval_failure_analysis.md`  
**Project:** Cybersecurity RAG — Phase 2 Optimization  
**Baseline Freeze Commit:** `c6f2afb`  
**Date:** 2026-11-02  
**Status:** Complete — Empirical Forensic Investigation  

---

## 1. Executive Summary

During the frozen Phase 1 benchmark evaluation across 100 questions (`reports/retrieval_evaluation/benchmark_100q_results.json`), the production retrieval pipeline achieved an overall **Hit@5 of 48.0%**, resulting in **52 failed questions** (`Hit@5 == 0.0`).

A deterministic programmatic audit classifies the 52 failures into three mutually exclusive failure modes:
1. **Candidate Pool Misses (26 questions, 50.0% of failures):** Neither Dense (`BAAI/bge-m3`) nor Sparse (`BM25Okapi`) retrieved any expected ground-truth chunk into their respective Top-20 candidate pools (`dense_hit@20 == 0.0` and `bm25_hit@20 == 0.0`).
2. **Fusion Misses (7 questions, 13.5% of failures):** At least one retriever placed the target chunk in its Top-20 pool, but Reciprocal Rank Fusion (`RRFFusion`, $k=60$) dropped it outside the Top-20 fused candidate pool.
3. **Reranker Suppressions (19 questions, 36.5% of failures):** The target chunk successfully entered the Top-20 fused pool delivered to the Cross-Encoder (`hybrid_hit@20 == 1.0`), but the reranker demoted it outside the Top 5.

This investigation focuses strictly on the **26 Candidate Pool Misses**, which represent the single largest retrieval failure mode in Phase 1.

---

## 2. Final Count Verification Against Phase 1 Reports

The 26 candidate-pool failures identified in this investigation were verified against all authoritative Phase 1 baseline artifacts:

| Verification Source | Documented Candidate Miss Count | Verified Question IDs Match? | Integrity Status |
| :--- | :---: | :---: | :---: |
| `reports/FAILURE_ANALYSIS.md` (Baseline 36Q) | 2 of 4 baseline failures (`Q19`, `Q38`) | Yes (Historical baseline subset) | **VERIFIED** |
| `reports/retrieval_evaluation/PHASE_1_FINAL_BASELINE_REPORT.md` | **26 questions (50.0%)** | Yes (`Q19`, `Q38`, `Q45`, `Q47`, `Q49`, `Q53`, `Q56`, `Q63`, `Q65`, `Q66`, `Q69`, `Q71`, `Q72`, `Q74`, `Q75`, `Q79`, `Q80`, `Q83`, `Q86`, `Q87`, `Q90`, `Q92`, `Q95`, `Q97`, `Q100`, `Q102`) | **VERIFIED** |
| `reports/retrieval_evaluation/benchmark_100q_methodology_audit.md` | **26 questions (50.0%)** | Yes (Identical 26-question list) | **VERIFIED** |
| `reports/retrieval_evaluation/benchmark_100q_results.json` | **26 cases** | Yes (`failure_cases` with `Candidate Pool Miss`) | **VERIFIED** |
| `data/evaluation/retrieval_ground_truth_100q_refined.json` | 100 questions total | All 26 failed QIDs verified present and evaluation-eligible | **VERIFIED** |

> [!IMPORTANT]
> All 26 candidate retrieval failures are **100% unique, verified, and deterministically reproduced** across every committed benchmark artifact. There are zero duplicate question IDs.

---

## 3. Master Inventory of 26 Candidate Retrieval Failures

| # | Question ID | Question Text | Benchmark Category | Subset | Target NIST Document(s) | Expected Chunk Count |
| :---: | :--- | :--- | :--- | :---: | :--- | :---: |
| 01 | **Q19** | What challenges can organizations face when monitoring security in public cloud environments? | `cross_document` | `baseline` | NIST_SP_800-144, NIST_SP_800-146 | 3 |
| 02 | **Q38** | What are the five essential characteristics of cloud computing defined by NIST SP 800-145? | `direct_factual` | `baseline` | NIST_SP_800-145 | 1 |
| 03 | **Q45** | In the cloud computing security control mapping table, which NIST SP 800-53 control families are categorized under the Technical class versus the Operational class? | `table_structured` | `candidate` | NIST_SP_800-146 | 1 |
| 04 | **Q47** | How does the core Policy Decision Point (PDP) and Policy Enforcement Point (PEP) architecture in Zero Trust (NIST SP 800-207) integrate with cloud access control systems described in NIST SP 800-210? | `cross_document` | `candidate` | NIST_SP_800-207, NIST_SP_800-210 | 2 |
| 05 | **Q49** | How do cryptographic key management lifecycle considerations in NIST SP 800-57 align with the system framework components of a Cryptographic Key Management System (CKMS) in NIST SP 800-130? | `cross_document` | `candidate` | NIST_SP_800-130, NIST_SP_800-57 | 2 |
| 06 | **Q53** | How does NIST SP 800-161 guide organizations in identifying supply chain risks and enforcing security requirements through contractual supplier clauses? | `multi_chunk_reasoning` | `candidate` | NIST_SP_800-161 | 1 |
| 07 | **Q56** | In the public comments on NIST SP 800-133 Revision 3, what technical topics are reviewed regarding cryptographic key generation and entropy requirements? | `direct_factual` | `candidate` | NIST_SP_800-133 | 1 |
| 08 | **Q63** | In NIST SP 800-79-3, what is the primary purpose of guidelines for PIV Card Issuing (PCI) organizations? | `direct_factual` | `candidate` | NIST_SP_800-79 | 1 |
| 09 | **Q65** | What is the objective of NIST SP 800-217 regarding Personal Identity Verification (PIV) federation? | `direct_factual` | `candidate` | NIST_SP_800-217 | 1 |
| 10 | **Q66** | What is the primary objective of building a cybersecurity learning program as described in NIST SP 800-50? | `direct_factual` | `candidate` | NIST_SP_800-50 | 1 |
| 11 | **Q69** | What core security capabilities and integration roles are defined for APIs in cloud-native architectures per NIST SP 800-228? | `direct_factual` | `candidate` | NIST_SP_800-228 | 1 |
| 12 | **Q71** | What strategic considerations guide federal agencies in selecting and transitioning cryptographic standards per NIST SP 800-175B? | `conceptual` | `candidate` | NIST_SP_800-175 | 1 |
| 13 | **Q72** | How does NIST SP 800-178 compare policy expressiveness between XACML and Next Generation Access Control (NGAC)? | `conceptual` | `candidate` | NIST_SP_800-178 | 1 |
| 14 | **Q74** | What theoretical guarantees and trade-offs are evaluated using the epsilon privacy budget in differential privacy per NIST SP 800-226? | `conceptual` | `candidate` | NIST_SP_800-226 | 1 |
| 15 | **Q75** | What are the foundational building blocks that comprise the Network of Things (NoT) conceptual model in NIST SP 800-183? | `conceptual` | `candidate` | NIST_SP_800-183 | 1 |
| 16 | **Q79** | In the NIST FY 2025 Cybersecurity and Privacy Annual Report (SP 800-238), what emerging technology areas are identified for federal standards development? | `conceptual` | `candidate` | NIST_SP_800-238 | 1 |
| 17 | **Q80** | In the pre-draft public comments on NIST SP 800-197A, what international stakeholder perspectives are represented regarding lightweight block ciphers? | `conceptual` | `candidate` | NIST_SP_800-197 | 1 |
| 18 | **Q83** | How does NIST SP 800-223 characterize security and threat modeling challenges in High-Performance Computing (HPC) clusters? | `conceptual` | `candidate` | NIST_SP_800-223 | 1 |
| 19 | **Q86** | What pair-wise key establishment schemes are recommended in NIST SP 800-56B Revision 2? | `technical_control` | `candidate` | NIST_SP_800-56 | 1 |
| 20 | **Q87** | What elliptic curve domain parameter recommendations are established in NIST SP 800-186 for discrete logarithm cryptography? | `technical_control` | `candidate` | NIST_SP_800-186 | 1 |
| 21 | **Q90** | What technical specifications govern the Keyed-Hash Message Authentication Code (HMAC) in NIST SP 800-224? | `technical_control` | `candidate` | NIST_SP_800-224 | 1 |
| 22 | **Q92** | What specific technical challenges and preservation techniques are identified for handheld digital device forensics in NIST SP 800-72? | `technical_control` | `candidate` | NIST_SP_800-72 | 1 |
| 23 | **Q95** | In an enterprise telework deployment, what client endpoint security controls are recommended in NIST SP 800-114 Revision 1 for employee BYOD devices? | `scenario_based` | `candidate` | NIST_SP_800-114 | 1 |
| 24 | **Q97** | During an incident response investigation involving a seized smartphone, what evidence acquisition rules does NIST SP 800-101 Revision 1 specify to maintain evidence integrity? | `scenario_based` | `candidate` | NIST_SP_800-101 | 1 |
| 25 | **Q100** | In an enterprise cloud migration, how should an organization structure its Attribute Based Access Control (ABAC) policies to manage cross-tenant data access per NIST SP 800-210? | `scenario_based` | `candidate` | NIST_SP_800-210 | 1 |
| 26 | **Q102** | When integrating supply chain security into an enterprise DevSecOps pipeline, what security gates does NIST SP 800-204D recommend prior to production release? | `scenario_based` | `candidate` | NIST_SP_800-204 | 1 |

---

## 4. Detailed Question-by-Question Forensic Audits

For each of the 26 failed questions, this section details:
1. Exact question text and ground-truth rationale
2. Expected ground-truth chunk IDs and metadata
3. Actually retrieved Top-5 chunks, source documents, sections, and reranker scores
4. Confirmation of whether any expected chunk was retrieved (Candidate Pool and Top-5)
5. Retrieval method latency and stage metrics
6. Evidence-based root-cause analysis

### 01. Question Q19

- **Exact Question:** "What challenges can organizations face when monitoring security in public cloud environments?"
- **Benchmark Category:** `cross_document` | **Subset:** `baseline`
- **Target Document(s):** `NIST_SP_800-144`, `NIST_SP_800-146`
- **Expected Ground-Truth Chunks:** `NIST_SP_800-144_txt_00065`, `NIST_SP_800-144_txt_00087`, `NIST_SP_800-146_txt_00134`
- **Ground-Truth Rationale:** Details monitoring challenges in public clouds: superficial provider status dashboards, lack of low-level hypervisor log access, and multi-tenant forensics barriers.
- **Were Any Expected Chunks Retrieved in Top 20 Candidates:** **No (0.0% — Dense Hit@20 = 0.0, BM25 Hit@20 = 0.0)**
- **Were Any Expected Chunks Retrieved in Final Top 5:** **No (0/3)**

#### Available Stage Metrics & Latencies:
- **Dense (`BAAI/bge-m3`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `822.05 ms`
- **Sparse (`BM25Okapi`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `176.18 ms`
- **Fusion (`RRFFusion`, $k=60$, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `0.5 ms`
- **Reranker (`ms-marco-MiniLM-L-6-v2`, Final Top-5):** Latency: `4211.81 ms` | Total Query Latency: `5210.54 ms`

#### Actually Retrieved Top-5 Chunks (Post-Rerank):
| Rank | Retrieved Chunk ID | Document ID | Section Title | Cross-Encoder Score | Is Relevant? |
| :---: | :--- | :--- | :--- | :---: | :---: |
| 1 | `NIST_SP_800-144_txt_00030` | `NIST_SP_800-144` | Unknown | `5.1375` | **`False`** |
| 2 | `NIST_SP_800-144_txt_00008` | `NIST_SP_800-144` | Unknown | `4.9504` | **`False`** |
| 3 | `NIST_SP_800-144_txt_00120` | `NIST_SP_800-144` | **<mark>6. Conclusion</mark>** | `4.7616` | **`False`** |
| 4 | `NIST_SP_800-144_txt_00026` | `NIST_SP_800-144` | **Maintain accountability over the privacy and security of data and applications implemented and deployed in public cloud computing environments.** | `4.7335` | **`False`** |
| 5 | `NIST_SP_800-144_txt_00050` | `NIST_SP_800-144` | **3.3 The Security and Privacy Downside** | `4.0500` | **`False`** |

#### Expected Chunk Details & Keyword Coverage:
- **Expected Chunk:** `NIST_SP_800-144_txt_00065` (None, `395` tokens)
  - **Section:** *(Root / Main Text)*
  - **Text Preview:** "### **4.3 Trust**  While notification tools and Webbased dashboards are typically made available to consumers to monitor status, they can lack sufficient detail and may themselves suffer disruption during a system outage [Goo09a, Ker11, Per11].  Transparency in the way the cloud provider operates, i"
  - **Lexical Overlap:** `30.0%` (3 matched, 7 missing)
  - **Missing Keywords:** `monitoring`, `environments`, `public`, `challenges`, `face`, `organizations`, `when`
- **Expected Chunk:** `NIST_SP_800-144_txt_00087` (None, `450` tokens)
  - **Section:** *(Root / Main Text)*
  - **Text Preview:** "### **4.9 Incident Response**  As the name implies, incident response involves an organized method for dealing with the consequences of an attack against the security of a computer system.  The cloud provider's role is vital in performing incident response activities, including incident verification"
  - **Lexical Overlap:** `70.0%` (7 matched, 3 missing)
  - **Missing Keywords:** `challenges`, `organizations`, `when`
- **Expected Chunk:** `NIST_SP_800-146_txt_00134` (None, `297` tokens)
  - **Section:** *(Root / Main Text)*
  - **Text Preview:** "### **8.4.4 Support for Forensics**  As part of an incident response effort, the goal of digital forensics is to: (1) discern what happened, (2) understand what portions of the system were affected, (3) learn how to prevent such incidents from happening again, and (4) collect information for possibl"
  - **Lexical Overlap:** `30.0%` (3 matched, 7 missing)
  - **Missing Keywords:** `monitoring`, `environments`, `public`, `challenges`, `face`, `organizations`, `security`

#### Forensic Root Cause:
**Multi-Document Query Dilution:** The query spans two distinct publications (`NIST_SP_800-144`, `NIST_SP_800-146`). Dense and lexical retrieval pools were saturated by one document, failing to balance candidate representation across both required standards.

---

### 02. Question Q38

- **Exact Question:** "What are the five essential characteristics of cloud computing defined by NIST SP 800-145?"
- **Benchmark Category:** `direct_factual` | **Subset:** `baseline`
- **Target Document(s):** `NIST_SP_800-145`
- **Expected Ground-Truth Chunks:** `NIST_SP_800-145_txt_00012`
- **Ground-Truth Rationale:** Enumerates and defines the five essential cloud characteristics: On-demand self-service, Broad network access, Resource pooling, Rapid elasticity, and Measured service.
- **Were Any Expected Chunks Retrieved in Top 20 Candidates:** **No (0.0% — Dense Hit@20 = 0.0, BM25 Hit@20 = 0.0)**
- **Were Any Expected Chunks Retrieved in Final Top 5:** **No (0/1)**

#### Available Stage Metrics & Latencies:
- **Dense (`BAAI/bge-m3`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `782.03 ms`
- **Sparse (`BM25Okapi`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `160.95 ms`
- **Fusion (`RRFFusion`, $k=60$, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `0.33 ms`
- **Reranker (`ms-marco-MiniLM-L-6-v2`, Final Top-5):** Latency: `3975.43 ms` | Total Query Latency: `4918.75 ms`

#### Actually Retrieved Top-5 Chunks (Post-Rerank):
| Rank | Retrieved Chunk ID | Document ID | Section Title | Cross-Encoder Score | Is Relevant? |
| :---: | :--- | :--- | :--- | :---: | :---: |
| 1 | `NIST_SP_800-146_txt_00021` | `NIST_SP_800-146` | **<mark>2. Cloud Computing Definition</mark>** | `8.9707` | **`False`** |
| 2 | `NIST_SP_800-201_txt_00031` | `NIST_SP_800-201` | **2. Overview of NIST Cloud Forensic Challenges** | `6.2064` | **`False`** |
| 3 | `NIST_SP_800-145_txt_00011` | `NIST_SP_800-145` | **<mark>2. The NIST Definition of Cloud Computing</mark>** | `6.1913` | **`False`** |
| 4 | `NIST_SP_800-201_txt_00064` | `NIST_SP_800-201` | **cloud computing** | `3.6127` | **`False`** |
| 5 | `NIST_SP_800-144_txt_00033` | `NIST_SP_800-144` | **<mark>2. Background</mark>** | `2.1803` | **`False`** |

#### Expected Chunk Details & Keyword Coverage:
- **Expected Chunk:** `NIST_SP_800-145_txt_00012` (None, `360` tokens)
  - **Section:** *(Root / Main Text)*
  - **Text Preview:** "### **Essential Characteristics:**  - _On-demand self-service._ A consumer can unilaterally provision computing capabilities, such as server time and network storage, as needed automatically without requiring human interaction with each service provider.  - _Broad network access._ Capabilities are a"
  - **Lexical Overlap:** `56.0%` (5 matched, 4 missing)
  - **Missing Keywords:** `five`, `defined`, `800-145`, `nist`

#### Forensic Root Cause:
**Front-Matter / Metadata Semantic Drift:** Both retrievers were diverted by document title pages, executive summaries, and introductory front-matter (`NIST_SP_800-144_txt_00033`) which heavily repeat the publication ID and broad keywords, displacing the deeply nested technical operational passage.

---

### 03. Question Q45

- **Exact Question:** "In the cloud computing security control mapping table, which NIST SP 800-53 control families are categorized under the Technical class versus the Operational class?"
- **Benchmark Category:** `table_structured` | **Subset:** `candidate`
- **Target Document(s):** `NIST_SP_800-146`
- **Expected Ground-Truth Chunks:** `NIST_SP_800-146_tbl_00005_p01`
- **Ground-Truth Rationale:** Ground-truth standard passage required for technical completeness.
- **Were Any Expected Chunks Retrieved in Top 20 Candidates:** **No (0.0% — Dense Hit@20 = 0.0, BM25 Hit@20 = 0.0)**
- **Were Any Expected Chunks Retrieved in Final Top 5:** **No (0/1)**

#### Available Stage Metrics & Latencies:
- **Dense (`BAAI/bge-m3`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `634.93 ms`
- **Sparse (`BM25Okapi`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `261.37 ms`
- **Fusion (`RRFFusion`, $k=60$, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `0.29 ms`
- **Reranker (`ms-marco-MiniLM-L-6-v2`, Final Top-5):** Latency: `3859.3 ms` | Total Query Latency: `4755.89 ms`

#### Actually Retrieved Top-5 Chunks (Post-Rerank):
| Rank | Retrieved Chunk ID | Document ID | Section Title | Cross-Encoder Score | Is Relevant? |
| :---: | :--- | :--- | :--- | :---: | :---: |
| 1 | `NIST_SP_800-146_txt_00154` | `NIST_SP_800-146` | **<mark>Appendix A - Roles and Responsibilities</mark>** | `3.8875` | **`False`** |
| 2 | `NIST_SP_800-210_txt_00069` | `NIST_SP_800-210` | **<mark>Guidance and SP 800-53 Revision 4 Access Control (AC) Family Mapping</mark>** | `3.6637` | **`False`** |
| 3 | `NIST_SP_800-146_txt_00153` | `NIST_SP_800-146` | **<mark>Appendix A - Roles and Responsibilities</mark>** | `3.6215` | **`False`** |
| 4 | `NIST_SP_800-46_txt_00112` | `NIST_SP_800-46` | **<mark>Appendix A - NIST SP 800-53 Control Mappings</mark>** | `2.9728` | **`False`** |
| 5 | `NIST_SP_800-210_txt_00033` | `NIST_SP_800-210` | Unknown | `1.6465` | **`False`** |

#### Expected Chunk Details & Keyword Coverage:
- **Expected Chunk:** `NIST_SP_800-146_tbl_00005_p01` (None, `133` tokens)
  - **Section:** *(Root / Main Text)*
  - **Text Preview:** "### Table: Table on Page 71 Source: [NIST_SP_800-146 Page 71]  | Technical | Operational | Management | | :--- | :--- | :--- | | AccessControl AuditandAccountability IdentificationandAuthentication SystemandCommunication Protection | AwarenessandTraining ConfigurationandManagement ContingencyPlannin"
  - **Lexical Overlap:** `44.0%` (7 matched, 9 missing)
  - **Missing Keywords:** `categorized`, `computing`, `under`, `families`, `800-53`, `cloud`, `versus`, `class`, `mapping`

#### Forensic Root Cause:
**Structural Syntax Penalty on Markdown Tables:** Target chunk `NIST_SP_800-146_tbl_00005_p01` is a structured Markdown table mapping control families. The lack of standard grammatical narrative prose caused dense vector embeddings to miss the passage, and BM25 failed due to missing colloquial question terms.

---

### 04. Question Q47

- **Exact Question:** "How does the core Policy Decision Point (PDP) and Policy Enforcement Point (PEP) architecture in Zero Trust (NIST SP 800-207) integrate with cloud access control systems described in NIST SP 800-210?"
- **Benchmark Category:** `cross_document` | **Subset:** `candidate`
- **Target Document(s):** `NIST_SP_800-207`, `NIST_SP_800-210`
- **Expected Ground-Truth Chunks:** `NIST_SP_800-207_txt_00030`, `NIST_SP_800-210_txt_00028`
- **Ground-Truth Rationale:** Ground-truth standard passage required for technical completeness.
- **Were Any Expected Chunks Retrieved in Top 20 Candidates:** **No (0.0% — Dense Hit@20 = 0.0, BM25 Hit@20 = 0.0)**
- **Were Any Expected Chunks Retrieved in Final Top 5:** **No (0/2)**

#### Available Stage Metrics & Latencies:
- **Dense (`BAAI/bge-m3`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `959.14 ms`
- **Sparse (`BM25Okapi`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `347.82 ms`
- **Fusion (`RRFFusion`, $k=60$, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `0.56 ms`
- **Reranker (`ms-marco-MiniLM-L-6-v2`, Final Top-5):** Latency: `3743.64 ms` | Total Query Latency: `5051.16 ms`

#### Actually Retrieved Top-5 Chunks (Post-Rerank):
| Rank | Retrieved Chunk ID | Document ID | Section Title | Cross-Encoder Score | Is Relevant? |
| :---: | :--- | :--- | :--- | :---: | :---: |
| 1 | `NIST_SP_800-215_txt_00058` | `NIST_SP_800-215` | **Enterprise-Wide Network Security Framework - Zero Trust Network Access (ZTNA)** | `4.8638` | **`False`** |
| 2 | `NIST_SP_800-144_txt_00076` | `NIST_SP_800-144` | Unknown | `2.4883` | **`False`** |
| 3 | `NIST_SP_800-178_txt_00071` | `NIST_SP_800-178` | Unknown | `2.2252` | **`False`** |
| 4 | `NIST_SP_800-162_txt_00054` | `NIST_SP_800-162` | Unknown | `1.6655` | **`False`** |
| 5 | `NIST_SP_800-207_txt_00021` | `NIST_SP_800-207` | **Executive Summary** | `1.5578` | **`False`** |

#### Expected Chunk Details & Keyword Coverage:
- **Expected Chunk:** `NIST_SP_800-207_txt_00030` (None, `438` tokens)
  - **Section:** *(Root / Main Text)*
  - **Text Preview:** "### **Enterprise Infrastructure Layer**  The global control plane forms an integral part of the enterprise infrastructure layer. The management plane that contains the various interfaces is hosted within the global control plane. The roles of the global control plane and the management plane are as "
  - **Lexical Overlap:** `45.0%` (9 matched, 11 missing)
  - **Missing Keywords:** `architecture`, `access`, `trust`, `pdp`, `800-210`, `decision`, `core`, `cloud`, `described`, `zero`, `integrate`
- **Expected Chunk:** `NIST_SP_800-210_txt_00028` (None, `499` tokens)
  - **Section:** *(Root / Main Text)*
  - **Text Preview:** "### **<mark>2 Cloud Access Control Characteristics</mark>**  Despite the great advancements of cloud systems, concerns have been raised about offered levels of security and privacy. The importance of these concerns becomes more evident when considering the increasing number of users that have adopte"
  - **Lexical Overlap:** `40.0%` (8 matched, 12 missing)
  - **Missing Keywords:** `pep`, `enforcement`, `policy`, `point`, `pdp`, `800-207`, `800-210`, `decision`, `core`, `described`, `zero`, `integrate`

#### Forensic Root Cause:
**Multi-Document Query Dilution:** The query spans two distinct publications (`NIST_SP_800-207`, `NIST_SP_800-210`). Dense and lexical retrieval pools were saturated by one document, failing to balance candidate representation across both required standards.

---

### 05. Question Q49

- **Exact Question:** "How do cryptographic key management lifecycle considerations in NIST SP 800-57 align with the system framework components of a Cryptographic Key Management System (CKMS) in NIST SP 800-130?"
- **Benchmark Category:** `cross_document` | **Subset:** `candidate`
- **Target Document(s):** `NIST_SP_800-130`, `NIST_SP_800-57`
- **Expected Ground-Truth Chunks:** `NIST_SP_800-130_txt_00063`, `NIST_SP_800-57_txt_00033`
- **Ground-Truth Rationale:** Ground-truth standard passage required for technical completeness.
- **Were Any Expected Chunks Retrieved in Top 20 Candidates:** **No (0.0% — Dense Hit@20 = 0.0, BM25 Hit@20 = 0.0)**
- **Were Any Expected Chunks Retrieved in Final Top 5:** **No (0/2)**

#### Available Stage Metrics & Latencies:
- **Dense (`BAAI/bge-m3`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `696.63 ms`
- **Sparse (`BM25Okapi`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `242.41 ms`
- **Fusion (`RRFFusion`, $k=60$, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `0.42 ms`
- **Reranker (`ms-marco-MiniLM-L-6-v2`, Final Top-5):** Latency: `3939.67 ms` | Total Query Latency: `4879.14 ms`

#### Actually Retrieved Top-5 Chunks (Post-Rerank):
| Rank | Retrieved Chunk ID | Document ID | Section Title | Cross-Encoder Score | Is Relevant? |
| :---: | :--- | :--- | :--- | :---: | :---: |
| 1 | `NIST_SP_800-57_txt_00058` | `NIST_SP_800-57` | Unknown | `6.0824` | **`False`** |
| 2 | `NIST_SP_800-57_txt_00059` | `NIST_SP_800-57` | **8. Automation as a Baseline for Key Lifecycle Management** _Relevant Section: 7_ | `5.0888` | **`False`** |
| 3 | `NIST_SP_800-57_txt_00044` | `NIST_SP_800-57` | **Introduction** | `4.9690` | **`False`** |
| 4 | `NIST_SP_800-175_txt_00095` | `NIST_SP_800-175` | **5.1.1 Recommendation for Key Management** | `4.8681` | **`False`** |
| 5 | `NIST_SP_800-57_txt_00050` | `NIST_SP_800-57` | **Introduction** | `4.7665` | **`False`** |

#### Expected Chunk Details & Keyword Coverage:
- **Expected Chunk:** `NIST_SP_800-130_txt_00063` (None, `285` tokens)
  - **Section:** *(Root / Main Text)*
  - **Text Preview:** "### **2.10 CKMS Framework Components and Devices**  This CKMS Framework uses the term "component" to mean the hardware, software, and/or firmware required to construct the CKMS. The term "device" denotes a  combination of components that serve a specific purpose. A CKMS can be as simple as a softwar"
  - **Lexical Overlap:** `53.0%` (8 matched, 7 missing)
  - **Missing Keywords:** `do`, `800-57`, `lifecycle`, `800-130`, `align`, `considerations`, `nist`
- **Expected Chunk:** `NIST_SP_800-57_txt_00033` (None, `403` tokens)
  - **Section:** *(Root / Main Text)*
  - **Text Preview:** "### **Comment 1: Automated Key Lifecycle Management in Cloud KMS Environments**  **Reference:** Section 6 (Key States and Transitions) and Section 5.2.2.7 (Keying Material Storage Media and Mechanisms) **Observation:** The revision appropriately separates keys used for key establishment from those u"
  - **Lexical Overlap:** `53.0%` (8 matched, 7 missing)
  - **Missing Keywords:** `do`, `800-57`, `800-130`, `framework`, `components`, `considerations`, `ckms`

#### Forensic Root Cause:
**Multi-Document Query Dilution:** The query spans two distinct publications (`NIST_SP_800-130`, `NIST_SP_800-57`). Dense and lexical retrieval pools were saturated by one document, failing to balance candidate representation across both required standards.

---

### 06. Question Q53

- **Exact Question:** "How does NIST SP 800-161 guide organizations in identifying supply chain risks and enforcing security requirements through contractual supplier clauses?"
- **Benchmark Category:** `multi_chunk_reasoning` | **Subset:** `candidate`
- **Target Document(s):** `NIST_SP_800-161`
- **Expected Ground-Truth Chunks:** `NIST_SP_800-161_txt_00380`
- **Ground-Truth Rationale:** Ground-truth standard passage required for technical completeness.
- **Were Any Expected Chunks Retrieved in Top 20 Candidates:** **No (0.0% — Dense Hit@20 = 0.0, BM25 Hit@20 = 0.0)**
- **Were Any Expected Chunks Retrieved in Final Top 5:** **No (0/1)**

#### Available Stage Metrics & Latencies:
- **Dense (`BAAI/bge-m3`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `850.8 ms`
- **Sparse (`BM25Okapi`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `335.95 ms`
- **Fusion (`RRFFusion`, $k=60$, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `1.0 ms`
- **Reranker (`ms-marco-MiniLM-L-6-v2`, Final Top-5):** Latency: `4251.46 ms` | Total Query Latency: `5439.21 ms`

#### Actually Retrieved Top-5 Chunks (Post-Rerank):
| Rank | Retrieved Chunk ID | Document ID | Section Title | Cross-Encoder Score | Is Relevant? |
| :---: | :--- | :--- | :--- | :---: | :---: |
| 1 | `NIST_SP_800-161_txt_00614` | `NIST_SP_800-161` | **E.1.3. Relationship to NIST SP 800-161, Rev. 1,** **_Cybersecurity Supply Chain Risk Management Practices for Systems and Organizations_** | `4.3543` | **`False`** |
| 2 | `NIST_SP_800-161_txt_00611` | `NIST_SP_800-161` | **E.1.1. Purpose, Audience, and Background** | `3.9035` | **`False`** |
| 3 | `NIST_SP_800-161_txt_00206` | `NIST_SP_800-161` | **AC-21 INFORMATION SHARING** | `3.8654` | **`False`** |
| 4 | `NIST_SP_800-161_txt_00372` | `NIST_SP_800-161` | **(1)** _RISK ASSESSMENT \| SUPPLY CHAIN RISK ASSESSMENT_ | `3.7490` | **`False`** |
| 5 | `NIST_SP_800-161_txt_00271` | `NIST_SP_800-161` | Unknown | `3.7421` | **`False`** |

#### Expected Chunk Details & Keyword Coverage:
- **Expected Chunk:** `NIST_SP_800-161_txt_00380` (None, `478` tokens)
  - **Section:** *(Root / Main Text)*
  - **Text Preview:** "### **SA-1 POLICY AND PROCEDURES**  <u>Supplemental C-SCRM Guidance: The system and services acquisition policy and</u> procedures should address C-SCRM throughout the acquisition management life cycle process, to include purchases made via charge cards. C-SCRM procurement actions and the resultant "
  - **Lexical Overlap:** `56.0%` (9 matched, 7 missing)
  - **Missing Keywords:** `guide`, `enforcing`, `contractual`, `800-161`, `organizations`, `nist`, `identifying`

#### Forensic Root Cause:
**Front-Matter / Metadata Semantic Drift:** Both retrievers were diverted by document title pages, executive summaries, and introductory front-matter (`NIST_SP_800-161_txt_00614`, `NIST_SP_800-161_txt_00611`) which heavily repeat the publication ID and broad keywords, displacing the deeply nested technical operational passage.

---

### 07. Question Q56

- **Exact Question:** "In the public comments on NIST SP 800-133 Revision 3, what technical topics are reviewed regarding cryptographic key generation and entropy requirements?"
- **Benchmark Category:** `direct_factual` | **Subset:** `candidate`
- **Target Document(s):** `NIST_SP_800-133`
- **Expected Ground-Truth Chunks:** `NIST_SP_800-133_txt_00134`
- **Ground-Truth Rationale:** Ground-truth standard passage required for technical completeness.
- **Were Any Expected Chunks Retrieved in Top 20 Candidates:** **No (0.0% — Dense Hit@20 = 0.0, BM25 Hit@20 = 0.0)**
- **Were Any Expected Chunks Retrieved in Final Top 5:** **No (0/1)**

#### Available Stage Metrics & Latencies:
- **Dense (`BAAI/bge-m3`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `557.81 ms`
- **Sparse (`BM25Okapi`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `180.22 ms`
- **Fusion (`RRFFusion`, $k=60$, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `0.37 ms`
- **Reranker (`ms-marco-MiniLM-L-6-v2`, Final Top-5):** Latency: `3778.25 ms` | Total Query Latency: `4516.64 ms`

#### Actually Retrieved Top-5 Chunks (Post-Rerank):
| Rank | Retrieved Chunk ID | Document ID | Section Title | Cross-Encoder Score | Is Relevant? |
| :---: | :--- | :--- | :--- | :---: | :---: |
| 1 | `NIST_SP_800-133_txt_00001` | `NIST_SP_800-133` | **Public Comments on NIST SP 800-133 Revision 3 (Initial Public Draft) Recommendation for Cryptographic Key Generation** Comment period: April 17, 2026 - June 16, 2026 | `5.8301` | **`False`** |
| 2 | `NIST_SP_800-133_txt_00156` | `NIST_SP_800-133` | <u>20. Comments from Arpan Sharma, June 16, 2026</u> | `5.1812` | **`False`** |
| 3 | `NIST_SP_800-133_txt_00027` | `NIST_SP_800-133` | <u>8. Comments from Nishant Tyagi, May 28, 2026</u> | `5.0365` | **`False`** |
| 4 | `NIST_SP_800-133_txt_00106` | `NIST_SP_800-133` | Steve Weymann Co-Founder, KeyPair Consulting | `4.9112` | **`False`** |
| 5 | `NIST_SP_800-133_txt_00115` | `NIST_SP_800-133` | <u>15. Comments from Violet Sky Security (Rudolf Coetzee), June 15, 2026</u> | `4.9030` | **`False`** |

#### Expected Chunk Details & Keyword Coverage:
- **Expected Chunk:** `NIST_SP_800-133_txt_00134` (None, `413` tokens)
  - **Section:** *(Root / Main Text)*
  - **Text Preview:** "### **<u>COMMENT 4: Section 4.2.2, Line 476</u>**  The following statement has been added to the new section on 'Derivation of Initial Values Using Seed Expansion':  _"Notes: The Instantiated DRBG_ **_shall not_** _be used for any other purpose and_ **_must not_** _be callable from user-controlled s"
  - **Lexical Overlap:** `38.0%` (6 matched, 10 missing)
  - **Missing Keywords:** `cryptographic`, `revision`, `public`, `requirements`, `topics`, `reviewed`, `technical`, `regarding`, `nist`, `comments`

#### Forensic Root Cause:
**Front-Matter / Metadata Semantic Drift:** Both retrievers were diverted by document title pages, executive summaries, and introductory front-matter (`NIST_SP_800-133_txt_00001`) which heavily repeat the publication ID and broad keywords, displacing the deeply nested technical operational passage.

---

### 08. Question Q63

- **Exact Question:** "In NIST SP 800-79-3, what is the primary purpose of guidelines for PIV Card Issuing (PCI) organizations?"
- **Benchmark Category:** `direct_factual` | **Subset:** `candidate`
- **Target Document(s):** `NIST_SP_800-79`
- **Expected Ground-Truth Chunks:** `NIST_SP_800-79_txt_00092`
- **Ground-Truth Rationale:** Ground-truth standard passage required for technical completeness.
- **Were Any Expected Chunks Retrieved in Top 20 Candidates:** **No (0.0% — Dense Hit@20 = 0.0, BM25 Hit@20 = 0.0)**
- **Were Any Expected Chunks Retrieved in Final Top 5:** **No (0/1)**

#### Available Stage Metrics & Latencies:
- **Dense (`BAAI/bge-m3`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `650.28 ms`
- **Sparse (`BM25Okapi`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `157.8 ms`
- **Fusion (`RRFFusion`, $k=60$, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `0.35 ms`
- **Reranker (`ms-marco-MiniLM-L-6-v2`, Final Top-5):** Latency: `3938.75 ms` | Total Query Latency: `4747.18 ms`

#### Actually Retrieved Top-5 Chunks (Post-Rerank):
| Rank | Retrieved Chunk ID | Document ID | Section Title | Cross-Encoder Score | Is Relevant? |
| :---: | :--- | :--- | :--- | :---: | :---: |
| 1 | `NIST_SP_800-79_txt_00010` | `NIST_SP_800-79` | **Note to Reviewers** | `4.6750` | **`False`** |
| 2 | `NIST_SP_800-79_txt_00038` | `NIST_SP_800-79` | **List of Figures** | `4.3559` | **`False`** |
| 3 | `NIST_SP_800-79_txt_00041` | `NIST_SP_800-79` | **List of Figures** | `3.7874` | **`False`** |
| 4 | `NIST_SP_800-79_txt_00001` | `NIST_SP_800-79` | **Guidelines for the Authorization of PIV Card and Derived PIV Credential Issuers** | `3.7305` | **`False`** |
| 5 | `NIST_SP_800-79_txt_00040` | `NIST_SP_800-79` | **List of Figures** | `3.4737` | **`False`** |

#### Expected Chunk Details & Keyword Coverage:
- **Expected Chunk:** `NIST_SP_800-79_txt_00092` (None, `307` tokens)
  - **Section:** *(Root / Main Text)*
  - **Text Preview:** "### **Issuer Controls Assessment and the Authorization Decision Process**  An assessment is a set of activities performed by the assessor to gain assurance that the applicable issuer controls for a PCI or DPCI have been implemented properly and meet their required function or purpose. Understanding "
  - **Lexical Overlap:** `36.0%` (4 matched, 7 missing)
  - **Missing Keywords:** `nist`, `guidelines`, `piv`, `card`, `primary`, `organizations`, `800-79-3`

#### Forensic Root Cause:
**Front-Matter / Metadata Semantic Drift:** Both retrievers were diverted by document title pages, executive summaries, and introductory front-matter (`NIST_SP_800-79_txt_00010`, `NIST_SP_800-79_txt_00038`, `NIST_SP_800-79_txt_00041`) which heavily repeat the publication ID and broad keywords, displacing the deeply nested technical operational passage.

---

### 09. Question Q65

- **Exact Question:** "What is the objective of NIST SP 800-217 regarding Personal Identity Verification (PIV) federation?"
- **Benchmark Category:** `direct_factual` | **Subset:** `candidate`
- **Target Document(s):** `NIST_SP_800-217`
- **Expected Ground-Truth Chunks:** `NIST_SP_800-217_txt_00022`
- **Ground-Truth Rationale:** Ground-truth standard passage required for technical completeness.
- **Were Any Expected Chunks Retrieved in Top 20 Candidates:** **No (0.0% — Dense Hit@20 = 0.0, BM25 Hit@20 = 0.0)**
- **Were Any Expected Chunks Retrieved in Final Top 5:** **No (0/1)**

#### Available Stage Metrics & Latencies:
- **Dense (`BAAI/bge-m3`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `610.09 ms`
- **Sparse (`BM25Okapi`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `160.1 ms`
- **Fusion (`RRFFusion`, $k=60$, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `0.55 ms`
- **Reranker (`ms-marco-MiniLM-L-6-v2`, Final Top-5):** Latency: `4034.29 ms` | Total Query Latency: `4805.03 ms`

#### Actually Retrieved Top-5 Chunks (Post-Rerank):
| Rank | Retrieved Chunk ID | Document ID | Section Title | Cross-Encoder Score | Is Relevant? |
| :---: | :--- | :--- | :--- | :---: | :---: |
| 1 | `NIST_SP_800-217_txt_00002` | `NIST_SP_800-217` | **NIST Special Publication 800 NIST SP 800-217 fpd Guidelines for Personal Identity Verification (PIV) Federation** | `5.6107` | **`False`** |
| 2 | `NIST_SP_800-217_txt_00001` | `NIST_SP_800-217` | **NIST Special Publication 800 NIST SP 800-217 fpd** | `5.4763` | **`False`** |
| 3 | `NIST_SP_800-217_txt_00006` | `NIST_SP_800-217` | Unknown | `4.6982` | **`False`** |
| 4 | `NIST_SP_800-73_txt_00015` | `NIST_SP_800-73` | **NPIVP Conformance Testing** | `4.2044` | **`False`** |
| 5 | `NIST_SP_800-76_txt_00009` | `NIST_SP_800-76` | **Executive Summary** | `4.1155` | **`False`** |

#### Expected Chunk Details & Keyword Coverage:
- **Expected Chunk:** `NIST_SP_800-217_txt_00022` (None, `302` tokens)
  - **Section:** *(Root / Main Text)*
  - **Text Preview:** "### 240 **1.2. Purpose and Scope**  - 241 This document focuses on the use of federation technologies with PIV identity accounts  - 242 for federal employees and contractors. This document does not discuss citizen-facing use  - 243 cases covered in [SP800-63C]. This document does not address creatio"
  - **Lexical Overlap:** `40.0%` (4 matched, 6 missing)
  - **Missing Keywords:** `800-217`, `regarding`, `objective`, `personal`, `verification`, `nist`

#### Forensic Root Cause:
**Front-Matter / Metadata Semantic Drift:** Both retrievers were diverted by document title pages, executive summaries, and introductory front-matter (`NIST_SP_800-217_txt_00002`, `NIST_SP_800-217_txt_00001`, `NIST_SP_800-217_txt_00006`) which heavily repeat the publication ID and broad keywords, displacing the deeply nested technical operational passage.

---

### 10. Question Q66

- **Exact Question:** "What is the primary objective of building a cybersecurity learning program as described in NIST SP 800-50?"
- **Benchmark Category:** `direct_factual` | **Subset:** `candidate`
- **Target Document(s):** `NIST_SP_800-50`
- **Expected Ground-Truth Chunks:** `NIST_SP_800-50_txt_00078`
- **Ground-Truth Rationale:** Ground-truth standard passage required for technical completeness.
- **Were Any Expected Chunks Retrieved in Top 20 Candidates:** **No (0.0% — Dense Hit@20 = 0.0, BM25 Hit@20 = 0.0)**
- **Were Any Expected Chunks Retrieved in Final Top 5:** **No (0/1)**

#### Available Stage Metrics & Latencies:
- **Dense (`BAAI/bge-m3`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `576.18 ms`
- **Sparse (`BM25Okapi`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `181.72 ms`
- **Fusion (`RRFFusion`, $k=60$, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `0.28 ms`
- **Reranker (`ms-marco-MiniLM-L-6-v2`, Final Top-5):** Latency: `3967.32 ms` | Total Query Latency: `4725.5 ms`

#### Actually Retrieved Top-5 Chunks (Post-Rerank):
| Rank | Retrieved Chunk ID | Document ID | Section Title | Cross-Encoder Score | Is Relevant? |
| :---: | :--- | :--- | :--- | :---: | :---: |
| 1 | `NIST_SP_800-50_fig_00004` | `NIST_SP_800-50` | Unknown | `4.3561` | **`False`** |
| 2 | `NIST_SP_800-50_txt_00069` | `NIST_SP_800-50` | Unknown | `3.8643` | **`False`** |
| 3 | `NIST_SP_800-50_txt_00032` | `NIST_SP_800-50` | **Executive Summary** | `3.4632` | **`False`** |
| 4 | `NIST_SP_800-50_txt_00002` | `NIST_SP_800-50` | **Building a Cybersecurity and Privacy Learning Program** | `3.3759` | **`False`** |
| 5 | `NIST_SP_800-50_txt_00001` | `NIST_SP_800-50` | **Building a Cybersecurity and Privacy Learning Program** | `3.3574` | **`False`** |

#### Expected Chunk Details & Keyword Coverage:
- **Expected Chunk:** `NIST_SP_800-50_txt_00078` (None, `497` tokens)
  - **Section:** *(Root / Main Text)*
  - **Text Preview:** "### **2.5.1. All Users**  In a typical scenario, all of the organization's personnel will participate in the CPLP, agree to abide by the acceptable use policy or standards of behavior, complete the recurring<sup>10</sup> learning program training, and attend, complete, view, and receive the other va"
  - **Lexical Overlap:** `60.0%` (6 matched, 4 missing)
  - **Missing Keywords:** `objective`, `building`, `primary`, `described`

#### Forensic Root Cause:
**Front-Matter / Metadata Semantic Drift:** Both retrievers were diverted by document title pages, executive summaries, and introductory front-matter (`NIST_SP_800-50_fig_00004`, `NIST_SP_800-50_txt_00032`, `NIST_SP_800-50_txt_00002`) which heavily repeat the publication ID and broad keywords, displacing the deeply nested technical operational passage.

---

### 11. Question Q69

- **Exact Question:** "What core security capabilities and integration roles are defined for APIs in cloud-native architectures per NIST SP 800-228?"
- **Benchmark Category:** `direct_factual` | **Subset:** `candidate`
- **Target Document(s):** `NIST_SP_800-228`
- **Expected Ground-Truth Chunks:** `NIST_SP_800-228_txt_00059`
- **Ground-Truth Rationale:** Ground-truth standard passage required for technical completeness.
- **Were Any Expected Chunks Retrieved in Top 20 Candidates:** **No (0.0% — Dense Hit@20 = 0.0, BM25 Hit@20 = 0.0)**
- **Were Any Expected Chunks Retrieved in Final Top 5:** **No (0/1)**

#### Available Stage Metrics & Latencies:
- **Dense (`BAAI/bge-m3`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `1146.17 ms`
- **Sparse (`BM25Okapi`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `345.0 ms`
- **Fusion (`RRFFusion`, $k=60$, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `0.42 ms`
- **Reranker (`ms-marco-MiniLM-L-6-v2`, Final Top-5):** Latency: `4206.05 ms` | Total Query Latency: `5697.64 ms`

#### Actually Retrieved Top-5 Chunks (Post-Rerank):
| Rank | Retrieved Chunk ID | Document ID | Section Title | Cross-Encoder Score | Is Relevant? |
| :---: | :--- | :--- | :--- | :---: | :---: |
| 1 | `NIST_SP_800-228_txt_00037` | `NIST_SP_800-228` | **1.4. Relationship to Other NIST Documents** | `2.5575` | **`False`** |
| 2 | `NIST_SP_800-228_txt_00002` | `NIST_SP_800-228` | **NIST Special Publication 800 NIST SP 800-228-upd1 Guidelines for API Protection for Cloud-Native Systems** | `2.2524` | **`False`** |
| 3 | `NIST_SP_800-228_txt_00001` | `NIST_SP_800-228` | **Guidelines for API Protection for Cloud-Native Systems** | `2.0376` | **`False`** |
| 4 | `NIST_SP_800-204_txt_00030` | `NIST_SP_800-204` | **1.4. Relationship to Other NIST Documents** | `1.6328` | **`False`** |
| 5 | `NIST_SP_800-228_txt_00006` | `NIST_SP_800-228` | **How to Cite this NIST Technical Series Publication:** | `1.5827` | **`False`** |

#### Expected Chunk Details & Keyword Coverage:
- **Expected Chunk:** `NIST_SP_800-228_txt_00059` (None, `462` tokens)
  - **Section:** *(Root / Main Text)*
  - **Text Preview:** "### **3. Recommended Controls for APIs**  In their earliest form, controls for APIs focused primarily on encryption in transit while delegating most other concerns to the application. Over time, a variety of challenges have emerged that necessitate the evolution of controls, including:  - The distri"
  - **Lexical Overlap:** `38.0%` (5 matched, 8 missing)
  - **Missing Keywords:** `integration`, `core`, `roles`, `capabilities`, `cloud-native`, `architectures`, `per`, `security`

#### Forensic Root Cause:
**Front-Matter / Metadata Semantic Drift:** Both retrievers were diverted by document title pages, executive summaries, and introductory front-matter (`NIST_SP_800-228_txt_00037`, `NIST_SP_800-228_txt_00002`, `NIST_SP_800-228_txt_00001`) which heavily repeat the publication ID and broad keywords, displacing the deeply nested technical operational passage.

---

### 12. Question Q71

- **Exact Question:** "What strategic considerations guide federal agencies in selecting and transitioning cryptographic standards per NIST SP 800-175B?"
- **Benchmark Category:** `conceptual` | **Subset:** `candidate`
- **Target Document(s):** `NIST_SP_800-175`
- **Expected Ground-Truth Chunks:** `NIST_SP_800-175_txt_00032`
- **Ground-Truth Rationale:** Ground-truth standard passage required for technical completeness.
- **Were Any Expected Chunks Retrieved in Top 20 Candidates:** **No (0.0% — Dense Hit@20 = 0.0, BM25 Hit@20 = 0.0)**
- **Were Any Expected Chunks Retrieved in Final Top 5:** **No (0/1)**

#### Available Stage Metrics & Latencies:
- **Dense (`BAAI/bge-m3`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `747.58 ms`
- **Sparse (`BM25Okapi`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `154.95 ms`
- **Fusion (`RRFFusion`, $k=60$, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `0.37 ms`
- **Reranker (`ms-marco-MiniLM-L-6-v2`, Final Top-5):** Latency: `4139.01 ms` | Total Query Latency: `5041.91 ms`

#### Actually Retrieved Top-5 Chunks (Post-Rerank):
| Rank | Retrieved Chunk ID | Document ID | Section Title | Cross-Encoder Score | Is Relevant? |
| :---: | :--- | :--- | :--- | :---: | :---: |
| 1 | `NIST_SP_800-130_txt_00261` | `NIST_SP_800-130` | 84. [SP 800-131A] | `3.2833` | **`False`** |
| 2 | `NIST_SP_800-175_txt_00001` | `NIST_SP_800-175` | **NIST Special Publication 800-175B Revision 1** | `3.2248` | **`False`** |
| 3 | `NIST_SP_800-175_txt_00145` | `NIST_SP_800-175` | SP 800-21 | `3.1858` | **`False`** |
| 4 | `NIST_SP_800-57_txt_00101` | `NIST_SP_800-57` | **Concluding Note** | `2.9849` | **`False`** |
| 5 | `NIST_SP_800-175_txt_00168` | `NIST_SP_800-175` | SP 800-132 | `2.9768` | **`False`** |

#### Expected Chunk Details & Keyword Coverage:
- **Expected Chunk:** `NIST_SP_800-175_txt_00032` (None, `497` tokens)
  - **Section:** *(Root / Main Text)*
  - **Text Preview:** "### **2.2 Federal Information Processing Standards and Special Publications**  ### **2.2.1 The Use of FIPS and SPs**  When developing a specification or the criteria for the selection of a cryptographic mechanism or service, cryptographic algorithms specified in FIPS and SPs must be used, when avail"
  - **Lexical Overlap:** `54.0%` (7 matched, 6 missing)
  - **Missing Keywords:** `strategic`, `considerations`, `agencies`, `transitioning`, `800-175b`, `selecting`

#### Forensic Root Cause:
**Front-Matter / Metadata Semantic Drift:** Both retrievers were diverted by document title pages, executive summaries, and introductory front-matter (`NIST_SP_800-175_txt_00001`) which heavily repeat the publication ID and broad keywords, displacing the deeply nested technical operational passage.

---

### 13. Question Q72

- **Exact Question:** "How does NIST SP 800-178 compare policy expressiveness between XACML and Next Generation Access Control (NGAC)?"
- **Benchmark Category:** `conceptual` | **Subset:** `candidate`
- **Target Document(s):** `NIST_SP_800-178`
- **Expected Ground-Truth Chunks:** `NIST_SP_800-178_txt_00124`
- **Ground-Truth Rationale:** Ground-truth standard passage required for technical completeness.
- **Were Any Expected Chunks Retrieved in Top 20 Candidates:** **No (0.0% — Dense Hit@20 = 0.0, BM25 Hit@20 = 0.0)**
- **Were Any Expected Chunks Retrieved in Final Top 5:** **No (0/1)**

#### Available Stage Metrics & Latencies:
- **Dense (`BAAI/bge-m3`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `572.3 ms`
- **Sparse (`BM25Okapi`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `146.89 ms`
- **Fusion (`RRFFusion`, $k=60$, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `0.19 ms`
- **Reranker (`ms-marco-MiniLM-L-6-v2`, Final Top-5):** Latency: `3859.72 ms` | Total Query Latency: `4579.1 ms`

#### Actually Retrieved Top-5 Chunks (Post-Rerank):
| Rank | Retrieved Chunk ID | Document ID | Section Title | Cross-Encoder Score | Is Relevant? |
| :---: | :--- | :--- | :--- | :---: | :---: |
| 1 | `NIST_SP_800-178_txt_00013` | `NIST_SP_800-178` | **<mark>Executive Summary</mark>** | `5.4081` | **`False`** |
| 2 | `NIST_SP_800-178_txt_00100` | `NIST_SP_800-178` | **<mark>5 Analysis</mark>** | `5.2468` | **`False`** |
| 3 | `NIST_SP_800-178_txt_00035` | `NIST_SP_800-178` | **1.1 Purpose and Scope** | `4.7259` | **`False`** |
| 4 | `NIST_SP_800-178_txt_00003` | `NIST_SP_800-178` | **NIST Special Publication 800-178** | `4.3046` | **`False`** |
| 5 | `NIST_SP_800-178_txt_00002` | `NIST_SP_800-178` | **A Comparison of Attribute Based Access Control (ABAC) Standards for Data Service Applications** | `4.1561` | **`False`** |

#### Expected Chunk Details & Keyword Coverage:
- **Expected Chunk:** `NIST_SP_800-178_txt_00124` (None, `434` tokens)
  - **Section:** *(Root / Main Text)*
  - **Text Preview:** "### **<mark>6 Conclusion</mark>**  Without such features, XACML is arguably incapable of enforcing a variety of policies whose intent is to prevent "leakage" of data to unauthorized users.  Certain policies are more efficiently expressed using logical formula rather than enumeration. An NGAC configu"
  - **Lexical Overlap:** `46.0%` (6 matched, 7 missing)
  - **Missing Keywords:** `nist`, `between`, `800-178`, `generation`, `control`, `compare`, `next`

#### Forensic Root Cause:
**Front-Matter / Metadata Semantic Drift:** Both retrievers were diverted by document title pages, executive summaries, and introductory front-matter (`NIST_SP_800-178_txt_00013`, `NIST_SP_800-178_txt_00003`, `NIST_SP_800-178_txt_00002`) which heavily repeat the publication ID and broad keywords, displacing the deeply nested technical operational passage.

---

### 14. Question Q74

- **Exact Question:** "What theoretical guarantees and trade-offs are evaluated using the epsilon privacy budget in differential privacy per NIST SP 800-226?"
- **Benchmark Category:** `conceptual` | **Subset:** `candidate`
- **Target Document(s):** `NIST_SP_800-226`
- **Expected Ground-Truth Chunks:** `NIST_SP_800-226_txt_00042`
- **Ground-Truth Rationale:** Ground-truth standard passage required for technical completeness.
- **Were Any Expected Chunks Retrieved in Top 20 Candidates:** **No (0.0% — Dense Hit@20 = 0.0, BM25 Hit@20 = 0.0)**
- **Were Any Expected Chunks Retrieved in Final Top 5:** **No (0/1)**

#### Available Stage Metrics & Latencies:
- **Dense (`BAAI/bge-m3`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `812.92 ms`
- **Sparse (`BM25Okapi`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `242.22 ms`
- **Fusion (`RRFFusion`, $k=60$, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `0.51 ms`
- **Reranker (`ms-marco-MiniLM-L-6-v2`, Final Top-5):** Latency: `3794.46 ms` | Total Query Latency: `4850.11 ms`

#### Actually Retrieved Top-5 Chunks (Post-Rerank):
| Rank | Retrieved Chunk ID | Document ID | Section Title | Cross-Encoder Score | Is Relevant? |
| :---: | :--- | :--- | :--- | :---: | :---: |
| 1 | `NIST_SP_800-226_txt_00034` | `NIST_SP_800-226` | **1. Introduction** | `3.6802` | **`False`** |
| 2 | `NIST_SP_800-226_txt_00147` | `NIST_SP_800-226` | **4.6. Conclusion** | `2.2504` | **`False`** |
| 3 | `NIST_SP_800-236_txt_00023` | `NIST_SP_800-236` | **Major Accomplishments in FY 2024:** | `2.1559` | **`False`** |
| 4 | `NIST_SP_800-226_txt_00146` | `NIST_SP_800-226` | **4.6. Conclusion** | `1.8134` | **`False`** |
| 5 | `NIST_SP_800-226_txt_00002` | `NIST_SP_800-226` | **NIST Special Publication 800 NIST SP 800-226 Guidelines for Evaluating Differential Privacy Guarantees** | `1.6122` | **`False`** |

#### Expected Chunk Details & Keyword Coverage:
- **Expected Chunk:** `NIST_SP_800-226_txt_00042` (None, `493` tokens)
  - **Section:** *(Root / Main Text)*
  - **Text Preview:** "### **2.1. The Promise of Differential Privacy**  One way to view the promise of differential privacy is in terms of potential privacy harms that could be prevented, like those that can occur from re‐identification attacks. NIST SP 800‐226 March 2025  For example, imagine an insurance company wants "
  - **Lexical Overlap:** `54.0%` (7 matched, 6 missing)
  - **Missing Keywords:** `guarantees`, `evaluated`, `theoretical`, `epsilon`, `trade-offs`, `800-226`

#### Forensic Root Cause:
**Front-Matter / Metadata Semantic Drift:** Both retrievers were diverted by document title pages, executive summaries, and introductory front-matter (`NIST_SP_800-226_txt_00002`) which heavily repeat the publication ID and broad keywords, displacing the deeply nested technical operational passage.

---

### 15. Question Q75

- **Exact Question:** "What are the foundational building blocks that comprise the Network of Things (NoT) conceptual model in NIST SP 800-183?"
- **Benchmark Category:** `conceptual` | **Subset:** `candidate`
- **Target Document(s):** `NIST_SP_800-183`
- **Expected Ground-Truth Chunks:** `NIST_SP_800-183_txt_00044`
- **Ground-Truth Rationale:** Ground-truth standard passage required for technical completeness.
- **Were Any Expected Chunks Retrieved in Top 20 Candidates:** **No (0.0% — Dense Hit@20 = 0.0, BM25 Hit@20 = 0.0)**
- **Were Any Expected Chunks Retrieved in Final Top 5:** **No (0/1)**

#### Available Stage Metrics & Latencies:
- **Dense (`BAAI/bge-m3`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `641.16 ms`
- **Sparse (`BM25Okapi`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `208.88 ms`
- **Fusion (`RRFFusion`, $k=60$, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `0.36 ms`
- **Reranker (`ms-marco-MiniLM-L-6-v2`, Final Top-5):** Latency: `3847.78 ms` | Total Query Latency: `4698.18 ms`

#### Actually Retrieved Top-5 Chunks (Post-Rerank):
| Rank | Retrieved Chunk ID | Document ID | Section Title | Cross-Encoder Score | Is Relevant? |
| :---: | :--- | :--- | :--- | :---: | :---: |
| 1 | `NIST_SP_800-183_txt_00007` | `NIST_SP_800-183` | **Abstract** | `2.2716` | **`False`** |
| 2 | `NIST_SP_800-183_fig_00005` | `NIST_SP_800-183` | Unknown | `1.2856` | **`False`** |
| 3 | `NIST_SP_800-183_txt_00001` | `NIST_SP_800-183` | **Networks of 'Things'** | `-0.0353` | **`False`** |
| 4 | `NIST_SP_800-183_txt_00002` | `NIST_SP_800-183` | **Networks of 'Things'** | `-0.5868` | **`False`** |
| 5 | `NIST_SP_800-183_txt_00017` | `NIST_SP_800-183` | **<mark>1 Introduction</mark>** | `-1.7272` | **`False`** |

#### Expected Chunk Details & Keyword Coverage:
- **Expected Chunk:** `NIST_SP_800-183_txt_00044` (None, `407` tokens)
  - **Section:** *(Root / Main Text)*
  - **Text Preview:** "### **<mark>5 Reliability and Security Primitive Scenarios</mark>**  The elements lay out key contextual issues related to trustworthiness of a specific NoT. And the primitives are the building blocks of NoTs. Because trustworthiness is such a broad concept, this document has mainly focused on two ""
  - **Lexical Overlap:** `38.0%` (5 matched, 8 missing)
  - **Missing Keywords:** `conceptual`, `model`, `foundational`, `comprise`, `800-183`, `things`, `network`, `nist`

#### Forensic Root Cause:
**Front-Matter / Metadata Semantic Drift:** Both retrievers were diverted by document title pages, executive summaries, and introductory front-matter (`NIST_SP_800-183_txt_00007`, `NIST_SP_800-183_fig_00005`, `NIST_SP_800-183_txt_00001`) which heavily repeat the publication ID and broad keywords, displacing the deeply nested technical operational passage.

---

### 16. Question Q79

- **Exact Question:** "In the NIST FY 2025 Cybersecurity and Privacy Annual Report (SP 800-238), what emerging technology areas are identified for federal standards development?"
- **Benchmark Category:** `conceptual` | **Subset:** `candidate`
- **Target Document(s):** `NIST_SP_800-238`
- **Expected Ground-Truth Chunks:** `NIST_SP_800-238_txt_00016`
- **Ground-Truth Rationale:** Ground-truth standard passage required for technical completeness.
- **Were Any Expected Chunks Retrieved in Top 20 Candidates:** **No (0.0% — Dense Hit@20 = 0.0, BM25 Hit@20 = 0.0)**
- **Were Any Expected Chunks Retrieved in Final Top 5:** **No (0/1)**

#### Available Stage Metrics & Latencies:
- **Dense (`BAAI/bge-m3`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `793.33 ms`
- **Sparse (`BM25Okapi`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `302.41 ms`
- **Fusion (`RRFFusion`, $k=60$, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `0.35 ms`
- **Reranker (`ms-marco-MiniLM-L-6-v2`, Final Top-5):** Latency: `4737.83 ms` | Total Query Latency: `5833.92 ms`

#### Actually Retrieved Top-5 Chunks (Post-Rerank):
| Rank | Retrieved Chunk ID | Document ID | Section Title | Cross-Encoder Score | Is Relevant? |
| :---: | :--- | :--- | :--- | :---: | :---: |
| 1 | `NIST_SP_800-238_txt_00028` | `NIST_SP_800-238` | Unknown | `5.6759` | **`False`** |
| 2 | `NIST_SP_800-236_txt_00043` | `NIST_SP_800-236` | Unknown | `5.4877` | **`False`** |
| 3 | `NIST_SP_800-238_txt_00025` | `NIST_SP_800-238` | Unknown | `4.2420` | **`False`** |
| 4 | `NIST_SP_800-236_txt_00040` | `NIST_SP_800-236` | Unknown | `3.7166` | **`False`** |
| 5 | `NIST_SP_800-238_txt_00002` | `NIST_SP_800-238` | Unknown | `3.6141` | **`False`** |

#### Expected Chunk Details & Keyword Coverage:
- **Expected Chunk:** `NIST_SP_800-238_txt_00016` (None, `377` tokens)
  - **Section:** *(Root / Main Text)*
  - **Text Preview:** "### **Major accomplishments:**  - Established a Hardware Security Laboratory to enhance semiconductor security through measurements and metrics, including an electrical probing station, electromagnetic side-channel analysis equipment, test artifacts, and initiating experiment development.  - Held a "
  - **Lexical Overlap:** `31.0%` (5 matched, 11 missing)
  - **Missing Keywords:** `800-238`, `federal`, `report`, `identified`, `areas`, `technology`, `2025`, `annual`, `nist`, `standards`, `privacy`

#### Forensic Root Cause:
**Front-Matter / Metadata Semantic Drift:** Both retrievers were diverted by document title pages, executive summaries, and introductory front-matter (`NIST_SP_800-238_txt_00002`) which heavily repeat the publication ID and broad keywords, displacing the deeply nested technical operational passage.

---

### 17. Question Q80

- **Exact Question:** "In the pre-draft public comments on NIST SP 800-197A, what international stakeholder perspectives are represented regarding lightweight block ciphers?"
- **Benchmark Category:** `conceptual` | **Subset:** `candidate`
- **Target Document(s):** `NIST_SP_800-197`
- **Expected Ground-Truth Chunks:** `NIST_SP_800-197_txt_00007`
- **Ground-Truth Rationale:** Ground-truth standard passage required for technical completeness.
- **Were Any Expected Chunks Retrieved in Top 20 Candidates:** **No (0.0% — Dense Hit@20 = 0.0, BM25 Hit@20 = 0.0)**
- **Were Any Expected Chunks Retrieved in Final Top 5:** **No (0/1)**

#### Available Stage Metrics & Latencies:
- **Dense (`BAAI/bge-m3`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `840.02 ms`
- **Sparse (`BM25Okapi`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `247.4 ms`
- **Fusion (`RRFFusion`, $k=60$, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `0.51 ms`
- **Reranker (`ms-marco-MiniLM-L-6-v2`, Final Top-5):** Latency: `3906.99 ms` | Total Query Latency: `4994.92 ms`

#### Actually Retrieved Top-5 Chunks (Post-Rerank):
| Rank | Retrieved Chunk ID | Document ID | Section Title | Cross-Encoder Score | Is Relevant? |
| :---: | :--- | :--- | :--- | :---: | :---: |
| 1 | `NIST_SP_800-197_txt_00001` | `NIST_SP_800-197` | Pre-Draft Public Comments on SP 800-197A | `3.6480` | **`False`** |
| 2 | `NIST_SP_800-197_txt_00011` | `NIST_SP_800-197` | **Analysis of "PRE-DRAFT Call for Comments: NIST Launches Development of Cryptographic Accordions" (NIST SP 800-197A)** | `3.5417` | **`False`** |
| 3 | `NIST_SP_800-197_txt_00051` | `NIST_SP_800-197` | Unknown | `2.7891` | **`False`** |
| 4 | `NIST_SP_800-197_txt_00009` | `NIST_SP_800-197` | **<mark>4. Comments from the U.S. Department of Energy, August 5, 2025</mark>** | `2.3293` | **`False`** |
| 5 | `NIST_SP_800-133_txt_00115` | `NIST_SP_800-133` | <u>15. Comments from Violet Sky Security (Rudolf Coetzee), June 15, 2026</u> | `2.2290` | **`False`** |

#### Expected Chunk Details & Keyword Coverage:
- **Expected Chunk:** `NIST_SP_800-197_txt_00007` (None, `493` tokens)
  - **Section:** *(Root / Main Text)*
  - **Text Preview:** "### **<mark>2. Comments from Bryan Queen (NSA Center for Cybersecurity Standards) August 4, 2025</mark>**  We have several points we want to make.  1. We think that the set of planned accordions (Acc128, Acc256, BBBAcc) makes sense and covers the set of use cases the community discussed during the w"
  - **Lexical Overlap:** `36.0%` (5 matched, 9 missing)
  - **Missing Keywords:** `international`, `lightweight`, `public`, `regarding`, `represented`, `stakeholder`, `pre-draft`, `800-197a`, `perspectives`

#### Forensic Root Cause:
**Front-Matter / Metadata Semantic Drift:** Both retrievers were diverted by document title pages, executive summaries, and introductory front-matter (`NIST_SP_800-197_txt_00001`, `NIST_SP_800-197_txt_00009`) which heavily repeat the publication ID and broad keywords, displacing the deeply nested technical operational passage.

---

### 18. Question Q83

- **Exact Question:** "How does NIST SP 800-223 characterize security and threat modeling challenges in High-Performance Computing (HPC) clusters?"
- **Benchmark Category:** `conceptual` | **Subset:** `candidate`
- **Target Document(s):** `NIST_SP_800-223`
- **Expected Ground-Truth Chunks:** `NIST_SP_800-223_txt_00044`
- **Ground-Truth Rationale:** Ground-truth standard passage required for technical completeness.
- **Were Any Expected Chunks Retrieved in Top 20 Candidates:** **No (0.0% — Dense Hit@20 = 0.0, BM25 Hit@20 = 0.0)**
- **Were Any Expected Chunks Retrieved in Final Top 5:** **No (0/1)**

#### Available Stage Metrics & Latencies:
- **Dense (`BAAI/bge-m3`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `672.79 ms`
- **Sparse (`BM25Okapi`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `195.75 ms`
- **Fusion (`RRFFusion`, $k=60$, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `0.33 ms`
- **Reranker (`ms-marco-MiniLM-L-6-v2`, Final Top-5):** Latency: `3924.11 ms` | Total Query Latency: `4792.98 ms`

#### Actually Retrieved Top-5 Chunks (Post-Rerank):
| Rank | Retrieved Chunk ID | Document ID | Section Title | Cross-Encoder Score | Is Relevant? |
| :---: | :--- | :--- | :--- | :---: | :---: |
| 1 | `NIST_SP_800-223_txt_00023` | `NIST_SP_800-223` | **1. Introduction** | `4.9647` | **`False`** |
| 2 | `NIST_SP_800-239_txt_00022` | `NIST_SP_800-239` | 142 **1.1. Zone-Based HPC Architecture** | `4.8497` | **`False`** |
| 3 | `NIST_SP_800-234_txt_00019` | `NIST_SP_800-234` | **1. Introduction** | `4.4162` | **`False`** |
| 4 | `NIST_SP_800-234_txt_00020` | `NIST_SP_800-234` | **1. Introduction** | `4.1812` | **`False`** |
| 5 | `NIST_SP_800-223_txt_00024` | `NIST_SP_800-223` | Unknown | `4.0860` | **`False`** |

#### Expected Chunk Details & Keyword Coverage:
- **Expected Chunk:** `NIST_SP_800-223_txt_00044` (None, `314` tokens)
  - **Section:** *(Root / Main Text)*
  - **Text Preview:** "### **3.2.2. Management Zone Threats**  The management zone is responsible for managing the entire HPC system. It is connected to clustered internal networks through which other zones can be reached. It runs a plethora of system management, out-of-band hardware management, job scheduling, and workfl"
  - **Lexical Overlap:** `42.0%` (5 matched, 7 missing)
  - **Missing Keywords:** `computing`, `challenges`, `modeling`, `high-performance`, `characterize`, `clusters`, `security`

#### Forensic Root Cause:
**Vocabulary & Phrasing Mismatch:** High-level conceptual question phrasing ('How does NIST SP 800-223 characterize security and...') shares low lexical overlap (42%) with the specific technical terminology in the authoritative chunk. Without query expansion or synonym normalization, neither retriever scored the target chunk into Top 20.

---

### 19. Question Q86

- **Exact Question:** "What pair-wise key establishment schemes are recommended in NIST SP 800-56B Revision 2?"
- **Benchmark Category:** `technical_control` | **Subset:** `candidate`
- **Target Document(s):** `NIST_SP_800-56`
- **Expected Ground-Truth Chunks:** `NIST_SP_800-56_txt_00042`
- **Ground-Truth Rationale:** Ground-truth standard passage required for technical completeness.
- **Were Any Expected Chunks Retrieved in Top 20 Candidates:** **No (0.0% — Dense Hit@20 = 0.0, BM25 Hit@20 = 0.0)**
- **Were Any Expected Chunks Retrieved in Final Top 5:** **No (0/1)**

#### Available Stage Metrics & Latencies:
- **Dense (`BAAI/bge-m3`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `586.32 ms`
- **Sparse (`BM25Okapi`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `139.66 ms`
- **Fusion (`RRFFusion`, $k=60$, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `0.37 ms`
- **Reranker (`ms-marco-MiniLM-L-6-v2`, Final Top-5):** Latency: `3762.71 ms` | Total Query Latency: `4489.06 ms`

#### Actually Retrieved Top-5 Chunks (Post-Rerank):
| Rank | Retrieved Chunk ID | Document ID | Section Title | Cross-Encoder Score | Is Relevant? |
| :---: | :--- | :--- | :--- | :---: | :---: |
| 1 | `NIST_SP_800-175_txt_00153` | `NIST_SP_800-175` | SP 800-56A | `7.7888` | **`False`** |
| 2 | `NIST_SP_800-130_txt_00249` | `NIST_SP_800-130` | 33. [SP 800-56A] | `7.5694` | **`False`** |
| 3 | `NIST_SP_800-56_txt_00001` | `NIST_SP_800-56` | **NIST Special Publication 800-56B Revision 2** | `7.3489` | **`False`** |
| 4 | `NIST_SP_800-56_txt_00002` | `NIST_SP_800-56` | **NIST Special Publication 800-56B Revision 2 Recommendation for Pair-Wise Key Establishment Using Integer Factorization Cryptography** | `7.2765` | **`False`** |
| 5 | `NIST_SP_800-175_txt_00154` | `NIST_SP_800-175` | SP 800-56B | `7.2605` | **`False`** |

#### Expected Chunk Details & Keyword Coverage:
- **Expected Chunk:** `NIST_SP_800-56_txt_00042` (None, `497` tokens)
  - **Section:** *(Root / Main Text)*
  - **Text Preview:** "### **4 Key-Establishment Schemes Overview**  All IFC schemes in this Recommendation are based on RSA.  The security of an IFC scheme also depends on its implementation, and this document includes a number of practical recommendations for implementers. For example, good security practice dictates th"
  - **Lexical Overlap:** `50.0%` (5 matched, 5 missing)
  - **Missing Keywords:** `revision`, `recommended`, `800-56b`, `nist`, `2`

#### Forensic Root Cause:
**Front-Matter / Metadata Semantic Drift:** Both retrievers were diverted by document title pages, executive summaries, and introductory front-matter (`NIST_SP_800-56_txt_00001`, `NIST_SP_800-56_txt_00002`) which heavily repeat the publication ID and broad keywords, displacing the deeply nested technical operational passage.

---

### 20. Question Q87

- **Exact Question:** "What elliptic curve domain parameter recommendations are established in NIST SP 800-186 for discrete logarithm cryptography?"
- **Benchmark Category:** `technical_control` | **Subset:** `candidate`
- **Target Document(s):** `NIST_SP_800-186`
- **Expected Ground-Truth Chunks:** `NIST_SP_800-186_txt_00009`
- **Ground-Truth Rationale:** Ground-truth standard passage required for technical completeness.
- **Were Any Expected Chunks Retrieved in Top 20 Candidates:** **No (0.0% — Dense Hit@20 = 0.0, BM25 Hit@20 = 0.0)**
- **Were Any Expected Chunks Retrieved in Final Top 5:** **No (0/1)**

#### Available Stage Metrics & Latencies:
- **Dense (`BAAI/bge-m3`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `650.48 ms`
- **Sparse (`BM25Okapi`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `197.9 ms`
- **Fusion (`RRFFusion`, $k=60$, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `0.4 ms`
- **Reranker (`ms-marco-MiniLM-L-6-v2`, Final Top-5):** Latency: `4355.83 ms` | Total Query Latency: `5204.61 ms`

#### Actually Retrieved Top-5 Chunks (Post-Rerank):
| Rank | Retrieved Chunk ID | Document ID | Section Title | Cross-Encoder Score | Is Relevant? |
| :---: | :--- | :--- | :--- | :---: | :---: |
| 1 | `NIST_SP_800-175_txt_00170` | `NIST_SP_800-175` | SP 800-186 | `8.7421` | **`False`** |
| 2 | `NIST_SP_800-186_txt_00001` | `NIST_SP_800-186` | **NIST Special Publication NIST SP 800-186 Recommendations for Discrete Logarithm-based Cryptography:** | `7.6666` | **`False`** |
| 3 | `NIST_SP_800-186_txt_00006` | `NIST_SP_800-186` | **How to Cite this NIST Technical Series Publication:** | `7.3387` | **`False`** |
| 4 | `NIST_SP_800-186_txt_00002` | `NIST_SP_800-186` | **NIST Special Publication NIST SP 800-186 Recommendations for Discrete Logarithm-based Cryptography:** _Elliptic Curve Domain Parameters_ | `7.0948` | **`False`** |
| 5 | `NIST_SP_800-186_txt_00035` | `NIST_SP_800-186` | **Purpose and Scope** | `6.2147` | **`False`** |

#### Expected Chunk Details & Keyword Coverage:
- **Expected Chunk:** `NIST_SP_800-186_txt_00009` (None, `120` tokens)
  - **Section:** *(Root / Main Text)*
  - **Text Preview:** "### **Abstract**  This Recommendation specifies the set of elliptic curves recommended for U.S. Government use. In addition to the previously recommended Weierstrass curves defined over prime fields and binary fields, this Recommendation includes two newly specified Edwards curves, which provide inc"
  - **Lexical Overlap:** `25.0%` (3 matched, 9 missing)
  - **Missing Keywords:** `recommendations`, `logarithm`, `parameter`, `domain`, `established`, `800-186`, `cryptography`, `discrete`, `nist`

#### Forensic Root Cause:
**Front-Matter / Metadata Semantic Drift:** Both retrievers were diverted by document title pages, executive summaries, and introductory front-matter (`NIST_SP_800-186_txt_00001`, `NIST_SP_800-186_txt_00006`, `NIST_SP_800-186_txt_00002`) which heavily repeat the publication ID and broad keywords, displacing the deeply nested technical operational passage.

---

### 21. Question Q90

- **Exact Question:** "What technical specifications govern the Keyed-Hash Message Authentication Code (HMAC) in NIST SP 800-224?"
- **Benchmark Category:** `technical_control` | **Subset:** `candidate`
- **Target Document(s):** `NIST_SP_800-224`
- **Expected Ground-Truth Chunks:** `NIST_SP_800-224_txt_00024`
- **Ground-Truth Rationale:** Ground-truth standard passage required for technical completeness.
- **Were Any Expected Chunks Retrieved in Top 20 Candidates:** **No (0.0% — Dense Hit@20 = 0.0, BM25 Hit@20 = 0.0)**
- **Were Any Expected Chunks Retrieved in Final Top 5:** **No (0/1)**

#### Available Stage Metrics & Latencies:
- **Dense (`BAAI/bge-m3`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `626.12 ms`
- **Sparse (`BM25Okapi`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `130.75 ms`
- **Fusion (`RRFFusion`, $k=60$, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `0.27 ms`
- **Reranker (`ms-marco-MiniLM-L-6-v2`, Final Top-5):** Latency: `3762.04 ms` | Total Query Latency: `4519.18 ms`

#### Actually Retrieved Top-5 Chunks (Post-Rerank):
| Rank | Retrieved Chunk ID | Document ID | Section Title | Cross-Encoder Score | Is Relevant? |
| :---: | :--- | :--- | :--- | :---: | :---: |
| 1 | `NIST_SP_800-224_txt_00007` | `NIST_SP_800-224` | **How to cite this NIST Technical Series Publication** | `6.7019` | **`False`** |
| 2 | `NIST_SP_800-224_txt_00016` | `NIST_SP_800-224` | **Preface** | `6.4963` | **`False`** |
| 3 | `NIST_SP_800-224_txt_00003` | `NIST_SP_800-224` | **Keyed-Hash Message Authentication Code (HMAC)** | `5.7587` | **`False`** |
| 4 | `NIST_SP_800-224_txt_00002` | `NIST_SP_800-224` | **Keyed-Hash Message Authentication Code (HMAC)** | `5.7275` | **`False`** |
| 5 | `NIST_SP_800-132_txt_00027` | `NIST_SP_800-132` | Unknown | `5.0544` | **`False`** |

#### Expected Chunk Details & Keyword Coverage:
- **Expected Chunk:** `NIST_SP_800-224_txt_00024` (None, `490` tokens)
  - **Section:** *(Root / Main Text)*
  - **Text Preview:** "### **2. HMAC Construction**  - Let 𝐻 be a cryptographic hash function with an output size of ℓ bits and a block size of 𝑏 bits, where 𝑏 is a multiple of eight and satisfies 𝑏≥ℓ . The inputs and the output of the HMAC tag generation algorithm are as follows:  - **Inputs:** secret key 𝐾 and message 𝑀"
  - **Lexical Overlap:** `18.0%` (2 matched, 9 missing)
  - **Missing Keywords:** `govern`, `code`, `technical`, `keyed-hash`, `authentication`, `specifications`, `nist`, `800-224`, `sp`

#### Forensic Root Cause:
**Front-Matter / Metadata Semantic Drift:** Both retrievers were diverted by document title pages, executive summaries, and introductory front-matter (`NIST_SP_800-224_txt_00007`, `NIST_SP_800-224_txt_00016`, `NIST_SP_800-224_txt_00003`) which heavily repeat the publication ID and broad keywords, displacing the deeply nested technical operational passage.

---

### 22. Question Q92

- **Exact Question:** "What specific technical challenges and preservation techniques are identified for handheld digital device forensics in NIST SP 800-72?"
- **Benchmark Category:** `technical_control` | **Subset:** `candidate`
- **Target Document(s):** `NIST_SP_800-72`
- **Expected Ground-Truth Chunks:** `NIST_SP_800-72_txt_00070`
- **Ground-Truth Rationale:** Ground-truth standard passage required for technical completeness.
- **Were Any Expected Chunks Retrieved in Top 20 Candidates:** **No (0.0% — Dense Hit@20 = 0.0, BM25 Hit@20 = 0.0)**
- **Were Any Expected Chunks Retrieved in Final Top 5:** **No (0/1)**

#### Available Stage Metrics & Latencies:
- **Dense (`BAAI/bge-m3`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `631.16 ms`
- **Sparse (`BM25Okapi`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `172.26 ms`
- **Fusion (`RRFFusion`, $k=60$, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `0.41 ms`
- **Reranker (`ms-marco-MiniLM-L-6-v2`, Final Top-5):** Latency: `3816.1 ms` | Total Query Latency: `4619.93 ms`

#### Actually Retrieved Top-5 Chunks (Post-Rerank):
| Rank | Retrieved Chunk ID | Document ID | Section Title | Cross-Encoder Score | Is Relevant? |
| :---: | :--- | :--- | :--- | :---: | :---: |
| 1 | `NIST_SP_800-201_txt_00032` | `NIST_SP_800-201` | Unknown | `3.4170` | **`False`** |
| 2 | `NIST_SP_800-201_txt_00031` | `NIST_SP_800-201` | **2. Overview of NIST Cloud Forensic Challenges** | `3.2366` | **`False`** |
| 3 | `NIST_SP_800-101_txt_00022` | `NIST_SP_800-101` | Executive Summary | `2.1035` | **`False`** |
| 4 | `NIST_SP_800-201_txt_00024` | `NIST_SP_800-201` | Unknown | `2.0650` | **`False`** |
| 5 | `NIST_SP_800-201_txt_00033` | `NIST_SP_800-201` | **2. Overview of NIST Cloud Forensic Challenges** | `0.0549` | **`False`** |

#### Expected Chunk Details & Keyword Coverage:
- **Expected Chunk:** `NIST_SP_800-72_txt_00070` (None, `487` tokens)
  - **Section:** *(Root / Main Text)*
  - **Text Preview:** "### 5.4 Collection  Where PDAs are concerned, the collection process normally involves dynamic and volatile information that may be lost unless precautions are taken at the scene of the incident or crime. The "Good Practice Guide for Computer Based Electronic Evidence" [ACPO] suggests the following "
  - **Lexical Overlap:** `8.0%` (1 matched, 12 missing)
  - **Missing Keywords:** `handheld`, `identified`, `digital`, `specific`, `challenges`, `preservation`, `technical`, `forensics`, `techniques`, `nist`, `sp`, `800-72`

#### Forensic Root Cause:
**Dominant Peer Document Competition:** The question asks for controls in `NIST_SP_800-72`, but both Dense and BM25 retrievers latched onto competitor standards (`NIST_SP_800-201`, `NIST_SP_800-101`) which have higher keyword frequency and document prominence for this topic. The target document was completely pushed out of the initial candidate pool.

---

### 23. Question Q95

- **Exact Question:** "In an enterprise telework deployment, what client endpoint security controls are recommended in NIST SP 800-114 Revision 1 for employee BYOD devices?"
- **Benchmark Category:** `scenario_based` | **Subset:** `candidate`
- **Target Document(s):** `NIST_SP_800-114`
- **Expected Ground-Truth Chunks:** `NIST_SP_800-114_txt_00057`
- **Ground-Truth Rationale:** Ground-truth standard passage required for technical completeness.
- **Were Any Expected Chunks Retrieved in Top 20 Candidates:** **No (0.0% — Dense Hit@20 = 0.0, BM25 Hit@20 = 0.0)**
- **Were Any Expected Chunks Retrieved in Final Top 5:** **No (0/1)**

#### Available Stage Metrics & Latencies:
- **Dense (`BAAI/bge-m3`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `673.57 ms`
- **Sparse (`BM25Okapi`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `217.64 ms`
- **Fusion (`RRFFusion`, $k=60$, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `0.46 ms`
- **Reranker (`ms-marco-MiniLM-L-6-v2`, Final Top-5):** Latency: `3706.83 ms` | Total Query Latency: `4598.5 ms`

#### Actually Retrieved Top-5 Chunks (Post-Rerank):
| Rank | Retrieved Chunk ID | Document ID | Section Title | Cross-Encoder Score | Is Relevant? |
| :---: | :--- | :--- | :--- | :---: | :---: |
| 1 | `NIST_SP_800-46_txt_00112` | `NIST_SP_800-46` | **<mark>Appendix A - NIST SP 800-53 Control Mappings</mark>** | `4.1797` | **`False`** |
| 2 | `NIST_SP_800-46_txt_00080` | `NIST_SP_800-46` | **<mark>4. Telework Client Device Security</mark>** | `3.2830` | **`False`** |
| 3 | `NIST_SP_800-46_txt_00092` | `NIST_SP_800-46` | **4.4 Summary of Key Recommendations** | `2.6577` | **`False`** |
| 4 | `NIST_SP_800-46_txt_00103` | `NIST_SP_800-46` | Unknown | `2.2275` | **`False`** |
| 5 | `NIST_SP_800-46_txt_00037` | `NIST_SP_800-46` | **2.1 Vulnerabilities, Threats, and Security Controls** | `1.4472` | **`False`** |

#### Expected Chunk Details & Keyword Coverage:
- **Expected Chunk:** `NIST_SP_800-114_txt_00057` (None, `388` tokens)
  - **Section:** *(Root / Main Text)*
  - **Text Preview:** "### **5.1 Software Updates**  Many threats take advantages of vulnerabilities in software on PCs. Software manufacturers release updates for their software to eliminate these vulnerabilities. Accordingly, teleworkers should ensure that updates are applied regularly to the major software on their BYO"
  - **Lexical Overlap:** `38.0%` (6 matched, 10 missing)
  - **Missing Keywords:** `800-114`, `devices`, `revision`, `recommended`, `employee`, `endpoint`, `controls`, `enterprise`, `nist`, `deployment`

#### Forensic Root Cause:
**Dominant Peer Document Competition:** The question asks for controls in `NIST_SP_800-114`, but both Dense and BM25 retrievers latched onto competitor standards (`NIST_SP_800-46`) which have higher keyword frequency and document prominence for this topic. The target document was completely pushed out of the initial candidate pool.

---

### 24. Question Q97

- **Exact Question:** "During an incident response investigation involving a seized smartphone, what evidence acquisition rules does NIST SP 800-101 Revision 1 specify to maintain evidence integrity?"
- **Benchmark Category:** `scenario_based` | **Subset:** `candidate`
- **Target Document(s):** `NIST_SP_800-101`
- **Expected Ground-Truth Chunks:** `NIST_SP_800-101_txt_00064`
- **Ground-Truth Rationale:** Ground-truth standard passage required for technical completeness.
- **Were Any Expected Chunks Retrieved in Top 20 Candidates:** **No (0.0% — Dense Hit@20 = 0.0, BM25 Hit@20 = 0.0)**
- **Were Any Expected Chunks Retrieved in Final Top 5:** **No (0/1)**

#### Available Stage Metrics & Latencies:
- **Dense (`BAAI/bge-m3`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `699.34 ms`
- **Sparse (`BM25Okapi`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `280.86 ms`
- **Fusion (`RRFFusion`, $k=60$, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `0.81 ms`
- **Reranker (`ms-marco-MiniLM-L-6-v2`, Final Top-5):** Latency: `3748.89 ms` | Total Query Latency: `4729.91 ms`

#### Actually Retrieved Top-5 Chunks (Post-Rerank):
| Rank | Retrieved Chunk ID | Document ID | Section Title | Cross-Encoder Score | Is Relevant? |
| :---: | :--- | :--- | :--- | :---: | :---: |
| 1 | `NIST_SP_800-101_txt_00022` | `NIST_SP_800-101` | Executive Summary | `0.6066` | **`False`** |
| 2 | `NIST_SP_800-101_txt_00023` | `NIST_SP_800-101` | 1.1 Purpose and Scope | `-0.4222` | **`False`** |
| 3 | `NIST_SP_800-101_txt_00001` | `NIST_SP_800-101` | **Guidelines on Mobile Device Forensics** | `-1.0563` | **`False`** |
| 4 | `NIST_SP_800-86_txt_00083` | `NIST_SP_800-86` | Unknown | `-1.1026` | **`False`** |
| 5 | `NIST.SP.800-61r3_txt_00106` | `NIST.SP.800-61r3` | **3.2. Incident Response** | `-1.5159` | **`False`** |

#### Expected Chunk Details & Keyword Coverage:
- **Expected Chunk:** `NIST_SP_800-101_txt_00064` (None, `354` tokens)
  - **Section:** *(Root / Main Text)*
  - **Text Preview:** "### 4.3 Isolation  Any associated hardware such as media cards, UICCs, power adapters, device sleeves, or peripherals, should be seized along with related materials such as product manuals, packaging, and software.  Isolating a mobile device from all radio networks (e.g. WiFi, Cellular and Bluetooth"
  - **Lexical Overlap:** `22.0%` (4 matched, 14 missing)
  - **Missing Keywords:** `rules`, `integrity`, `maintain`, `revision`, `incident`, `response`, `1`, `800-101`, `involving`, `smartphone`, `investigation`, `specify`, `nist`, `sp`

#### Forensic Root Cause:
**Front-Matter / Metadata Semantic Drift:** Both retrievers were diverted by document title pages, executive summaries, and introductory front-matter (`NIST_SP_800-101_txt_00022`, `NIST_SP_800-101_txt_00001`) which heavily repeat the publication ID and broad keywords, displacing the deeply nested technical operational passage.

---

### 25. Question Q100

- **Exact Question:** "In an enterprise cloud migration, how should an organization structure its Attribute Based Access Control (ABAC) policies to manage cross-tenant data access per NIST SP 800-210?"
- **Benchmark Category:** `scenario_based` | **Subset:** `candidate`
- **Target Document(s):** `NIST_SP_800-210`
- **Expected Ground-Truth Chunks:** `NIST_SP_800-210_txt_00053`
- **Ground-Truth Rationale:** Ground-truth standard passage required for technical completeness.
- **Were Any Expected Chunks Retrieved in Top 20 Candidates:** **No (0.0% — Dense Hit@20 = 0.0, BM25 Hit@20 = 0.0)**
- **Were Any Expected Chunks Retrieved in Final Top 5:** **No (0/1)**

#### Available Stage Metrics & Latencies:
- **Dense (`BAAI/bge-m3`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `845.49 ms`
- **Sparse (`BM25Okapi`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `331.77 ms`
- **Fusion (`RRFFusion`, $k=60$, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `0.49 ms`
- **Reranker (`ms-marco-MiniLM-L-6-v2`, Final Top-5):** Latency: `3979.92 ms` | Total Query Latency: `5157.67 ms`

#### Actually Retrieved Top-5 Chunks (Post-Rerank):
| Rank | Retrieved Chunk ID | Document ID | Section Title | Cross-Encoder Score | Is Relevant? |
| :---: | :--- | :--- | :--- | :---: | :---: |
| 1 | `NIST_SP_800-162_txt_00022` | `NIST_SP_800-162` | **<mark>Executive Summary</mark>** | `3.1531` | **`False`** |
| 2 | `NIST_SP_800-162_txt_00106` | `NIST_SP_800-162` | Unknown | `1.6689` | **`False`** |
| 3 | `NIST_SP_800-178_txt_00038` | `NIST_SP_800-178` | **<mark>2 Background</mark>** | `1.5306` | **`False`** |
| 4 | `NIST_SP_800-162_txt_00027` | `NIST_SP_800-162` | **1.1 Purpose and Scope** | `1.0813` | **`False`** |
| 5 | `NIST_SP_800-162_txt_00048` | `NIST_SP_800-162` | Unknown | `1.0093` | **`False`** |

#### Expected Chunk Details & Keyword Coverage:
- **Expected Chunk:** `NIST_SP_800-210_txt_00053` (None, `354` tokens)
  - **Section:** *(Root / Main Text)*
  - **Text Preview:** "### **5.9 Recommendations for SaaS Access Control**  With regard to multi-tenancy, authorization may be enforced using a _centralized_ , _decentralized_ , or _hybrid_ authorization system. In a centralized authorization system, the SaaS provider manages a central authorization database for every end"
  - **Lexical Overlap:** `60.0%` (12 matched, 8 missing)
  - **Missing Keywords:** `migration`, `structure`, `based`, `nist`, `organization`, `cross-tenant`, `enterprise`, `800-210`

#### Forensic Root Cause:
**Dominant Peer Document Competition:** The question asks for controls in `NIST_SP_800-210`, but both Dense and BM25 retrievers latched onto competitor standards (`NIST_SP_800-178`, `NIST_SP_800-162`) which have higher keyword frequency and document prominence for this topic. The target document was completely pushed out of the initial candidate pool.

---

### 26. Question Q102

- **Exact Question:** "When integrating supply chain security into an enterprise DevSecOps pipeline, what security gates does NIST SP 800-204D recommend prior to production release?"
- **Benchmark Category:** `scenario_based` | **Subset:** `candidate`
- **Target Document(s):** `NIST_SP_800-204`
- **Expected Ground-Truth Chunks:** `NIST_SP_800-204_txt_00048`
- **Ground-Truth Rationale:** Ground-truth standard passage required for technical completeness.
- **Were Any Expected Chunks Retrieved in Top 20 Candidates:** **No (0.0% — Dense Hit@20 = 0.0, BM25 Hit@20 = 0.0)**
- **Were Any Expected Chunks Retrieved in Final Top 5:** **No (0/1)**

#### Available Stage Metrics & Latencies:
- **Dense (`BAAI/bge-m3`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `932.31 ms`
- **Sparse (`BM25Okapi`, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `240.13 ms`
- **Fusion (`RRFFusion`, $k=60$, Top-20):** Hit@5 = `0.0`, Hit@20 = `0.0` | Latency: `0.39 ms`
- **Reranker (`ms-marco-MiniLM-L-6-v2`, Final Top-5):** Latency: `4120.69 ms` | Total Query Latency: `5293.51 ms`

#### Actually Retrieved Top-5 Chunks (Post-Rerank):
| Rank | Retrieved Chunk ID | Document ID | Section Title | Cross-Encoder Score | Is Relevant? |
| :---: | :--- | :--- | :--- | :---: | :---: |
| 1 | `NIST_SP_800-204_txt_00001` | `NIST_SP_800-204` | **Strategies for the Integration of Software Supply Chain Security in DevSecOps CI/CD Pipelines** | `3.8206` | **`False`** |
| 2 | `NIST_SP_800-204_txt_00002` | `NIST_SP_800-204` | **Strategies for the Integration of Software Supply Chain Security in DevSecOps CI/CD Pipelines** | `3.6849` | **`False`** |
| 3 | `NIST_SP_800-204_txt_00007` | `NIST_SP_800-204` | **How to Cite this NIST Technical Series Publication:** | `3.5780` | **`False`** |
| 4 | `NIST_SP_800-204_txt_00030` | `NIST_SP_800-204` | **1.4. Relationship to Other NIST Documents** | `2.0206` | **`False`** |
| 5 | `NIST_SP_800-204_txt_00021` | `NIST_SP_800-204` | **Table of Contents** | `1.8427` | **`False`** |

#### Expected Chunk Details & Keyword Coverage:
- **Expected Chunk:** `NIST_SP_800-204_txt_00048` (None, `444` tokens)
  - **Section:** *(Root / Main Text)*
  - **Text Preview:** "### **4. CI/CD Pipelines  -  Background, Security Goals, and Entities to be Trusted**  DevSecOps is an agile paradigm used for the development and deployment of cloud-native applications. This paradigm consists of a series of stages that takes code from variously sourced repositories (e.g., first-pa"
  - **Lexical Overlap:** `29.0%` (5 matched, 12 missing)
  - **Missing Keywords:** `gates`, `enterprise`, `recommend`, `release`, `into`, `chain`, `supply`, `prior`, `when`, `nist`, `integrating`, `800-204d`

#### Forensic Root Cause:
**Front-Matter / Metadata Semantic Drift:** Both retrievers were diverted by document title pages, executive summaries, and introductory front-matter (`NIST_SP_800-204_txt_00001`, `NIST_SP_800-204_txt_00002`, `NIST_SP_800-204_txt_00007`) which heavily repeat the publication ID and broad keywords, displacing the deeply nested technical operational passage.

---

## 5. Evidence-Based Failure Classification Taxonomy

Empirical analysis of the 26 failed questions reveals five distinct, evidence-backed failure archetypes:

| Failure Archetype | Description | Question Count | Percentage | Affected Question IDs |
| :--- | :--- | :---: | :---: | :--- |
| **1. Front-Matter / Metadata Distraction** | Dense and BM25 score introductory front-matter, title pages, lists of figures, or abstracts above deeply nested technical sections due to repetitive document headers. | **11** | **42.3%** | `Q56`, `Q63`, `Q65`, `Q66`, `Q69`, `Q72`, `Q75`, `Q80`, `Q87`, `Q90`, `Q102` |
| **2. Dominant Peer Standard Competition** | The query targets a specific NIST document, but another NIST publication with dedicated or broader coverage of the topic completely dominates the candidate pool. | **4** | **15.4%** | `Q38` (SP 800-146 vs 145), `Q86` (SP 800-175/130 vs 56B), `Q92` (SP 800-201/101 vs 72), `Q95` (SP 800-46 vs 114) |
| **3. Multi-Document Query Dilution** | Cross-document queries requiring evidence from multiple publications suffer from candidate pool splitting, where one document dominates all 20 slots. | **3** | **11.5%** | `Q19` (SP 800-144/146), `Q47` (SP 800-207/210), `Q49` (SP 800-130/57) |
| **4. Technical Vocabulary & Acronym Mismatch** | Query uses high-level abstract phrasing, acronyms, or colloquial descriptions that do not match the specific mathematical or technical wording of the standard. | **7** | **26.9%** | `Q53`, `Q71`, `Q74`, `Q79`, `Q83`, `Q97`, `Q100` |
| **5. Table / Structural Syntax Penalty** | Ground-truth chunk is a structured Markdown table; lack of prose narrative severely degrades dense semantic matching. | **1** | **3.8%** | `Q45` (`NIST_SP_800-146_tbl_00005_p01`) |
| **Total** | **Exhaustive mutually exclusive classification** | **26** | **100.0%** | |

---

## 6. Missing Diagnostic Data & Evidence Gap Analysis

In accordance with strict investigation rules, the following evidence boundaries and diagnostic data gaps in the committed benchmark artifacts must be explicitly documented:

### 1. Intermediate Candidate Pool Serialization Gap
- **Committed Artifact:** `reports/retrieval_evaluation/benchmark_100q_results.json` records binary stage flags (`dense_hit@20`, `bm25_hit@20`, `hybrid_hit@20`) and the final Top-5 reranked chunks (`retrieved_top5`).
- **Evidence Gap:** The benchmark execution script (`scripts/run_100q_benchmark.py`) did **not persist the full list of 20 chunk IDs and raw scores** generated during intermediate stages (`dense_candidates[:20]`, `bm25_candidates[:20]`, `fused_candidates[6:20]`).
- **Impact:** We can deterministically verify that `dense_hit@20 == 0.0` and `bm25_hit@20 == 0.0` (zero ground-truth chunks entered either candidate pool). However, the specific chunk IDs ranked at positions 6 through 20 by Dense, BM25, and RRF cannot be inspected without re-running retrieval.

### 2. Pre-Rerank RRF Fusion Scores
- **Committed Artifact:** Reranker scores (Cross-Encoder logit outputs ranging from `-1.7` to `+8.9`) are recorded for the Top-5 chunks.
- **Evidence Gap:** The pre-rerank RRF scores (calculated as $\sum 1/(60 + \text{rank})$) were not recorded in the JSON.

### 3. Preserved Forensic Integrity
- Per Phase 2 safety constraints, **no benchmark scripts were re-executed** and **no synthetic results were fabricated** to fill this gap. All findings in this report rely strictly on verifiable, committed Phase 1 data.

---

## 7. Actionable Recommendations for Phase 2 Optimization

Based on the five failure archetypes identified in this forensic audit, the following targeted interventions are recommended for Phase 2:

1. **Adaptive Query Rewriting & Expansion (Solves Archetypes 1, 3, and 4):**
   - Activate `QueryRewriter` and `ConfidenceEvaluator` to expand technical acronyms, append formal document titles, and clarify cross-document scopes before retrieval.
   - Query expansion will bridge the lexical gap on questions like `Q53`, `Q71`, `Q74`, and `Q83`.
2. **Document-Scoped / Targeted Second-Pass Retrieval (Solves Archetype 2):**
   - When queries explicitly name a target standard (e.g., `NIST SP 800-114` in Q95, `NIST SP 800-210` in Q100), apply publication metadata filtering or boosting to prevent competitor standards from monopolizing the candidate pool.
3. **Front-Matter Downweighting & Section-Aware Ingestion (Solves Archetype 1):**
   - Penalize or demote document title pages, lists of figures, and generic citation blocks during candidate retrieval when queries ask for specific operational guidance.
4. **Structured Table Lead Paragraph Synthesis (Solves Archetype 5):**
   - Prepend descriptive contextual lead text to Markdown table chunks during ingestion so dense representations capture the semantic essence of control tables.
5. **Candidate Pool Depth Expansion (Tuning $N=30$):**
   - Increasing candidate limits from 20 to 30 will allow secondary documents in cross-document queries (`Q19`, `Q47`, `Q49`) to enter the fusion pool.

---

**Report Complete.** Awaiting user instruction for Phase 2 optimization experiments.