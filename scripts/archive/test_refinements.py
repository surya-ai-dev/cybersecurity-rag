import json
from pathlib import Path

# Load all chunks from corpus
all_chunks = {}
for p in Path('data').glob('chunks_*/**/*.jsonl'):
    with open(p, 'r', encoding='utf-8') as f:
        for line in f:
            c = json.loads(line)
            all_chunks[c['chunk_id']] = c

# Full map of refinements for any candidate question or baseline question needing update
refinements = {
    # Task 1: Q4 & Q17 de-coupling
    'Q4': {
        'relevant_chunks': ['NIST_SP_800-144_txt_00055'],
        'verification_status': 'verified',
        'rationale': 'Directly explains why cloud governance is essential (shadow IT risks, bypassing capital expenditure controls under operational expenses, regulatory and privacy exposure).'
    },
    'Q17': {
        'relevant_chunks': ['NIST_SP_800-144_txt_00056'],
        'verification_status': 'verified',
        'rationale': 'Directly specifies key operational governance practices for public cloud (extending organizational policies/standards to cloud, negotiating audit rights, defining provider roles/responsibilities, and dynamic risk management).'
    },
    # Table questions: Q41 - Q45 verified against original table chunks
    'Q41': {
        'verification_status': 'verified',
        'verification_notes': 'Table chunk from comment matrix on Page 14 specifically recording stakeholder feedback on legacy-use algorithms.'
    },
    'Q42': {
        'verification_status': 'verified',
        'verification_notes': 'Table chunk from HPC Overlay on Page 10 specifying zone allocations for AC-2 and AC-3 across compute and storage zones.'
    },
    'Q43': {
        'verification_status': 'verified',
        'verification_notes': 'Table chunk on Page 46 specifying requirement PR:5.1 mapped to AC-2, mandating 5 distinct FCKMS roles.'
    },
    'Q44': {
        'verification_status': 'verified',
        'verification_notes': 'Table chunk on Page 17 defining SSDF Practice PO.1, Task PO.1.1, and notional implementation examples.'
    },
    'Q45': {
        'verification_status': 'verified',
        'verification_notes': 'Table chunk on Page 71 categorizing all NIST SP 800-53 control families into Technical, Operational, and Management classes.'
    },
    # Task 3: Q46, Q68, Q98 resolved from English NIST documents
    'Q46': {
        'question': 'How do secure build tasks and attestation mechanisms in DevSecOps CI/CD pipelines (NIST SP 800-204D) integrate with Software Bill of Materials (SBOM) supply chain transparency requirements in NIST SP 800-161 Revision 1?',
        'category': 'cross_document',
        'primary_document': 'NIST_SP_800-204',
        'supporting_documents': ['NIST_SP_800-161'],
        'relevant_chunk_ids': ['NIST_SP_800-204_txt_00054', 'NIST_SP_800-161_txt_00777'],
        'expected_answer_summary': 'NIST SP 800-204D mandates secure isolated build environments, policy enforcement engines, and automated generation of build attestations during CI/CD execution, which operationalize NIST SP 800-161 Rev. 1 requirements for formal Software Bills of Materials (SBOMs) to verify component provenance, track open source dependencies, and detect supply chain tampering.',
        'source_section': '5.1.1. Secure Build | Glossary: Software Bill of Materials',
        'source_page': '20, 309',
        'verification_status': 'verified',
        'verification_notes': 'Synthesizes DevSecOps CI/CD build security tasks (SP 800-204D Section 5.1.1) with C-SCRM Software Bill of Materials supply chain verification (SP 800-161 Rev. 1 Glossary & Section 3).'
    },
    'Q68': {
        'question': 'In NIST SP 800-233, what are the primary data plane proxy models (architectures) defined for service mesh implementations in cloud-native applications?',
        'category': 'direct_factual',
        'primary_document': 'NIST_SP_800-233',
        'supporting_documents': [],
        'relevant_chunk_ids': ['NIST_SP_800-233_txt_00035', 'NIST_SP_800-233_txt_00036'],
        'expected_answer_summary': 'NIST SP 800-233 defines four primary data plane proxy architectures (DPAs): DPA-1 (Sidecar model: dedicated L4/L7 proxy per service instance), DPA-2 (Shared L4 node proxy with dedicated L7 per service), DPA-3 (Shared L4 and L7 proxy per node), and DPA-4 (Proxyless / gRPC library model with L4/L7 in application code).',
        'source_section': '3. Proxy Models (Data Plane Architectures) in Service Mesh Implementations',
        'source_page': '17',
        'verification_status': 'verified',
        'verification_notes': 'Direct factual retrieval from NIST SP 800-233 Section 3 defining the four data plane proxy models.'
    },
    'Q98': {
        'question': 'When deploying cloud-native applications with high-risk profiles per NIST SP 800-233, what specific service mesh capabilities and cryptographic isolation requirements must be enforced in the data plane?',
        'category': 'scenario_based',
        'primary_document': 'NIST_SP_800-233',
        'supporting_documents': [],
        'relevant_chunk_ids': ['NIST_SP_800-233_txt_00093'],
        'expected_answer_summary': 'For high-risk profile applications, NIST SP 800-233 mandates HIGH-REQ1 (full user-to-resource access control in addition to mutual authentication and service-to-service authorization), HIGH-REQ2 (mandatory L7 authorization with deep request inspection), and HIGH-REQ3 (cryptographic isolation requiring unique identities, per-service keys, and dedicated proxies to prevent cross-tenant key compromise).',
        'source_section': '6.3 Cloud-Native Applications With High Risk Profiles',
        'source_page': '40',
        'verification_status': 'verified',
        'verification_notes': 'Scenario-based retrieval from NIST SP 800-233 Section 6.3 high-risk cloud-native application requirements.'
    },
    # Cross-document title chunk refinements (Q47 - Q51)
    'Q47': {
        'relevant_chunk_ids': ['NIST_SP_800-207_txt_00030', 'NIST_SP_800-210_txt_00028'],
        'source_section': '3.1 Core Zero Trust Architecture Logical Components | 2 Cloud Access Control Characteristics',
        'source_page': '9, 11',
        'verification_status': 'verified',
        'verification_notes': 'Synthesizes Zero Trust PEP/PDP logical architecture with SP 800-210 Section 2 cloud access control characteristics and multi-tenant virtualization mediation.'
    },
    'Q48': {
        'relevant_chunk_ids': ['NIST_SP_800-63_txt_00081', 'NIST_SP_800-116_txt_00067'],
        'source_section': '5.1.3 Authenticator Assurance Level 3 | 4.3 Selection of PIV Authentication Factors',
        'source_page': '38, 24',
        'verification_status': 'verified',
        'verification_notes': 'Synthesizes AAL3 hardware cryptographic authenticator requirements with SP 800-116 Section 4.3 risk-based PIV authentication factor selection for facility access.'
    },
    'Q49': {
        'relevant_chunk_ids': ['NIST_SP_800-130_txt_00063', 'NIST_SP_800-57_txt_00033'],
        'source_section': '2.10 CKMS Framework Components and Devices | 8.3 Cryptographic Key Management Lifecycle',
        'source_page': '21, 35',
        'verification_status': 'verified',
        'verification_notes': 'Synthesizes CKMS Framework components/devices (SP 800-130 Section 2.10) with SP 800-57 Part 1 key management lifecycle phases.'
    },
    'Q50': {
        'relevant_chunk_ids': ['NIST_SP_800-216_txt_00061', 'NIST_SP_800-218_txt_00029'],
        'source_section': '3.2.4. Development of Vulnerability Disclosure Handling Procedures | Respond to Vulnerabilities (RV)',
        'source_page': '27, 32',
        'verification_status': 'verified',
        'verification_notes': 'Synthesizes SP 800-216 Section 3.2.4 internal vulnerability handling procedures with SSDF Practice RV.1 / RV.2 vulnerability response.'
    },
    'Q51': {
        'relevant_chunk_ids': ['NIST_SP_800-61_txt_00087', 'NIST_SP_800-101_txt_00060'],
        'source_section': '3.3.2 Evidence Handling | 4.1 Securing and Evaluating the Scene',
        'source_page': '37, 37',
        'verification_status': 'verified',
        'verification_notes': 'Synthesizes incident evidence preservation/chain of custody (SP 800-61 Section 3.3.2) with mobile device evidence handling rules during seizure (SP 800-101 Section 4.1).'
    },
    # Multi-chunk reasoning (Q52, Q53)
    'Q52': {
        'relevant_chunk_ids': ['NIST_SP_800-53_txt_00280'],
        'source_section': 'CA-7 CONTINUOUS MONITORING',
        'source_page': '117',
        'verification_status': 'verified',
        'verification_notes': 'Direct retrieval from SP 800-53 control CA-7 specifying system-level continuous monitoring strategy and ongoing authorization.'
    },
    'Q53': {
        'relevant_chunk_ids': ['NIST_SP_800-161_txt_00380'],
        'source_section': 'SA-1 POLICY AND PROCEDURES',
        'source_page': '151',
        'verification_status': 'verified',
        'verification_notes': 'Direct retrieval from SP 800-161 control SA-1 Supplemental C-SCRM Guidance on contractual supplier clauses throughout acquisition lifecycle.'
    },
    # Direct Factual (Q54 - Q69)
    'Q54': {
        'relevant_chunk_ids': ['NIST_SP_800-57_txt_00012'],
        'source_section': 'Editorial Comment 1 (Page 8)',
        'source_page': '8',
        'verification_status': 'verified',
        'verification_notes': 'Direct factual retrieval from SP 800-57 Part 1 Rev. 6 public comments identifying emerging key management terms BYOK and KEM.'
    },
    'Q55': {
        'relevant_chunk_ids': ['NIST_SP_800-130_txt_00043'],
        'source_section': '1. Introduction',
        'source_page': '9',
        'verification_status': 'verified',
        'verification_notes': 'Direct factual retrieval from SP 800-130 Section 1 defining the primary scope and purpose of the CKMS design framework.'
    },
    'Q56': {
        'relevant_chunk_ids': ['NIST_SP_800-133_txt_00134'],
        'source_section': 'Public Comments: COMMENT 4 (Section 4.2.2)',
        'source_page': '64',
        'verification_status': 'verified',
        'verification_notes': 'Direct factual retrieval from SP 800-133 Rev. 3 public comment 4 detailing entropy sources and key derivation requirements.'
    },
    'Q57': {
        'relevant_chunk_ids': ['NIST_SP_800-185_txt_00017'],
        'source_section': '1 Introduction',
        'source_page': '7',
        'verification_status': 'verified',
        'verification_notes': 'Direct factual retrieval from SP 800-185 Section 1 defining cSHAKE, KMAC, TupleHash, and ParallelHash.'
    },
    'Q58': {
        'relevant_chunk_ids': ['NIST_SP_800-208_txt_00024'],
        'source_section': '1 Introduction',
        'source_page': '10',
        'verification_status': 'verified',
        'verification_notes': 'Direct factual retrieval from SP 800-208 Section 1 specifying LMS and XMSS stateful hash-based signature schemes.'
    },
    'Q59': {
        'relevant_chunk_ids': ['NIST_SP_800-232_txt_00020'],
        'source_section': '1. Introduction',
        'source_page': '12',
        'verification_status': 'verified',
        'verification_notes': 'Direct factual retrieval from SP 800-232 Section 1 specifying the Ascon family of algorithms (AEAD, hashing, XOF).'
    },
    'Q60': {
        'relevant_chunk_ids': ['NIST_SP_800-73_txt_00108'],
        'source_section': 'Appendix A. PIV Data Model',
        'source_page': '48',
        'verification_status': 'verified',
        'verification_notes': 'Direct factual retrieval from SP 800-73 Appendix A defining Cardholder Unique Identifier (CHUID) specifications.'
    },
    'Q61': {
        'relevant_chunk_ids': ['NIST_SP_800-76_txt_00006'],
        'source_section': 'Abstract',
        'source_page': '4',
        'verification_status': 'verified',
        'verification_notes': 'Direct factual retrieval from SP 800-76-2 Abstract identifying HSPD-12 as the policy baseline for biometric specifications.'
    },
    'Q62': {
        'relevant_chunk_ids': ['NIST_SP_800-78_txt_00023'],
        'source_section': '1.4. Document Overview',
        'source_page': '10',
        'verification_status': 'verified',
        'verification_notes': 'Direct factual retrieval from SP 800-78-5 Section 1.4 defining the scope of cryptographic algorithms and key sizes for PIV.'
    },
    'Q63': {
        'relevant_chunk_ids': ['NIST_SP_800-79_txt_00092'],
        'source_section': 'Issuer Controls Assessment and the Authorization Decision Process',
        'source_page': '37',
        'verification_status': 'verified',
        'verification_notes': 'Direct factual retrieval from SP 800-79-3 on assessor activities and issuer controls for PIV Card Issuing (PCI) organizations.'
    },
    'Q64': {
        'relevant_chunk_ids': ['NIST_SP_800-157_txt_00006'],
        'source_section': 'II. Managing Identities, Credentials, and Access in Modern Government',
        'source_page': '3',
        'verification_status': 'verified',
        'verification_notes': 'Direct factual retrieval from SP 800-157 Section II on HSPD-12 policy baseline for Derived PIV Credentials.'
    },
    'Q65': {
        'relevant_chunk_ids': ['NIST_SP_800-217_txt_00022'],
        'source_section': '1.2. Purpose and Scope',
        'source_page': '10',
        'verification_status': 'verified',
        'verification_notes': 'Direct factual retrieval from SP 800-217 Section 1.2 defining the objectives of PIV identity account federation.'
    },
    'Q66': {
        'relevant_chunk_ids': ['NIST_SP_800-50_txt_00078'],
        'source_section': '2.5.1. All Users',
        'source_page': '36',
        'verification_status': 'verified',
        'verification_notes': 'Direct factual retrieval from SP 800-50 Section 2.5.1 on CPLP participation and mandatory security awareness training.'
    },
    'Q67': {
        'relevant_chunk_ids': ['NIST_SP_800-221_txt_00024'],
        'source_section': 'Information and Communications Technology Areas',
        'source_page': '9',
        'verification_status': 'verified',
        'verification_notes': 'Direct factual retrieval from SP 800-221A Section on ICT Areas defining the core focus of the ICT ROF on overarching risk governance and management.'
    },
    'Q69': {
        'relevant_chunk_ids': ['NIST_SP_800-228_txt_00059'],
        'source_section': '3. Recommended Controls for APIs',
        'source_page': '27',
        'verification_status': 'verified',
        'verification_notes': 'Direct factual retrieval from SP 800-228 Section 3 defining the core recommended controls and security capabilities for APIs in cloud-native architectures.'
    },
    # Conceptual (Q70 - Q83)
    'Q70': {
        'relevant_chunk_ids': ['NIST_SP_800-107_txt_00018'],
        'source_section': '4.1 Hash Function Properties',
        'source_page': '10',
        'verification_status': 'verified',
        'verification_notes': 'Conceptual retrieval from SP 800-107 Rev. 1 Section 4.1 defining preimage resistance, second preimage resistance, and collision resistance.'
    },
    'Q71': {
        'relevant_chunk_ids': ['NIST_SP_800-175_txt_00032'],
        'source_section': '2.2.1 The Use of FIPS and SPs',
        'source_page': '23',
        'verification_status': 'verified',
        'verification_notes': 'Conceptual retrieval from SP 800-175B Section 2.2.1 detailing federal agency transition and selection considerations for cryptographic standards.'
    },
    'Q72': {
        'relevant_chunk_ids': ['NIST_SP_800-178_txt_00124'],
        'source_section': '6 Conclusion',
        'source_page': '59',
        'verification_status': 'verified',
        'verification_notes': 'Conceptual retrieval from SP 800-178 Section 6 comparing access policy expressiveness and data leakage prevention between XACML and NGAC.'
    },
    'Q73': {
        'relevant_chunk_ids': ['NIST_SP_800-205_txt_00049'],
        'source_section': '3.1.4 Environment Condition Preparation',
        'source_page': '19',
        'verification_status': 'verified',
        'verification_notes': 'Conceptual retrieval from SP 800-205 Section 3.1.4 explaining dynamic environmental/contextual conditions for access control.'
    },
    'Q74': {
        'relevant_chunk_ids': ['NIST_SP_800-226_txt_00042'],
        'source_section': '2.1. The Promise of Differential Privacy',
        'source_page': '20',
        'verification_status': 'verified',
        'verification_notes': 'Conceptual retrieval from SP 800-226 Section 2.1 evaluating privacy loss bounds and the epsilon privacy budget parameter.'
    },
    'Q75': {
        'relevant_chunk_ids': ['NIST_SP_800-183_txt_00044'],
        'source_section': '5 Reliability and Security Primitive Scenarios',
        'source_page': '25',
        'verification_status': 'verified',
        'verification_notes': 'Conceptual retrieval from SP 800-183 Section 5 defining the five primitives (sensor, aggregator, communication channel, external utility, decision trigger) of Network of Things.'
    },
    'Q76': {
        'relevant_chunk_ids': ['NIST_SP_800-215_txt_00066'],
        'source_section': '5.2 Software-defined Perimeter (SDP)',
        'source_page': '30',
        'verification_status': 'verified',
        'verification_notes': 'Conceptual retrieval from SP 800-215 Section 5.2 analyzing the shift from static perimeter firewalls to software-defined perimeters.'
    },
    'Q77': {
        'relevant_chunk_ids': ['NIST_SP_800-231_txt_00031'],
        'source_section': '3. Bugs Framework Formalism',
        'source_page': '12',
        'verification_status': 'verified',
        'verification_notes': 'Conceptual retrieval from SP 800-231 Section 3 formalizing software weaknesses and vulnerabilities using the Bugs Framework language.'
    },
    'Q78': {
        'relevant_chunk_ids': ['NIST_SP_800-236_txt_00011'],
        'source_section': 'Major Accomplishments in FY 2024',
        'source_page': '8',
        'verification_status': 'verified',
        'verification_notes': 'Conceptual retrieval from SP 800-236 detailing strategic milestones in FY 2024 (NICE Framework, PQC FIPS, AI RMF).'
    },
    'Q79': {
        'relevant_chunk_ids': ['NIST_SP_800-238_txt_00016'],
        'source_section': 'Major accomplishments',
        'source_page': '12',
        'verification_status': 'verified',
        'verification_notes': 'Conceptual retrieval from SP 800-238 identifying FY 2025 accomplishments in semiconductor security, hardware security, and emerging standards.'
    },
    'Q80': {
        'relevant_chunk_ids': ['NIST_SP_800-197_txt_00007'],
        'source_section': '2. Comments from Bryan Queen (NSA Center for Cybersecurity Standards)',
        'source_page': '4',
        'verification_status': 'verified',
        'verification_notes': 'Conceptual retrieval from SP 800-197A pre-draft public comments on lightweight block ciphers and Accordion development.'
    },
    'Q81': {
        'relevant_chunk_ids': ['NIST_SP_800-51_txt_00017'],
        'source_section': '2.1 Common Vulnerabilities and Exposures (CVE)',
        'source_page': '7',
        'verification_status': 'verified',
        'verification_notes': 'Conceptual retrieval from SP 800-51 Rev. 1 Section 2.1 on the role of CVE in standardizing software flaw naming across security tools.'
    },
    'Q82': {
        'relevant_chunk_ids': ['NIST_SP_800-140_txt_00019'],
        'source_section': '6.2 Approved non-invasive attack mitigation test metrics',
        'source_page': '7',
        'verification_status': 'verified',
        'verification_notes': 'Conceptual retrieval from SP 800-140F Rev. 1 Section 6.2 evaluating non-invasive physical attack mitigations (SPA/DPA, side-channels).'
    },
    'Q83': {
        'relevant_chunk_ids': ['NIST_SP_800-223_txt_00044'],
        'source_section': '3.2.2. Management Zone Threats',
        'source_page': '19',
        'verification_status': 'verified',
        'verification_notes': 'Conceptual retrieval from SP 800-223 Section 3.2.2 on HPC cluster management zone threat modeling and clustered network security.'
    },
    # Technical Control (Q84 - Q94)
    'Q84': {
        'relevant_chunk_ids': ['NIST_SP_800-89_txt_00018'],
        'source_section': '4 Assurance of Domain Parameter Validity',
        'source_page': '11',
        'verification_status': 'verified',
        'verification_notes': 'Technical control retrieval from SP 800-89 Section 4 establishing domain parameter validation assurances for digital signature keys.'
    },
    'Q85': {
        'relevant_chunk_ids': ['NIST_SP_800-38_txt_00021'],
        'source_section': '2. Introduction',
        'source_page': '10',
        'verification_status': 'verified',
        'verification_notes': 'Technical control retrieval from SP 800-38G Rev. 1 Section 2 specifying Format-Preserving Encryption methods (FF1 Feistel-based mode).'
    },
    'Q86': {
        'relevant_chunk_ids': ['NIST_SP_800-56_txt_00042'],
        'source_section': '4 Key-Establishment Schemes Overview',
        'source_page': '26',
        'verification_status': 'verified',
        'verification_notes': 'Technical control retrieval from SP 800-56B Rev. 2 Section 4 specifying pair-wise key-establishment schemes based on RSA integer factorization.'
    },
    'Q87': {
        'relevant_chunk_ids': ['NIST_SP_800-186_txt_00009'],
        'source_section': 'Abstract',
        'source_page': '5',
        'verification_status': 'verified',
        'verification_notes': 'Technical control retrieval from SP 800-186 specifying recommended elliptic curves for federal use (Weierstrass, Edwards Ed25519/Ed448).'
    },
    'Q88': {
        'relevant_chunk_ids': ['NIST_SP_800-132_txt_00019'],
        'source_section': '5 Password-Based Key Derivation Functions',
        'source_page': '9',
        'verification_status': 'verified',
        'verification_notes': 'Technical control retrieval from SP 800-132 Section 5 establishing password-based key derivation functions (PBKDF) and salt/iteration recommendations.'
    },
    'Q89': {
        'relevant_chunk_ids': ['NIST_SP_800-192_txt_00010'],
        'source_section': 'Executive Summary',
        'source_page': '5',
        'verification_status': 'verified',
        'verification_notes': 'Technical control retrieval from SP 800-192 Executive Summary defining verification and test methods for access control policies and models.'
    },
    'Q90': {
        'relevant_chunk_ids': ['NIST_SP_800-224_txt_00024'],
        'source_section': '2. HMAC Construction',
        'source_page': '14',
        'verification_status': 'verified',
        'verification_notes': 'Technical control retrieval from SP 800-224 Section 2 specifying HMAC construction, ipad/opad constants, and block sizes.'
    },
    'Q91': {
        'relevant_chunk_ids': ['NIST_SP_800-153_txt_00036'],
        'source_section': '3.1.1 Attack Monitoring',
        'source_page': '16',
        'verification_status': 'verified',
        'verification_notes': 'Technical control retrieval from SP 800-153 Section 3.1.1 on rogue wireless access point monitoring and detection techniques.'
    },
    'Q92': {
        'relevant_chunk_ids': ['NIST_SP_800-72_txt_00070'],
        'source_section': '5.4 Collection',
        'source_page': '38',
        'verification_status': 'verified',
        'verification_notes': 'Technical control retrieval from SP 800-72 Section 5.4 on PDA volatile information preservation and physical evidence collection precautions.'
    },
    'Q93': {
        'relevant_chunk_ids': ['NIST_SP_800-201_txt_00029'],
        'source_section': '1.2. The Approach',
        'source_page': '13',
        'verification_status': 'verified',
        'verification_notes': 'Technical control retrieval from SP 800-201 Section 1.2 defining the foundational architectural tiers of the Cloud Computing Forensic Reference Architecture.'
    },
    'Q94': {
        'relevant_chunk_ids': ['NIST_SP_800-234_txt_00021'],
        'source_section': '2. HPC Security Overlay Summary',
        'source_page': '10',
        'verification_status': 'verified',
        'verification_notes': 'Technical control retrieval from SP 800-234 Section 2 adapting 287 moderate baseline controls for parallel HPC environments.'
    },
    # Scenario-Based (Q95 - Q104)
    'Q95': {
        'relevant_chunk_ids': ['NIST_SP_800-114_txt_00057'],
        'source_section': '5.1 Software Updates',
        'source_page': '23',
        'verification_status': 'verified',
        'verification_notes': 'Scenario-based retrieval from SP 800-114 Rev. 1 Section 5.1 specifying client endpoint software updates and patching controls for employee BYOD telework.'
    },
    'Q96': {
        'relevant_chunk_ids': ['NIST_SP_800-116_txt_00067'],
        'source_section': '4.3 Selection of PIV Authentication Factors',
        'source_page': '24',
        'verification_status': 'verified',
        'verification_notes': 'Scenario-based retrieval from SP 800-116 Rev. 1 Section 4.3 specifying risk-based PIV authentication factors for high-security facility perimeters.'
    },
    'Q97': {
        'relevant_chunk_ids': ['NIST_SP_800-101_txt_00064'],
        'source_section': '4.3 Isolation',
        'source_page': '39',
        'verification_status': 'verified',
        'verification_notes': 'Scenario-based retrieval from SP 800-101 Rev. 1 Section 4.3 detailing isolation and hardware seizure procedures for mobile device forensic integrity.'
    },
    'Q99': {
        'relevant_chunk_ids': ['NIST_SP_800-228_txt_00086'],
        'source_section': '4.1. Centralized API Gateway',
        'source_page': '42',
        'verification_status': 'verified',
        'verification_notes': 'Scenario-based retrieval from SP 800-228 Section 4.1 on API gateway exposure control and caller authentication for microservices.'
    },
    'Q100': {
        'relevant_chunk_ids': ['NIST_SP_800-210_txt_00053'],
        'source_section': '5.9 Recommendations for SaaS Access Control',
        'source_page': '23',
        'verification_status': 'verified',
        'verification_notes': 'Scenario-based retrieval from SP 800-210 Section 5.9 specifying centralized, decentralized, and hybrid ABAC architectures for multi-tenant cross-tenant access control.'
    },
    'Q101': {
        'relevant_chunk_ids': ['NIST_SP_800-239_txt_00048'],
        'source_section': '3.8. Multi-Tenant Threats and the Three-Way "Trust Dilemma"',
        'source_page': '22',
        'verification_status': 'verified',
        'verification_notes': 'Scenario-based retrieval from SP 800-239 Section 3.8 detailing multi-tenant threat models and GPU resource isolation controls to prevent cross-job data leakage.'
    },
    'Q102': {
        'relevant_chunk_ids': ['NIST_SP_800-204_txt_00048'],
        'source_section': '4. CI/CD Pipelines - Background, Security Goals, and Entities to be Trusted',
        'source_page': '22',
        'verification_status': 'verified',
        'verification_notes': 'Scenario-based retrieval from SP 800-204D Section 4 on pipeline security goals and release validation gates prior to production deployment.'
    },
    'Q103': {
        'relevant_chunk_ids': ['NIST_SP_800-216_txt_00061'],
        'source_section': '3.2.4. Development of Vulnerability Disclosure Handling Procedures',
        'source_page': '27',
        'verification_status': 'verified',
        'verification_notes': 'Scenario-based retrieval from SP 800-216 Section 3.2.4 establishing internal procedures for vulnerability report intake, triage, and remediation.'
    },
    'Q104': {
        'relevant_chunk_ids': ['NIST_SP_800-221_txt_00025', 'NIST_SP_800-221_txt_00026'],
        'source_section': 'ICT Risk Outcomes Framework (ROF)',
        'source_page': '10',
        'verification_status': 'verified',
        'verification_notes': 'Scenario-based retrieval from SP 800-221A Section on ICT Risk Outcomes Framework applying measurable risk outcomes, Functions (GV, MA), Categories (MA.RA, MA.RM), and implementation models to evaluate systemic disruptions.'
    }
}

print(f"Total defined refinements: {len(refinements)}")

# Verify all replacement chunks exist in corpus
missing_chunks = []
for qid, ref in refinements.items():
    rc = ref.get('relevant_chunks') or ref.get('relevant_chunk_ids') or []
    for c in rc:
        if c not in all_chunks:
            missing_chunks.append((qid, c))

print(f"Missing chunks: {len(missing_chunks)}")
if missing_chunks:
    print(missing_chunks)
else:
    print("ALL replacement chunks physically exist in corpus!")
