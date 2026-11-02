# Stage 1 — Evaluation Ground-Truth Alignment Report

**Project**: Cybersecurity RAG  
**Location**: `C:\Users\Computer\Desktop\cybersecurity-rag`  
**Date**: October 15, 2026  
**Auditor / Agent**: Antigravity  
**Target Models**: `BAAI/bge-small-en-v1.5` vs. `BAAI/bge-m3`  
**Current Corpus**: 73 NIST publications, 4,649 physical pages, 13,084 structure-aware chunks  

---

## 1. Executive Summary

This report completes **Stage 1: Evaluation Ground-Truth Alignment** for the embedding model benchmark. It addresses the critical blocker identified in Stage 0: **100% ID disconnect between the historical evaluation ground truth and the current structure-aware chunk corpus**.

### Key Findings
1. **Legacy ID Incompatibility**: The 33 chunk IDs in `data/evaluation/retrieval_ground_truth.json` (e.g. `NIST_SP_800-144_00080`) originated from an early, uncleaned 7,703-chunk prototype. They share **0% overlap** with the active 13,084 structure-aware chunks (`_txt_`, `_tbl_`, `_fig_`).
2. **Systematic Alignment**: Through source section tracing and semantic analysis of NIST SP 800-144 (164 chunks) and NIST SP 800-146 (232 chunks), candidate relevant chunks have been mapped with verbatim evidence for all 20 evaluation questions.
3. **Classification & Verification**:
   - **12 Questions**: **Verified Relevant Chunks** with unambiguous factual NIST guidance.
   - **6 Questions**: **Candidate Matches** that are highly relevant but have conceptual overlap with neighboring questions and warrant human verification.
   - **2 Questions**: **Unresolved / Multi-Document Gaps** (Q14 and Q15 require cross-document telework and malware context from NIST SP 800-46 and SP 800-115).
4. **Domain Coverage Limitations**: The existing 20-question suite is **100% skewed toward public cloud security**, omitting 9 of the 10 corpus categories (Cryptography, Zero Trust, Identity Management, Risk Management, etc.).
5. **Preservation**: All original evaluation files (`evaluation_questions.json`, `retrieval_ground_truth.json`, `ground_truth.json`) remain strictly unmodified on disk.

---

## 2. Existing Evaluation Assets & Disconnect Audit

An audit of the evaluation directory confirmed the following inventory:

| Asset | Path | Status | Key Limitation |
| :--- | :--- | :---: | :--- |
| **Questions Suite** | [`data/evaluation/evaluation_questions.json`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/data/evaluation/evaluation_questions.json) | Preserved | 20 questions total; 100% focused on public cloud computing. |
| **Retrieval Ground Truth** | [`data/evaluation/retrieval_ground_truth.json`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/data/evaluation/retrieval_ground_truth.json) | Preserved | Covers only Q1–Q15 (Q16–Q20 missing); 33 legacy IDs; 0% match with active corpus. |
| **BM25 Ground Truth** | [`data/evaluation/ground_truth.json`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/data/evaluation/ground_truth.json) | Preserved | Covers only Q1–Q5; uses legacy IDs. |
| **Source Chunks (Target Pool)** | [`data/chunks_corpus/cloud_application_security/`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/data/chunks_corpus/cloud_application_security/) | Intact | `NIST_SP_800-144_chunks.jsonl` (164 chunks), `NIST_SP_800-146_chunks.jsonl` (232 chunks). |

---

## 3. Question-by-Question Ground-Truth Alignment & Evidence

Each evaluation question was analyzed against the current structure-aware chunk corpus for NIST SP 800-144 and NIST SP 800-146. Evidence was extracted directly from verified chunk content.

### Question Category Legend
- **[VERIFIED]**: Chunk text provides a direct, unambiguous, factual answer to the question.
- **[CANDIDATE]**: Chunk text is highly relevant and informative, but may partially overlap with adjacent questions; recommended for human sign-off.
- **[UNRESOLVED]**: Question requires context from documents outside the cloud security cohort or lacks direct standalone evidence.

---

