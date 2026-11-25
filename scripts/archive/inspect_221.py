import json
from pathlib import Path

for p in Path('data').glob('chunks_*/**/NIST_SP_800-221_chunks.jsonl'):
    with open(p, 'r', encoding='utf-8') as f:
        for line in f:
            c = json.loads(line)
            h = c.get('section_heading', '').encode('ascii', 'ignore').decode('ascii')
            print(f"{c['chunk_id']} p.{c.get('page_start')} {h}")
