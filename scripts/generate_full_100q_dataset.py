import glob
import json
import re
from pathlib import Path
from collections import Counter, defaultdict

# Load corpus
print("Loading active corpus chunks...")
chunk_by_id = {}
chunks_by_doc = {}
for fpath in glob.glob("data/chunks_*/**/*.jsonl", recursive=True):
    with open(fpath, "r", encoding="utf-8") as f:
        for line in f:
            c = json.loads(line)
            cid = c["chunk_id"]
            doc = c["document_id"]
            chunk_by_id[cid] = c
            if doc not in chunks_by_doc:
                chunks_by_doc[doc] = []
            chunks_by_doc[doc].append(c)

print(f"Loaded {len(chunk_by_id)} chunks across {len(chunks_by_doc)} documents.")

def make_candidate(qid, qtext, category, pdoc, sdocs, cids, answer_summary, notes=""):
    for cid in cids:
        assert cid in chunk_by_id, f"Error on {qid}: Chunk {cid} does not exist in active corpus!"
        text = chunk_by_id[cid].get("text", "")
        assert len(text) >= 40, f"Error on {qid}: Chunk {cid} text too short ({len(text)} chars)!"

    chunks = [chunk_by_id[c] for c in cids]
    sections = [c.get("section_heading") or c.get("section_path") or "" for c in chunks]
    pages = [c.get("page_start") for c in chunks if c.get("page_start") is not None]
    clean_sections = " | ".join(dict.fromkeys([s for s in sections if s]))
    page_str = ", ".join(str(p) for p in sorted(set(pages))) if pages else "N/A"

    return {
        "question_id": qid,
        "question": qtext,
        "category": category,
        "primary_document": pdoc,
        "supporting_documents": sdocs,
        "relevant_chunk_ids": cids,
        "expected_answer_summary": answer_summary,
        "source_section": clean_sections,
        "source_page": page_str,
        "verification_status": "candidate",
        "verification_notes": notes
    }

# Build the 64 new candidate questions (Q41 - Q104)
candidates = []

# =========================================================================
# GROUP 1: TABLE / STRUCTURED DATA (5 questions: Q41 - Q45)
# =========================================================================

candidates.append(make_candidate(
    "Q41",
    "In the public comment matrix for NIST SP 800-131A Rev. 3, what specific concern is raised regarding legacy-use algorithms and the lack of transition guidance for existing deployments?",
    "table_structured",
    "NIST_SP_800-131",
    [],
    ["NIST_SP_800-131_tbl_00003_p01"],
    "The public comment table highlights concerns that SP 800-131A provides transition guidance for new systems but lacks clear legacy-use transition rules and timelines for existing operational deployments.",
    "Table chunk from comment matrix on Page 14 specifically recording stakeholder feedback on legacy-use algorithms."
))

candidates.append(make_candidate(
    "Q42",
    "In the High-Performance Computing (HPC) Security Overlay moderate baseline table, which zone allocations are designated for Access Control controls AC-2 and AC-3?",
    "table_structured",
    "NIST_SP_800-234",
    [],
    ["NIST_SP_800-234_tbl_00001_p01"],
    "Table on Page 10 specifies zone overlay allocations: AC-2 is designated across All Zones (D), Access Zone (G), Management Zone (G), Computing Zone (G), and Data Storage Zone (GD), while AC-3 is designated in All Zones (G).",
    "Table chunk from HPC Security Control Overlay on Page 10 delineating zone-specific control baseline adaptations."
))

candidates.append(make_candidate(
    "Q43",
    "According to the Federal Cryptographic Key Management System (FCKMS) profile table for NIST SP 800-53 control AC-2, what distinct operational roles must a Federal CKMS support?",
    "table_structured",
    "NIST_SP_800-152",
    [],
    ["NIST_SP_800-152_tbl_00035_p01"],
    "Table on Page 46 specifies requirement PR:5.1 (mapped to AC-2), mandating that a Federal CKMS support five distinct roles: System Authority, System Administrator, Audit Administrator, Cryptographic Officer, and User.",
    "Table chunk from FCKMS Profile on Page 46 defining mandatory administrative roles."
))

candidates.append(make_candidate(
    "Q44",
    "In the Secure Software Development Framework (SSDF) practice table, what is the stated objective of Practice PO.1 (Define Security Requirements for Software Development)?",
    "table_structured",
    "NIST_SP_800-218",
    [],
    ["NIST_SP_800-218_tbl_00001_p02"],
    "Table on Page 17 specifies Practice PO.1: ensuring that security requirements for software development are known, documented, and integrated into the organization's software development practices.",
    "Table chunk from SSDF practices table on Page 17 defining Practice PO.1."
))

candidates.append(make_candidate(
    "Q45",
    "In the cloud computing security control mapping table, which NIST SP 800-53 control families are categorized under the Technical class versus the Operational class?",
    "table_structured",
    "NIST_SP_800-146",
    [],
    ["NIST_SP_800-146_tbl_00005_p01"],
    "Table on Page 71 categorizes Access Control, Audit and Accountability, Identification and Authentication, and System and Communication Protection under Technical controls, while Awareness and Training, Configuration Management, Contingency Planning, Incident Response, Maintenance, Media Protection, Physical Protection, Personnel Security, and System/Information Integrity are categorized under Operational controls.",
    "Table chunk on Page 71 mapping SP 800-53 control families to Technical, Operational, and Management classes."
))

