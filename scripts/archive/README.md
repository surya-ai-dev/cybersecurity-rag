# Scripts Archive: Phase 1 Investigation & Diagnostic Tools

This directory contains 30 ad-hoc diagnostic, inspection, and verification scripts created during **Phase 1: Ground-Truth Dataset Development and Refinement**.

## Purpose

During the development of the 100-question retrieval benchmark ground-truth dataset (`data/evaluation/retrieval_ground_truth_100q_refined.json`), extensive exploratory audits and candidate chunk searches were executed to:
1. Identify high-substance candidate chunks across all 71 unique NIST publications.
2. Resolve title-only and placeholder chunk references into substantive technical chunks.
3. Validate candidate mappings, verify chunk alignments, and audit candidate pools against active Qdrant vector collections.
4. Perform deep dives into specific document chunk sets (e.g., SP 800-201, SP 800-221, SP 800-38 series).

## Script Inventory

The archived scripts include:

- **Missing Chunk & Candidate Discovery**:
  - `analyze_missing_15.py`
  - `build_100q_candidates.py`
  - `build_candidate_definitions.py`
  - `check_candidate_status.py`
  - `evaluate_all_statuses.py`
  - `find_all_substantive.py`
  - `find_candidate_chunks.py`
  - `find_replacements.py`
  - `find_substantive_chunks.py`
  - `locate_64_chunks.py`
  - `search_lenient.py`
  - `search_substantive_remaining.py`

- **Document-Specific & Batch Inspection**:
  - `inspect_201_only.py`
  - `inspect_221.py`
  - `inspect_221_text.py`
  - `inspect_38_201.py`
  - `inspect_batch1.py`
  - `inspect_candidate_25.py`
  - `inspect_cross_doc.py`
  - `inspect_doc_chunks.py`
  - `inspect_exact_chunks.py`
  - `inspect_inventory.py`
  - `inspect_questions_chunks.py`

- **Validation & Refinement Testing**:
  - `audit_100q_benchmark.py`
  - `audit_all_100_questions.py`
  - `resolve_title_chunks.py`
  - `test_candidate_matches.py`
  - `test_refinements.py`
  - `validate_100q_candidates.py`
  - `verify_and_build_questions.py`

## Usage Notes

- These are standalone diagnostic utilities and are **not** part of the production retrieval pipeline or automated test suite.
- All scripts use project-relative paths (e.g., `data/...`) and should be executed from the repository root:
  ```bash
  python scripts/archive/<script_name>.py
  ```
- Pytest test discovery is explicitly configured in `pyproject.toml` to ignore `scripts/` (including this archive directory) to avoid import-time overhead during testing.

## Active Phase 1 Scripts

Official benchmark and evaluation scripts remain in `scripts/` and `evaluation/`:
- `scripts/run_100q_benchmark.py`: Production 100-question retrieval benchmark runner.
- `scripts/validate_100q_ground_truth.py`: Ground truth integrity validator (13 checks).
- `evaluation/run_full_evaluation.py`: Unified evaluation runner.
