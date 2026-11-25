import json
from pathlib import Path

all_chunks = {}
for p in Path('data').glob('chunks_*/**/*.jsonl'):
    with open(p, 'r', encoding='utf-8') as f:
        for line in f:
            c = json.loads(line)
            all_chunks[c['chunk_id']] = c

def check_chunks(doc_id, terms):
    print(f"=== Searching {doc_id} for {terms} ===")
    matches = []
    for cid, c in all_chunks.items():
        if c['document_id'] == doc_id and not cid.endswith('_txt_00001'):
            txt = c['text'].lower()
            if all(t.lower() in txt for t in terms):
                matches.append(c)
    print(f"Found {len(matches)} matches.")
    for m in matches[:5]:
        print(f"[{m['chunk_id']}] p.{m.get('page_start')} {m.get('section_heading')}")
        print(m['text'][:300].replace('\n', ' '))
        print('-'*30)

# Q47: NIST_SP_800-210 for PDP / PEP or cloud access control architecture
check_chunks('NIST_SP_800-210', ['access control', 'cloud', 'architecture'])
# Q48: NIST_SP_800-116 for PIV authentication factors, AAL3, physical access
check_chunks('NIST_SP_800-116', ['piv', 'authentication', 'facility'])
# Q49: NIST_SP_800-130 for CKMS components / lifecycle
check_chunks('NIST_SP_800-130', ['ckms', 'framework', 'components'])
# Q50: NIST_SP_800-216 for intake / triage of vulnerability reports
check_chunks('NIST_SP_800-216', ['intake', 'triage'])
if not all_chunks.get('matches'):
    check_chunks('NIST_SP_800-216', ['vulnerability', 'handling', 'procedures'])
# Q51: NIST_SP_800-101 for mobile device evidence collection / chain of custody
check_chunks('NIST_SP_800-101', ['evidence', 'chain of custody'])