# =========================================================================
# GROUP 2: CROSS-DOCUMENT SYNTHESIS (6 questions: Q46 - Q51)
# =========================================================================

candidates.append(make_candidate(
    "Q46",
    "How do container image vulnerability scanning requirements in NIST SP 800-190 align with CI/CD software supply chain security tasks recommended in NIST SP 800-204D?",
    "cross_document",
    "NIST_SP_800-204",
    ["NIST_SP_800-190"],
    ["NIST_SP_800-204_txt_00054", "NIST_SP_800-190_txt_00076"],
    "NIST SP 800-204D specifies secure build tasks including automated dependency checks and container artifact signing, aligning with NIST SP 800-190 image scanner requirements to prevent deploying vulnerable images.",
    "Synthesizes DevSecOps CI/CD build security tasks (SP 800-204D Section 5.1.1) with container image scanning requirements (SP 800-190 Section 2.3.2)."
))

candidates.append(make_candidate(
    "Q47",
    "How does the core Policy Decision Point (PDP) and Policy Enforcement Point (PEP) architecture in Zero Trust (NIST SP 800-207) integrate with cloud access control systems described in NIST SP 800-210?",
    "cross_document",
    "NIST_SP_800-207",
    ["NIST_SP_800-210"],
    ["NIST_SP_800-207_txt_00030", "NIST_SP_800-210_txt_00001"],
    "NIST SP 800-207 establishes the global control plane consisting of PDP and PEP for continuous session evaluation, which NIST SP 800-210 applies to cloud systems by mediating user requests across virtualized cloud multi-tenant boundaries.",
    "Synthesizes Zero Trust enterprise infrastructure control planes (SP 800-207 Section 3) with cloud access control guidance (SP 800-210)."
))

candidates.append(make_candidate(
    "Q48",
    "How do Authenticator Assurance Level 3 (AAL3) hardware cryptographic requirements in NIST SP 800-63 relate to physical facility access controls using PIV credentials in NIST SP 800-116?",
    "cross_document",
    "NIST_SP_800-63",
    ["NIST_SP_800-116"],
    ["NIST_SP_800-63_txt_00081", "NIST_SP_800-116_txt_00001"],
    "NIST SP 800-63 requires AAL3 authenticators to use hardware-based cryptographic keys that provide proof of possession and verifier impersonation resistance, which matches the cryptographic challenge-response mechanisms executed by PIV card credentials at Physical Access Control Systems (PACS) per SP 800-116.",
    "Synthesizes AAL3 digital authenticator assurance criteria (SP 800-63) with PIV facility physical access integration (SP 800-116)."
))

candidates.append(make_candidate(
    "Q49",
    "How do cryptographic key management lifecycle considerations in NIST SP 800-57 align with the system framework components of a Cryptographic Key Management System (CKMS) in NIST SP 800-130?",
    "cross_document",
    "NIST_SP_800-130",
    ["NIST_SP_800-57"],
    ["NIST_SP_800-130_txt_00001", "NIST_SP_800-57_txt_00033"],
    "NIST SP 800-130 defines the architectural framework for CKMS (governance, policy, components, and automated services), providing the structural design to enforce the key lifecycle states (generation, activation, deactivation, destruction) and cloud key management policies outlined in SP 800-57.",
    "Synthesizes CKMS architectural system design (SP 800-130) with key management lifecycle guidance (SP 800-57)."
))

candidates.append(make_candidate(
    "Q50",
    "How do coordinated vulnerability disclosure intake policies in NIST SP 800-216 integrate with the vulnerability response practice group (RV) in the Secure Software Development Framework (NIST SP 800-218)?",
    "cross_document",
    "NIST_SP_800-216",
    ["NIST_SP_800-218"],
    ["NIST_SP_800-216_txt_00001", "NIST_SP_800-218_txt_00029"],
    "NIST SP 800-216 establishes federal guidelines for receiving and coordinating external vulnerability reports, directly feeding the intake phase of SSDF Practice Group RV (Respond to Vulnerabilities) in SP 800-218 to identify root causes and remediate software flaws.",
    "Synthesizes coordinated vulnerability disclosure guidelines (SP 800-216) with SSDF vulnerability response practices (SP 800-218)."
))

candidates.append(make_candidate(
    "Q51",
    "How do forensic chain of custody and evidence handling requirements in NIST SP 800-61 support mobile device forensic investigations outlined in NIST SP 800-101?",
    "cross_document",
    "NIST_SP_800-61",
    ["NIST_SP_800-101"],
    ["NIST_SP_800-61_txt_00087", "NIST_SP_800-101_txt_00001"],
    "NIST SP 800-61 establishes core forensic evidence handling, documentation, and chain-of-custody protocols during incident response, which NIST SP 800-101 operationalizes for the specialized collection, preservation, and isolation of mobile device hardware and volatile memory.",
    "Synthesizes general incident response forensic principles (SP 800-61 Section 3.2) with mobile device forensic guidelines (SP 800-101)."
))

# =========================================================================
# GROUP 3: MULTI-CHUNK REASONING (2 questions: Q52 - Q53)
# =========================================================================

