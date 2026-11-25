import json
from pathlib import Path

for p in Path('data').glob('chunks_*/**/NIST_SP_800-221_chunks.jsonl'):
    with open(p, 'r', encoding='utf-8') as f:
        for line in f:
            c = json.loads(line)
            if c['chunk_id'] in ['NIST_SP_800-221_txt_00024', 'NIST_SP_800-221_txt_00025', 'NIST_SP_800-221_txt_00026', 'NIST_SP_800-221_txt_00027']:
                print(f"=== {c['chunk_id']} (p.{c.get('page_start')}) ===")
                print(c['text'].encode('ascii', 'ignore').decode('ascii'))
