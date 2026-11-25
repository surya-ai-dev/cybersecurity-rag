import json
from pathlib import Path

for p in Path('data').glob('chunks_*/**/NIST_SP_800-233_chunks.jsonl'):
    with open(p, 'r', encoding='utf-8') as f:
        for line in f:
            c = json.loads(line)
            heading = c.get('section_heading', '')
            txt = c['text']
            if 'model' in txt.lower() and ('sidecar' in txt.lower() or 'ambient' in txt.lower() or 'node' in txt.lower()):
                print(f"ID: {c['chunk_id']} | p.{c.get('page_start')} | Heading: {heading}")
                print(txt[:250].replace('\n', ' '))
                print('-'*40)
