import json
from pathlib import Path
from collections import Counter

# Load combined candidates dataset
json_path = Path("data/evaluation/retrieval_ground_truth_100q_candidates.json")
with open(json_path, "r", encoding="utf-8") as f:
    data = json.load(f)

print(f"Total entries in {json_path.name}: {len(data)}")
assert len(data) == 100, f"Expected 100, got {len(data)}"

# Check original 36
with open("data/evaluation/retrieval_ground_truth_v2.json", "r", encoding="utf-8") as f:
    v2_data = json.load(f)

for qid, qobj in v2_data.items():
    assert qid in data, f"Original question {qid} missing from candidates!"
    assert data[qid] == qobj, f"Original question {qid} was modified!"

print("Verified: All 36 original questions are 100% identical and preserved.")

# Check 64 new candidates
required_fields = [
    "question_id", "question", "category", "primary_document",
    "supporting_documents", "relevant_chunk_ids", "expected_answer_summary",
    "source_section", "source_page", "verification_status", "verification_notes"
]

all_cids = []
all_qtexts = []
cand_categories = Counter()
cand_docs = Counter()

for i in range(41, 105):
    qid = f"Q{i}"
    assert qid in data, f"Candidate {qid} missing!"
    item = data[qid]
    for rf in required_fields:
        assert rf in item, f"Missing required field {rf} in {qid}!"
        assert item[rf] is not None, f"Field {rf} is None in {qid}!"
    assert item["verification_status"] == "candidate", f"Invalid status {item['verification_status']} in {qid}!"
    assert len(item["relevant_chunk_ids"]) >= 1, f"No relevant chunks in {qid}!"
    all_cids.extend(item["relevant_chunk_ids"])
    all_qtexts.append(item["question"].strip().lower())
    cand_categories[item["category"]] += 1
    cand_docs[item["primary_document"]] += 1
    for sd in item["supporting_documents"]:
        cand_docs[sd] += 1

# Check duplicate question texts
dup_qtexts = [q for q, count in Counter(all_qtexts).items() if count > 1]
assert len(dup_qtexts) == 0, f"Duplicate questions found: {dup_qtexts}"
print("Verified: Zero duplicate questions among new candidates.")

# Check chunk existence in active corpus
import sys
sys.path.append('.')
from scripts.build_candidate_definitions import chunk_by_id
missing_cids = [cid for cid in all_cids if cid not in chunk_by_id]
assert len(missing_cids) == 0, f"Missing chunks in corpus: {missing_cids}"
print(f"Verified: All {len(all_cids)} assigned chunk references physically exist in active corpus.")

print("\nCandidate Categories:")
for cat, cnt in cand_categories.items():
    print(f"  {cat}: {cnt}")

print("\nDocuments referenced across 64 candidates:")
for doc, cnt in sorted(cand_docs.items()):
    print(f"  {doc:25s}: {cnt:2d} references")

print(f"\nTotal unique documents referenced across candidates: {len(cand_docs)}")

print("\nALL 100-QUESTION VALIDATION CHECKS PASSED PERFECTLY!")
