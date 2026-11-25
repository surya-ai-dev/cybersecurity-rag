import json
from pathlib import Path

# Load all chunks
all_chunks = {}
chunks_by_doc = {}
for p in Path('data').glob('chunks_*/**/*.jsonl'):
    with open(p, 'r', encoding='utf-8') as f:
        for line in f:
            c = json.loads(line)
            all_chunks[c['chunk_id']] = c
            chunks_by_doc.setdefault(c['document_id'], []).append(c)

# Define query keywords for each question requiring refinement
search_configs = {
    'Q47': [('NIST_SP_800-210', ['pdp', 'pep', 'access control', 'policy enforcement', 'architecture'])],
    'Q48': [('NIST_SP_800-116', ['aal3', 'piv', 'facility', 'physical access', 'perimeter'])],
    'Q49': [('NIST_SP_800-130', ['ckms', 'framework', 'components', 'architecture', 'lifecycle'])],
    'Q50': [('NIST_SP_800-216', ['intake', 'triage', 'policy', 'vulnerability disclosure', 'handling'])],
    'Q51': [('NIST_SP_800-101', ['chain of custody', 'evidence', 'mobile', 'acquisition', 'integrity'])],
    'Q55': [('NIST_SP_800-130', ['scope', 'purpose', 'ckms', 'design framework', 'components'])],
    'Q56': [('NIST_SP_800-133', ['comment', 'entropy', 'key generation', 'matrix', 'table'])],
    'Q57': [('NIST_SP_800-185', ['cshake', 'kmac', 'tuplehash', 'parallelhash'])],
    'Q58': [('NIST_SP_800-208', ['lms', 'xmss', 'stateful', 'hash-based', 'signature'])],
    'Q59': [('NIST_SP_800-232', ['ascon', 'lightweight', 'aead', 'hash', 'permutation'])],
    'Q62': [('NIST_SP_800-78', ['scope', 'piv', 'cryptographic algorithms', 'key sizes', 'suite'])],
    'Q65': [('NIST_SP_800-217', ['federation', 'piv', 'federated', 'identity', 'objective'])],
    'Q67': [('NIST_SP_800-221', ['ict risk outcomes', 'risk outcomes', 'enterprise risk', 'measuring', 'core focus'])],
    'Q70': [('NIST_SP_800-107', ['security properties', 'hash functions', 'preimage', 'collision', 'second preimage'])],
    'Q71': [('NIST_SP_800-175', ['transitioning', 'selection', 'transition', 'strategic', 'algorithm'])],
    'Q73': [('NIST_SP_800-205', ['dynamic', 'contextual', 'attributes', 'environmental', 'access control'])],
    'Q74': [('NIST_SP_800-226', ['epsilon', 'privacy budget', 'trade-offs', 'differential privacy', 'guarantees'])],
    'Q76': [('NIST_SP_800-215', ['perimeter', 'software-defined', 'landscape', 'transition', 'sdn'])],
    'Q77': [('NIST_SP_800-231', ['bugs framework', 'bf', 'formalizing', 'weaknesses', 'vulnerabilities', 'model'])],
    'Q78': [('NIST_SP_800-236', ['annual report', 'strategic', 'milestones', 'research priorities', 'fy 2024'])],
    'Q80': [('NIST_SP_800-197', ['lightweight block cipher', 'ascon', 'comments', 'stakeholder', 'draft'])],
    'Q82': [('NIST_SP_800-140', ['non-invasive', 'physical attack', 'cmvp', 'mitigation', 'side-channel'])],
    'Q84': [('NIST_SP_800-89', ['validation', 'assurances', 'digital signature', 'keys', 'generation'])],
    'Q85': [('NIST_SP_800-38', ['ff1', 'ff3', 'fpe', 'format-preserving', 'mode'])],
    'Q86': [('NIST_SP_800-56', ['pair-wise', 'key establishment', 'integer factorization', 'rsa', 'scheme'])],
    'Q87': [('NIST_SP_800-186', ['elliptic curve', 'domain parameter', 'curve', 'recommended', 'edwards', 'weierstrass'])],
    'Q88': [('NIST_SP_800-132', ['pbkdf', 'password-based', 'key derivation', 'iteration', 'salt'])],
    'Q89': [('NIST_SP_800-192', ['verification', 'test methods', 'access control policies', 'model', 'conformance'])],
    'Q93': [('NIST_SP_800-201', ['forensic reference architecture', 'tiers', 'architectural tiers', 'cloud forensic'])],
    'Q95': [('NIST_SP_800-114', ['byod', 'telework', 'endpoint security', 'employee', 'device'])],
    'Q96': [('NIST_SP_800-116', ['piv authentication', 'facility', 'perimeters', 'high-security', 'physical access'])],
    'Q97': [('NIST_SP_800-101', ['mobile', 'seized', 'evidence acquisition', 'integrity', 'forensic'])],
    'Q100': [('NIST_SP_800-210', ['abac', 'cloud', 'cross-tenant', 'tenant', 'policies'])],
    'Q101': [('NIST_SP_800-239', ['gpu', 'memory', 'ai cluster', 'multi-tenant', 'cross-job', 'leakage'])],
    'Q103': [('NIST_SP_800-216', ['vdp', 'intake', 'triage', 'vulnerability disclosure', 'procedures'])],
    'Q104': [('NIST_SP_800-221', ['ict risk outcomes', 'supply chain', 'systemic', 'disruptions', 'assessment'])]
}

for qid, configs in search_configs.items():
    print(f"\n==========================================")
    print(f"SEARCH FOR {qid}:")
    for doc_id, kws in configs:
        doc_chunks = chunks_by_doc.get(doc_id, [])
        scored = []
        for c in doc_chunks:
            if c['chunk_id'].endswith('_txt_00001'):
                continue
            txt = c['text'].lower()
            s = sum(1 for kw in kws if kw in txt)
            if s > 0:
                scored.append((s, c))
        scored.sort(key=lambda x: x[0], reverse=True)
        print(f"  Doc: {doc_id} (Top 3 matches out of {len(scored)}):")
        for s, c in scored[:3]:
            h = c.get('section_heading', '').replace('\n', ' ')
            p = c.get('page_start', '')
            t = c['text'][:140].replace('\n', ' ')
            print(f"    [{c['chunk_id']}] (p.{p}) [Score {s}] {h}: {t}")
