# 36-Question Retrieval Benchmark: Baseline vs Revised Experimental Rewriter

- **Timestamp:** `2026-10-21T05:26:25.500674`
- **Total Questions Evaluated:** `36`
- **Outcome Distribution:** Improved: `5` | Neutral: `23` | Regressed: `8`
- **Dense Embedding Model:** `BAAI/bge-m3`
- **Cross-Encoder Model:** `cross-encoder/ms-marco-MiniLM-L-6-v2`
- **Rewriter Model:** `qwen/qwen3.8-27b`
- **Retrieval Pipeline Cutoffs:** `Dense=20, BM25=20, RRF Pool=20, Top Context=5`

---

## 1. Executive Macro-Average Comparison

| Metric | Baseline (Original Queries) | Revised Rewriter (LLM Expanded) | Delta |
|---|---|---|---|
| **Hit@1** | 50.00% | 38.89% | **-11.11%** |
| **Hit@5 (Context Delivered)** | 83.33% | 77.78% | **-5.55%** |
| **Hit@20 (Pool Ceiling)** | 83.33% | 77.78% | **-5.55%** |
| **Recall@5** | 59.03% | 57.41% | **-1.62%** |
| **Recall@20** | 59.03% | 57.41% | **-1.62%** |
| **Precision@5** | 18.89% | 16.67% | **-2.22%** |
| **MRR@5** | 0.6222 | 0.5245 | **-0.0977** |
| **MRR@20** | 0.6222 | 0.5245 | **-0.0977** |
| **NDCG@5** | 0.5262 | 0.4717 | **-0.0545** |
| **NDCG@20** | 0.5262 | 0.4717 | **-0.0545** |
| **Avg End-to-End Latency** | 5224.5 ms | 5441.4 ms | +216.9 ms |

---

## 2. Per-Question Detailed Results Matrix

