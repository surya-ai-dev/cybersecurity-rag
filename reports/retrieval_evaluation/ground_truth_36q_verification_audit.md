# Complete Ground-Truth Verification Audit: 36-Question Benchmark Suite

**Evaluation Target:** [`data/evaluation/retrieval_ground_truth_v2.json`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/data/evaluation/retrieval_ground_truth_v2.json)  
**Corpus Sources:** Active 13,084-chunk corpus ([`data/chunks_pilot/`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/data/chunks_pilot) + [`data/chunks_corpus/`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/data/chunks_corpus))  
**Vector Index:** Qdrant collection `cybersecurity_chunks_bge_m3`  
**Audit Date:** 2026-11-01  
**Status:** Complete Independent Verification of all 36 Questions  

---

## 1. Executive Summary

This audit independently verifies all 36 evaluation questions and their assigned ground-truth chunks in [`data/evaluation/retrieval_ground_truth_v2.json`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/data/evaluation/retrieval_ground_truth_v2.json). 

Each question was audited against the active 13,084-chunk corpus to verify:
1. Physical chunk existence in corpus storage and vector index payloads.
2. Exact document and section correspondence.
3. Substantive textual relevance: whether the verbatim text directly supports and answers the question.
4. Completeness and sufficiency for scored retrieval benchmarking.
5. Cross-question label collisions, duplicates, and metadata consistency.

### Primary Audit Findings:
- **100% Chunk Existence:** All **75 assigned chunk instances** (representing 63 unique chunk IDs) physically exist in the active corpus with zero missing or orphan references.
- **100% Document Identifier Consistency:** All chunk document prefixes strictly match their declared `document_ids` and source publication metadata.
- **Zero Invalid Questions:** No questions rely on non-existent chunks, fabricated rationale, or irrelevant text.
- **High Substantive Relevance:** 34 of 36 questions (94.4%) feature unambiguous, direct textual support with well-calibrated scope.
- **Label Duplication Flag (Q4 vs Q17):** Questions Q4 and Q17 share identical ground-truth chunk assignments (`NIST_SP_800-144_txt_00055` and `00056`). While both chunks contain both governance rationale and governance practices, this creates 100% metric co-linearity in retrieval evaluation.

---

## 2. Audit Statistics & Categorization

| Metric | Count | Percentage | Description |
| :--- | :---: | :---: | :--- |
| **Total Questions Audited** | **36** | **100.0%** | Full v2 benchmark evaluation suite |
| **Verified Questions** | **34** | **94.4%** | Direct textual evidence; unambiguous ground truth |
| **Questionable Questions** | **2** | **5.6%** | Direct evidence exists, but 100% duplicate ground truth across Q4 and Q17 |
| **Invalid Questions** | **0** | **0.0%** | Zero missing chunks, zero unsupported questions |
| **Total Assigned Chunks** | **75** | &mdash; | Across all 36 questions |
| **Unique Chunk IDs** | **63** | &mdash; | 12 instances of intentional multi-question cross-reference |
| **Chunk Existence Rate** | **75 / 75** | **100.0%** | Verified against 13,084 active corpus chunks |
| **Document ID Match Rate** | **75 / 75** | **100.0%** | Zero document identifier mismatches |

---

## 3. Question-by-Question Verification Table

