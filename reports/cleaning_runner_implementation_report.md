# Production Corpus Cleaning Runner Implementation Report

> **Project**: `cybersecurity-rag`
> **Pipeline Stage**: Stage 3 — Full-Corpus Cleaning Infrastructure
> **Author**: Senior Document-Processing Engineer & Cybersecurity RAG Pipeline Architect
> **Date**: 2026-10-14
> **Status**: **`IMPLEMENTATION COMPLETE & VERIFIED`**
> **Final Recommendation**: **`READY FOR PREFLIGHT`**

---

## 1. Executive Summary

A safe, resumable, and batch-controlled production runner has been developed for Stage 3 full-corpus text cleaning in the Cybersecurity RAG project.

The implementation bridges the validated Stage 2 conservative cleaning engine with full-corpus operations across the remaining **63 publications (3,592 physical pages)**. It introduces atomic checkpointing, path-bounded safe recovery, active disk-space guards, and strict artifact validation without modifying any existing cleaning rules, source PDFs, or pilot outputs.

### High-Level Metrics

| Metric | Target / Specification | Measured Implementation | Status |
| :--- | :--- | :--- | :--- |
| **Eligible Workload** | 63 non-pilot documents | Exactly 63 documents (3,592 pages) | **VERIFIED** |
| **Pilot Exclusion** | 10 Stage 2 pilot documents | 10/10 pilot documents excluded (1,057 pages) | **VERIFIED** |
| **Batch Architecture** | 4 deterministic, disjoint batches | Batch 1: 16 (871 pgs), Batch 2: 16 (776 pgs), Batch 3: 16 (1339 pgs), Batch 4: 15 (606 pgs) | **VERIFIED** |
| **Output Destination** | `data/cleaned_corpus/` | Isolated directory, no overwrites | **VERIFIED** |
| **Checkpoint Path** | `data/cleaned_corpus/corpus_cleaning_checkpoint.json` | Atomic `.tmp` replacement, 4-state lifecycle | **VERIFIED** |
| **Safety Threshold** | 500 MB free disk reserve | 1,935 MB available vs 148.32 MB required | **VERIFIED** |
| **Test Suite Coverage** | Unit + integration tests | **97/97 passed (100%)** | **VERIFIED** |
| **Preflight Gate Status** | Preflight prerequisites | **`READY`** | **VERIFIED** |

---

## 2. Architecture & Design Principles

The runner architecture follows the proven principles established by the Stage 1 extraction coordinator (`scripts/run_corpus_extraction.py`), adapted specifically for document text cleaning:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   CLI Entry Points / Invocation                         │
│   app/ingestion/clean_text.py  OR  scripts/run_corpus_cleaning.py      │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                     CorpusCleaningRunner Orchestrator                   │
│  - Active Disk Space Guard (> 500 MB reserve check)                     │
│  - Startup Recovery of interrupted IN_PROGRESS documents                │
│  - Checkpoint Manifest Management (atomic writes)                      │
│  - Deterministic Batch Slicing (1-4) & Single Document execution        │
└───────────────────┬────────────────────────────────┬───────────────────┘
                    │                                │
                    ▼                                ▼