| QID | Status | Base Hit@5 | Rev Hit@5 | Base Recall@5 | Rev Recall@5 | Base MRR@5 | Rev MRR@5 | Rewritten Query Preview |
|---|---|---|---|---|---|---|---|---|
| **Q1** | ❌ REGRESSED | 100% | **100%** | 66.7% | **33.3%** | 1.000 | 0.500 | *public cloud computing security risks shared ...* |
| **Q3** | ⚪ NEUTRAL | 100% | **100%** | 33.3% | **33.3%** | 1.000 | 0.500 | *client-side malware public cloud security end...* |
| **Q4** | ❌ REGRESSED | 100% | **0%** | 50.0% | **0.0%** | 0.333 | 0.000 | *public cloud security governance shared respo...* |
| **Q5** | ⚪ NEUTRAL | 100% | **100%** | 25.0% | **25.0%** | 0.500 | 1.000 | *public cloud computing shared responsibility ...* |
| **Q7** | ⚪ NEUTRAL | 100% | **100%** | 33.3% | **33.3%** | 1.000 | 0.250 | *public cloud services privacy risks data co-l...* |
| **Q8** | ⚪ NEUTRAL | 0% | **0%** | 0.0% | **0.0%** | 0.000 | 0.000 | *loss of control public cloud computing securi...* |
| **Q9** | ❌ REGRESSED | 100% | **0%** | 33.3% | **0.0%** | 1.000 | 0.000 | *cloud computing security risks outsourcing sh...* |
| **Q10** | ✅ IMPROVED | 0% | **100%** | 0.0% | **66.7%** | 0.000 | 1.000 | *public cloud data storage security implicatio...* |
| **Q11** | ❌ REGRESSED | 100% | **0%** | 25.0% | **0.0%** | 1.000 | 0.000 | *shared responsibility model public cloud prov...* |
| **Q12** | ❌ REGRESSED | 100% | **0%** | 50.0% | **0.0%** | 1.000 | 0.000 | *shared responsibility model cloud provider cu...* |
| **Q13** | ⚪ NEUTRAL | 100% | **100%** | 33.3% | **33.3%** | 0.500 | 0.200 | *third-party cloud service provider risks shar...* |
| **Q14** | ❌ REGRESSED | 100% | **100%** | 100.0% | **50.0%** | 1.000 | 0.333 | *social engineering attacks public cloud secur...* |
| **Q16** | ⚪ NEUTRAL | 100% | **100%** | 33.3% | **33.3%** | 0.250 | 0.200 | *cloud system lifecycle security privacy consi...* |
| **Q17** | ❌ REGRESSED | 100% | **0%** | 100.0% | **0.0%** | 0.250 | 0.000 | *cloud governance practices public cloud servi...* |
| **Q19** | ✅ IMPROVED | 0% | **100%** | 0.0% | **33.3%** | 0.000 | 1.000 | *public cloud security monitoring challenges e...* |
| **Q20** | ⚪ NEUTRAL | 100% | **100%** | 25.0% | **25.0%** | 0.333 | 1.000 | *public cloud provider security evaluation fac...* |
| **Q21** | ⚪ NEUTRAL | 100% | **100%** | 100.0% | **100.0%** | 1.000 | 1.000 | *NIST incident handling guidance incident resp...* |
| **Q22** | ⚪ NEUTRAL | 100% | **100%** | 100.0% | **100.0%** | 0.500 | 0.200 | *malware containment decisions trade-offs inci...* |
| **Q23** | ⚪ NEUTRAL | 100% | **100%** | 100.0% | **100.0%** | 1.000 | 0.500 | *Zero Trust Architecture implicit trust networ...* |
| **Q24** | ⚪ NEUTRAL | 100% | **100%** | 100.0% | **100.0%** | 1.000 | 1.000 | *network segmentation virtual machine protecti...* |
| **Q25** | ✅ IMPROVED | 0% | **100%** | 0.0% | **100.0%** | 0.000 | 1.000 | *SSDF Secure Software Development Framework co...* |
| **Q26** | ⚪ NEUTRAL | 100% | **100%** | 100.0% | **100.0%** | 1.000 | 1.000 | *enterprise patch management actionable metric...* |
| **Q27** | ⚪ NEUTRAL | 100% | **100%** | 33.3% | **33.3%** | 1.000 | 1.000 | *multitiered risk management approach three ti...* |
| **Q28** | ⚪ NEUTRAL | 100% | **100%** | 100.0% | **100.0%** | 1.000 | 0.333 | *security control tailoring process modify ini...* |
| **Q29** | ⚪ NEUTRAL | 100% | **100%** | 100.0% | **100.0%** | 1.000 | 1.000 | *Authenticator Assurance Level AAL2 requiremen...* |
| **Q30** | ❌ REGRESSED | 100% | **0%** | 50.0% | **0.0%** | 0.200 | 0.000 | *Attribute Based Access Control ABAC attribute...* |
| **Q31** | ⚪ NEUTRAL | 100% | **100%** | 100.0% | **100.0%** | 1.000 | 1.000 | *Full Disk Encryption FDE File Folder Encrypti...* |
| **Q32** | ⚪ NEUTRAL | 100% | **100%** | 100.0% | **100.0%** | 1.000 | 1.000 | *application-proxy gateway packet filtering fi...* |
| **Q33** | ⚪ NEUTRAL | 0% | **0%** | 0.0% | **0.0%** | 0.000 | 0.000 | *remote access security controls client softwa...* |
| **Q34** | ⚪ NEUTRAL | 100% | **100%** | 100.0% | **100.0%** | 1.000 | 1.000 | *cyber threat information sharing strategic be...* |
| **Q35** | ⚪ NEUTRAL | 100% | **100%** | 100.0% | **100.0%** | 0.200 | 0.333 | *technical penetration testing automated vulne...* |
| **Q36** | ⚪ NEUTRAL | 100% | **100%** | 100.0% | **100.0%** | 0.333 | 0.200 | *digital forensics process four phases primary...* |
| **Q37** | ⚪ NEUTRAL | 100% | **100%** | 100.0% | **100.0%** | 1.000 | 1.000 | *Cybersecurity Supply Chain Risk Management C-...* |
| **Q38** | ✅ IMPROVED | 0% | **100%** | 0.0% | **100.0%** | 0.000 | 0.333 | *NIST SP 800-145 five essential characteristic...* |
| **Q39** | ⚪ NEUTRAL | 100% | **100%** | 100.0% | **100.0%** | 0.500 | 0.500 | *data-centric threat modeling security control...* |
| **Q40** | ✅ IMPROVED | 100% | **100%** | 33.3% | **66.7%** | 0.500 | 0.500 | *service mesh infrastructure security assuranc...* |

