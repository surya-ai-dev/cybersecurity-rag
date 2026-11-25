import json
from pathlib import Path

all_chunks = {}
for p in Path('data').glob('chunks_*/**/*.jsonl'):
    with open(p, 'r', encoding='utf-8') as f:
        for line in f:
            c = json.loads(line)
            all_chunks[c['chunk_id']] = c

def check(doc_id, kws):
    print(f"\n==================== {doc_id} ====================")
    matches = []
    for cid, c in all_chunks.items():
        if c['document_id'] == doc_id and not cid.endswith('_txt_00001'):
            txt = c['text'].lower()
            s = sum(1 for kw in kws if kw.lower() in txt)
            if s > 0:
                matches.append((s, c))
    matches.sort(key=lambda x: (x[0], len(x[1]['text'])), reverse=True)
    for s, c in matches[:3]:
        cid = c['chunk_id']
        p = c.get('page_start')
        h = c.get('section_heading', '').replace('\n', ' ')
        preview = c['text'][:200].replace('\n', ' ').encode('ascii', 'ignore').decode('ascii')
        print(f"[{cid}] (p.{p}) [score {s}] {h}")
        print(f"   {preview}")

# SP 800-89: assurances digital signature keys
check('NIST_SP_800-89', ['assurance', 'digital signature', 'generation', 'validation'])

# SP 800-38: FF1, FF3-1 format-preserving encryption
check('NIST_SP_800-38', ['ff1', 'ff3', 'format-preserving', 'fpe'])

# SP 800-56: pair-wise key establishment integer factorization
check('NIST_SP_800-56', ['pair-wise', 'key establishment', 'rsa', 'scheme', 'integer factorization'])

# SP 800-186: elliptic curve recommendations
check('NIST_SP_800-186', ['curve', 'weierstrass', 'edwards', 'recommended'])

# SP 800-132: pbkdf recommendations
check('NIST_SP_800-132', ['pbkdf', 'iteration', 'salt', 'key derivation'])

# SP 800-192: verification and test methods access control
check('NIST_SP_800-192', ['verification', 'test methods', 'access control', 'conformance', 'model'])

# SP 800-201: cloud forensic reference architecture tiers
check('NIST_SP_800-201', ['tier', 'forensic', 'architecture', 'cloud forensic'])

# SP 800-114: BYOD telework client endpoint controls
check('NIST_SP_800-114', ['byod', 'telework', 'client', 'endpoint', 'antivirus', 'firewall'])

# SP 800-116: high-security perimeter PIV
check('NIST_SP_800-116', ['perimeter', 'high-security', 'exclusion', 'piv', 'authentication'])

# SP 800-101: seized smartphone evidence acquisition
check('NIST_SP_800-101', ['seized', 'acquisition', 'faraday', 'isolation', 'smartphone', 'mobile'])

# SP 800-239: GPU memory AI cluster multi-tenant
check('NIST_SP_800-239', ['gpu', 'memory', 'leakage', 'multi-tenant', 'isolation'])