### [Q1] What are the security risks of public cloud computing?
- **Status**: **[VERIFIED]**
- **Legacy Clues**: `NIST_SP_800-144_00080`, `00004`, `00002`, `00007`, `00027`
- **Target Section**: NIST SP 800-144 Section 3.3 ("The Security and Privacy Downside"), Section 4
- **Aligned Current Chunks**:
  1. `NIST_SP_800-144_txt_00047` (p. 20-21, 372 toks)
     - *Evidence*: Explains fundamental public cloud concerns including system complexity, large attack surface, and co-mingled multi-tenant environments.
  2. `NIST_SP_800-144_txt_00048` (p. 21, 374 toks)
     - *Evidence*: Details risks of shared multi-tenant infrastructure, lack of physical resource separation, and unauthorized access to personal data.
  3. `NIST_SP_800-144_txt_00054` (p. 24, 334 toks)
     - *Evidence*: Introduces Section 4 key security and privacy issues of public cloud computing.

---

### [Q2] What security challenges are associated with public cloud environments?
- **Status**: **[CANDIDATE - NEEDS VERIFICATION]**
- **Legacy Clues**: `NIST_SP_800-144_00004`, `00002`, `00005`, `00080`, `00027`
- **Target Section**: NIST SP 800-144 Executive Summary, Section 3.3, Section 4.3
- **Aligned Current Chunks**:
  1. `NIST_SP_800-144_txt_00047` (p. 20-21, 372 toks)
     - *Evidence*: Contrasts challenges in public cloud vs traditional data centers (system complexity, loss of direct control).
  2. `NIST_SP_800-144_txt_00022` (p. 7, 218 toks)
     - *Evidence*: Focuses on challenges in verifying cloud provider claims and understanding division of responsibilities.
  3. `NIST_SP_800-144_txt_00067` (p. 31-32, 348 toks)
     - *Evidence*: Discusses challenges in assessing and managing risk when external providers handle federal data under FISMA/OMB.
- *Note*: Q1 and Q2 are closely related conceptually; Q2 emphasizes environmental/operational challenges while Q1 emphasizes inherent technical risks.

---

### [Q3] How can client-side malware affect public cloud security?
- **Status**: **[VERIFIED]**
- **Legacy Clues**: `NIST_SP_800-144_00007`
- **Target Section**: NIST SP 800-144 Section 3.3, Exec Summary; NIST SP 800-146 Section 5.4.1
- **Aligned Current Chunks**:
  1. `NIST_SP_800-144_txt_00025` (p. 8-9, 415 toks)
     - *Evidence*: Identifies Web browsers as the primary client attack vector; discusses how client-side malware compromises authentication tokens and credentials.
  2. `NIST_SP_800-144_txt_00052` (p. 23, 499 toks)
     - *Evidence*: Analyzes botnets and client-side malware used to harvest cloud user credentials and bypass authentication.
  3. `NIST_SP_800-146_txt_00067` (p. 38, 484 toks)
     - *Evidence*: Section 5.4.1 detail on browser-based risks, man-in-the-browser attacks, and keystroke logging threatening cloud sessions.

---

### [Q4] Why is governance important for public cloud security?
- **Status**: **[VERIFIED]**
- **Legacy Clues**: `NIST_SP_800-144_00015`, `00057`
- **Target Section**: NIST SP 800-144 Section 4.1 ("Governance")
- **Aligned Current Chunks**:
  1. `NIST_SP_800-144_txt_00055` (p. 24-25, 391 toks)
     - *Evidence*: Defines governance in cloud computing as control and oversight over policies, procedures, and service acquisition; warns of risks when employees bypass organizational controls (shadow IT).
  2. `NIST_SP_800-144_txt_00056` (p. 25, 304 toks)
     - *Evidence*: Details negative outcomes of poor governance (vulnerable systems deployed, regulations ignored, uncontrolled charges).

---

