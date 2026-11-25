import json
from pathlib import Path

# Load all chunks
all_chunks = {}
for p in Path('data').glob('chunks_*/**/*.jsonl'):
    with open(p, 'r', encoding='utf-8') as f:
        for line in f:
            c = json.loads(line)
            all_chunks[c['chunk_id']] = c

with open('data/evaluation/retrieval_ground_truth_100q_refined.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

# Inspect the 25 questions
cand_qids = [
    'Q41', 'Q42', 'Q43', 'Q44', 'Q45',
    'Q52', 'Q53', 'Q54', 'Q60', 'Q61',
    'Q63', 'Q64', 'Q66', 'Q69', 'Q72',
    'Q75', 'Q79', 'Q81', 'Q83', 'Q90',
    'Q91', 'Q92', 'Q94', 'Q99', 'Q102'
]

print(f"Inspecting {len(cand_qids)} questions currently labeled 'candidate'...")
verified_count = 0
for qid in cand_qids:
    item = d[qid]
    q = item['question']
    chunks = item.get('relevant_chunks') or item.get('relevant_chunk_ids')
    print(f"\n[{qid}] ({item.get('category')}) {item.get('primary_document')}")
    print(f"  Q: {q}")
    for cid in chunks:
        c = all_chunks.get(cid)
        if c:
            p = c.get('page_start')
            h = c.get('section_heading', '').encode('ascii', 'ignore').decode('ascii')
            t = c['text'][:120].replace('\n', ' ').encode('ascii', 'ignore').decode('ascii')
            print(f"    [{cid}] p.{p} [{h}]: {t}")
        else:
            print(f"    [{cid}] NOT FOUND!")
