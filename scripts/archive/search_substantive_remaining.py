import json
from pathlib import Path

all_chunks = {}
chunks_by_doc = {}
for p in Path('data').glob('chunks_*/**/*.jsonl'):
    with open(p, 'r', encoding='utf-8') as f:
        for line in f:
            c = json.loads(line)
            all_chunks[c['chunk_id']] = c
            chunks_by_doc.setdefault(c['document_id'], []).append(c)

def find_chunks(doc_id, terms, exclude_terms=['table of contents', 'contents']):
    matches = []
    for c in chunks_by_doc.get(doc_id, []):
        h = c.get('section_heading', '').lower()
        if any(ex in h for ex in exclude_terms) or c['chunk_id'].endswith('_txt_00001'):
            continue
        txt = c['text'].lower()
        if all(t.lower() in txt for t in terms):
            matches.append(c)
    matches.sort(key=lambda x: len(x['text']), reverse=True)
    return matches

searches = {
    'Q52': ('NIST_SP_800-53', ['ca-7', 'continuous monitoring']),
    'Q53': ('NIST_SP_800-161', ['contractual', 'supplier', 'clause']),
    'Q60': ('NIST_SP_800-73', ['chuid', 'cardholder unique identifier']),
    'Q63': ('NIST_SP_800-79', ['issuer controls', 'assessment', 'pci']),
    'Q64': ('NIST_SP_800-157', ['derived', 'credential', 'piv', 'mobile']),
    'Q66': ('NIST_SP_800-50', ['learning program', 'awareness', 'training']),
    'Q69': ('NIST_SP_800-228', ['api', 'cloud-native', 'protection']),
    'Q72': ('NIST_SP_800-178', ['xacml', 'ngac', 'expressiveness']),
    'Q75': ('NIST_SP_800-183', ['five primitive', 'building blocks', 'sensor', 'aggregator']),
    'Q79': ('NIST_SP_800-238', ['emerging', 'priorities', 'standards']),
    'Q81': ('NIST_SP_800-51', ['cve', 'naming scheme', 'vulnerability']),
    'Q83': ('NIST_SP_800-223', ['hpc', 'cluster', 'threat']),
    'Q90': ('NIST_SP_800-224', ['hmac', 'ipad', 'opad', 'hash']),
    'Q92': ('NIST_SP_800-72', ['pda', 'forensic', 'preservation', 'battery']),
    'Q94': ('NIST_SP_800-234', ['hpc', 'overlay', 'parallel', 'supercomputing']),
    'Q99': ('NIST_SP_800-228', ['api gateway', 'exposure', 'caller']),
    'Q102': ('NIST_SP_800-204', ['release', 'gate', 'pipeline', 'production'])
}

for qid, (doc_id, terms) in searches.items():
    res = find_chunks(doc_id, terms)
    print(f"\n==================== {qid} ({doc_id}) terms={terms} ====================")
    print(f"Found {len(res)} matches.")
    for m in res[:2]:
        p = m.get('page_start')
        h = m.get('section_heading', '').replace('\n', ' ')
        clean_h = h.encode('ascii', 'ignore').decode('ascii')
        clean_txt = m['text'][:200].replace('\n', ' ').encode('ascii', 'ignore').decode('ascii')
        print(f"  [{m['chunk_id']}] (p.{p}) {clean_h}")
        print(f"     {clean_txt}")