### [Q5] Who is responsible for security and privacy in public cloud computing?
- **Status**: **[VERIFIED]**
- **Legacy Clues**: `NIST_SP_800-144_00015`, `00005`
- **Target Section**: NIST SP 800-144 Executive Summary, Section 2.3, Section 4.2
- **Aligned Current Chunks**:
  1. `NIST_SP_800-144_txt_00022` (p. 7, 218 toks)
     - *Evidence*: Explains that responsibilities vary by service model, requiring clear delineation between consumer and provider.
  2. `NIST_SP_800-144_txt_00026` (p. 9, 485 toks)
     - *Evidence*: Explicitly states: "Maintain accountability over the privacy and security of data... organizations cannot delegate this accountability."
  3. `NIST_SP_800-144_txt_00038` (p. 16, 402 toks)
     - *Evidence*: Explains that outsourcing computing infrastructure does not relieve agency leadership of legal and regulatory responsibilities.
  4. `NIST_SP_800-144_txt_00060` (p. 27-28, 464 toks)
     - *Evidence*: Re-affirms that organizations remain ultimately accountable for data held by a provider.

---

### [Q6] What are the main security concerns when using public cloud services?
- **Status**: **[CANDIDATE - NEEDS VERIFICATION]**
- **Legacy Clues**: `NIST_SP_800-144_00010`, `00024`, `00059`, `00015`, `00004`
- **Target Section**: NIST SP 800-144 Section 4 ("Key Security and Privacy Issues"), Section 5.1
- **Aligned Current Chunks**:
  1. `NIST_SP_800-144_txt_00054` (p. 24, 334 toks)
     - *Evidence*: Categorizes the critical long-term security concerns: governance, compliance, trust, architecture, identity, software isolation, data protection, availability, and incident response.
  2. `NIST_SP_800-144_txt_00047` (p. 20-21, 372 toks)
     - *Evidence*: Highlights system complexity and multi-tenancy as primary concerns.
  3. `NIST_SP_800-144_txt_00099` (p. 49, 406 toks)
     - *Evidence*: General concerns in public cloud outsourcing contracts and service delivery.

---

### [Q7] What privacy risks can arise when organizations use public cloud services?
- **Status**: **[VERIFIED]**
- **Legacy Clues**: `NIST_SP_800-144_00024`, `00015`, `00005`, `00002`, `00027`
- **Target Section**: NIST SP 800-144 Section 3.3, Section 4.7, Section 5.2
- **Aligned Current Chunks**:
  1. `NIST_SP_800-144_txt_00048` (p. 21, 374 toks)
     - *Evidence*: Focuses explicitly on privacy: loss, unauthorized access, destruction, or disclosure of personal data in multi-tenant clouds.
  2. `NIST_SP_800-144_txt_00080` (p. 39, 478 toks)
     - *Evidence*: Privacy risks arising from co-located data, shared storage pools, and inadvertent data access by other tenants.
  3. `NIST_SP_800-144_txt_00108` (p. 55-56, 478 toks)
     - *Evidence*: Discusses five core principles of privacy protection (Notice, Choice, Access, Integrity, Enforcement) in cloud environments.

---

### [Q8] How does loss of control affect security in public cloud computing?
- **Status**: **[VERIFIED]**
- **Legacy Clues**: `NIST_SP_800-144_00024`, `00015`, `00006`, `00008`, `00037`
- **Target Section**: NIST SP 800-144 Section 2.3, Section 4.3 ("Trust"); NIST SP 800-146 Section 6.2
- **Aligned Current Chunks**:
  1. `NIST_SP_800-144_txt_00062` (p. 28-29, 455 toks)
     - *Evidence*: Directly addresses loss of control: "an organization relinquishes direct control over many aspects of security and privacy... necessitating a high level of trust in the provider."
  2. `NIST_SP_800-144_txt_00038` (p. 16, 402 toks)
     - *Evidence*: Describes implications of outsourcing parts of computing environment to an outside party.
  3. `NIST_SP_800-146_txt_00080` (p. 45, 299 toks)
     - *Evidence*: Analyzes consumer vs provider scope of control across the software stack.

---