┌──────────────────────────────────────┐  ┌──────────────────────────────┐
│     DocumentCleaningPipeline         │  │   Post-Cleaning Validation   │
│  - Running Header & Footer stripping │  │  - JSON schema & page count  │
│  - Domain-guarded Hyphen repair      │  │  - Non-empty MD & TXT files  │
│  - Typography & Whitespace norm      │  │  - Manifest verification     │
│  - Statutory Boilerplate tagging     │  │  - Figure asset parity check │
└──────────────────────────────────────┘  └──────────────────────────────┘
```

### Key Architectural Safeguards:
1. **Separation of Concerns**: Cleaning algorithms (`header_footer.py`, `hyphenation.py`, `encoding.py`, `boilerplate.py`, `pipeline.py`) remain completely untouched. The runner orchestrates execution, checkpointing, recovery, and validation.
2. **Atomic Checkpointing**: Checkpoint updates are written to `corpus_cleaning_checkpoint.json.tmp` and replaced atomically using `os.replace` to prevent file corruption during sudden interruption.
3. **Path-Bounded Directory Containment**: Directory cleanup operations (`_clean_partial_directory`) enforce that any targeted path is strictly a sub-descendant of `output_dir`, at least two levels deep (`<category>/<doc_id>`), and matches the expected document ID. Root and category levels cannot be deleted.
4. **Non-Destructive Recovery**: Recovery targets only unvalidated `IN_PROGRESS` directories. Completed documents with valid artifacts are protected from deletion or overwriting.
5. **Data-Driven Disk Guards**: Estimated storage is calculated using measured pilot statistics (~42.3 KB/page). A pre-document check ensures the remaining space will not breach the configurable 500 MB reserve.

---

## 3. Document Inventory & Batch Partitioning

The 63 eligible documents are partitioned into four non-overlapping, deterministic batches:

### Batch 1 (16 documents, 871 pages)
| # | Document ID | Category | Expected Pages | Duplicate Of |
| :- | :--- | :--- | :-: | :--- |
| 1 | `NIST_SP_800-233` | `root` | 43 | — |
| 2 | `NIST_SP_800-239` | `root` | 32 | — |
| 3 | `NIST_SP_800-144` | `cloud_application_security` | 80 | — |
| 4 | `NIST_SP_800-145` | `cloud_application_security` | 7 | — |
| 5 | `NIST_SP_800-146` | `cloud_application_security` | 81 | — |
| 6 | `NIST_SP_800-190` | `cloud_application_security` | 62 | — |
| 7 | `NIST_SP_800-207` | `cloud_application_security` | 31 | — |
| 8 | `NIST_SP_800-228` | `cloud_application_security` | 64 | — |
| 9 | `NIST_SP_800-107` | `cryptography_security` | 25 | — |
| 10 | `NIST_SP_800-111` | `cryptography_security` | 40 | — |
| 11 | `NIST_SP_800-130` | `cryptography_security` | 120 | — |
| 12 | `NIST_SP_800-131` | `cryptography_security` | 55 | — |
| 13 | `NIST_SP_800-133` | `cryptography_security` | 80 | — |
| 14 | `NIST_SP_800-175` | `cryptography_security` | 91 | — |
| 15 | `NIST_SP_800-185` | `cryptography_security` | 32 | — |
| 16 | `NIST_SP_800-197` | `cryptography_security` | 28 | — |

### Batch 2 (16 documents, 776 pages)
| # | Document ID | Category | Expected Pages | Duplicate Of |
| :- | :--- | :--- | :-: | :--- |
| 17 | `NIST_SP_800-208` | `cryptography_security` | 59 | — |
| 18 | `NIST_SP_800-232` | `cryptography_security` | 52 | — |
| 19 | `NIST_SP_800-38` | `cryptography_security` | 34 | — |
| 20 | `NIST_SP_800-56` | `cryptography_security` | 131 | — |
| 21 | `NIST_SP_800-57` | `cryptography_security` | 54 | — |
| 22 | `NIST_SP_800-78` | `cryptography_security` | 34 | — |
| 23 | `NIST_SP_800-89` | `cryptography_security` | 38 | — |
| 24 | `NIST_SP_800-132` | `identity_access` | 18 | — |
| 25 | `NIST_SP_800-157` | `identity_access` | 13 | — |
| 26 | `NIST_SP_800-162` | `identity_access` | 47 | — |
| 27 | `NIST_SP_800-178` | `identity_access` | 68 | — |
| 28 | `NIST_SP_800-192` | `identity_access` | 68 | — |
| 29 | `NIST_SP_800-205` | `identity_access` | 42 | — |
| 30 | `NIST_SP_800-210` | `identity_access` | 34 | — |
| 31 | `NIST_SP_800-217` | `identity_access` | 50 | — |
| 32 | `NIST_SP_800-224` | `identity_access` | 34 | — |

### Batch 3 (16 documents, 1,339 pages)
| # | Document ID | Category | Expected Pages | Duplicate Of |
| :- | :--- | :--- | :-: | :--- |
| 33 | `NIST_SP_800-63` | `identity_access` | 96 | — |
| 34 | `NIST_SP_800-73` | `identity_access` | 81 | — |
| 35 | `NIST_SP_800-76` | `identity_access` | 61 | — |
| 36 | `NIST_SP_800-79` | `identity_access` | 123 | — |
| 37 | `NIST_SP_800-101` | `incident_response` | 85 | — |
| 38 | `NIST_SP_800-201` | `incident_response` | 39 | — |
| 39 | `NIST_SP_800-72` | `incident_response` | 67 | — |
| 40 | `NIST_SP_800-83` | `incident_response` | 47 | — |
| 41 | `NIST_SP_800-86` | `incident_response` | 121 | — |
| 42 | `NIST_SP_800-161` | `risk_management` | 325 | — |
| 43 | `NIST_SP_800-221` | `risk_management` | 20 | — |
| 44 | `NIST_SP_800-226` | `risk_management` | 90 | — |
| 45 | `NIST_SP_800-50` | `risk_management` | 87 | — |
| 46 | `NIST_SP_800-61` | `risk_management` | 48 | `documents/NIST.SP.800-61r3.pdf` |
| 47 | `NIST_SP_800-204` | `supply_chain_security` | 41 | — |
| 48 | `NIST_SP_800-140` | `threats_malware` | 8 | — |

### Batch 4 (15 documents, 606 pages)
| # | Document ID | Category | Expected Pages | Duplicate Of |
| :- | :--- | :--- | :-: | :--- |
| 49 | `NIST_SP_800-150` | `threats_malware` | 43 | — |
| 50 | `NIST_SP_800-154` | `threats_malware` | 25 | — |
| 51 | `NIST_SP_800-223` | `threats_malware` | 34 | — |
| 52 | `NIST_SP_800-115` | `vulnerability_management` | 80 | — |
| 53 | `NIST_SP_800-216` | `vulnerability_management` | 37 | — |
| 54 | `NIST_SP_800-231` | `vulnerability_management` | 76 | — |
| 55 | `NIST_SP_800-40` | `vulnerability_management` | 28 | — |
| 56 | `NIST_SP_800-51` | `vulnerability_management` | 13 | — |
| 57 | `NIST_SP_800-114` | `zero_trust_network_security` | 44 | — |
| 58 | `NIST_SP_800-125` | `zero_trust_network_security` | 30 | — |
| 59 | `NIST_SP_800-153` | `zero_trust_network_security` | 24 | — |
| 60 | `NIST_SP_800-183` | `zero_trust_network_security` | 30 | — |
| 61 | `NIST_SP_800-215` | `zero_trust_network_security` | 41 | — |
| 62 | `NIST_SP_800-41` | `zero_trust_network_security` | 48 | — |
| 63 | `NIST_SP_800-46` | `zero_trust_network_security` | 53 | — |

---

## 4. Checkpoint Schema & State Machine

The checkpoint is maintained at:
`data/cleaned_corpus/corpus_cleaning_checkpoint.json`

### Document Lifecycle State Machine:
```
           ┌───────────┐
           │  PENDING  │ ◄────────────────────────┐
           └─────┬─────┘                          │
                 │ (Runner picks doc)             │ (Recovery / Retry)
                 ▼                                │
          ┌─────────────┐                         │
          │ IN_PROGRESS │ ────────────────────────┤
          └──────┬──────┘   (Worker interrupted)  │
                 │                                │
        ┌────────┴────────┐                       │
        │                 │                       │
 (Validation passed) (Error or validation failed) │
        │                 │                       │
        ▼                 ▼                       │
  ┌───────────┐     ┌───────────┐                 │
  │  SUCCESS  │     │  FAILED   │ ────────────────┘
  └───────────┘     └───────────┘
