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

def find_best(doc_id, kws, skip_00001=True):
    doc_chunks = chunks_by_doc.get(doc_id, [])
    scored = []
    for c in doc_chunks:
        if skip_00001 and c['chunk_id'].endswith('_txt_00001'):
            continue
        txt = c['text'].lower()
        score = sum(1 for kw in kws if kw.lower() in txt)
        if score > 0:
            scored.append((score, c))
    scored.sort(key=lambda x: (x[0], len(x[1]['text'])), reverse=True)
    return scored[:4]

queries = {
    'Q74': ('NIST_SP_800-226', ['epsilon', 'privacy budget', 'trade-off', 'differential privacy', 'guarantees']),
    'Q76': ('NIST_SP_800-215', ['perimeter', 'software-defined', 'landscape', 'transition', 'sdn']),
    'Q77': ('NIST_SP_800-231', ['bugs framework', 'bf', 'formalizing', 'weaknesses', 'vulnerability model']),
    'Q78': ('NIST_SP_800-236', ['annual report', 'research priorities', 'strategic', 'milestones']),
    'Q80': ('NIST_SP_800-197', ['lightweight block cipher', 'ascon', 'public comments', 'stakeholders']),
    'Q82': ('NIST_SP_800-140', ['non-invasive attack', 'physical attack', 'cmvp', 'mitigation', 'side channel']),
    'Q84': ('NIST_SP_800-89', ['validation', 'assurances', 'digital signature', 'generation', 'keys']),
    'Q85': ('NIST_SP_800-38', ['ff1', 'ff3', 'format-preserving', 'fpe', 'mode']),
    'Q86': ('NIST_SP_800-56', ['pair-wise', 'key establishment', 'integer factorization', 'rsa']),
    'Q87': ('NIST_SP_800-186', ['curve', 'weierstrass', 'edwards', 'recommended elliptic curve', 'domain parameter']),
    'Q88': ('NIST_SP_800-132', ['pbkdf', 'password-based', 'iteration count', 'salt', 'key derivation']),
    'Q89': ('NIST_SP_800-192', ['verification', 'test methods', 'access control policy', 'conformance', 'model']),
    'Q93': ('NIST_SP_800-201', ['cloud computing forensic', 'reference architecture', 'tiers', 'architectural']),
    'Q95': ('NIST_SP_800-114', ['byod', 'telework', 'client endpoint', 'employee', 'device security']),
    'Q96': ('NIST_SP_800-116', ['high-security', 'perimeter', 'piv authentication', 'controlled area', 'exclusion']),
    'Q97': ('NIST_SP_800-101', ['seized', 'smartphone', 'mobile', 'acquisition', 'integrity', 'isolation']),
    'Q100': ('NIST_SP_800-210', ['abac', 'cross-tenant', 'tenant', 'multi-tenancy', 'cloud']),
    'Q101': ('NIST_SP_800-239', ['gpu', 'memory', 'leakage', 'multi-tenant', 'isolation', 'cross-job']),
    'Q103': ('NIST_SP_800-216', ['vdp', 'intake', 'triage', 'remediation', 'handling procedures']),
    'Q104': ('NIST_SP_800-221', ['supply chain', 'systemic', 'disruption', 'ict risk', 'assessment'])
}

for label, (doc_id, kws) in queries.items():
    results = find_best(doc_id, kws)
    print(f"\n=== {label} ({doc_id}) ===")
    for score, c in results:
        cid = c['chunk_id']
        p = c.get('page_start')
        h = c.get('section_heading', '').replace('\n', ' ').encode('ascii', 'ignore').decode('ascii')
        preview = c['text'][:150].replace('\n', ' ').encode('ascii', 'ignore').decode('ascii')
        print(f"  [{cid}] (p.{p}) [sc:{score}] {h}: {preview}")
