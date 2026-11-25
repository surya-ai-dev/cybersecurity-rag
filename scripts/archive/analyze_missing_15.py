import json
from pathlib import Path

with open('data/document_inventory/document_inventory.json', 'r', encoding='utf-8') as f:
    inv = json.load(f)
all_docs = {d['file_name'].replace('.pdf', ''): d for d in inv['documents']}

with open('data/evaluation/retrieval_ground_truth_100q_candidates.json', 'r', encoding='utf-8') as f:
    data_100 = json.load(f)

import sys
sys.path.append('.')
from scripts.build_candidate_definitions import chunk_by_id

cand_docs = set()
for qid in range(41, 105):
    q = data_100["Q%d" % qid]
    for cid in q['relevant_chunk_ids']:
        cand_docs.add(chunk_by_id[cid]['document_id'])
    cand_docs.add(q['primary_document'])
    for sd in q['supporting_documents']:
        cand_docs.add(sd)

print("Docs in 64 candidates: %d" % len(cand_docs))
missing_from_candidates = sorted(set(all_docs.keys()) - cand_docs)
print("Missing from 64 candidates (%d):" % len(missing_from_candidates))

# Also check which of these were in the original 36 questions
v2_docs = set()
with open('data/evaluation/retrieval_ground_truth_v2.json', 'r', encoding='utf-8') as f:
    v2_data = json.load(f)
for q in v2_data.values():
    for cid in q['relevant_chunks']:
        v2_docs.add(chunk_by_id[cid]['document_id'])
    for d in q['document_ids']:
        v2_docs.add(d)

for m in missing_from_candidates:
    d = all_docs[m]
    in_v2 = m in v2_docs
    print("  %-25s | %3dp | %-26s | In original 36: %s" % (m, d['page_count'], d['category'], in_v2))
