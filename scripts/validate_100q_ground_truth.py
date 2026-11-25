"""
Structural and Integrity Validation Script for 100-Question Retrieval Benchmark.

Validates `data/evaluation/retrieval_ground_truth_100q_refined.json` against the active corpus
and checks all structural, schema, provenance, and verification constraints.

Returns exit code 0 if all 13 checks pass, or non-zero (sys.exit(1)) if any check fails.
"""

import sys
import json
from pathlib import Path
from collections import Counter


def run_validation():
    print("=" * 80)
    print("CYBERSECURITY RAG: 100-QUESTION BENCHMARK FINAL VALIDATION")
    print("=" * 80)

    dataset_path = Path("data/evaluation/retrieval_ground_truth_100q_refined.json")
    v2_path = Path("data/evaluation/retrieval_ground_truth_v2.json")

    if not dataset_path.exists():
        print(f"[FAIL] Dataset file not found: {dataset_path}")
        sys.exit(1)

    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Load corpus chunks
    corpus_chunks = {}
    corpus_docs = set()
    for p in Path("data").glob("chunks_*/**/*.jsonl"):
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                c = json.loads(line)
                corpus_chunks[c["chunk_id"]] = c
                corpus_docs.add(c["document_id"])

    print(f"Loaded {len(corpus_chunks)} active corpus chunks across {len(corpus_docs)} documents.")

    passed_checks = 0
    total_checks = 13
    errors = []

    # ---------------------------------------------------------
    # CHECK 1: Confirm exactly 100 unique question IDs
    # ---------------------------------------------------------
    print("\n[Check 1/13] Confirming exactly 100 entries in dataset...")
    if len(data) == 100 and len(set(data.keys())) == 100:
        print(f"  [PASS] Exactly 100 unique question IDs in dataset (count={len(data)}).")
        passed_checks += 1
    else:
        err = f"Expected 100 unique entries, found {len(data)} (unique={len(set(data.keys()))})"
        print(f"  [FAIL] {err}")
        errors.append(err)

    # ---------------------------------------------------------
    # CHECK 2: Confirm all question IDs are present and unique
    # ---------------------------------------------------------
    print("\n[Check 2/13] Confirming presence and format of all 100 question IDs...")
    expected_baseline_ids = [
        "Q1", "Q3", "Q4", "Q5", "Q7", "Q8", "Q9", "Q10", "Q11", "Q12",
        "Q13", "Q14", "Q16", "Q17", "Q19", "Q20", "Q21", "Q22", "Q23", "Q24",
        "Q25", "Q26", "Q27", "Q28", "Q29", "Q30", "Q31", "Q32", "Q33", "Q34",
        "Q35", "Q36", "Q37", "Q38", "Q39", "Q40"
    ]
    expected_candidate_ids = [f"Q{i}" for i in range(41, 105)]
    all_expected_ids = set(expected_baseline_ids + expected_candidate_ids)

    actual_ids = set(data.keys())
    missing_ids = all_expected_ids - actual_ids
    unexpected_ids = actual_ids - all_expected_ids
    id_mismatches = [qid for qid, item in data.items() if item.get("question_id") != qid]

    if not missing_ids and not unexpected_ids and not id_mismatches:
        print(f"  [PASS] All 36 baseline IDs and all 64 candidate IDs (Q41-Q104) are present and match internal question_id.")
        passed_checks += 1
    else:
        err = f"ID discrepancy: missing={missing_ids}, unexpected={unexpected_ids}, mismatched_field={id_mismatches}"
        print(f"  [FAIL] {err}")
        errors.append(err)

    # ---------------------------------------------------------
    # CHECK 3: Confirm all 100 questions have verification_status = "verified"
    # ---------------------------------------------------------
    print("\n[Check 3/13] Confirming verification_status = 'verified' across all 100 entries...")
    status_counts = Counter(item.get("verification_status") for item in data.values())
    print(f"  Status distribution: {dict(status_counts)}")
    if status_counts.get("verified") == 100 and len(status_counts) == 1:
        print("  [PASS] All 100 questions have verification_status = 'verified'.")
        passed_checks += 1
    else:
        err = f"Non-verified statuses present: {dict(status_counts)}"
        print(f"  [FAIL] {err}")
        errors.append(err)

    # ---------------------------------------------------------
    # CHECK 4: Confirm all assigned chunk IDs exist in active corpus
    # ---------------------------------------------------------
    print("\n[Check 4/13] Confirming physical chunk existence in active corpus...")
    all_assigned_chunks = []
    missing_chunks = []
    for qid, item in data.items():
        chunks = item.get("relevant_chunk_ids") or item.get("relevant_chunks") or []
        all_assigned_chunks.extend(chunks)
        for c in chunks:
            if c not in corpus_chunks:
                missing_chunks.append((qid, c))

    unique_chunks = set(all_assigned_chunks)
    if not missing_chunks:
        print(f"  [PASS] All {len(all_assigned_chunks)} chunk assignments ({len(unique_chunks)} unique) physically exist in active corpus.")
        passed_checks += 1
    else:
        err = f"{len(missing_chunks)} assigned chunks missing from corpus: {missing_chunks[:5]}"
        print(f"  [FAIL] {err}")
        errors.append(err)

    # ---------------------------------------------------------
    # CHECK 5: Confirm every referenced document ID is valid
    # ---------------------------------------------------------
    print("\n[Check 5/13] Confirming referenced document IDs exist in corpus...")
    invalid_docs = []
    for qid, item in data.items():
        doc_refs = []
        if "document_ids" in item:
            doc_refs.extend(item["document_ids"])
        if "primary_document" in item:
            doc_refs.append(item["primary_document"])
        if "supporting_documents" in item:
            doc_refs.extend(item["supporting_documents"])

        for d in doc_refs:
            if d not in corpus_docs:
                invalid_docs.append((qid, d))

    if not invalid_docs:
        print("  [PASS] All referenced document IDs match valid corpus documents.")
        passed_checks += 1
    else:
        err = f"Invalid document IDs referenced: {invalid_docs}"
        print(f"  [FAIL] {err}")
        errors.append(err)

    # ---------------------------------------------------------
    # CHECK 6: Check that there are no duplicate ground-truth chunk sets
    # ---------------------------------------------------------
    print("\n[Check 6/13] Checking for duplicate ground-truth chunk sets...")
    seen_chunk_sets = {}
    duplicate_sets = []
    for qid, item in data.items():
        chunks = tuple(sorted(item.get("relevant_chunk_ids") or item.get("relevant_chunks") or []))
        if chunks in seen_chunk_sets:
            duplicate_sets.append((qid, seen_chunk_sets[chunks], chunks))
        else:
            seen_chunk_sets[chunks] = qid

    if not duplicate_sets:
        print("  [PASS] Zero duplicate ground-truth chunk sets across all 100 questions.")
        passed_checks += 1
    else:
        err = f"Duplicate ground truth chunk sets detected: {duplicate_sets}"
        print(f"  [FAIL] {err}")
        errors.append(err)

    # ---------------------------------------------------------
    # CHECK 7: Check that Q4 and Q17 have distinct ground truth
    # ---------------------------------------------------------
    print("\n[Check 7/13] Verifying de-coupled ground truth for Q4 and Q17...")
    q4_chunks = data.get("Q4", {}).get("relevant_chunks", [])
    q17_chunks = data.get("Q17", {}).get("relevant_chunks", [])
    print(f"  Q4 chunks: {q4_chunks}")
    print(f"  Q17 chunks: {q17_chunks}")

    if (q4_chunks == ["NIST_SP_800-144_txt_00055"] and 
        q17_chunks == ["NIST_SP_800-144_txt_00056"] and 
        set(q4_chunks).isdisjoint(set(q17_chunks))):
        print("  [PASS] Q4 and Q17 have distinct, de-coupled ground truth in Section 4.1.")
        passed_checks += 1
    else:
        err = f"Q4 and Q17 ground truth not properly separated: Q4={q4_chunks}, Q17={q17_chunks}"
        print(f"  [FAIL] {err}")
        errors.append(err)

    # ---------------------------------------------------------
    # CHECK 8: Check that no technical question uses title-only placeholder chunks
    # ---------------------------------------------------------
    print("\n[Check 8/13] Checking for title-only placeholder chunks (_txt_00001)...")
    title_chunk_usage = []
    for qid, item in data.items():
        chunks = item.get("relevant_chunk_ids") or item.get("relevant_chunks") or []
        for c in chunks:
            if c.endswith("_txt_00001"):
                title_chunk_usage.append((qid, c))

    if not title_chunk_usage:
        print("  [PASS] Zero title-only placeholder chunks (_txt_00001) remain.")
        passed_checks += 1
    else:
        err = f"Title chunks remaining in dataset: {title_chunk_usage}"
        print(f"  [FAIL] {err}")
        errors.append(err)

    # ---------------------------------------------------------
    # CHECK 9: Verify category counts against refinement report
    # ---------------------------------------------------------
    print("\n[Check 9/13] Verifying category archetype counts...")
    expected_categories = {
        "unspecified": 36,
        "direct_factual": 16,
        "conceptual": 14,
        "technical_control": 11,
        "scenario_based": 10,
        "cross_document": 6,
        "table_structured": 5,
        "multi_chunk_reasoning": 2
    }
    actual_categories = Counter(item.get("category", "unspecified") for item in data.values())

    cat_mismatches = []
    for cat, exp_count in expected_categories.items():
        act_count = actual_categories.get(cat, 0)
        if act_count != exp_count:
            cat_mismatches.append(f"{cat}: expected {exp_count}, got {act_count}")

    if not cat_mismatches and sum(actual_categories.values()) == 100:
        print(f"  [PASS] All 8 category counts match the refinement report exactly: {dict(actual_categories)}.")
        passed_checks += 1
    else:
        err = f"Category count mismatches: {cat_mismatches}"
        print(f"  [FAIL] {err}")
        errors.append(err)

    # ---------------------------------------------------------
    # CHECK 10: Confirm publication representation
    # ---------------------------------------------------------
    print("\n[Check 10/13] Confirming publication representation...")
    referenced_docs = set()
    for item in data.values():
        if "document_ids" in item:
            referenced_docs.update(item["document_ids"])
        if "primary_document" in item:
            referenced_docs.add(item["primary_document"])
        if "supporting_documents" in item:
            referenced_docs.update(item["supporting_documents"])

    # Active corpus has 73 files:
    # - 1 duplicate file: NIST.SP.800-61r3 (identical to NIST_SP_800-61)
    # - 1 non-English IPA Japanese translation: NIST_SP_800-190 (intentionally excluded per Task 3)
    # Total valid English NIST evaluation publications: exactly 71
    unrepresented_valid = (corpus_docs - {"NIST.SP.800-61r3", "NIST_SP_800-190"}) - referenced_docs

    if len(referenced_docs) == 71 and not unrepresented_valid:
        print(f"  [PASS] All 71 valid English publications in corpus are represented (100.0% coverage).")
        print(f"         Excluded non-English publication NIST_SP_800-190 per Task 3 rules.")
        print(f"         Represented unique NIST publications: {len(referenced_docs)}/71.")
        passed_checks += 1
    else:
        err = f"Publication representation issue: referenced={len(referenced_docs)}, unrepresented_valid={unrepresented_valid}"
        print(f"  [FAIL] {err}")
        errors.append(err)

    # ---------------------------------------------------------
    # CHECK 11: Check JSON schema consistency across all 100 entries
    # ---------------------------------------------------------
    print("\n[Check 11/13] Checking JSON schema consistency...")
    baseline_schema = {
        "question_id": str, "question": str, "document_ids": list,
        "relevant_chunks": list, "verification_status": str,
        "evaluation_eligible": bool, "rationale": str
    }
    candidate_schema = {
        "question_id": str, "question": str, "category": str,
        "primary_document": str, "supporting_documents": list,
        "relevant_chunk_ids": list, "expected_answer_summary": str,
        "source_section": str, "source_page": str,
        "verification_status": str, "verification_notes": str
    }

    schema_errors = []
    for qid, item in data.items():
        if qid in expected_baseline_ids:
            # Baseline Profile
            for field, f_type in baseline_schema.items():
                if field not in item:
                    schema_errors.append(f"{qid} missing baseline field {field}")
                elif not isinstance(item[field], f_type):
                    schema_errors.append(f"{qid} field {field} invalid type {type(item[field])}")
        else:
            # Candidate Profile
            for field, f_type in candidate_schema.items():
                if field not in item:
                    schema_errors.append(f"{qid} missing candidate field {field}")
                elif not isinstance(item[field], f_type):
                    schema_errors.append(f"{qid} field {field} invalid type {type(item[field])}")

    if not schema_errors:
        print("  [PASS] 100% schema consistency: 36 entries match Baseline Profile, 64 match Candidate Profile.")
        passed_checks += 1
    else:
        err = f"{len(schema_errors)} schema errors detected: {schema_errors[:5]}"
        print(f"  [FAIL] {err}")
        errors.append(err)

    # ---------------------------------------------------------
    # CHECK 12: Check that no question has an empty relevant chunks array
    # ---------------------------------------------------------
    print("\n[Check 12/13] Checking for non-empty relevant chunks...")
    empty_chunk_entries = []
    for qid, item in data.items():
        chunks = item.get("relevant_chunk_ids") or item.get("relevant_chunks") or []
        if len(chunks) == 0:
            empty_chunk_entries.append(qid)

    if not empty_chunk_entries:
        print(f"  [PASS] Every question has >= 1 relevant chunk (total assigned chunks: {len(all_assigned_chunks)}).")
        passed_checks += 1
    else:
        err = f"Questions with empty relevant chunks: {empty_chunk_entries}"
        print(f"  [FAIL] {err}")
        errors.append(err)

    # ---------------------------------------------------------
    # CHECK 13: Confirm expected_answer_summary and provenance fields populated
    # ---------------------------------------------------------
    print("\n[Check 13/13] Confirming expected_answer_summary and provenance fields are populated...")
    provenance_errors = []
    for qid, item in data.items():
        if qid in expected_candidate_ids:
            summary = item.get("expected_answer_summary", "").strip()
            section = item.get("source_section", "").strip()
            page = item.get("source_page", "").strip()
            pdoc = item.get("primary_document", "").strip()
            if not summary:
                provenance_errors.append(f"{qid} empty expected_answer_summary")
            if not section:
                provenance_errors.append(f"{qid} empty source_section")
            if not page:
                provenance_errors.append(f"{qid} empty source_page")
            if not pdoc:
                provenance_errors.append(f"{qid} empty primary_document")
        else:
            rationale = item.get("rationale", "").strip()
            doc_ids = item.get("document_ids", [])
            if not rationale:
                provenance_errors.append(f"{qid} empty rationale")
            if not doc_ids:
                provenance_errors.append(f"{qid} empty document_ids")

    if not provenance_errors:
        print("  [PASS] All candidate questions have populated expected_answer_summary, section, page, and document provenance.")
        print("         All baseline questions have populated rationale and document_ids.")
        passed_checks += 1
    else:
        err = f"Provenance errors: {provenance_errors}"
        print(f"  [FAIL] {err}")
        errors.append(err)

    # ---------------------------------------------------------
    # FINAL SUMMARY
    # ---------------------------------------------------------
    print("\n" + "=" * 80)
    print(f"VALIDATION SUMMARY: {passed_checks}/{total_checks} CHECKS PASSED")
    print("=" * 80)

    if passed_checks == total_checks:
        print("[SUCCESS] All 13 validation checks PASSED perfectly.")
        print("Dataset is 100% structurally valid and ready for formal retrieval evaluation.")
        return 0
    else:
        print(f"[FAILURE] {len(errors)} validation checks failed!")
        for e in errors:
            print(f"  - {e}")
        return 1


if __name__ == "__main__":
    exit_code = run_validation()
    sys.exit(exit_code)
