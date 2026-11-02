# Qdrant Ingestion Preflight & Architecture Design Report

**Date:** 2026-10-17  
**Project:** Cybersecurity RAG (`C:\Users\Computer\Desktop\cybersecurity-rag`)  
**Status:** Preflight Verified & Script Implemented (Awaiting Ingestion Approval)  

---

## 1. Executive Summary

This report establishes the inspection findings and operational design for ingesting the finalized **13,084 BAAI/bge-m3 embeddings** into the Qdrant vector database.

All embedding matrix checkpoints (53 batches) and unified arrays have been verified against the SHA-256 buffer signature (`9cf5f8d30d98c7e295f4514a0f29a3bcecb606722be2e2a2a1d1083d9e7c237e`) and corpus fingerprint (`91f3d87f4fe3ece9930cc72c9576a01dd313ef94b585b6bb1f94b1a16f61c018`).

In accordance with strict safety gates:
- **Zero embeddings were recomputed.**
- **No Qdrant database writes or connections were performed.**
- **No existing collections or source files were modified or deleted.**
- A dedicated, resilient ingestion tool [`scripts/ingest_embeddings_qdrant.py`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/scripts/ingest_embeddings_qdrant.py) has been developed and verified in `--preflight` dry-run mode.

---

## 2. Phase 1 Inspection Findings

### 2.1 Repository Structure & Dependencies
- **Qdrant Client:** `qdrant-client` version `1.19.0` is installed in the local virtual environment (`.venv\Scripts\python.exe`).
- **Disk Free Space:** 21.25 GB available on `C:` drive (well exceeding the 500 MB minimum reserve).
- **RAM / Swap:** 7.82 GB RAM, 15.94 GB available swap space. Total process memory footprint during ingestion is estimated at ~150–200 MB.

### 2.2 Qdrant Deployment & Connection Architecture
- **Process Check:** Neither native `qdrant` nor `docker` processes are running in the background.
- **Connection Mode:** Configured as an **embedded local instance** (`path="data/qdrant"`). The `qdrant-client` interacts directly with local RocksDB/sled-backed storage files on disk via embedded Rust bindings.
- **Existing Collections:**
  - `data/qdrant`: Does not exist yet.
  - `qdrant_data/`: Contains only `.lock` and empty `meta.json` (`{"collections": {}, "aliases": {}}`, 0 points).
  - `qdrant_db/`: Contains only `.lock` and empty `meta.json` (`{"collections": {}, "aliases": {}}`, 0 points).
  - **Result:** No legacy vectors will be impacted.

### 2.3 Finalized Embedding Artifacts & Alignment
- **Location:** `data/embeddings_bge_m3/`
  - `embeddings.npy`: `(13084, 1024)` float32 array, $L_2$-normalized, 53,592,192 bytes.
  - `chunk_metadata.jsonl`: Exactly 13,084 records matching matrix rows 1-to-1.
  - `manifest.json`: Status `FINALIZED`, fingerprint `91f3d87f4fe3ece9930cc72c9576a01dd313ef94b585b6bb1f94b1a16f61c018`.
- **Row Mapping:** Row index $i$ in `embeddings.npy` corresponds strictly to line $i$ in `chunk_metadata.jsonl`.

### 2.4 Payload Schema & Chunk Text Analysis
- **Authoritative Chunk Files:** 73 JSONL files (10 pilot in `data/chunks_pilot/`, 63 corpus in `data/chunks_corpus/`).
- **Total Text Size:** 12.51 MB UTF-8 across all 13,084 chunks (total chunk JSONL size is 23.18 MB).
- **Text Inclusion Strategy:**
  - In `app/retrieval/dense.py`, `DenseRetriever` reads `payload.get("text", "")` directly from Qdrant search results.
  - Storing text directly inside Qdrant payloads requires only ~12–15 MB additional storage. This enables immediate sub-millisecond retrieval of chunk text for downstream RAG generators, hybrid fusion, reranking, and evaluation scripts without requiring disk I/O to JSONL files during querying.
  - The script also provides a `--metadata-only` flag if decoupled text storage is ever preferred.

---

## 3. Ingestion Design & Script Implementation

The ingestion script [`scripts/ingest_embeddings_qdrant.py`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/scripts/ingest_embeddings_qdrant.py) implements the following architecture:

```
+-----------------------------------------------------------------------------------+
|                            Ingestion Pipeline Flow                                |
+-----------------------------------------------------------------------------------+
|  1. Preflight Validation                                                          |
|     - Check embeddings.npy shape (13084, 1024), float32                          |
|     - Verify buffer SHA-256 against manifest.json                                |
|     - Verify 13,084 metadata records & corpus fingerprint                        |
|                                                                                   |
|  2. Payload Enrichment                                                            |
|     - Match chunk_id to source JSONLs                                             |
|     - Attach section_heading, section_path, citation_label, text                  |
|                                                                                   |
|  3. Deterministic Point ID Generation                                             |
|     - Default: Integer Index 0..13083 (matches matrix row index)                  |
|     - Alternative: UUIDv5 via fixed namespace UUID                               |
|                                                                                   |
|  4. Batch Upload (Default: 256 points/batch)                                      |
|     - PointStruct(id=..., vector=..., payload=...)                                |
|     - Progress logging: rate, ETA, percent complete                               |
|     - Idempotent upsert (re-running updates existing points, 0 duplicates)        |
|                                                                                   |
|  5. Post-Ingestion Verification                                                   |
|     - Assert points_count == 13084                                                |
|     - Assert vector_size == 1024 and distance == COSINE                           |
|     - Scroll sample records and verify fields                                     |
+-----------------------------------------------------------------------------------+
```

