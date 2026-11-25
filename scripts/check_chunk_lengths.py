import re
import sys
sys.path.append('.')
from scripts.build_candidate_definitions import chunk_by_id

with open('scripts/generate_full_100q_dataset.py', 'r', encoding='utf-8') as f:
    code = f.read()

cids = re.findall(r'\[\s*\"(NIST_[^\"]+)\"\s*(?:,\s*\"(NIST_[^\"]+)\"\s*)?\]', code)
flat_cids = []
for group in cids:
    for cid in group:
        if cid:
            flat_cids.append(cid)

print(f"Total chunk IDs found: {len(flat_cids)}")

short_chunks = []
missing_chunks = []

for cid in flat_cids:
    if cid not in chunk_by_id:
        missing_chunks.append(cid)
    else:
        text = chunk_by_id[cid].get("text", "")
        if len(text) < 120:
            short_chunks.append((cid, len(text), text[:60].replace("\n", " ")))

print(f"Missing chunks ({len(missing_chunks)}): {missing_chunks}")
print(f"Short chunks (< 120 chars): {len(short_chunks)}")
for sc in short_chunks:
    print(" ", sc[0], f"({sc[1]} chars):", sc[2].encode('ascii', 'ignore').decode('ascii'))