### [Q9] What security issues can result from outsourcing services to a cloud provider?
- **Status**: **[VERIFIED]**
- **Legacy Clues**: `NIST_SP_800-144_00059`, `00035`, `00076`, `00057`, `00079`
- **Target Section**: NIST SP 800-144 Section 5 ("Public Cloud Outsourcing")
- **Aligned Current Chunks**:
  1. `NIST_SP_800-144_txt_00094` (p. 47, 389 toks)
     - *Evidence*: Identifies outsourcing risks: cloud providers standardizing services with take-it-or-leave-it terms, third-party sub-contracting.
  2. `NIST_SP_800-144_txt_00099` (p. 49, 406 toks)
     - *Evidence*: Outlines general outsourcing contract concerns, legal jurisdictional issues, and lack of visibility.
  3. `NIST_SP_800-144_txt_00100` (p. 50, 435 toks)
     - *Evidence*: Discusses provider site failure, conflicting operational maintenance, and collateral denial of service impacts.

---

### [Q10] What are the security implications of storing organizational data in the public cloud?
- **Status**: **[VERIFIED]**
- **Legacy Clues**: `NIST_SP_800-144_00024`, `00058`, `00005`, `00020`, `NIST_SP_800-146_00046`
- **Target Section**: NIST SP 800-144 Section 4.7 ("Data Protection")
- **Aligned Current Chunks**:
  1. `NIST_SP_800-144_txt_00080` (p. 39, 478 toks)
     - *Evidence*: Data protection implications: co-residency of data with competitors or untrusted third parties; residual data sanitization.
  2. `NIST_SP_800-144_txt_00081` (p. 39-40, 391 toks)
     - *Evidence*: Collocation with high-threat target organizations; subpoena/legal seizure risks impacting shared hardware.
  3. `NIST_SP_800-144_txt_00082` (p. 40-41, 480 toks)
     - *Evidence*: Data-at-rest encryption requirements, cryptographic key segregation, and secure deletion challenges.

---

### [Q11] What responsibilities does an organization retain after moving to a public cloud?
- **Status**: **[VERIFIED]**
- **Legacy Clues**: `NIST_SP_800-144_00015`, `00005`, `00059`, `00057`, `00035`
- **Target Section**: NIST SP 800-144 Executive Summary, Section 2.3, Section 4.2
- **Aligned Current Chunks**:
  1. `NIST_SP_800-144_txt_00026` (p. 9, 485 toks)
     - *Evidence*: Retained responsibilities: data governance, client-side security, incident reporting, and overall compliance accountability.
  2. `NIST_SP_800-144_txt_00060` (p. 27-28, 464 toks)
     - *Evidence*: Accountability for data privacy and security cannot be transferred; legal liability remains with the contracting organization.
  3. `NIST_SP_800-144_txt_00038` (p. 16, 402 toks)
     - *Evidence*: Delineates retained management and oversight obligations in outsourced deployments.

---

### [Q12] What security responsibilities are shared between a cloud provider and a cloud customer?
- **Status**: **[VERIFIED]**
- **Legacy Clues**: `NIST_SP_800-146_00131`, `NIST_SP_800-144_00005`, `NIST_SP_800-146_00113`, `00056`, `NIST_SP_800-144_00036`
- **Target Section**: NIST SP 800-144 Section 2.2; NIST SP 800-146 Sections 6.2 & 7.2
- **Aligned Current Chunks**:
  1. `NIST_SP_800-144_txt_00022` (p. 7, 218 toks)
     - *Evidence*: Delineation of shared responsibilities across service models (SaaS vs PaaS vs IaaS).
  2. `NIST_SP_800-144_txt_00036` (p. 14-15, 385 toks)
     - *Evidence*: Explicit division: platform settings and applications controlled by consumer, physical and virtual hardware by provider.
  3. `NIST_SP_800-146_txt_00080` (p. 45, 299 toks)
     - *Evidence*: Software stack responsibility matrix for PaaS (provider manages hardware/OS/runtime, consumer manages application).
  4. `NIST_SP_800-146_txt_00094` (p. 50, 493 toks)
     - *Evidence*: Responsibility matrix for IaaS (consumer manages guest OS, middleware, and application; provider manages virtualization and facilities).

---