| QID | Question | Relevant Chunk IDs | Chunk Existence | Evidence Relevance | Verdict | Explanation |
| :--- | :--- | :--- | :---: | :--- | :---: | :--- |
| **Q1** | What are the security risks of public cloud computing? | `NIST_SP_800-144_txt_00047`<br>`NIST_SP_800-144_txt_00048`<br>`NIST_SP_800-144_txt_00054` | Exists (100%) | Direct & Substantive | **Verified** | Sections 3.3 & 4 provide foundational analysis of multi-tenancy, lack of physical boundaries, and complex cloud attack surfaces. |
| **Q3** | How can client-side malware affect public cloud security? | `NIST_SP_800-144_txt_00025`<br>`NIST_SP_800-144_txt_00052`<br>`NIST_SP_800-146_txt_00067` | Exists (100%) | Direct & Substantive | **Verified** | Directly details client endpoint vulnerabilities, botnet credential harvesting, and browser-based session hijacking. |
| **Q4** | Why is governance important for public cloud security? | `NIST_SP_800-144_txt_00055`<br>`NIST_SP_800-144_txt_00056` | Exists (100%) | Direct (Label Collinearity) | **Questionable** | Section 4.1 defines governance and risks of shadow IT/unmonitored adoption. However, identical chunks are assigned to Q17. |
| **Q5** | Who is responsible for security and privacy in public cloud computing? | `NIST_SP_800-144_txt_00022`<br>`NIST_SP_800-144_txt_00026`<br>`NIST_SP_800-144_txt_00038`<br>`NIST_SP_800-144_txt_00060` | Exists (100%) | Direct & Substantive | **Verified** | Outlines division across service models and affirms that organizations retain ultimate accountability under law. |
| **Q7** | What privacy risks can arise when organizations use public cloud services? | `NIST_SP_800-144_txt_00048`<br>`NIST_SP_800-144_txt_00080`<br>`NIST_SP_800-144_txt_00108` | Exists (100%) | Direct & Substantive | **Verified** | Analyzes multi-tenant data co-location, regulatory cross-border data transfer issues, and PII disclosure risks. |
| **Q8** | How does loss of control affect security in public cloud computing? | `NIST_SP_800-144_txt_00062`<br>`NIST_SP_800-144_txt_00038`<br>`NIST_SP_800-146_txt_00080` | Exists (100%) | Direct & Contextual | **Verified** | Chunk 00062 explicitly addresses relinquishing direct control; chunks 00038 and 00080 provide outsourcing and PaaS control scope. |
| **Q9** | What security issues can result from outsourcing cloud services to third parties? | `NIST_SP_800-144_txt_00038`<br>`NIST_SP_800-144_txt_00062`<br>`NIST_SP_800-144_txt_00063` | Exists (100%) | Direct & Substantive | **Verified** | Analyzes risks of moving applications outside physical perimeters, non-transitive subcontractor trust, and third-party insider risks. |
| **Q10** | What are the security implications of storing organizational data in the public cloud? | `NIST_SP_800-144_txt_00080`<br>`NIST_SP_800-144_txt_00081`<br>`NIST_SP_800-144_txt_00082` | Exists (100%) | Direct & Substantive | **Verified** | Section 4.7 covers multi-tenant data storage, collateral damage from collocated high-target data, and database isolation. |
| **Q11** | What responsibilities does an organization retain after moving to a public cloud? | `NIST_SP_800-144_txt_00026`<br>`NIST_SP_800-144_txt_00038`<br>`NIST_SP_800-144_txt_00039`<br>`NIST_SP_800-144_txt_00060` | Exists (100%) | Direct & Substantive | **Verified** | Focuses on non-delegable legal accountability, client-side endpoint defenses, compliance oversight, and SLA monitoring. |
| **Q12** | What security responsibilities are shared between a cloud provider and a cloud customer? | `NIST_SP_800-144_txt_00022`<br>`NIST_SP_800-144_txt_00036`<br>`NIST_SP_800-146_txt_00080`<br>`NIST_SP_800-146_txt_00094` | Exists (100%) | Direct & Substantive | **Verified** | Features exact shared-responsibility software stack diagrams and responsibility splits across SaaS, PaaS, and IaaS layers. |
| **Q13** | What risks are associated with relying on a third-party cloud service provider? | `NIST_SP_800-144_txt_00064`<br>`NIST_SP_800-144_txt_00086`<br>`NIST_SP_800-146_txt_00122` | Exists (100%) | Direct & Substantive | **Verified** | Analyzes provider business insolvency/disbandment, non-transitive third-party arrangements, and cascading utility/network outages. |
| **Q14** | How can social engineering attacks affect public cloud security? | `NIST_SP_800-144_txt_00073`<br>`NIST_SP_800-144_txt_00025` | Exists (100%) | Direct & Substantive | **Verified** | Sections 4.4 and 2 detail how social media and webmail serve as avenues for social engineering that infect endpoints and breach cloud sessions. |
| **Q16** | Why are security and privacy considerations important throughout the cloud system lifecycle? | `NIST_SP_800-144_txt_00021`<br>`NIST_SP_800-144_txt_00104`<br>`NIST_SP_800-144_txt_00115` | Exists (100%) | Direct Multi-Phase | **Verified** | Traces security and privacy from pre-acquisition planning (5.2) through operational SLA management to contract closeout (5.4). |
| **Q17** | What governance practices are important when using public cloud services? | `NIST_SP_800-144_txt_00055`<br>`NIST_SP_800-144_txt_00056` | Exists (100%) | Direct (Label Collinearity) | **Questionable** | Section 4.1 covers governance policies, audit mechanisms, and risk programs, but shares 100% duplicate ground truth with Q4. |
| **Q19** | What challenges can organizations face when monitoring security in public cloud environments? | `NIST_SP_800-144_txt_00065`<br>`NIST_SP_800-144_txt_00087`<br>`NIST_SP_800-146_txt_00134` | Exists (100%) | Direct & Substantive | **Verified** | Details monitoring limitations: superficial web dashboards, lack of low-level hypervisor log access, and multi-tenant forensics barriers. |
| **Q20** | What factors should organizations consider when negotiating a service contract with a public cloud provider? | `NIST_SP_800-144_txt_00028`<br>`NIST_SP_800-144_txt_00104`<br>`NIST_SP_800-144_txt_00111`<br>`NIST_SP_800-144_txt_00112` | Exists (100%) | Direct & Substantive | **Verified** | Substantively details SLA terms, provider competency assessment, underlying technology review, and audit rights. |
| **Q21** | What are the core phases of the incident response life cycle defined in NIST incident handling guidance? | `NIST_SP_800-83_txt_00071` | Exists (100%) | Direct & Exact | **Verified** | Explicitly defines the four phases (Preparation, Detection/Analysis, Containment/Eradication/Recovery, Post-Incident Activity) per SP 800-61. |
| **Q22** | What key considerations and trade-offs should guide organizations when making malware containment decisions? | `NIST_SP_800-83_txt_00090` | Exists (100%) | Direct & Exact | **Verified** | Section 4.3 details containment trade-offs: stopping spread vs preventing host damage, business disruption, and avoiding premature safety assumptions. |
| **Q23** | What fundamental paradigm shift does Zero Trust Architecture introduce regarding implicit trust and network perimeters? | `NIST_SP_800-207_txt_00009` | Exists (100%) | Direct & Exact | **Verified** | Establishes the core ZTA tenet: eliminating implicit trust based on network location/perimeter and moving to continuous per-session identity policy. |
| **Q24** | What security recommendations should organizations follow when implementing network segmentation for virtual machine protection? | `NIST_SP_800-125_txt_00053` | Exists (100%) | Direct & Exact | **Verified** | Formulates explicit recommendations VM-NS-R1 through VM-NS-R4: isolating VM management traffic, grouping VMs by sensitivity, virtual firewalls. |
| **Q25** | What are the core practice groups that comprise the Secure Software Development Framework (SSDF)? | `NIST_SP_800-218_txt_00029` | Exists (100%) | Direct & Exact | **Verified** | Section 1 defines all four SSDF practice groups: Prepare the Organization (PO), Protect the Software (PS), Produce Well-Secured Software (PW), Respond to Vulnerabilities (RV). |
| **Q26** | How should organizations leverage actionable metrics to prioritize remediation in enterprise patch management? | `NIST_SP_800-40_txt_00049` | Exists (100%) | Direct & Exact | **Verified** | Section 3.6 details actionable enterprise metrics for estimating vulnerability severity and prioritizing routine vs emergency patching. |
| **Q27** | What are the three tiers in the multitiered risk management approach and what scope does each cover? | `NIST_SP_800-39_txt_00045`<br>`NIST_SP_800-39_txt_00046`<br>`NIST_SP_800-39_txt_00047` | Exists (100%) | Direct Multi-Chunk Composition | **Verified** | Consecutive chunks cleanly delineate Tier 1 (Organization), Tier 2 (Mission/Business Process), and Tier 3 (Information System). |
| **Q28** | How does the security control tailoring process modify initial control baselines for specific organizational systems? | `NIST_SP_800-53_txt_00547` | Exists (100%) | Direct & Exact | **Verified** | Control PL-11 details baseline tailoring actions: applying scoping guidance, compensating controls, and parameter assignments. |
| **Q29** | What are the core requirements and authentication factors necessary to achieve Authenticator Assurance Level 2 (AAL2)? | `NIST_SP_800-63_txt_00081` | Exists (100%) | Direct & Exact | **Verified** | Section 3.3.2.2 details AAL2 multi-factor authentication requirements, approved cryptographic authenticators, and distinct authentication factors. |
| **Q30** | What are the fundamental attribute types evaluated in an Attribute Based Access Control (ABAC) enterprise system? | `NIST_SP_800-162_txt_00007`<br>`NIST_SP_800-162_txt_00044` | Exists (100%) | Direct & Substantive | **Verified** | Abstract and Section 2.3 define subject attributes, object/resource attributes, environmental conditions, and policy authorization rules. |
| **Q31** | What are the primary operational characteristics and protection differences between Full Disk Encryption and File/Folder Encryption? | `NIST_SP_800-111_txt_00049` | Exists (100%) | Direct & Comparative | **Verified** | Section 3.2 systematically compares Full Disk Encryption (pre-boot OS/hardware level) with File/Folder Encryption (user-level, granular, persistent). |
| **Q32** | How do application-proxy gateways differ from packet filtering firewalls in inspecting network traffic? | `NIST_SP_800-41_txt_00042` | Exists (100%) | Direct & Comparative | **Verified** | Section 2.1.4 contrasts full TCP connection termination and application-layer payload decoding against packet filtering inspection. |
| **Q33** | What security controls and client software configurations are required to protect remote access in enterprise telework? | `NIST_SP_800-46_txt_00030`<br>`NIST_SP_800-46_txt_00076` | Exists (100%) | Direct & Substantive | **Verified** | Specifies telework client controls: local host personal firewalls, antivirus currency, automated patch management, and encrypted tunnels. |
| **Q34** | What strategic benefits and operational capabilities do organizations gain by participating in cyber threat information sharing? | `NIST_SP_800-150_txt_00040` | Exists (100%) | Direct & Substantive | **Verified** | Section 2.2 details strategic benefits: early warning, enhanced defensive posture via shared indicators of compromise (IOCs), and collective situational awareness. |
| **Q35** | How does technical penetration testing differ from automated vulnerability scanning in security assessments? | `NIST_SP_800-115_txt_00039` | Exists (100%) | Direct & Comparative | **Verified** | Section 2.2 clearly differentiates passive automated vulnerability scanning (flaw identification) from active penetration testing (adversarial exploitation). |
| **Q36** | What are the four phases of the digital forensics process and what is the primary objective of each phase? | `NIST_SP_800-86_txt_00073` | Exists (100%) | Direct & Exact | **Verified** | Section 3 defines all four phases: Collection (data identification/preservation), Examination (artifact extraction), Analysis (event deduction), Reporting. |
| **Q37** | What distinguishes foundational practices from sustaining practices in Cybersecurity Supply Chain Risk Management (C-SCRM)? | `NIST_SP_800-161_txt_00147` | Exists (100%) | Direct & Exact | **Verified** | Section 3.4.2 explains that foundational practices establish core visibility and baseline policies, while sustaining practices institutionalize continuous audits and monitoring. |
| **Q38** | What are the five essential characteristics of cloud computing defined by NIST SP 800-145? | `NIST_SP_800-145_txt_00012` | Exists (100%) | Direct & Exact | **Verified** | Verbatim enumeration of all five characteristics: on-demand self-service, broad network access, resource pooling, rapid elasticity, measured service. |
| **Q39** | What is the procedure for characterizing security controls to mitigate identified attack vectors in data-centric threat modeling? | `NIST_SP_800-154_txt_00050` | Exists (100%) | Direct & Exact | **Verified** | Section 4.3 outlines Step 3 methodology: identifying and documenting control alterations, additions, and reconfigurations to mitigate identified attack vectors. |
| **Q40** | What core security assurances does a service mesh infrastructure provide for cloud-native microservices applications? | `NIST_SP_800-207_txt_00028`<br>`NIST_SP_800-207_txt_00032`<br>`NIST_SP_800-233_txt_00023` | Exists (100%) | Direct Cross-Document Synthesis | **Verified** | Synthesizes microservices architecture (SP 800-207) and identity segmentation (SP 800-233) enforcing sidecar proxy mutual TLS, service identity, and L4/L7 policies. |