---

## 3. Regressions Analysis (If Any)

### Question Q1
- **Original Question:** *"What are the security risks of public cloud computing?"*
- **Rewritten Query:** *"public cloud computing security risks shared environment multi-tenant isolation data co-location data at rest encryption cryptographic key management"*
- **Hit@5 Change:** `100%` -> `100%`
- **Recall@5 Change:** `66.7%` -> `33.3%`
- **Expected Chunks:** `['NIST_SP_800-144_txt_00047', 'NIST_SP_800-144_txt_00048', 'NIST_SP_800-144_txt_00054']`

### Question Q4
- **Original Question:** *"Why is governance important for public cloud security?"*
- **Rewritten Query:** *"public cloud security governance shared responsibility model compliance risk management policy enforcement"*
- **Hit@5 Change:** `100%` -> `0%`
- **Recall@5 Change:** `50.0%` -> `0.0%`
- **Expected Chunks:** `['NIST_SP_800-144_txt_00055', 'NIST_SP_800-144_txt_00056']`

### Question Q9
- **Original Question:** *"What security issues can result from outsourcing services to a cloud provider?"*
- **Rewritten Query:** *"cloud computing security risks outsourcing shared responsibility model data co-location multi-tenant isolation provider audit controls"*
- **Hit@5 Change:** `100%` -> `0%`
- **Recall@5 Change:** `33.3%` -> `0.0%`
- **Expected Chunks:** `['NIST_SP_800-144_txt_00094', 'NIST_SP_800-144_txt_00099', 'NIST_SP_800-144_txt_00100']`

### Question Q11
- **Original Question:** *"What responsibilities does an organization retain after moving to a public cloud?"*
- **Rewritten Query:** *"shared responsibility model public cloud provider customer responsibilities retained"*
- **Hit@5 Change:** `100%` -> `0%`
- **Recall@5 Change:** `25.0%` -> `0.0%`
- **Expected Chunks:** `['NIST_SP_800-144_txt_00026', 'NIST_SP_800-144_txt_00038', 'NIST_SP_800-144_txt_00039', 'NIST_SP_800-144_txt_00060']`

### Question Q12
- **Original Question:** *"What security responsibilities are shared between a cloud provider and a cloud customer?"*
- **Rewritten Query:** *"shared responsibility model cloud provider customer security responsibilities"*
- **Hit@5 Change:** `100%` -> `0%`
- **Recall@5 Change:** `50.0%` -> `0.0%`
- **Expected Chunks:** `['NIST_SP_800-144_txt_00022', 'NIST_SP_800-144_txt_00036', 'NIST_SP_800-146_txt_00080', 'NIST_SP_800-146_txt_00094']`

### Question Q14
- **Original Question:** *"How can social engineering attacks affect public cloud security?"*
- **Rewritten Query:** *"social engineering attacks public cloud security phishing credential theft multi-tenant environment access control identity management"*
- **Hit@5 Change:** `100%` -> `100%`
- **Recall@5 Change:** `100.0%` -> `50.0%`
- **Expected Chunks:** `['NIST_SP_800-144_txt_00073', 'NIST_SP_800-144_txt_00025']`

### Question Q17
- **Original Question:** *"What governance practices are important when using public cloud services?"*
- **Rewritten Query:** *"cloud governance practices public cloud services shared responsibility model compliance risk management"*
- **Hit@5 Change:** `100%` -> `0%`
- **Recall@5 Change:** `100.0%` -> `0.0%`
- **Expected Chunks:** `['NIST_SP_800-144_txt_00055', 'NIST_SP_800-144_txt_00056']`

### Question Q30
- **Original Question:** *"What are the fundamental attribute types evaluated in an Attribute Based Access Control (ABAC) enterprise system?"*
- **Rewritten Query:** *"Attribute Based Access Control ABAC attribute types subject attributes resource attributes environment attributes action attributes"*
- **Hit@5 Change:** `100%` -> `0%`
- **Recall@5 Change:** `50.0%` -> `0.0%`
- **Expected Chunks:** `['NIST_SP_800-162_txt_00007', 'NIST_SP_800-162_txt_00044']`