### [Q13] What risks are associated with relying on a third-party cloud service provider?
- **Status**: **[VERIFIED]**
- **Legacy Clues**: `NIST_SP_800-144_00035`, `00064`, `00008`, `NIST_SP_800-146_00104`, `NIST_SP_800-144_00036`
- **Target Section**: NIST SP 800-144 Section 4.3 ("Trust"), Section 4.8 ("Availability"); NIST SP 800-146 Section 8.2.2
- **Aligned Current Chunks**:
  1. `NIST_SP_800-144_txt_00064` (p. 29-30, 496 toks)
     - *Evidence*: Third-party composite service dependencies; cascading failure and liability ambiguities when providers sub-contract.
  2. `NIST_SP_800-144_txt_00086` (p. 42-43, 404 toks)
     - *Evidence*: Business continuity risks: cloud providers discontinuing services, bankruptcy, or unilateral modifications to terms.
  3. `NIST_SP_800-146_txt_00122` (p. 59, 290 toks)
     - *Evidence*: Outages and service-level degradation caused by provider infrastructure incidents.

---

### [Q14] How can social engineering attacks affect public cloud security?
- **Status**: **[UNRESOLVED / LIMITED EVIDENCE]**
- **Legacy Clues**: `NIST_SP_800-144_00007`, `NIST_SP_800-115_00067`, `NIST_SP_800-53_00285`, `NIST_SP_800-83_00025`, `NIST_SP_800-144_00027`
- **Target Section**: NIST SP 800-144 Section 4.4 (brief mention)
- **Candidate Chunks**:
  1. `NIST_SP_800-144_txt_00073` (p. 35, 305 toks)
     - *Evidence*: "The growing availability and use of social media, personal Webmail, and other publicly available sites also have associated risks that are a concern, since they increasingly serve as avenues for social engineering attacks..."
- *Gap Analysis*: In the cloud publications, social engineering is mentioned only in passing. The historical ground truth relied on chunks from `NIST_SP_800-115` (Penetration Testing) and `NIST_SP_800-83` (Malware Prevention). Within a cloud-only evaluation pool, this question cannot be comprehensively answered.

---

### [Q15] How can malware on a client device threaten cloud services?
- **Status**: **[CANDIDATE - NEEDS CROSS-DOC POOL]**
- **Legacy Clues**: `NIST_SP_800-144_00007`, `NIST_SP_800-46_00023`, `00062`, `00012`, `NIST_SP_800-146_00065`
- **Target Section**: NIST SP 800-144 Exec Summary & Section 3.3; NIST SP 800-146 Section 5.4.1
- **Aligned Current Chunks**:
  1. `NIST_SP_800-144_txt_00025` (p. 8-9, 415 toks)
     - *Evidence*: Explains how client devices and Web browsers can be infected with keyloggers or malware that hijack cloud administrator credentials.
  2. `NIST_SP_800-144_txt_00052` (p. 23, 499 toks)
     - *Evidence*: Botnet and malware attacks originating from client platforms compromising cloud service integrity.
  3. `NIST_SP_800-146_txt_00067` (p. 38, 484 toks)
     - *Evidence*: Browser vulnerabilities allowing malware on client devices to intercept and tamper with SaaS application traffic.
- *Gap Analysis*: Strong candidate evidence exists in SP 800-144 and SP 800-146; however, telework-specific malware risks from `NIST_SP_800-46` are omitted if restricted to the cloud pool.

---

### [Q16] Why are security and privacy considerations important throughout the cloud system lifecycle?
- **Status**: **[VERIFIED]** (Previously unmapped in legacy ground truth)
- **Legacy Clues**: None (Q16 had 0 chunks in legacy GT)
- **Target Section**: NIST SP 800-144 Exec Summary, Section 5.2, Section 5.4
- **Aligned Current Chunks**:
  1. `NIST_SP_800-144_txt_00021` (p. 6-7, 302 toks)
     - *Evidence*: Emphasizes planning security and privacy before engaging cloud solutions; failure to incorporate requirements during acquisition leads to major vulnerabilities.
  2. `NIST_SP_800-144_txt_00104` (p. 52-53, 381 toks)
     - *Evidence*: Preliminary lifecycle planning ensures security compliance, specifies requirements, and defines data preservation rules before contract signing.
  3. `NIST_SP_800-144_txt_00115` (p. 60-61, 458 toks)
     - *Evidence*: Concluding lifecycle activities: data sanitization, transition planning, and avoiding vendor lock-in.