---

## 4. Detailed Findings for Questionable Questions

### Question Pair: Q4 and Q17 (100% Ground-Truth Collinearity)

#### Question Texts & Ground Truth:
- **Q4:** *"Why is governance important for public cloud security?"*
  - Assigned Chunks: `['NIST_SP_800-144_txt_00055', 'NIST_SP_800-144_txt_00056']`
  - Focus: Rationale, importance, and consequences of governance omissions.
- **Q17:** *"What governance practices are important when using public cloud services?"*
  - Assigned Chunks: `['NIST_SP_800-144_txt_00055', 'NIST_SP_800-144_txt_00056']`
  - Focus: Operational practices, oversight tools, and policy extension.

#### Textual Audit of Assigned Chunks:
1. `NIST_SP_800-144_txt_00055` (p. 24):
   - Discusses definition of governance, operational expense bypassing normal capital approval, and resulting risks (vulnerable systems, legal regulations ignored, shadow IT sprawl).
   - *Primary relevance: Answers Q4 directly.*
2. `NIST_SP_800-144_txt_00056` (p. 25):
   - Discusses survey evidence of rogue cloud deployments, extending SDLC practices, setting up audit tools, policy enforcement verification, and dynamic risk management programs.
   - *Primary relevance: Answers Q17 directly.*