```

### Manifest Schema Sample:
```json
{
  "target_output_dir": "C:\\Users\\Computer\\Desktop\\cybersecurity-rag\\data\\cleaned_corpus",
  "total_documents": 63,
  "total_pages": 3592,
  "created_at": "2026-10-14T14:31:24.123456",
  "updated_at": "2026-10-14T14:31:24.123456",
  "batches": {
    "1": { "document_count": 16, "total_pages": 871 },
    "2": { "document_count": 16, "total_pages": 776 },
    "3": { "document_count": 16, "total_pages": 1339 },
    "4": { "document_count": 15, "total_pages": 606 }
  },
  "summary": {
    "completed": 0,
    "failed": 0,
    "in_progress": 0,
    "pending": 63
  },
  "documents": {
    "NIST_SP_800-233": {
      "document_id": "NIST_SP_800-233",
      "category": "root",
      "batch_number": 1,
      "relative_path": "documents/NIST_SP_800-233.pdf",
      "input_dir": "C:\\Users\\Computer\\Desktop\\cybersecurity-rag\\data\\extraction_corpus_68\\root\\NIST_SP_800-233",
      "expected_pages": 43,
      "sha256_hash": "...",
      "duplicate_of": [],
      "status": "PENDING",
      "started_at": null,
      "completed_at": null,
      "elapsed_seconds": null,
      "actual_pages": null,
      "original_char_count": null,
      "cleaned_char_count": null,
      "delta_chars": null,
      "total_headers_removed": null,
      "total_footers_removed": null,
      "total_hyphens_repaired": null,
      "total_encoding_transforms": null,
      "validation_status": null,
      "error": null
    }
  }
}
```

---

## 5. Automated Test Suite Results

The runner and integrated CLI were subjected to comprehensive unit and integration testing:

```powershell
python -m unittest tests/test_corpus_cleaning_runner.py -v
```

### Results:
| Test Case | Objective | Result |
| :--- | :--- | :---: |
| `test_deterministic_batch_assignment` | Verifies 4 disjoint batches (16, 16, 16, 15), 3,592 pages, invalid batch guard | **PASSED** |
| `test_pilot_exclusion_all_10_documents` | Confirms all 10 pilot IDs are strictly absent from inventory and batches | **PASSED** |
| `test_atomic_checkpointing` | Verifies atomic file replacement, state persistence, and summary recalculation | **PASSED** |
| `test_success_output_validation` | Enforces JSON page count, non-empty MD/TXT, manifest, and figure checks | **PASSED** |
| `test_interrupted_document_recovery` | Confirms path-bounded removal of partial dirs and reset to PENDING (idempotent) | **PASSED** |
| `test_failed_document_retry` | Verifies reset of FAILED status to PENDING upon retry request | **PASSED** |
| `test_output_path_containment_security_guard` | Rejects cleanup outside output root, category level, or doc_id mismatches | **PASSED** |
| `test_insufficient_disk_space_handling` | Halts execution when space falls below 500 MB reserve | **PASSED** |
| `test_duplicate_source_document_cross_references` | Verifies `NIST_SP_800-61` preserves mutual duplicate cross-reference | **PASSED** |
| `test_idempotent_reruns` | Valid completed documents are skipped without modifying disk artifacts | **PASSED** |
| `test_no_accidental_overwriting_of_valid_outputs` | Recovery never removes a directory with valid SUCCESS artifacts | **PASSED** |

### Complete Regression Suite:
```powershell
python -m unittest discover -s tests -v
```
- **Total Tests Discovered**: 97
- **Total Tests Passed**: 97 (100%)
- **Failures / Errors**: 0
- **Execution Time**: 35.456s

---

## 6. Exact Commands for Dry-Run and Single-Document Testing

### Exact Dry-Run Commands:
```powershell
# Dry-run inspection across the entire 63-document corpus
python scripts/run_corpus_cleaning.py --dry-run --all

# Dry-run inspection for Batch 1 only
python scripts/run_corpus_cleaning.py --dry-run --batch 1

# Dry-run inspection via the main clean_text CLI
python app/ingestion/clean_text.py --dry-run --batch 1
```

### Exact Single-Document Test Commands:
```powershell
# Dry-run inspection for a single document
python scripts/run_corpus_cleaning.py --dry-run --doc NIST_SP_800-233

# When authorized for execution: run cleaning on a single document
python scripts/run_corpus_cleaning.py --doc NIST_SP_800-233
```

---

## 7. Conclusion & Recommendation

The safe, resumable production cleaning runner and updated CLI interfaces have been fully implemented, rigorously tested (97/97 tests green), and certified to have zero impact on existing pilot outputs or extraction data.

All preflight preconditions are satisfied.

### Final Recommendation: **`READY FOR PREFLIGHT`**
