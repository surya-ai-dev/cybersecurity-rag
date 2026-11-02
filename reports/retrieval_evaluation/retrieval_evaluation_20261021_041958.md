# Cybersecurity RAG: Retrieval Pipeline Benchmark Report

- **Timestamp:** `2026-10-21T04:19:58.789137`
- **Questions Evaluated:** `36`
- **Dense Embedding Model:** `BAAI/bge-m3`
- **Cross-Encoder Reranker:** `cross-encoder/ms-marco-MiniLM-L-6-v2`
- **Initial Candidate Top-K:** `20`
- **Production Cutoff:** `Top 5`

---

## 1. Executive Summary & Configuration Comparison

| Configuration | Hit@1 | Hit@5 | Hit@20 | Recall@5 | Recall@20 | Precision@5 | MRR@20 | NDCG@5 | NDCG@20 | Avg Latency |
|---|---|---|---|---|---|---|---|---|---|---|
| **Dense Retrieval Only (BGE-M3)** | 47.22% | **83.33%** | 91.67% | **59.49%** | 75.69% | 20.00% | **0.6447** | **0.5288** | 0.5907 | 611.3 ms |
| **BM25 Retrieval Only (Okapi)** | 25.00% | **58.33%** | 77.78% | **44.44%** | 61.57% | 12.78% | **0.3858** | **0.3382** | 0.3989 | 124.7 ms |
| **Hybrid Retrieval (Dense + BM25 + RRF)** | 41.67% | **72.22%** | 91.67% | **51.85%** | 73.61% | 16.11% | **0.5608** | **0.4542** | 0.5339 | 736.2 ms |
| **Hybrid + Cross-Encoder Reranker** | 50.00% | **83.33%** | 91.67% | **59.03%** | 73.61% | 18.89% | **0.6305** | **0.5262** | 0.5807 | 4253.6 ms |

> [!NOTE]
> **Production Impact:** Configuration D evaluates the actual candidate stream delivered into the context builder. Top-5 metrics represent the exact context injected into prompt generation, while Top-20 metrics reflect the underlying candidate pool ceiling.

---

## 2. Per-Question Detailed Performance Matrix