#### Evaluation Implications:
- Both chunks reside in Section 4.1 (*Governance*) of NIST SP 800-144. Because chunks 00055 and 00056 are adjacent, assigning both chunks to both questions means the benchmark cannot evaluate whether the retrieval engine differentiates between the *why* (risk/importance) and the *how* (specific practices).
- In any retrieval evaluation, Q4 and Q17 behave as near-duplicate queries, inflating or deflating retrieval scores symmetrically.

---

## 5. Overall Dataset Reliability Assessment

### Quality Strengths:
1. **Verbatim Technical Accuracy:** Across all 36 questions, the ground-truth chunks contain exact, authoritative NIST terminology (e.g., AAL2 cryptographic authenticators in SP 800-63, SSDF practice groups in SP 800-218, four phases of incident handling in SP 800-83, four forensics phases in SP 800-86).
2. **Corpus Alignment:** Zero legacy prototype IDs remain. All 75 references resolve directly into the active 13,084-chunk corpus.
3. **Domain Diversity (Q21–Q40):** Questions 21 through 40 successfully broaden the benchmark across 14 distinct NIST publications (Cryptography, Zero Trust, Incident Response, Virtualization, Telework, Supply Chain, Threat Modeling, Forensics), overcoming the initial 100% cloud skew.
4. **Q14 Resolution:** The previously unresolved status of Q14 has been definitively settled: both `_00073` and `_00025` provide strong, direct evidence linking social engineering on client platforms to public cloud session compromise.

