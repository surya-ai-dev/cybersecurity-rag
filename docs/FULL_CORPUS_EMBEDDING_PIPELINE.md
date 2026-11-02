# Full-Corpus Embedding Generation Pipeline: BAAI/bge-m3

**Project**: Cybersecurity RAG  
**Location**: `C:\Users\Computer\Desktop\cybersecurity-rag`  
**Target Script**: [`scripts/generate_full_corpus_embeddings.py`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/scripts/generate_full_corpus_embeddings.py)  
**Model**: `BAAI/bge-m3` (1024-dimensional dense representations)  
**Corpus**: 73 NIST publications, 13,084 structure-aware chunks  

---

## 1. Executive Summary

This pipeline generates 1024-dimensional dense embeddings for the entire 13,084-chunk NIST cybersecurity corpus using locally cached `BAAI/bge-m3` weights. It is designed specifically for **CPU-only execution on a 16 GB laptop with tight disk space reserves**.

### Key Architectural Safeguards
1. **Zero Downloads / Offline Mode**: Uses `local_files_only=True`. Never contacts external Hugging Face servers or installs packages.
2. **Durable, Atomic Checkpoints**: Writes intermediate batches (`batch_XXXXX.npz` + `.json`) every 250 chunks via temporary files and atomic renames. If interrupted, at most one 17-minute batch is ever repeated.
3. **Flat RAM Footprint**: Immediately deletes generated vector tensors from Python memory and calls `gc.collect()` after each checkpoint write. Memory usage remains stable at ~1.0–1.2 GB process RSS and will not balloon.
4. **Mandatory Disk Space Reserve**: Enforces a strict **500.0 MB** free disk space floor. Halts safely before disk exhaustion.
5. **Deterministic Corpus Fingerprinting**: Computes a SHA-256 fingerprint (`91f3d87f4fe3ece9...`) across all 13,084 chunks. Resumption verifies corpus and model compatibility to prevent mixing incompatible embeddings.
6. **Decoupled from Vector DB**: Qdrant insertion is completely isolated and left for a future phase.

---

## 2. Authoritative Corpus Verification

The active corpus consists of **13,084 unique chunks** across **73 NIST publications**:

| Directory | File Count | Chunk Count | Content Breakdown |
| :--- | :---: | :---: | :--- |
| [`data/chunks_pilot/`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/data/chunks_pilot/) | 10 | 3,175 | 2,425 text, 656 tables, 94 figures |
| [`data/chunks_corpus/`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/data/chunks_corpus/) | 63 | 9,909 | 8,259 text, 1,153 tables, 497 figures |
| **Total Combined Corpus** | **73** | **13,084** | **10,684 text, 1,809 tables, 591 figures** |

- **Duplicate Chunk IDs**: **0** (100% unique IDs).
- **Schema Consistency**: 100% of chunks conform to the unified structure-aware schema (`chunk_id`, `document_id`, `content_type`, `page_start`, `page_end`, `text`, `token_count`, `category`).

---

## 3. Storage & Resource Budget

| Dimension | Metric / Value | Notes |
| :--- | :---: | :--- |
| **Current Free Disk Space** | **2,131.38 MB (~2.08 GB)** | Verified from drive root |
| **Mandatory Reserve Floor** | **500.00 MB** | Pipeline automatically halts if free space drops below this |
| **Net Usable Headroom** | **1,631.38 MB** | Available space above the reserve |
| **Raw Vector Storage (float32)**| **51.11 MB** | $13,084 \text{ chunks} \times 1,024 \text{ floats} \times 4 \text{ bytes}$ |
| **Intermediate Checkpoints** | **~55.0 MB** | 53 checkpoint `.npz` files (1.02 MB each) |
| **Metadata & Manifest** | **~11.0 MB** | Aligned JSONL metadata and manifests |
| **Total Maximum Artifact Footprint** | **~117.22 MB** | Combined checkpoints + finalized array |
| **Storage Safety Margin** | **13.9x** | Net usable headroom is ~14x larger than total artifact size |

---

## 4. Operational Commands

All commands must be executed from the project root (`C:\Users\Computer\Desktop\cybersecurity-rag`).

### Step 1: Preflight Audit (Non-Executing)
Inspects the corpus, model cache, and disk space without loading models or generating vectors:

```powershell
python scripts\generate_full_corpus_embeddings.py --preflight
```

### Step 2: Full-Corpus Embedding Generation
Starts (or resumes) the batch-wise generation process:

```powershell
python scripts\generate_full_corpus_embeddings.py
```

#### Configurable CLI Options
- `--checkpoint-size 250`: Number of chunks per checkpoint file (default: 250).
- `--batch-size 16`: Number of chunks passed to `model.encode(...)` per forward pass (default: 16).
- `--output-dir data/embeddings_bge_m3`: Custom output location.

### Step 3: Standalone Validation & Finalization
Inspects all completed checkpoints, verifies 100% coverage, checks for finite values, and merges them into unified `embeddings.npy`:

```powershell
python scripts\generate_full_corpus_embeddings.py --finalize
```

---

## 5. Checkpoint & Resumption Architecture

### Checkpoint Directory Structure
```text
data/embeddings_bge_m3/
├── manifest.json                  # Overall progress, model revision, fingerprint, completed batches
├── checkpoints/
│   ├── checkpoint_00000.npz       # Vectors (250 x 1024) and chunk IDs
│   ├── checkpoint_00000.json      # Batch metadata, chunk ranges, SHA-256 checksum
│   ├── checkpoint_00001.npz
│   ├── checkpoint_00001.json
│   └── ... (up to checkpoint_00052)
├── embeddings.npy                 # (Generated upon finalization) 13,084 x 1024 float32 matrix (51.1 MB)
└── chunk_metadata.jsonl           # (Generated upon finalization) Aligned chunk metadata rows
```

### Crash Recovery & Interruption Protocol
1. **Graceful Cancellation**: You can safely interrupt the process at any time via `Ctrl+C`. The current batch is cleanly discarded, but all previously written checkpoints remain intact.
2. **Crash Resilience**: If power is cut during a write, the incomplete `.tmp.npz` file is simply ignored on the next startup.
3. **Resumption**: Re-running the script automatically detects existing checkpoints, verifies their SHA-256 integrity and chunk ID alignment, and resumes at the first uncompleted batch.

---

## 6. Known Risks & Mitigations

| Risk | Impact | Mitigation Strategy |
| :--- | :--- | :--- |
| **Long CPU Duration (~15.1 hours)** | Machine must remain awake and active | Run as an uninterrupted overnight job. Keep laptop plugged into AC power and disable sleep mode. Use `/goal` if running autonomously. |
| **Memory Pressure (0.38 GB RAM available)** | Risk of OS thrashing | Batch size is strictly limited to 16 chunks per forward pass. Memory is purged every 250 chunks via `del vectors; gc.collect()`. |
| **Disk Exhaustion** | System instability if drive fills up | Total disk footprint is capped at ~117 MB (13.9x safety margin). Hard floor at 500 MB stops the process safely. |