candidates.append(make_candidate(
    "Q52",
    "What core objectives and continuous monitoring activities are mandated under NIST SP 800-53 security control CA-7 to support ongoing system authorization?",
    "multi_chunk_reasoning",
    "NIST_SP_800-53",
    [],
    ["NIST_SP_800-53_txt_00076", "NIST_SP_800-53_txt_00547"],
    "NIST SP 800-53 establishes that continuous monitoring under control CA-7 requires rigorous planning across the system lifecycle, ongoing assessment of control effectiveness, tracking system changes, and updating security plans to support risk-based re-authorization decisions.",
    "Multi-chunk synthesis across SP 800-53 Chapter 1 foundational planning principles and control tailoring/monitoring guidance."
))

candidates.append(make_candidate(
    "Q53",
    "How does NIST SP 800-161 guide organizations in identifying supply chain risks and enforcing security requirements through contractual supplier clauses?",
    "multi_chunk_reasoning",
    "NIST_SP_800-161",
    [],
    ["NIST_SP_800-161_txt_00011", "NIST_SP_800-161_txt_00147"],
    "NIST SP 800-161 requires organizations to manage risks from products and services throughout the supply chain by implementing foundational practices (establishing visibility and contract requirements) and sustaining practices (continuous audit, SLA verification, and third-party supplier oversight).",
    "Multi-chunk synthesis across SP 800-161 Abstract and Section 3.4.2 foundational vs sustaining practices."
))

# =========================================================================
# GROUP 4: DIRECT FACTUAL (16 questions: Q54 - Q69)
# =========================================================================

candidates.append(make_candidate(
    "Q54",
    "In the public comments on NIST SP 800-57 Part 1 Rev. 6, what emerging key management terms and concepts, such as BYOK and KEM, are identified for formal definition?",
    "direct_factual",
    "NIST_SP_800-57",
    [],
    ["NIST_SP_800-57_txt_00012"],
    "The comments identify terms including BYOK (Bring Your Own Key), CUI, DKE (Double Key Encryption), HYOK (Hold Your Own Key), KEM (Key Encapsulation Mechanism), and OUP as used in cloud and modern key management text requiring formal definition.",
    "Direct factual retrieval from SP 800-57 Part 1 Rev. 6 public comments Section 4.1.2."
))

candidates.append(make_candidate(
    "Q55",
    "What is the primary scope and purpose of the Cryptographic Key Management System (CKMS) design framework defined in NIST SP 800-130?",
    "direct_factual",
    "NIST_SP_800-130",
    [],
    ["NIST_SP_800-130_txt_00001"],
    "NIST SP 800-130 provides a framework for designing a Cryptographic Key Management System (CKMS), specifying architectural requirements, security policies, cryptographic services, and component specifications needed to protect cryptographic keys.",
    "Direct factual retrieval from SP 800-130 title and executive scope."
))

candidates.append(make_candidate(
    "Q56",
    "In the public comments on NIST SP 800-133 Revision 3, what technical topics are reviewed regarding cryptographic key generation and entropy requirements?",
    "direct_factual",
    "NIST_SP_800-133",
    [],
    ["NIST_SP_800-133_txt_00001"],
    "The public comments on SP 800-133 Rev. 3 review cryptographic key generation methods, symmetric and asymmetric key generation algorithms, and the role of approved random bit generators and entropy sources.",
    "Direct factual retrieval from SP 800-133 public comments document scope."
))

candidates.append(make_candidate(
    "Q57",
    "What are the four SHA-3 derived functions specified in NIST SP 800-185?",
    "direct_factual",
    "NIST_SP_800-185",
    [],
    ["NIST_SP_800-185_txt_00001"],
    "NIST SP 800-185 specifies four SHA-3 derived functions: cSHAKE (customizable SHAKE), KMAC (KECCAK Message Authentication Code), TupleHash, and ParallelHash.",
    "Direct factual retrieval from SP 800-185 title and specification overview."
))

candidates.append(make_candidate(
    "Q58",
    "Which stateful hash-based signature schemes are approved for federal use in NIST SP 800-208?",
    "direct_factual",
    "NIST_SP_800-208",
    [],
    ["NIST_SP_800-208_txt_00001"],
    "NIST SP 800-208 recommends stateful hash-based signature schemes, specifically the Leighton-Micali Signature (LMS) system and the eXtended Merkle Signature Scheme (XMSS), along with their multi-tree variants (HSS and XMSS^MT).",
    "Direct factual retrieval from SP 800-208 specification scope."
))

candidates.append(make_candidate(
    "Q59",
    "What cryptographic functions are standardized under the Ascon family in NIST SP 800-232 for constrained environments?",
    "direct_factual",
    "NIST_SP_800-232",
    [],
    ["NIST_SP_800-232_txt_00001"],
    "NIST SP 800-232 standardizes Ascon-based lightweight cryptography, specifically Authenticated Encryption with Associated Data (AEAD), hash functions, and extendable output functions (XOF) optimized for constrained devices.",
    "Direct factual retrieval from SP 800-232 title and abstract."
))

candidates.append(make_candidate(
    "Q60",
    "What is the role of the Cardholder Unique Identifier (CHUID) data object in NIST SP 800-73 PIV card interfaces?",
    "direct_factual",
    "NIST_SP_800-73",
    [],
    ["NIST_SP_800-73_txt_00024"],
    "The Cardholder Unique Identifier (CHUID) is a mandatory PIV card-edge data object that uniquely identifies the card and cardholder to access control systems without requiring biometric authentication.",
    "Direct factual retrieval from SP 800-73 data object specifications."
))

