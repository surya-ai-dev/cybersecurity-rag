import json
from pathlib import Path
from collections import Counter, defaultdict

# Load doc inventory
with open('data/document_inventory/document_inventory.json', 'r', encoding='utf-8') as f:
    inv = json.load(f)

all_docs = {d['file_name'].replace('.pdf', ''): d for d in inv['documents']}
print("Total inventory documents: %d" % len(all_docs))

# Load candidate 100 questions
with open('data/evaluation/retrieval_ground_truth_100q_candidates.json', 'r', encoding='utf-8') as f:
    data_100 = json.load(f)

# Load chunk index
import sys
sys.path.append('.')
from scripts.build_candidate_definitions import chunk_by_id

referenced_docs = set()
for qid, q in data_100.items():
    cids = q.get('relevant_chunks') or q.get('relevant_chunk_ids') or []
    for cid in cids:
        if cid in chunk_by_id:
            referenced_docs.add(chunk_by_id[cid]['document_id'])
    if 'document_ids' in q:
        for d in q['document_ids']:
            referenced_docs.add(d)
    if 'primary_document' in q:
        referenced_docs.add(q['primary_document'])
    if 'supporting_documents' in q:
        for d in q['supporting_documents']:
            referenced_docs.add(d)

print("Total referenced documents: %d" % len(referenced_docs))
missing_docs = sorted(set(all_docs.keys()) - referenced_docs)
print("Missing documents count: %d" % len(missing_docs))
for m in missing_docs:
    d = all_docs[m]
    title = (d.get('title') or '').encode('ascii', 'ignore').decode('ascii')[:60]
    print("  %-25s | %3dp | %-25s | %s" % (m, d.get('page_count', 0), d.get('category', ''), title))

# Duplicate group check
for g in inv.get('duplicate_groups', []):
    print("Duplicate group hash:", g)