| QID | Question Preview | Expected Chunks | Dense Hit@5 | BM25 Hit@5 | Hybrid Hit@5 | Reranked Hit@5 | Reranked Recall@5 | Reranked MRR@20 |
|---|---|---|---|---|---|---|---|---|
| **Q1** | What are the security risks of public cloud c... | 3 | ✅ | ✅ | ✅ | ✅ | 66.7% | 1.000 |
| **Q3** | How can client-side malware affect public clo... | 3 | ✅ | ✅ | ✅ | ✅ | 33.3% | 1.000 |
| **Q4** | Why is governance important for public cloud ... | 2 | ✅ | ❌ | ✅ | ✅ | 50.0% | 0.333 |
| **Q5** | Who is responsible for security and privacy i... | 4 | ✅ | ❌ | ❌ | ✅ | 25.0% | 0.500 |
| **Q7** | What privacy risks can arise when organizatio... | 3 | ✅ | ❌ | ❌ | ✅ | 33.3% | 1.000 |
| **Q8** | How does loss of control affect security in p... | 3 | ✅ | ❌ | ❌ | ❌ | 0.0% | 0.100 |
| **Q9** | What security issues can result from outsourc... | 3 | ✅ | ✅ | ✅ | ✅ | 33.3% | 1.000 |
| **Q10** | What are the security implications of storing... | 3 | ❌ | ❌ | ❌ | ❌ | 0.0% | 0.000 |
| **Q11** | What responsibilities does an organization re... | 4 | ✅ | ✅ | ✅ | ✅ | 25.0% | 1.000 |
| **Q12** | What security responsibilities are shared bet... | 4 | ✅ | ❌ | ✅ | ✅ | 50.0% | 1.000 |
| **Q13** | What risks are associated with relying on a t... | 3 | ❌ | ❌ | ✅ | ✅ | 33.3% | 0.500 |
| **Q14** | How can social engineering attacks affect pub... | 2 | ✅ | ✅ | ✅ | ✅ | 100.0% | 1.000 |
| **Q16** | Why are security and privacy considerations i... | 3 | ✅ | ✅ | ✅ | ✅ | 33.3% | 0.250 |
| **Q17** | What governance practices are important when ... | 2 | ✅ | ✅ | ✅ | ✅ | 100.0% | 0.250 |
| **Q19** | What challenges can organizations face when m... | 3 | ❌ | ❌ | ❌ | ❌ | 0.0% | 0.000 |
| **Q20** | What factors should organizations consider wh... | 4 | ✅ | ✅ | ✅ | ✅ | 25.0% | 0.333 |
| **Q21** | What are the core phases of the incident resp... | 1 | ❌ | ✅ | ✅ | ✅ | 100.0% | 1.000 |
| **Q22** | What key considerations and trade-offs should... | 1 | ✅ | ✅ | ✅ | ✅ | 100.0% | 0.500 |
| **Q23** | What fundamental paradigm shift does Zero Tru... | 1 | ✅ | ✅ | ✅ | ✅ | 100.0% | 1.000 |
| **Q24** | What security recommendations should organiza... | 1 | ✅ | ✅ | ✅ | ✅ | 100.0% | 1.000 |
| **Q25** | What are the core practice groups that compri... | 1 | ❌ | ❌ | ❌ | ❌ | 0.0% | 0.071 |
| **Q26** | How should organizations leverage actionable ... | 1 | ✅ | ✅ | ✅ | ✅ | 100.0% | 1.000 |
| **Q27** | What are the three tiers in the multitiered r... | 3 | ✅ | ✅ | ✅ | ✅ | 33.3% | 1.000 |
| **Q28** | How does the security control tailoring proce... | 1 | ✅ | ✅ | ✅ | ✅ | 100.0% | 1.000 |
| **Q29** | What are the core requirements and authentica... | 1 | ✅ | ✅ | ✅ | ✅ | 100.0% | 1.000 |
| **Q30** | What are the fundamental attribute types eval... | 2 | ✅ | ❌ | ❌ | ✅ | 50.0% | 0.200 |
| **Q31** | What are the primary operational characterist... | 1 | ✅ | ✅ | ✅ | ✅ | 100.0% | 1.000 |
| **Q32** | How do application-proxy gateways differ from... | 1 | ✅ | ✅ | ✅ | ✅ | 100.0% | 1.000 |
| **Q33** | What security controls and client software co... | 2 | ✅ | ❌ | ❌ | ❌ | 0.0% | 0.125 |
| **Q34** | What strategic benefits and operational capab... | 1 | ✅ | ✅ | ✅ | ✅ | 100.0% | 1.000 |
| **Q35** | How does technical penetration testing differ... | 1 | ✅ | ❌ | ✅ | ✅ | 100.0% | 0.200 |
| **Q36** | What are the four phases of the digital foren... | 1 | ✅ | ✅ | ✅ | ✅ | 100.0% | 0.333 |
| **Q37** | What distinguishes foundational practices fro... | 1 | ✅ | ✅ | ✅ | ✅ | 100.0% | 1.000 |
| **Q38** | What are the five essential characteristics o... | 1 | ❌ | ❌ | ❌ | ❌ | 0.0% | 0.000 |
| **Q39** | What is the procedure for characterizing secu... | 1 | ✅ | ❌ | ❌ | ✅ | 100.0% | 0.500 |
| **Q40** | What core security assurances does a service ... | 3 | ✅ | ❌ | ✅ | ✅ | 33.3% | 0.500 |

---

## 3. Top Missing or Suboptimal Queries (Config D Hit@5 = 0)

### Question Q8
- **Query:** How does loss of control affect security in public cloud computing?
- **Expected Chunks:** `['NIST_SP_800-144_txt_00038', 'NIST_SP_800-144_txt_00062', 'NIST_SP_800-146_txt_00080']`
- **Hit@5:** `0.0` | **Hit@20:** `1.0` | **MRR@20:** `0.1`
- **Top-5 Retrieved Chunks:**
  1. ⚪ `NIST_SP_800-144_txt_00050` (NIST_SP_800-144) — score: 5.6937
  2. ⚪ `NIST_SP_800-144_txt_00048` (NIST_SP_800-144) — score: 3.9594
  3. ⚪ `NIST_SP_800-144_txt_00027` (NIST_SP_800-144) — score: 3.5785
  4. ⚪ `NIST_SP_800-144_txt_00099` (NIST_SP_800-144) — score: 3.4864
  5. ⚪ `NIST_SP_800-144_txt_00120` (NIST_SP_800-144) — score: 2.5178