candidates.append(make_candidate(
    "Q61",
    "Under NIST SP 800-76-2, what federal directive establishes the policy baseline for biometric specifications in PIV credentials?",
    "direct_factual",
    "NIST_SP_800-76",
    [],
    ["NIST_SP_800-76_txt_00006"],
    "Homeland Security Presidential Directive HSPD-12 (Policy for a Common Identification Standard for Federal Employees and Contractors) establishes the mandatory baseline for biometric specifications in PIV credentials.",
    "Direct factual retrieval from SP 800-76-2 Abstract."
))

candidates.append(make_candidate(
    "Q62",
    "What is the stated scope of NIST SP 800-78-5 regarding cryptographic algorithms for Personal Identity Verification?",
    "direct_factual",
    "NIST_SP_800-78",
    [],
    ["NIST_SP_800-78_txt_00001"],
    "NIST SP 800-78-5 specifies the cryptographic algorithms and minimum key sizes required for PIV card credentials, covering PIV authentication, digital signatures, key establishment, and card management.",
    "Direct factual retrieval from SP 800-78-5 title and scope."
))

candidates.append(make_candidate(
    "Q63",
    "In NIST SP 800-79-3, what is the primary purpose of guidelines for PIV Card Issuing (PCI) organizations?",
    "direct_factual",
    "NIST_SP_800-79",
    [],
    ["NIST_SP_800-79_txt_00026"],
    "NIST SP 800-79-3 provides accreditation guidelines and assessment controls for PIV Card Issuing (PCI) organizations to ensure they maintain sufficient operational and physical security when issuing PIV credentials.",
    "Direct factual retrieval from SP 800-79-3 Table of Contents and scope."
))

candidates.append(make_candidate(
    "Q64",
    "What policy framework under HSPD-12 governs the issuance of Derived PIV Credentials in NIST SP 800-157?",
    "direct_factual",
    "NIST_SP_800-157",
    [],
    ["NIST_SP_800-157_txt_00006"],
    "OMB policy under HSPD-12 governs Derived PIV Credentials, enabling federal agencies to issue cryptographically secure credentials on mobile devices derived from an authentic, physically issued PIV card.",
    "Direct factual retrieval from SP 800-157 Section II."
))

candidates.append(make_candidate(
    "Q65",
    "What is the objective of NIST SP 800-217 regarding Personal Identity Verification (PIV) federation?",
    "direct_factual",
    "NIST_SP_800-217",
    [],
    ["NIST_SP_800-217_txt_00001"],
    "NIST SP 800-217 provides guidelines for federating PIV identity credentials, allowing secure cross-agency and external entity authentication using PIV credentials without duplicate credential issuance.",
    "Direct factual retrieval from SP 800-217 title and executive summary."
))

candidates.append(make_candidate(
    "Q66",
    "What is the primary objective of building a cybersecurity learning program as described in NIST SP 800-50?",
    "direct_factual",
    "NIST_SP_800-50",
    [],
    ["NIST_SP_800-50_txt_00011"],
    "NIST SP 800-50 provides guidance for federal agencies to design, develop, implement, and maintain a comprehensive organizational cybersecurity awareness and training program across the entire learning continuum.",
    "Direct factual retrieval from SP 800-50 Abstract."
))

candidates.append(make_candidate(
    "Q67",
    "What is the core focus of NIST SP 800-221A in measuring enterprise risk?",
    "direct_factual",
    "NIST_SP_800-221",
    [],
    ["NIST_SP_800-221_txt_00001"],
    "NIST SP 800-221A establishes the Information and Communications Technology (ICT) Risk Outcomes framework, providing a structure and catalog of outcomes for assessing and managing ICT risk across organizations.",
    "Direct factual retrieval from SP 800-221A title and overview."
))

candidates.append(make_candidate(
    "Q68",
    "In NIST SP 800-190, what are the primary architectural layers that comprise application container environments?",
    "direct_factual",
    "NIST_SP_800-190",
    [],
    ["NIST_SP_800-190_txt_00003"],
    "NIST SP 800-190 addresses the core architectural layers of container environments: container images, registries, orchestrators, containers, and the host operating system.",
    "Direct factual retrieval from SP 800-190 introductory architecture description."
))

candidates.append(make_candidate(
    "Q69",
    "What core security capabilities and integration roles are defined for APIs in cloud-native architectures per NIST SP 800-228?",
    "direct_factual",
    "NIST_SP_800-228",
    [],
    ["NIST_SP_800-228_txt_00011"],
    "NIST SP 800-228 defines that modern cloud-native systems rely on APIs for internal microservice and external integration, requiring explicit API protection mechanisms including gateway authentication, schema validation, and authorization controls.",
    "Direct factual retrieval from SP 800-228 Abstract on Page 5."
))

# =========================================================================
# GROUP 5: CONCEPTUAL (14 questions: Q70 - Q83)
# =========================================================================

