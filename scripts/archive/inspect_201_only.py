import json
from pathlib import Path

all_chunks = {}
for p in Path('data').glob('chunks_*/**/*.jsonl'):
    with open(p, 'r', encoding='utf-8') as f:
        for line in f:
            c = json.loads(line)
            if c['document_id'] == 'NIST_SP_800-201':
                all_chunks[c['chunk_id']] = c

print(f"Total SP 800-201 chunks: {len(all_chunks)}")

for cid, c in all_chunks.items():
    txt = c['text']
    h = c.get('section_heading', '')
    p = c.get('page_start')
    if 'tier' in txt.lower() or 'architecture' in txt.lower():
        clean_h = h.encode('ascii', 'ignore').decode('ascii')
        clean_txt = txt[:200].replace('\n', ' ').encode('ascii', 'ignore').decode('ascii')
        print(f"[{cid}] p.{p} {clean_h}")
        print(f"   {clean_txt}")
        print('-'*30)