### Question Q10
- **Query:** What are the security implications of storing organizational data in the public cloud?
- **Expected Chunks:** `['NIST_SP_800-144_txt_00080', 'NIST_SP_800-144_txt_00081', 'NIST_SP_800-144_txt_00082']`
- **Hit@5:** `0.0` | **Hit@20:** `0.0` | **MRR@20:** `0.0`
- **Top-5 Retrieved Chunks:**
  1. ⚪ `NIST_SP_800-144_txt_00021` (NIST_SP_800-144) — score: 3.7604
  2. ⚪ `NIST_SP_800-144_txt_00043` (NIST_SP_800-144) — score: 3.7304
  3. ⚪ `NIST_SP_800-144_txt_00038` (NIST_SP_800-144) — score: 3.5729
  4. ⚪ `NIST_SP_800-146_txt_00135` (NIST_SP_800-146) — score: 3.0460
  5. ⚪ `NIST_SP_800-144_txt_00024` (NIST_SP_800-144) — score: 2.7044

### Question Q19
- **Query:** What challenges can organizations face when monitoring security in public cloud environments?
- **Expected Chunks:** `['NIST_SP_800-144_txt_00065', 'NIST_SP_800-144_txt_00087', 'NIST_SP_800-146_txt_00134']`
- **Hit@5:** `0.0` | **Hit@20:** `0.0` | **MRR@20:** `0.0`
- **Top-5 Retrieved Chunks:**
  1. ⚪ `NIST_SP_800-144_txt_00030` (NIST_SP_800-144) — score: 5.1375
  2. ⚪ `NIST_SP_800-144_txt_00008` (NIST_SP_800-144) — score: 4.9504
  3. ⚪ `NIST_SP_800-144_txt_00120` (NIST_SP_800-144) — score: 4.7616
  4. ⚪ `NIST_SP_800-144_txt_00026` (NIST_SP_800-144) — score: 4.7335
  5. ⚪ `NIST_SP_800-144_txt_00050` (NIST_SP_800-144) — score: 4.0500

### Question Q25
- **Query:** What are the core practice groups that comprise the Secure Software Development Framework (SSDF)?
- **Expected Chunks:** `['NIST_SP_800-218_txt_00029']`
- **Hit@5:** `0.0` | **Hit@20:** `1.0` | **MRR@20:** `0.07142857142857142`
- **Top-5 Retrieved Chunks:**
  1. ⚪ `NIST_SP_800-218_txt_00011` (NIST_SP_800-218) — score: 5.4929
  2. ⚪ `NIST_SP_800-218_txt_00023` (NIST_SP_800-218) — score: 4.7757
  3. ⚪ `NIST_SP_800-218_txt_00028` (NIST_SP_800-218) — score: 3.6687
  4. ⚪ `NIST_SP_800-218_txt_00026` (NIST_SP_800-218) — score: 3.4671
  5. ⚪ `NIST_SP_800-218_txt_00012` (NIST_SP_800-218) — score: 3.2834

### Question Q33
- **Query:** What security controls and client software configurations are required to protect remote access in enterprise telework?
- **Expected Chunks:** `['NIST_SP_800-46_txt_00030', 'NIST_SP_800-46_txt_00076']`
- **Hit@5:** `0.0` | **Hit@20:** `1.0` | **MRR@20:** `0.125`
- **Top-5 Retrieved Chunks:**
  1. ⚪ `NIST_SP_800-46_txt_00074` (NIST_SP_800-46) — score: 5.6651
  2. ⚪ `NIST_SP_800-46_txt_00092` (NIST_SP_800-46) — score: 5.6185
  3. ⚪ `NIST_SP_800-46_txt_00036` (NIST_SP_800-46) — score: 5.6046
  4. ⚪ `NIST_SP_800-46_txt_00034` (NIST_SP_800-46) — score: 5.3403
  5. ⚪ `NIST_SP_800-46_txt_00079` (NIST_SP_800-46) — score: 5.1017

### Question Q38
- **Query:** What are the five essential characteristics of cloud computing defined by NIST SP 800-145?
- **Expected Chunks:** `['NIST_SP_800-145_txt_00012']`
- **Hit@5:** `0.0` | **Hit@20:** `0.0` | **MRR@20:** `0.0`
- **Top-5 Retrieved Chunks:**
  1. ⚪ `NIST_SP_800-146_txt_00021` (NIST_SP_800-146) — score: 8.9707
  2. ⚪ `NIST_SP_800-201_txt_00031` (NIST_SP_800-201) — score: 6.2064
  3. ⚪ `NIST_SP_800-145_txt_00011` (NIST_SP_800-145) — score: 6.1913
  4. ⚪ `NIST_SP_800-201_txt_00064` (NIST_SP_800-201) — score: 3.6127
  5. ⚪ `NIST_SP_800-144_txt_00033` (NIST_SP_800-144) — score: 2.1803