### 3.1 Point ID Strategy
- **Integer IDs (`0..13083`)**:
  - Matches row index in `embeddings.npy` directly.
  - Takes 8 bytes per ID in index.
  - 100% idempotent: upserting point ID `42` always updates row `42`.
- **UUIDv5 (`uuid.uuid5(NAMESPACE, chunk_id)`)**: Supported via `--id-scheme uuid`.

### 3.2 Target Collection Name
- **Proposed Name:** `cybersecurity_chunks_bge_m3`
- **Rationale:**
  - The existing configuration in `app/core/config.py` references `"cybersecurity_chunks"` configured for BGE-small (384 dimensions).
  - Naming the collection `cybersecurity_chunks_bge_m3` isolates the 1,024-dimension BGE-M3 index, preventing vector dimension collisions with legacy 384-dimension scripts.
  - If desired, the user can pass `--collection-name cybersecurity_chunks` to overwrite or use the default legacy name.

### 3.3 Payload Schema Specification
Each point payload contains:
```json
{
  "chunk_id": "NIST_SP_800-144_txt_00001",
  "document_id": "NIST_SP_800-144",
  "category": "cloud_application_security",
  "content_type": "text",
  "page_start": 1,
  "page_end": 1,
  "token_count": 9,
  "source_file": "data\\chunks_corpus\\cloud_application_security\\NIST_SP_800-144_chunks.jsonl",
  "section": "Introduction",
  "section_heading": "Introduction",
  "section_path": ["Introduction"],
  "citation_label": "[NIST_SP_800-144 Page 1]",
  "text": "**Special Publication 800-144**\n\n..."
}
```

---

## 4. Preflight Dry-Run Verification Results

The script was executed in `--preflight` dry-run mode:
```powershell
.venv\Scripts\python.exe scripts/ingest_embeddings_qdrant.py --preflight
```

**Results:**
- Disk Space: 21.25 GB free (Threshold: >= 0.5 GB) - **PASS**
- Manifest Status: `FINALIZED` - **PASS**
- Model Name: `BAAI/bge-m3` - **PASS**
- Matrix Shape: `(13084, 1024)` float32 - **PASS**
- SHA-256 Buffer Hash: `9cf5f8d30d98c7e295f4514a0f29a3bcecb606722be2e2a2a1d1083d9e7c237e` - **PASS**
- Metadata Records: 13,084 - **PASS**
- Corpus Fingerprint: `91f3d87f4fe3ece9930cc72c9576a01dd313ef94b585b6bb1f94b1a16f61c018` - **PASS**
- Chunk Text Matching: 100% (All 13,084 IDs matched source JSONL records) - **PASS**
- Zero database writes were performed.

---

## 5. Proposed Execution Commands

Once approved, the following commands can be executed:

### Option A: Standard Ingestion (Recommended)
Ingests all 13,084 vectors with rich payloads and chunk text into embedded Qdrant under collection `cybersecurity_chunks_bge_m3`:
```powershell
.venv\Scripts\python.exe scripts/ingest_embeddings_qdrant.py --collection-name cybersecurity_chunks_bge_m3
```

### Option B: Ingestion into Default Legacy Collection Name
If you prefer replacing the default collection name used in `config.py`:
```powershell
.venv\Scripts\python.exe scripts/ingest_embeddings_qdrant.py --collection-name cybersecurity_chunks --recreate
```

### Option C: Metadata-Only Ingestion (Decoupled Text)
If you prefer not storing chunk text in Qdrant payloads:
```powershell
.venv\Scripts\python.exe scripts/ingest_embeddings_qdrant.py --collection-name cybersecurity_chunks_bge_m3 --metadata-only
```

### Option D: Verification Only (Post-Ingestion Health Check)
To re-verify collection health at any time without re-ingesting:
```powershell
.venv\Scripts\python.exe scripts/ingest_embeddings_qdrant.py --collection-name cybersecurity_chunks_bge_m3 --verify-only
```

---

## 6. Strict Safety Gate — Waiting for User Approval

All inspections and script implementations are complete. In adherence to the safety gate, **no points have been uploaded and no Qdrant collections have been modified.**

Please confirm whether you approve proceeding with ingestion using **Option A** (`cybersecurity_chunks_bge_m3`), **Option B** (`cybersecurity_chunks`), or another configuration.