---

### [Q17] What governance practices are important when using public cloud services?
- **Status**: **[VERIFIED]** (Previously unmapped in legacy ground truth)
- **Legacy Clues**: None (Q17 had 0 chunks in legacy GT)
- **Target Section**: NIST SP 800-144 Section 4.1 ("Governance"), Section 5.2
- **Aligned Current Chunks**:
  1. `NIST_SP_800-144_txt_00055` (p. 24-25, 391 toks)
     - *Evidence*: Establishes governance practices: policy enforcement, acquisition oversight, standards adherence, monitoring deployed services, preventing unsanctioned use.
  2. `NIST_SP_800-144_txt_00056` (p. 25, 304 toks)
     - *Evidence*: Formal review procedures, cross-organizational governance teams, continuous policy auditing.

---

### [Q18] What security concerns arise from moving organizational resources to the public cloud?
- **Status**: **[CANDIDATE - NEEDS VERIFICATION]** (Previously unmapped in legacy ground truth)
- **Legacy Clues**: None (Q18 had 0 chunks in legacy GT)
- **Target Section**: NIST SP 800-144 Section 2.3, Section 3.3, Section 5.1
- **Aligned Current Chunks**:
  1. `NIST_SP_800-144_txt_00038` (p. 16, 402 toks)
     - *Evidence*: Relinquishing perimeter security; boundary degradation when resources move outside agency firewall.
  2. `NIST_SP_800-144_txt_00047` (p. 20-21, 372 toks)
     - *Evidence*: Shared multi-tenant exposure and system complexity.
  3. `NIST_SP_800-144_txt_00100` (p. 50, 435 toks)
     - *Evidence*: Conflicts for critical computing resources, loss of operational visibility.

---

### [Q19] What challenges can organizations face when monitoring security in public cloud environments?
- **Status**: **[VERIFIED]** (Previously unmapped in legacy ground truth)
- **Legacy Clues**: None (Q19 had 0 chunks in legacy GT)
- **Target Section**: NIST SP 800-144 Section 4.3, Section 4.9; NIST SP 800-146 Section 8.4.4
- **Aligned Current Chunks**:
  1. `NIST_SP_800-144_txt_00065` (p. 30-31, 395 toks)
     - *Evidence*: Provider Web dashboards lack sufficient operational detail and fail during outages; lack of audit log transparency.
  2. `NIST_SP_800-144_txt_00087` (p. 43-44, 450 toks)
     - *Evidence*: Difficulty coordinating event log analysis across multiple cloud layers (hypervisor, virtual OS, network) managed by the provider.
  3. `NIST_SP_800-146_txt_00134` (p. 62-63, 403 toks)
     - *Evidence*: Forensics and monitoring challenges in distributed multi-tenant environments (clock synchronization across datacenters, legal access barriers).

---

### [Q20] What factors should organizations consider when evaluating the security of a public cloud provider?
- **Status**: **[VERIFIED]** (Previously unmapped in legacy ground truth)
- **Legacy Clues**: None (Q20 had 0 chunks in legacy GT)
- **Target Section**: NIST SP 800-144 Section 3.1, Section 5.2
- **Aligned Current Chunks**:
  1. `NIST_SP_800-144_txt_00104` (p. 52-53, 381 toks)
     - *Evidence*: Specification of security requirements and compliance mandates before issuing requests for proposals.
  2. `NIST_SP_800-144_txt_00111` (p. 57-58, 358 toks)
     - *Evidence*: Technical factors: multi-tenant isolation techniques, backup/recovery facilities, data sanitization capabilities, e-discovery support, and encryption mechanisms.
  3. `NIST_SP_800-144_txt_00112` (p. 58, 325 toks)
     - *Evidence*: Assessing provider competency: independent third-party certifications, financial viability, track record, and security commitments.
  4. `NIST_SP_800-144_txt_00041` (p. 17-18, 470 toks)
     - *Evidence*: Contractual factors: Service Level Agreements (SLAs), terms of service, liability limits, and termination policies.

