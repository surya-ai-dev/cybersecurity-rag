# Stage 2 Structure-Aware Chunking Pilot — Revalidation Audit Report

> **Date**: 2026-10-14
> **Pipeline Stage**: Stage 4 Chunking — Stage 2 Pilot Refinements & Revalidation
> **Scope**: 10 Pilot Publications (`data/cleaned_pilot/`, 1,057 physical pages)
> **Output Location**: [data/chunks_pilot/](file:///C:/Users/Computer/Desktop/cybersecurity-rag/data/chunks_pilot/)
> **Manifest**: [data/chunks_pilot/chunks_manifest.json](file:///C:/Users/Computer/Desktop/cybersecurity-rag/data/chunks_pilot/chunks_manifest.json)
> **Previous Inspection Audit**: `stage2_pilot_chunking_inspection_audit.md`
> **Reference Plan**: [CHUNKING_IMPLEMENTATION_PLAN.md](file:///C:/Users/Computer/Desktop/cybersecurity-rag/CHUNKING_IMPLEMENTATION_PLAN.md)
> **Final Revalidation Verdict**: **`PASS — All 3 Audit Findings Fully Resolved. Pilot is Approved for Full-Corpus Chunking.`**

---

## 1. Executive Summary

Following the **Stage 2 Pilot Audit (Inspection Only)**, three specific findings were identified and refined in the chunking codebase:
1. **Fix 1 (Oversized table rows)**: Decomposed monolithic table rows exceeding `max_table_tokens` (500) into semantic sub-part chunks repeating Practice/Task context and column headers.
2. **Fix 2 (Unhelpful micro-chunks)**: Filtered bare draft margin line numbers (`### 13`, `### 17`), refined numbered-heading regex to prevent misclassifying acronym definitions (`481 Institute for Defense Analyses`), and attached consecutive headings (`CHAPTER ONE` -> `INTRODUCTION`) hierarchically.
3. **Fix 3 (Category metadata consistency)**: Normalized category metadata for root-level documents to `"root"` consistently across chunk records and the manifest.

All **25 chunking unit & integration tests** and all **122 project regression tests** pass cleanly. The 10-document pilot cohort was cleanly regenerated into `data/chunks_pilot/` with zero failures.

---

## 2. Before vs. After Comparative Metrics

| Metric | Previous Pilot Run | Revalidated Pilot Run | Delta / Impact |
| :--- | :---: | :---: | :---: |
| **Total Documents Processed** | 10 | 10 | 0 (10/10 SUCCESS) |
| **Total Physical Pages** | 1,057 | 1,057 | 0 (100% page parity) |
| **Total Chunks Emitted** | 2,868 | 3,175 | +307 (+10.7%) |
| **Normal Text Chunks** | 2,129 | 2,408 | +279 (better sentence & section boundaries) |
| **Table Chunks** | 592 | 620 | +28 (sub-split of 22 oversized rows) |
| **Figure Records** | 147 | 147 | 0 (100% parity, 0 missing assets) |
| **Oversized Chunks (> 500 tokens)** | **22** | **0** | **-22 (100% compliant with 512 context limit)** |
| **Maximum Token Count** | **848** | **500** | **-348 tokens** |
| **Minimum Token Count** | **4** | **7** | **+3 tokens (bare line numbers eliminated)** |
| **Median Token Count** | 343.0 | 265.0 | -78.0 tokens (clean embedding fit) |
| **Mean Token Count** | 298.2 | 264.8 | -33.4 tokens |
| **Bare Draft Lines (`### 13`, `17`)** | 2 | 0 | -2 (eliminated completely) |
| **Lone Heading Chunks (`CHAPTER ONE`)** | 4 | 0 | -4 (attached to sections) |
| **Root Document Category** | `documents` | `root` | Standardized to `root` across all files |
| **Missing Figure Assets** | 0 | 0 | 0 (147/147 on disk) |
| **Duplicate Chunk IDs** | 0 | 0 | 0 (3,175 unique IDs) |
| **Malformed JSONL Lines** | 0 | 0 | 0 (100% valid JSON) |
| **Encoding Warnings** | 13 | 13 | 0 (100% preserved verbatim) |

---

## 3. Detailed Verification of the Three Audit Fixes

### Fix 1: Oversized Table Rows
- **Problem**: Previously, 22 table chunks exceeded 500 tokens (up to 848 tokens in `NIST_SP_800-218_tbl_00016_p02`, page 32) because monolithic single rows contained massive multi-example or multi-reference cells.
- **Implementation**: Added `_split_cell_into_units` and `_split_oversized_row` to `TableChunker`. When a single row exceeds `max_table_tokens`, the row is partitioned across semantic boundaries (numbered examples, bullet points, framework reference prefixes, semicolon groupings). Context columns (`Practices`, `Tasks`, `Version`, `ReleaseDate`) are repeated in each sub-row alongside repeated column headers.
- **Verification**:
  - Across all 3,175 chunks, **zero chunks exceed 500 tokens** (`oversized_chunks_count: 0`).
  - Former 848-token chunk `NIST_SP_800-218_tbl_00016` (page 32) is now partitioned into 5 well-formed sub-parts:
    - Part 1/5: 104 tokens (rows 0-2)
    - Part 2/5: 369 tokens (Examples 1-2, BSAFSS/BSIMM references, repeated Practice/Task context)
    - Part 3/5: 320 tokens (Example 3, IEC/ISO/OWASP references, repeated Practice/Task context)
    - Part 4/5: 467 tokens (Examples 4-5, SP800-53/160/161 references, repeated Practice/Task context)
    - Part 5/5: 342 tokens (NICE SP800-181 workforce task references, repeated Practice/Task context)
  - All 5 examples, 30+ references, and practice context are 100% preserved.

### Fix 2: Unhelpful Micro-Chunks
- **Problem**: Bare draft line numbers (`### 13`, `### 17` on page 5 of `NIST_SP_800-218`) were emitted as 4-token chunks; acronym definitions (`481 Institute for Defense Analyses`) were misclassified as headings by the numbered-heading regex, stranding acronym headers (`### **IDA**`); and chapter titles (`### **CHAPTER ONE**`) were emitted as empty 9-token chunks.
- **Implementation**:
  - `_extract_segments`: Filtered out standalone paragraphs consisting solely of $\le 4$ digits (`para.lstrip("#").strip("*_ \t").isdigit()`).
  - `_detect_heading`: Prevented headings with solely digit content from being detected as headers. Refined numbered-heading regex to require dot-delimited numbering (`^(\d+(?:\.\d+)+|\d+\.)\s+([A-Z][^\n]+)$`), bounded single numbers to $\le 25$, and excluded sentences ending in punctuation.
  - `_group_by_section`: Accumulated consecutive headings with no intervening body text into a single hierarchical section group.
  - `_chunk_section_group`: Extracted all headings in the group into `heading_prefix` (`### Header 1\n\n### Header 2\n\n`) so parent titles are preserved above child content.
- **Verification**:
  - Bare numbers `### 13` and `### 17`: **0 chunks** (eliminated).
  - Standalone `### **CHAPTER ONE**`: **0 chunks** (attached with `INTRODUCTION`).
  - Acronym definitions: `### **IDA**` and `481 Institute for Defense Analyses` are preserved together in `NIST_SP_800-218_txt_00126` (14 tokens).
  - Legitimate short acronyms (`CPS: Cyber-Physical System`) are preserved.

### Fix 3: Category Metadata Consistency
- **Problem**: Root-level publications (`NIST.SP.800-61r3`, `NIST_SP_800-234`, `NIST_SP_800-236`, `NIST_SP_800-238`) had `category: "documents"` in chunk JSON records but `"root"` in the folder hierarchy and manifest.
- **Implementation**: In `DocumentChunkingPipeline.process_document`, normalized category assignment: if `raw_category in ("documents", "root") or parent_dir_category == "root"`, assign `category = "root"`.
- **Verification**: All 498 chunks across the 4 root publications now carry `"category": "root"`, matching `chunks_manifest.json` and directory structure with 100% consistency. Non-root publications (`cryptography_security`, `identity_access`, `risk_management`, `vulnerability_management`) and source file paths remain 100% unaltered.

---

## 4. Revalidated Document-by-Document Inventory

| Category | Document ID | Pages | Total Chunks | Text | Table | Figure | Warnings | Output Size | Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `cryptography_security` | [NIST_SP_800-152](file:///C:/Users/Computer/Desktop/cybersecurity-rag/data/chunks_pilot/cryptography_security/NIST_SP_800-152_chunks.jsonl) | 147 | 417 | 228 | 187 | 2 | 3 | 754.0 KB | `SUCCESS` |
| `cryptography_security` | [NIST_SP_800-186](file:///C:/Users/Computer/Desktop/cybersecurity-rag/data/chunks_pilot/cryptography_security/NIST_SP_800-186_chunks.jsonl) | 75 | 252 | 240 | 9 | 3 | 10 | 358.0 KB | `SUCCESS` |
| `identity_access` | [NIST_SP_800-116](file:///C:/Users/Computer/Desktop/cybersecurity-rag/data/chunks_pilot/identity_access/NIST_SP_800-116_chunks.jsonl) | 71 | 190 | 157 | 29 | 4 | 0 | 349.6 KB | `SUCCESS` |
| `risk_management` | [NIST_SP_800-39](file:///C:/Users/Computer/Desktop/cybersecurity-rag/data/chunks_pilot/risk_management/NIST_SP_800-39_chunks.jsonl) | 88 | 276 | 245 | 26 | 5 | 0 | 543.3 KB | `SUCCESS` |
| `risk_management` | [NIST_SP_800-53](file:///C:/Users/Computer/Desktop/cybersecurity-rag/data/chunks_pilot/risk_management/NIST_SP_800-53_chunks.jsonl) | 492 | 1,306 | 1,099 | 206 | 1 | 0 | 2,758.9 KB | `SUCCESS` |
| `root` | [NIST.SP.800-61r3](file:///C:/Users/Computer/Desktop/cybersecurity-rag/data/chunks_pilot/root/NIST.SP.800-61r3_chunks.jsonl) | 48 | 194 | 137 | 52 | 5 | 0 | 325.5 KB | `SUCCESS` |
| `root` | [NIST_SP_800-234](file:///C:/Users/Computer/Desktop/cybersecurity-rag/data/chunks_pilot/root/NIST_SP_800-234_chunks.jsonl) | 31 | 109 | 86 | 19 | 4 | 0 | 155.9 KB | `SUCCESS` |
| `root` | [NIST_SP_800-236](file:///C:/Users/Computer/Desktop/cybersecurity-rag/data/chunks_pilot/root/NIST_SP_800-236_chunks.jsonl) | 29 | 111 | 45 | 0 | 66 | 0 | 136.4 KB | `SUCCESS` |
| `root` | [NIST_SP_800-238](file:///C:/Users/Computer/Desktop/cybersecurity-rag/data/chunks_pilot/root/NIST_SP_800-238_chunks.jsonl) | 19 | 84 | 30 | 0 | 54 | 0 | 99.6 KB | `SUCCESS` |
| `vulnerability_management` | [NIST_SP_800-218](file:///C:/Users/Computer/Desktop/cybersecurity-rag/data/chunks_pilot/vulnerability_management/NIST_SP_800-218_chunks.jsonl) | 57 | 236 | 141 | 92 | 3 | 0 | 419.0 KB | `SUCCESS` |
| **TOTALS** | **5 Categories** | **1,057** | **3,175** | **2,408** | **620** | **147** | **13** | **5,900.2 KB** | **`10/10 SUCCESS`** |

---

## 5. Storage & Safety Invariants

- **Total Output Size**: **5.90 MB (6,041,805 bytes)**
- **Current Available Disk Space**: **1,550.2 MB (1.55 GB)**
- **Mandatory Reserve**: **500.0 MB**
- **Headroom Remaining**: **1,050.2 MB**
- **Estimated Full Corpus Space (4,649 pages)**: $\approx 26.5 \text{ MB}$ (leaves $> 1.02 \text{ GB}$ free headroom).
- **Invariants Preserved**:
  - Source PDFs (`documents/`): 100% untouched.
  - Raw extractions (`data/extraction_pilot_v3/`): 100% untouched.
  - Cleaned corpus (`data/cleaned_corpus/`, `data/cleaned_pilot/`): 100% untouched.
  - Git repository: Zero commits, pushes, or branching operations.
  - Embedding / Qdrant: Zero embedding generation; zero vector DB operations.

---

## 6. Final Revalidation Verdict

**`PASS — All 3 Audit Findings have been successfully resolved, fully tested, and verified against the regenerated 10-document pilot cohort. The chunking pipeline is approved and ready for full-corpus execution.`**
