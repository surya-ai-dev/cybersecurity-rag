import json
import sys
from pathlib import Path
sys.path.append('.')

# Load all chunks
all_chunks = {}
for p in Path('data').glob('chunks_*/**/*.jsonl'):
    with open(p, 'r', encoding='utf-8') as f:
        for line in f:
            c = json.loads(line)
            all_chunks[c['chunk_id']] = c

with open('data/evaluation/retrieval_ground_truth_100q_candidates.json', 'r', encoding='utf-8') as f:
    candidates = json.load(f)

# Load test refinements
from scripts.test_refinements import refinements

# Build refined dictionary
refined = {}

for qid, item in candidates.items():
    # Make a deep copy of item
    q_data = dict(item)
    
    if qid in refinements:
        q_data.update(refinements[qid])
        
    refined[qid] = q_data

print(f"Total refined questions: {len(refined)}")

# Revalidate all 100 questions
status_counts = {}
title_chunks_remaining = []
chunk_sets = {}
duplicate_chunk_sets = []
missing_chunk_ids = []

for qid, item in refined.items():
    st = item.get('verification_status', 'unspecified')
    status_counts[st] = status_counts.get(st, 0) + 1
    
    chunks = item.get('relevant_chunks') or item.get('relevant_chunk_ids') or []
    
    # Check physical existence
    for c in chunks:
        if c not in all_chunks:
            missing_chunk_ids.append((qid, c))
        if c.endswith('_txt_00001'):
            title_chunks_remaining.append((qid, c))
            
    # Check duplicate ground truth sets
    ch_tuple = tuple(sorted(chunks))
    if ch_tuple in chunk_sets:
        duplicate_chunk_sets.append((qid, chunk_sets[ch_tuple], ch_tuple))
    else:
        chunk_sets[ch_tuple] = qid

print("\n=== Validation Results ===")
print("Status counts:", status_counts)
print("Missing chunk IDs:", missing_chunk_ids)
print("Title chunks remaining:", title_chunks_remaining)
print("Duplicate chunk sets:", duplicate_chunk_sets)

# Save to data/evaluation/retrieval_ground_truth_100q_refined.json
out_path = Path('data/evaluation/retrieval_ground_truth_100q_refined.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(refined, f, indent=2, ensure_ascii=False)

print(f"\nSaved refined ground truth to {out_path} ({out_path.stat().st_size} bytes).")
