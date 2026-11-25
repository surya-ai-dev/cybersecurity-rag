import glob
import json
import re

def test_queries():
    # Load all chunks
    chunk_by_id = {}
    chunks_by_doc = {}
    for fpath in glob.glob("data/chunks_*/**/*.jsonl", recursive=True):
        with open(fpath, "r", encoding="utf-8") as f:
            for line in f:
                c = json.loads(line)
                cid = c["chunk_id"]
                doc = c["document_id"]
                chunk_by_id[cid] = c
                if doc not in chunks_by_doc:
                    chunks_by_doc[doc] = []
                chunks_by_doc[doc].append(c)

    print("Loaded %d chunks." % len(chunk_by_id))

    # Test queries for documents to be used in Q46-Q104
    doc_queries = [
        # Cross-document Q46-Q51
        ("NIST_SP_800-190", r"image vulnerability|image signing|registry", "text"),
        ("NIST_SP_800-204", r"pipeline|CI/CD|supply chain|provenance", "text"),
        ("NIST_SP_800-210", r"access control|cloud systems|authorization", "text"),
        ("NIST_SP_800-116", r"facility access|PACS|PIV card", "text"),
        ("NIST_SP_800-216", r"vulnerability disclosure|VDP|reporting", "text"),
        ("NIST_SP_800-61", r"chain of custody|evidence handling|forensic", "text"),
        # Multi-chunk Q52-Q53
        ("NIST_SP_800-53", r"CA-7|continuous monitoring|re-authorization", "text"),
        ("NIST_SP_800-161", r"supplier|contractual clause|assessment", "text"),
        # Direct Factual Q54-Q69
        ("NIST_SP_800-57", r"BYOK|Bring Your Own Key|cloud key", "text"),
        ("NIST_SP_800-130", r"CKMS|key management system|components", "text"),
        ("NIST_SP_800-133", r"Filippo Valsorda|key generation|entropy", "text"),
        ("NIST_SP_800-185", r"KMAC|cSHAKE|TupleHash", "text"),
        ("NIST_SP_800-208", r"stateful hash|LMS|XMSS|quantum", "text"),
        ("NIST_SP_800-232", r"Ascon|lightweight|permutation", "text"),
        ("NIST_SP_800-73", r"CHUID|Cardholder Unique Identifier|PIV authentication", "text"),
        ("NIST_SP_800-76", r"minutiae|fingerprint image|quality", "text"),
        ("NIST_SP_800-78", r"algorithms|key sizes|cryptographic specifications", "text"),
        ("NIST_SP_800-79", r"accreditation|PCI|card issuing organization", "text"),
        ("NIST_SP_800-157", r"derived credential|derived PIV|mobile", "text"),
        ("NIST_SP_800-217", r"federation|federated identity|trust model", "text"),
        ("NIST_SP_800-50", r"awareness|training|education|learning continuum", "text"),
        ("NIST_SP_800-221", r"ICT risk|outcomes|measurement", "text"),
        ("NIST_SP_800-190", r"threats|container architecture|images", "text"),
        ("NIST_SP_800-228", r"API gateway|microservice|tokens", "text"),
        ("NIST_SP_800-72", r"volatile memory|PDA|preservation", "text"),
        ("NIST_SP_800-201", r"cloud forensic|reference architecture|tenants", "text"),
        ("NIST_SP_800-51", r"CVE|naming|syntax", "text"),
        ("NIST_SP_800-140", r"non-invasive|attack mitigation|CMVP", "text"),
        ("NIST_SP_800-223", r"HPC|supercomputer|threat modeling", "text"),
        ("NIST_SP_800-234", r"HPC overlay|high performance computing|security overlay", "text"),
        ("NIST_SP_800-239", r"AI data center|GPU|cluster security", "text"),
    ]

    for doc, q, ctype in doc_queries:
        matches = []
        regex = re.compile(q, re.IGNORECASE)
        for c in chunks_by_doc.get(doc, []):
            if ctype and c.get("content_type") != ctype:
                continue
            text = f"{c.get('section_heading', '')} {c.get('text', '')}"
            if regex.search(text):
                matches.append(c)
                if len(matches) >= 1:
                    break
        if matches:
            m = matches[0]
            txt = m['text'][:120].replace('\n', ' ').encode('ascii', 'ignore').decode('ascii')
            print("[%s] -> %s (p.%s): %s..." % (doc, m['chunk_id'], m.get('page_start'), txt))
        else:
            print("[%s] -> NOT FOUND for query: %s" % (doc, q))

if __name__ == '__main__':
    test_queries()