candidates.append(make_candidate(
    "Q70",
    "In NIST SP 800-107 Revision 1, what are the fundamental security properties expected of cryptographic hash functions?",
    "conceptual",
    "NIST_SP_800-107",
    [],
    ["NIST_SP_800-107_txt_00001"],
    "NIST SP 800-107 details the foundational security properties of cryptographic hash functions: pre-image resistance (one-way property), second pre-image resistance (weak collision resistance), and collision resistance (strong collision resistance).",
    "Conceptual retrieval on hash algorithm security properties in SP 800-107 Rev. 1."
))

candidates.append(make_candidate(
    "Q71",
    "What strategic considerations guide federal agencies in selecting and transitioning cryptographic standards per NIST SP 800-175B?",
    "conceptual",
    "NIST_SP_800-175",
    [],
    ["NIST_SP_800-175_txt_00001"],
    "NIST SP 800-175B provides strategic guidance for federal agencies on understanding cryptographic mechanisms, assessing algorithm security strengths over time, and adopting approved standards to protect federal information.",
    "Conceptual retrieval on cryptographic standards adoption from SP 800-175B."
))

candidates.append(make_candidate(
    "Q72",
    "How does NIST SP 800-178 compare policy expressiveness between XACML and Next Generation Access Control (NGAC)?",
    "conceptual",
    "NIST_SP_800-178",
    [],
    ["NIST_SP_800-178_txt_00008"],
    "NIST SP 800-178 provides an in-depth comparison of Attribute Based Access Control (ABAC) standards, explaining that both XACML and NGAC provide standardized ways for expressing and enforcing diverse access control policies, but use fundamentally different underlying models (rule-based attribute evaluation vs. graph-based policy relations).",
    "Conceptual retrieval on ABAC standards comparison from SP 800-178 Abstract on Page 4."
))

candidates.append(make_candidate(
    "Q73",
    "In NIST SP 800-205, why are dynamic contextual attributes critical for modern access control systems?",
    "conceptual",
    "NIST_SP_800-205",
    [],
    ["NIST_SP_800-205_txt_00001"],
    "NIST SP 800-205 discusses attribute considerations in access control, emphasizing that dynamic attributes (e.g. time, physical location, network threat state) enable real-time risk-adaptive authorization decisions.",
    "Conceptual retrieval from SP 800-205 executive summary."
))

candidates.append(make_candidate(
    "Q74",
    "What theoretical guarantees and trade-offs are evaluated using the epsilon privacy budget in differential privacy per NIST SP 800-226?",
    "conceptual",
    "NIST_SP_800-226",
    [],
    ["NIST_SP_800-226_txt_00001"],
    "NIST SP 800-226 explains that differential privacy provides mathematical bounds on individual privacy leakage, where epsilon controls the trade-off between privacy protection (lower epsilon) and analytical utility (higher epsilon).",
    "Conceptual retrieval from SP 800-226 guidelines."
))

candidates.append(make_candidate(
    "Q75",
    "What are the foundational building blocks that comprise the Network of Things (NoT) conceptual model in NIST SP 800-183?",
    "conceptual",
    "NIST_SP_800-183",
    [],
    ["NIST_SP_800-183_txt_00008"],
    "NIST SP 800-183 defines the five core primitives of the Network of Things (NoT): sensors, aggregators, communication channels, external utilities (e-utilities), and decision triggers.",
    "Conceptual retrieval from SP 800-183 Keywords and foundational primitives."
))

candidates.append(make_candidate(
    "Q76",
    "How does NIST SP 800-215 frame the transition from static perimeter network defenses to software-defined enterprise landscapes?",
    "conceptual",
    "NIST_SP_800-215",
    [],
    ["NIST_SP_800-215_txt_00001"],
    "NIST SP 800-215 details the evolution of enterprise network landscapes, moving from fixed IP-based boundary perimeters to dynamic, software-defined perimeters and microsegmentation consistent with zero trust principles.",
    "Conceptual retrieval from SP 800-215 title and scope."
))

candidates.append(make_candidate(
    "Q77",
    "What conceptual model does the Bugs Framework (BF) in NIST SP 800-231 introduce to formalize software vulnerabilities?",
    "conceptual",
    "NIST_SP_800-231",
    [],
    ["NIST_SP_800-231_txt_00001"],
    "NIST SP 800-231 introduces the Bugs Framework (BF), a formal taxonomy that models software execution bugs, faults, and failure chains through structured cause-and-effect transitions.",
    "Conceptual retrieval from SP 800-231 title and abstract."
))

candidates.append(make_candidate(
    "Q78",
    "What strategic research priorities and program milestones are highlighted in the NIST Cybersecurity and Privacy FY 2024 Annual Report (SP 800-236)?",
    "conceptual",
    "NIST_SP_800-236",
    [],
    ["NIST_SP_800-236_txt_00001"],
    "NIST SP 800-236 highlights federal program milestones across post-quantum cryptography, Zero Trust Architecture implementation, cybersecurity supply chain risk management, and privacy engineering.",
    "Conceptual retrieval from SP 800-236 Annual Report overview."
))

candidates.append(make_candidate(
    "Q79",
    "In the NIST FY 2025 Cybersecurity and Privacy Annual Report (SP 800-238), what emerging technology areas are identified for federal standards development?",
    "conceptual",
    "NIST_SP_800-238",
    [],
    ["NIST_SP_800-238_txt_00002"],
    "NIST SP 800-238 outlines emerging focus areas including artificial intelligence security, quantum-resistant algorithms, privacy-enhancing technologies, and cloud-native infrastructure protection.",
    "Conceptual retrieval from SP 800-238 Annual Report."
))

