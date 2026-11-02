# Lightweight Embedding Benchmark Usage Guide

**Project**: Cybersecurity RAG  
**Location**: `C:\Users\Computer\Desktop\cybersecurity-rag`  
**Target Script**: [`scripts/benchmark_lightweight_embeddings.py`](file:///C:/Users/Computer/Desktop/cybersecurity-rag/scripts/benchmark_lightweight_embeddings.py)  

---

## 1. Overview

The lightweight embedding benchmark compares 384-dimensional models on CPU to evaluate retrieval accuracy and latency on the NIST cybersecurity corpus without the substantial compute overhead of heavyweight models like `BAAI/bge-m3`.

### Evaluated Models

| Model Name | Alias | Role | Dimension | Local Cache Status |
| :--- | :--- | :---: | :---: | :---: |
| `BAAI/bge-small-en-v1.5` | BGE-Small-en-v1.5 | Current Baseline | 384 | **Available** (Cached) |
| `intfloat/e5-small-v2` | E5-Small-v2 | Candidate | 384 | **Unavailable** (Not cached locally; skipped automatically) |
| `sentence-transformers/all-MiniLM-L6-v2` | MiniLM-L6-v2 | Candidate | 384 | **Available** (Cached) |
| `BAAI/bge-m3` | BGE-M3 | Historical Baseline | 1024 | **Historical Reference** (Pre-recorded numbers; not loaded or re-evaluated) |

---

## 2. Preflight & Dry-Run (Non-Executing)

To verify chunk integrity, question counts, and cache availability without loading models or generating embeddings:

```powershell
python scripts\benchmark_lightweight_embeddings.py --dry-run
```

Expected output:
```text
[Step 1] Loading pilot chunks from 2 files...
  Loaded 396 chunks (SP 800-144: 164, SP 800-146: 232).
[Step 2] Loading current ground truth...
  Loaded 15 verified, evaluation-eligible questions.
[Step 3] Validating ground truth chunk IDs against pilot chunk pool...
  [SUCCESS] All referenced ground-truth chunk IDs exist in the active pilot pool.
[Step 4] Checking local cache availability for lightweight models...
  [AVAILABLE] BGE-Small-en-v1.5 (`BAAI/bge-small-en-v1.5`)
  [UNAVAILABLE - SKIPPED] E5-Small-v2 (`intfloat/e5-small-v2`) is NOT cached locally.
  [AVAILABLE] MiniLM-L6-v2 (`sentence-transformers/all-MiniLM-L6-v2`)
```

---

## 3. Manual Benchmark Execution Command

When you are ready to execute the benchmark, run the following command from the project root (`C:\Users\Computer\Desktop\cybersecurity-rag`):

```powershell
python scripts\benchmark_lightweight_embeddings.py
```

### Optional Command-Line Arguments

- `--models`: Run specific models only (e.g. `python scripts\benchmark_lightweight_embeddings.py --models BAAI/bge-small-en-v1.5`).
- `--top-k`: Customize the retrieval ranking depth (default: `5`).
- `--batch-size`: Batch size for corpus chunk encoding (default: `16`).
- `--output-json`: Destination path for machine-readable results (default: `reports/benchmark_lightweight_results.json`).
- `--output-md`: Destination path for the Markdown comparison report (default: `reports/embedding_benchmark_lightweight_report.md`).

---

## 4. Benchmark Methodology & Technical Rules

1. **In-Memory Cosine Similarity**: All chunks and queries are $L_2$-normalized upon encoding (`normalize_embeddings=True`). Vector similarity is computed in memory via matrix dot product (`corpus_embeddings @ query_embedding`). No vectors are written to disk, and Qdrant is completely bypassed.
2. **Model-Appropriate Prefixes**:
   - `intfloat/e5-small-v2`: Automatically prefixes queries with `"query: "` and documents with `"passage: "`.
   - `BAAI/bge-small-en-v1.5` & `all-MiniLM-L6-v2`: Standard direct text encoding without prefixes.
3. **Strict Sequential Loading**: Models are loaded one at a time with `local_files_only=True`. After evaluating queries, the model and chunk embeddings are explicitly deleted (`del model`, `del corpus_embeddings`), and `gc.collect()` is called before loading the next model.
4. **Cache Enforcement**: Models that are not locally available in `C:\Users\Computer\.cache\huggingface\hub` are reported as skipped and will not trigger remote network downloads or API calls.
5. **Historical Reference Integrity**: Historical results for `BAAI/bge-m3` are embedded in the script as reference numbers and are never recomputed.

---

## 5. Output Interpretation

The script generates two artifacts:

1. **Machine-Readable JSON** (`reports/benchmark_lightweight_results.json`):
   - Contains raw latencies, per-query Hit@K, retrieved chunk IDs, top-1 similarity scores, and execution timestamps.
2. **Formatted Markdown Report** (`reports/embedding_benchmark_lightweight_report.md`):
   - Contains the side-by-side comparative table against the historical BGE-M3 reference.

### Key Metrics Guide

- **Hit@1 / Hit@3 / Hit@5**: Percentage of evaluation queries where at least one verified NIST chunk appears in the top 1, 3, or 5 retrieved candidates. Higher is better.
- **Precision@5**: Average proportion of retrieved top-5 chunks that are verified relevant. Higher is better.
- **MRR (Mean Reciprocal Rank)**: $1 / \text{rank}$ of the first relevant chunk found. Measures how close to the top position relevant content appears (1.0 = always first, 0.5 = rank 2). Higher is better.
- **Corpus Encoding Time**: Total seconds required to encode the 396 pilot chunks.
- **Throughput**: Chunks encoded per second on CPU.
- **Average Query Latency**: Time in milliseconds to encode a single query string on CPU. Sub-500 ms is considered responsive for interactive RAG.