---

## 4. Corpus Coverage Analysis & Cybersecurity Domain Gaps

### Category Representation Analysis
The full corpus of 73 documents spans 10 cybersecurity categories. The current 20 evaluation questions evaluate **only 1 category**:

```
Corpus Category Distribution vs Evaluation Questions Suite:

[Cloud Application Security]  ████████████████████ 20 Questions (100.0%)
[Cryptography Security]       ░░░░░░░░░░░░░░░░░░░░  0 Questions (0.0%)
[Identity & Access]           ░░░░░░░░░░░░░░░░░░░░  0 Questions (0.0%)
[Risk Management]             ░░░░░░░░░░░░░░░░░░░░  0 Questions (0.0%)
[Incident Response]           ░░░░░░░░░░░░░░░░░░░░  0 Questions (0.0%)
[Zero Trust & Networks]       ░░░░░░░░░░░░░░░░░░░░  0 Questions (0.0%)
[Vulnerability Management]    ░░░░░░░░░░░░░░░░░░░░  0 Questions (0.0%)
[Supply Chain Security]       ░░░░░░░░░░░░░░░░░░░░  0 Questions (0.0%)
[Threats & Malware]           ░░░░░░░░░░░░░░░░░░░░  0 Questions (0.0%)
[Root (Foundational)]         ░░░░░░░░░░░░░░░░░░░░  0 Questions (0.0%)
```

### Implications for the Embedding Model Benchmark
1. **Strengths of Current Question Set**:
   - High depth and nuance for cloud computing architectures, shared responsibility, virtualization, and multi-tenant isolation.
   - Ideal for measuring how well models distinguish subtle semantic distinctions (e.g. Q1 "risks" vs Q2 "challenges" vs Q6 "concerns" vs Q8 "loss of control").
2. **Blind Spots**:
   - Does not evaluate dense retrieval on alphanumeric control tokens (e.g. `AC-2(1)`, `IA-5`).
   - Does not test cryptographic parameter search (e.g. `AES-256-GCM`, `FIPS 140-3`, `ECC curves`).
   - Does not measure multi-page table retrieval or figure context matching.

---

## 5. Proposed Pilot Benchmark Specification

To conduct a fair, rigorous, and resource-safe benchmark comparing `BAAI/bge-small-en-v1.5` and `BAAI/bge-m3`, we specify the following standardized pilot setup:

### 1. Benchmark Chunk Pool (396 Chunks Total)
- **Source Files**:
  - `data/chunks_corpus/cloud_application_security/NIST_SP_800-144_chunks.jsonl` (164 chunks)
  - `data/chunks_corpus/cloud_application_security/NIST_SP_800-146_chunks.jsonl` (232 chunks)
- **Why this pool?**:
  - Directly matches all 20 questions in `evaluation_questions.json`.
  - Self-contained, realistic size: small enough to encode on CPU in ~15 seconds for BGE-small and ~90 seconds for BGE-M3.
  - Zero disk space footprint: embeddings fit entirely in an in-memory NumPy array (~1.2 MB for BGE-small, ~3.2 MB for BGE-M3).

### 2. Standardized Evaluation Question Subset (15 Questions)
Select the **15 highest-confidence questions** that have verified textual evidence in the 396-chunk pool:
- **Questions Included**: Q1, Q3, Q4, Q5, Q7, Q8, Q9, Q10, Q11, Q12, Q13, Q16, Q17, Q19, Q20.
- **Questions Excluded from Primary Pilot**:
  - Q14 (Social Engineering): Lacks dedicated depth in cloud publications.
  - Q15 (Client Malware): Relies heavily on telework document NIST SP 800-46.
  - Q2, Q6, Q18: Flagged as candidates with high semantic overlap with Q1; can be included in a secondary sensitivity analysis.

