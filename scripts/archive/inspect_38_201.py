import json
from pathlib import Path

all_chunks = {}
for p in Path('data').glob('chunks_*/**/*.jsonl'):
    with open(p, 'r', encoding='utf-8') as f:
        for line in f:
            c = json.loads(line)
            all_chunks[c['chunk_id']] = c

print("=== SP 800-38 Chunks on FF1 / FF3 ===")
for cid, c in all_chunks.items():
    if c['document_id'] == 'NIST_SP_800-38':
        txt = c['text']
        if 'FF1' in txt or 'FF3' in txt or 'format-preserving' in txt.lower():
            print(f"[{cid}] p.{c.get('page_start')} {c.get('section_heading')}")
            print(txt[:250].replace('\n', ' '))
            print('-'*30)

print("\n=== SP 800-201 Chunks on Architecture Tiers / Layers ===")
for cid, c in all_chunks.items():
    if c['document_id'] == 'NIST_SP_800-201':
        txt = c['text']
        if 'tier' in txt.lower() or 'architecture' in txt.lower() or 'layer' in txt.lower():
            if len(txt) > 300:
                print(f"[{cid}] p.{c.get('page_start')} {c.get('section_heading')}")
                print(txt[:250].replace('\n', ' '))
                print('-'*30)
