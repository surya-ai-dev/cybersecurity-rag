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

def search_doc_lenient(doc_id, terms, max_r=2):
    results = []
    for c in chunks_by_doc.get(doc_id, []):
        if c['chunk_id'].endswith('_txt_00001'):
            continue
        h = c.get('section_heading', '').lower()
        if 'table of contents' in h or 'contents' in h:
            continue
        txt = c['text'].lower()
        score = sum(1 for t in terms if t.lower() in txt)
        if score >= 1:
            results.append((score, c))
    results.sort(key=lambda x: (x[0], len(x[1]['text'])), reverse=True)
    print(f"\n=== {doc_id} search {terms} (Top {max_r}) ===")
    for s, c in results[:max_r]:
        p = c.get('page_start')
        h = c.get('section_heading', '').replace('\n', ' ').encode('ascii', 'ignore').decode('ascii')
        txt = c['text'][:200].replace('\n', ' ').encode('ascii', 'ignore').decode('ascii')
        print(f"[{c['chunk_id']}] p.{p} [sc:{s}] {h}")
        print(f"   {txt}")

search_doc_lenient('NIST_SP_800-161', ['contract', 'supplier', 'clause'])
search_doc_lenient('NIST_SP_800-73', ['chuid', 'cardholder'])
search_doc_lenient('NIST_SP_800-157', ['derived', 'credential', 'mobile'])
search_doc_lenient('NIST_SP_800-238', ['emerging', 'cybersecurity', 'priority'])
search_doc_lenient('NIST_SP_800-72', ['pda', 'preservation', 'seizure'])
search_doc_lenient('NIST_SP_800-234', ['overlay', 'parallel', 'baseline'])
search_doc_lenient('NIST_SP_800-228', ['gateway', 'exposure', 'proxy'])
search_doc_lenient('NIST_SP_800-204', ['gate', 'production', 'pipeline', 'deployment'])