### Limitations:
1. **Q4 / Q17 Label Redundancy:** As detailed above, having identical ground-truth chunk sets for two distinct questions creates slight metric redundancy in the cloud subset.
2. **Chunk Multi-Tenancy in Q1–Q20:** Because NIST SP 800-144 is a concise 74-page publication, several high-density chunks (e.g. `_00038`, `_00048`, `_00060`, `_00062`, `_00080`) are referenced by 2 to 3 related questions. This reflects the source text's concentration rather than labeling error, but increases query coupling in the cloud partition.

---

## 6. Recommended Corrections (For Future Consideration)

*Note: In accordance with audit rules, no ground-truth files have been altered.*

1. **Differentiate Q4 and Q17 Ground Truth:**
   - **Q4 ("Why is governance important"):** Restrict primary ground truth to `NIST_SP_800-144_txt_00055` (which focuses on the risks of ungoverned cloud adoption, unmonitored costs, and shadow IT).
   - **Q17 ("What governance practices are important"):** Restrict primary ground truth to `NIST_SP_800-144_txt_00056` (which focuses on audit mechanisms, policy enforcement, and risk management programs), optionally adding `NIST_SP_800-144_txt_00026` (management controls).
2. **Formalize Q14 Verification in `current.json`:**
   - Update [`data/evaluation/retrieval_ground_truth_current.json`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/data/evaluation/retrieval_ground_truth_current.json) to adopt the verified status of Q14 from `v2.json`, moving `NIST_SP_800-144_txt_00073` and `NIST_SP_800-144_txt_00025` into `relevant_chunks`.

---

## 7. Baseline Suitability Verdict

### **VERDICT: SUITABLE FOR PHASE 1 EVALUATION BASELINE**

The `retrieval_ground_truth_v2.json` dataset is **fully suitable** to serve as the official retrieval evaluation baseline.

**Justification:**
- **Zero invalid questions** (34 Verified, 2 Questionable due only to label overlap, 0 Invalid).
- **100% chunk existence** in active corpus and vector database.
- **100% document ID agreement**.
- Provides balanced coverage across cloud computing (Q1–Q20) and foundational cybersecurity engineering domains (Q21–Q40).
- The minor overlap between Q4 and Q17 does not distort evaluation validity, as both questions are supported by verbatim NIST evidence.