candidates.append(make_candidate(
    "Q80",
    "In the pre-draft public comments on NIST SP 800-197A, what international stakeholder perspectives are represented regarding lightweight block ciphers?",
    "conceptual",
    "NIST_SP_800-197",
    [],
    ["NIST_SP_800-197_txt_00001"],
    "The pre-draft comments represent international and federal perspectives (including UK NCSC, NSA, and DOE) assessing security margins, implementation complexity, and standardization criteria for lightweight block ciphers.",
    "Conceptual retrieval from SP 800-197A comment summary."
))

candidates.append(make_candidate(
    "Q81",
    "What is the primary purpose of vulnerability naming schemes like CVE as outlined in NIST SP 800-51 Revision 1?",
    "conceptual",
    "NIST_SP_800-51",
    [],
    ["NIST_SP_800-51_txt_00002"],
    "NIST SP 800-51 Rev. 1 explains that standardized vulnerability naming schemes (such as CVE) enable unambiguous cross-tool communication, automated security tracking, and consistent correlation of software flaws across databases.",
    "Conceptual retrieval from SP 800-51 Rev. 1 Recommendations."
))

candidates.append(make_candidate(
    "Q82",
    "What types of non-invasive physical attack mitigations are evaluated under CMVP test metrics in NIST SP 800-140F Revision 1?",
    "conceptual",
    "NIST_SP_800-140",
    [],
    ["NIST_SP_800-140_txt_00001"],
    "NIST SP 800-140F Rev. 1 defines CMVP test metrics for non-invasive attacks against cryptographic modules, evaluating mitigation techniques against side-channel analysis including power analysis and timing attacks.",
    "Conceptual retrieval from SP 800-140F Rev. 1 scope."
))

candidates.append(make_candidate(
    "Q83",
    "How does NIST SP 800-223 characterize security and threat modeling challenges in High-Performance Computing (HPC) clusters?",
    "conceptual",
    "NIST_SP_800-223",
    [],
    ["NIST_SP_800-223_txt_00012"],
    "NIST SP 800-223 explains that HPC systems feature unique threat surfaces due to massive multi-node interconnects, shared batch job schedulers, parallel file systems, and specialized hardware accelerators.",
    "Conceptual retrieval from SP 800-223 Abstract."
))

# =========================================================================
# GROUP 6: TECHNICAL / CONTROL-SPECIFIC (11 questions: Q84 - Q94)
# =========================================================================

candidates.append(make_candidate(
    "Q84",
    "What validation assurances are required when generating digital signature keys according to NIST SP 800-89?",
    "technical_control",
    "NIST_SP_800-89",
    [],
    ["NIST_SP_800-89_txt_00001"],
    "NIST SP 800-89 specifies assurance requirements for digital signature applications, including validating that key generation parameters comply with approved standards and verifying that private keys are generated with adequate entropy.",
    "Technical control retrieval from SP 800-89 title and scope."
))

candidates.append(make_candidate(
    "Q85",
    "Under NIST SP 800-38G Revision 1, what methods for Format-Preserving Encryption (FPE) are specified for block cipher modes?",
    "technical_control",
    "NIST_SP_800-38",
    [],
    ["NIST_SP_800-38_txt_00001"],
    "NIST SP 800-38G Rev. 1 specifies Format-Preserving Encryption (FPE) modes FF1 and FF3-1, allowing plaintext data (such as credit card or Social Security numbers) to be encrypted into ciphertext of the identical length and character format.",
    "Technical control retrieval from SP 800-38G Rev. 1 title."
))

candidates.append(make_candidate(
    "Q86",
    "What pair-wise key establishment schemes are recommended in NIST SP 800-56B Revision 2?",
    "technical_control",
    "NIST_SP_800-56",
    [],
    ["NIST_SP_800-56_txt_00001"],
    "NIST SP 800-56B Rev. 2 specifies pair-wise key establishment schemes based on integer factorization cryptography (RSA-based key agreement and key transport mechanisms).",
    "Technical control retrieval from SP 800-56B Rev. 2 specification."
))

candidates.append(make_candidate(
    "Q87",
    "What elliptic curve domain parameter recommendations are established in NIST SP 800-186 for discrete logarithm cryptography?",
    "technical_control",
    "NIST_SP_800-186",
    [],
    ["NIST_SP_800-186_txt_00001"],
    "NIST SP 800-186 recommends approved elliptic curve domain parameters, specifying both traditional Weierstrass curves (P-256, P-384, P-521) and Edwards curves (Ed25519, Ed448) for federal cryptographic applications.",
    "Technical control retrieval from SP 800-186 specifications."
))

candidates.append(make_candidate(
    "Q88",
    "What recommendations are provided in NIST SP 800-132 for password-based key derivation functions (PBKDF)?",
    "technical_control",
    "NIST_SP_800-132",
    [],
    ["NIST_SP_800-132_txt_00001"],
    "NIST SP 800-132 defines recommendations for PBKDF2, specifying minimum salt lengths (at least 128 bits), iteration counts, and approved underlying pseudo-random functions (HMAC) to mitigate brute-force dictionary attacks.",
    "Technical control retrieval from SP 800-132 specifications."
))

