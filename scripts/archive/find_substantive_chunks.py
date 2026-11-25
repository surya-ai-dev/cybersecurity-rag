import json
from pathlib import Path

# Load all chunks into memory
chunks_by_doc = {}
all_chunks = {}
for p in Path('data').glob('chunks_*/**/*.jsonl'):
    with open(p, 'r', encoding='utf-8') as f:
        for line in f:
            c = json.loads(line)
            cid = c['chunk_id']
            all_chunks[cid] = c
            doc_id = c['document_id']
            chunks_by_doc.setdefault(doc_id, []).append(c)

print(f"Loaded {len(all_chunks)} chunks across {len(chunks_by_doc)} docs.")

# Load candidates json
with open('data/evaluation/retrieval_ground_truth_100q_candidates.json', 'r', encoding='utf-8') as f:
    cand = json.load(f)

# Find all questions with _txt_00001
target_qids = []
for qid, item in cand.items():
    ch_list = item.get('relevant_chunks') or item.get('relevant_chunk_ids') or []
    if any(c.endswith('_txt_00001') for c in ch_list):
        target_qids.append((qid, item))

print(f"Found {len(target_qids)} questions referencing _txt_00001.")

for qid, item in target_qids:
    cat = item.get('category')
    doc = item.get('primary_document')
    q = item.get('question')
    ch_list = item.get('relevant_chunks') or item.get('relevant_chunk_ids')
    print(f"\n[{qid}] ({cat}) Doc: {doc} | Current: {ch_list}")
    print(f"Question: {q}")