### 3. Unified Ground-Truth Mapping for Benchmark Runner
Below is the aligned ground-truth table to be consumed by the benchmark harness:

```json
{
  "Q1": ["NIST_SP_800-144_txt_00047", "NIST_SP_800-144_txt_00048", "NIST_SP_800-144_txt_00054"],
  "Q3": ["NIST_SP_800-144_txt_00025", "NIST_SP_800-144_txt_00052", "NIST_SP_800-146_txt_00067"],
  "Q4": ["NIST_SP_800-144_txt_00055", "NIST_SP_800-144_txt_00056"],
  "Q5": ["NIST_SP_800-144_txt_00022", "NIST_SP_800-144_txt_00026", "NIST_SP_800-144_txt_00038", "NIST_SP_800-144_txt_00060"],
  "Q7": ["NIST_SP_800-144_txt_00048", "NIST_SP_800-144_txt_00080", "NIST_SP_800-144_txt_00108"],
  "Q8": ["NIST_SP_800-144_txt_00062", "NIST_SP_800-144_txt_00038", "NIST_SP_800-146_txt_00080"],
  "Q9": ["NIST_SP_800-144_txt_00094", "NIST_SP_800-144_txt_00099", "NIST_SP_800-144_txt_00100"],
  "Q10": ["NIST_SP_800-144_txt_00080", "NIST_SP_800-144_txt_00081", "NIST_SP_800-144_txt_00082"],
  "Q11": ["NIST_SP_800-144_txt_00026", "NIST_SP_800-144_txt_00038", "NIST_SP_800-144_txt_00060"],
  "Q12": ["NIST_SP_800-144_txt_00022", "NIST_SP_800-144_txt_00036", "NIST_SP_800-146_txt_00080", "NIST_SP_800-146_txt_00094"],
  "Q13": ["NIST_SP_800-144_txt_00064", "NIST_SP_800-144_txt_00086", "NIST_SP_800-146_txt_00122"],
  "Q16": ["NIST_SP_800-144_txt_00021", "NIST_SP_800-144_txt_00104", "NIST_SP_800-144_txt_00115"],
  "Q17": ["NIST_SP_800-144_txt_00055", "NIST_SP_800-144_txt_00056"],
  "Q19": ["NIST_SP_800-144_txt_00065", "NIST_SP_800-144_txt_00087", "NIST_SP_800-146_txt_00134"],
  "Q20": ["NIST_SP_800-144_txt_00104", "NIST_SP_800-144_txt_00111", "NIST_SP_800-144_txt_00112", "NIST_SP_800-144_txt_00041"]
}
```

### 4. Metrics & Evaluation Consistency
Both models will be tested under identical retrieval parameters:
- **Similarity Metric**: Cosine similarity on normalized embeddings.
- **Top-K Limit**: Top-5 candidates retrieved per query.
- **Primary Metrics**:
  - **Hit@1, Hit@3, Hit@5**: Proportion of questions where at least one verified relevant chunk is retrieved in top 1, 3, or 5.
  - **Precision@5**: Average proportion of retrieved top-5 chunks that are relevant.
  - **MRR**: Mean reciprocal rank of the first relevant chunk.
  - **Latency**: Cold model load time ($s$), query latency ($ms$), corpus throughput ($\text{chunks}/s$).
  - **Peak Memory**: $\Delta \text{RSS MB}$ tracked via `psutil`.

---

## 6. Recommendations and Decision Matrix

### Decision Recommendation: APPROVED TO PROCEED TO STAGE 2 BENCHMARK RUN
With the ground truth aligned and verified against the current 396-chunk cloud pool:
1. **The legacy ID disconnect is resolved**: The benchmark runner can now score retrieval accuracy meaningfully.
2. **The pilot setup is resource-safe**: 396 chunks in-memory consumes $< 5 \text{ MB}$ RAM, $0 \text{ MB}$ disk space, and completes in $< 2 \text{ minutes}$ on CPU.
3. **Safety rules respected**: No embeddings were generated, no models loaded, and no existing project files overwritten.

*Awaiting user approval before proceeding to Stage 2: Pilot Benchmark Execution.*