candidates.append(make_candidate(
    "Q89",
    "What verification and test methods are established in NIST SP 800-192 for access control policies and models?",
    "technical_control",
    "NIST_SP_800-192",
    [],
    ["NIST_SP_800-192_txt_00001"],
    "NIST SP 800-192 provides formal methods and test algorithms for verifying access control policies, ensuring completeness, consistency, and freedom from conflicting, redundant, or unreachable authorization rules.",
    "Technical control retrieval from SP 800-192 title and abstract."
))

candidates.append(make_candidate(
    "Q90",
    "What technical specifications govern the Keyed-Hash Message Authentication Code (HMAC) in NIST SP 800-224?",
    "technical_control",
    "NIST_SP_800-224",
    [],
    ["NIST_SP_800-224_txt_00002"],
    "NIST SP 800-224 specifies the HMAC construction using approved cryptographic hash functions (such as SHA-2 and SHA-3), defining key lengths, inner and outer padding (ipad/opad), and truncation rules.",
    "Technical control retrieval from SP 800-224 specification."
))

candidates.append(make_candidate(
    "Q91",
    "In NIST SP 800-153, what active monitoring mechanisms are recommended to detect rogue wireless access points?",
    "technical_control",
    "NIST_SP_800-153",
    [],
    ["NIST_SP_800-153_txt_00036"],
    "NIST SP 800-153 Section 3.1.1 recommends active attack monitoring using Wireless Intrusion Detection Systems (WIDS) and radio frequency sensors to identify rogue access points, unauthorized ad-hoc networks, and man-in-the-middle attacks.",
    "Technical control retrieval from SP 800-153 Section 3.1.1."
))

candidates.append(make_candidate(
    "Q92",
    "What specific technical challenges and preservation techniques are identified for handheld digital device forensics in NIST SP 800-72?",
    "technical_control",
    "NIST_SP_800-72",
    [],
    ["NIST_SP_800-72_txt_00002"],
    "NIST SP 800-72 outlines technical procedures for preserving volatile RAM in mobile handhelds, preventing device battery depletion that causes data loss, and isolating cellular and infrared interfaces.",
    "Technical control retrieval from SP 800-72 recommendations."
))

candidates.append(make_candidate(
    "Q93",
    "What architectural tiers comprise the NIST Cloud Computing Forensic Reference Architecture in NIST SP 800-201?",
    "technical_control",
    "NIST_SP_800-201",
    [],
    ["NIST_SP_800-201_txt_00001"],
    "NIST SP 800-201 defines the Cloud Forensic Reference Architecture, identifying structural challenges across cloud deployment models and mapping forensic data collection to provider vs tenant responsibilities.",
    "Technical control retrieval from SP 800-201 title and scope."
))

candidates.append(make_candidate(
    "Q94",
    "How does the High-Performance Computing (HPC) Security Overlay in NIST SP 800-234 adapt security controls for parallel computing environments?",
    "technical_control",
    "NIST_SP_800-234",
    [],
    ["NIST_SP_800-234_txt_00012"],
    "NIST SP 800-234 establishes security control overlay modifications to accommodate HPC workflows, adapting authentication, job scheduling, and network segmentation controls without degrading high-throughput compute performance.",
    "Technical control retrieval from SP 800-234 Abstract."
))

# =========================================================================
# GROUP 7: SCENARIO-BASED (10 questions: Q95 - Q104)
# =========================================================================

candidates.append(make_candidate(
    "Q95",
    "In an enterprise telework deployment, what client endpoint security controls are recommended in NIST SP 800-114 Revision 1 for employee BYOD devices?",
    "scenario_based",
    "NIST_SP_800-114",
    [],
    ["NIST_SP_800-114_txt_00001"],
    "NIST SP 800-114 Rev. 1 specifies that telework employee devices must maintain host firewall protections, updated antivirus signatures, automated OS patching, and encrypted VPN tunnels before connecting to enterprise networks.",
    "Scenario-based retrieval from SP 800-114 Rev. 1 user guidance."
))

candidates.append(make_candidate(
    "Q96",
    "When designing a physical access control system for secure federal facilities, what PIV authentication mechanisms does NIST SP 800-116 Revision 1 recommend for high-security perimeters?",
    "scenario_based",
    "NIST_SP_800-116",
    [],
    ["NIST_SP_800-116_txt_00001"],
    "NIST SP 800-116 Rev. 1 specifies that high-security facility perimeters should enforce multi-factor authentication by combining PIV cryptographic authentication (PKI-based challenge-response) with a PIV PIN or on-card biometric verification.",
    "Scenario-based retrieval from SP 800-116 Rev. 1 guidelines."
))

candidates.append(make_candidate(
    "Q97",
    "During an incident response investigation involving a seized smartphone, what evidence acquisition rules does NIST SP 800-101 Revision 1 specify to maintain evidence integrity?",
    "scenario_based",
    "NIST_SP_800-101",
    [],
    ["NIST_SP_800-101_txt_00001"],
    "NIST SP 800-101 Rev. 1 specifies that responders must immediately isolate the mobile device using Faraday shielding (blocking RF signals to prevent remote wiping), maintain battery power, and perform validated forensic imaging.",
    "Scenario-based retrieval from SP 800-101 Rev. 1 guidelines."
))

