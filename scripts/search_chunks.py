import json
from pathlib import Path

for p in Path('data').glob('chunks_*/**/NIST_SP_800-161_chunks.jsonl'):
    with open(p, 'r', encoding='utf-8') as f:
        for line in f:
            c = json.loads(line)
            txt = c['text'].lower()
            if 'devsecops' in txt or ('ci/cd' in txt) or ('software bill of materials' in txt) or ('sbom' in txt and 'build' in txt):
                print(f"ID: {c['chunk_id']} | Page: {c.get('page_start')}")
                print(c['text'][:300].replace('\n', ' '))
                print('-'*40)