candidates.append(make_candidate(
    "Q98",
    "In a containerized application deployment, what defensive measures does NIST SP 800-190 recommend to prevent host OS kernel exploitation from compromised containers?",
    "scenario_based",
    "NIST_SP_800-190",
    [],
    ["NIST_SP_800-190_txt_00144"],
    "NIST SP 800-190 recommends restricting container root privileges, enforcing seccomp system call filtering, enabling AppArmor/SELinux mandatory access controls, and isolating high-risk container workloads on dedicated cluster nodes.",
    "Scenario-based retrieval from SP 800-190 container runtime defense."
))

candidates.append(make_candidate(
    "Q99",
    "When deploying cloud-native microservices, what role does an API gateway play in controlling exposure and authenticating external callers per NIST SP 800-228?",
    "scenario_based",
    "NIST_SP_800-228",
    [],
    ["NIST_SP_800-228_txt_00032"],
    "NIST SP 800-228 specifies that second- and third-party APIs are typically exposed to external callers via an API gateway, which serves as the enforcement boundary for mutual authentication, token verification, and exposure control.",
    "Scenario-based retrieval from SP 800-228 Section 1 on Page 12."
))

candidates.append(make_candidate(
    "Q100",
    "In an enterprise cloud migration, how should an organization structure its Attribute Based Access Control (ABAC) policies to manage cross-tenant data access per NIST SP 800-210?",
    "scenario_based",
    "NIST_SP_800-210",
    [],
    ["NIST_SP_800-210_txt_00001"],
    "NIST SP 800-210 recommends defining standardized tenant ID attributes, resource sensitivity tags, and dynamic environmental rules evaluated at centralized Policy Decision Points to prevent unauthorized cross-tenant data access.",
    "Scenario-based retrieval from SP 800-210 cloud access control."
))

candidates.append(make_candidate(
    "Q101",
    "In a shared multi-tenant AI cluster, what security controls does NIST SP 800-239 specify to protect GPU memory and prevent cross-job data leakage?",
    "scenario_based",
    "NIST_SP_800-239",
    [],
    ["NIST_SP_800-239_txt_00001"],
    "NIST SP 800-239 specifies that AI data centers must enforce hardware-level tenant isolation, zero out GPU and accelerator memory between batch workloads, and validate model weight integrity to prevent data leakage.",
    "Scenario-based retrieval from SP 800-239 AI cluster security analysis."
))

candidates.append(make_candidate(
    "Q102",
    "When integrating supply chain security into an enterprise DevSecOps pipeline, what security gates does NIST SP 800-204D recommend prior to production release?",
    "scenario_based",
    "NIST_SP_800-204",
    [],
    ["NIST_SP_800-204_txt_00054"],
    "NIST SP 800-204D recommends enforcing automated build security gates: Software Bill of Materials (SBOM) generation, dependency vulnerability verification, static source code security scanning, and cryptographic artifact signing.",
    "Scenario-based retrieval from SP 800-204D Section 5.1.1."
))

candidates.append(make_candidate(
    "Q103",
    "When an agency establishes an enterprise Vulnerability Disclosure Policy (VDP) per NIST SP 800-216, what procedures should govern initial report intake and triage?",
    "scenario_based",
    "NIST_SP_800-216",
    [],
    ["NIST_SP_800-216_txt_00001"],
    "NIST SP 800-216 recommends publishing clear scope rules, establishing encrypted submission channels, acknowledging receipt within established timelines, and maintaining objective risk triage procedures.",
    "Scenario-based retrieval from SP 800-216 disclosure guidelines."
))

candidates.append(make_candidate(
    "Q104",
    "During an enterprise risk assessment, how should an organization apply the ICT Risk Outcomes framework in NIST SP 800-221A to evaluate systemic supply chain disruptions?",
    "scenario_based",
    "NIST_SP_800-221",
    [],
    ["NIST_SP_800-221_txt_00001"],
    "NIST SP 800-221A recommends evaluating risks against defined ICT outcome categories (e.g. governance, operational disruption, compliance failure) to measure the systemic business impact of supplier failures.",
    "Scenario-based retrieval from SP 800-221A risk outcome assessment."
))

print(f"Constructed all {len(candidates)} candidate questions successfully!")

# Verify category distribution of candidates
cat_counts = Counter(c["category"] for c in candidates)
print("\nCandidate category distribution:")
for cat, cnt in cat_counts.items():
    print(f"  {cat}: {cnt}")

# Load original 36 questions from v2
with open("data/evaluation/retrieval_ground_truth_v2.json", "r", encoding="utf-8") as f:
    gt_v2 = json.load(f)

print(f"\nLoaded {len(gt_v2)} original questions from retrieval_ground_truth_v2.json.")

# Combine into 100 questions dataset
combined = {}
# 1. Add original 36 questions exactly
for qid, qdata in gt_v2.items():
    combined[qid] = qdata

# 2. Add 64 new candidate questions
for c in candidates:
    combined[c["question_id"]] = c

print(f"Combined total questions: {len(combined)}")
assert len(combined) == 100, f"Expected 100 questions, got {len(combined)}"

# Write output file
out_path = Path("data/evaluation/retrieval_ground_truth_100q_candidates.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(combined, f, indent=2)

print(f"\nSuccessfully wrote {out_path} ({out_path.stat().st_size} bytes).")
