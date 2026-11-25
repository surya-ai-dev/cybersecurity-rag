import glob
import json
import re

def load_corpus():
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
    return chunk_by_id, chunks_by_doc

def search_text(chunks_by_doc, doc_id, query_str, limit=5, content_type=None):
    doc_chunks = chunks_by_doc.get(doc_id, [])
    regex = re.compile(query_str, re.IGNORECASE)
    results = []
    for c in doc_chunks:
        if content_type and c.get("content_type") != content_type:
            continue
        text = c.get("text", "")
        heading = c.get("section_heading", "") or ""
        path = c.get("section_path", "") or ""
        if regex.search(f"{heading} {path} {text}"):
            results.append(c)
            if len(results) >= limit:
                break
    return results

if __name__ == "__main__":
    chunk_by_id, chunks_by_doc = load_corpus()
    print(f"Loaded {len(chunk_by_id)} chunks across {len(chunks_by_doc)} documents.")

    # Test some key searches for our questions
    test_queries = [
        ("NIST_SP_800-57", r"states|lifecycle|pre-activation|active|deactivated|destroyed", "text"),
        ("NIST_SP_800-130", r"components|framework|CKMS", "text"),
        ("NIST_SP_800-133", r"asymmetric|key pair|generation", "text"),
        ("NIST_SP_800-185", r"KMAC|cSHAKE|customization", "text"),
        ("NIST_SP_800-208", r"LMS|XMSS|stateful hash", "text"),
        ("NIST_SP_800-232", r"Ascon|lightweight|permutation", "text"),
        ("NIST_SP_800-73", r"CHUID|PIV auth|fingerprint|card-edge", "text"),
        ("NIST_SP_800-76", r"minutiae|biometric|image quality", "text"),
        ("NIST_SP_800-78", r"algorithms|key sizes|cryptographic specifications", "text"),
        ("NIST_SP_800-79", r"accreditation|PCI|card issuing", "text"),
    ]

    for doc, q, ctype in test_queries:
        res = search_text(chunks_by_doc, doc, q, limit=1, content_type=ctype)
        if res:
            r = res[0]
            print(f"[{doc}] -> {r['chunk_id']} (p.{r.get('page_start')}): {r.get('section_heading')} | {r['text'][:100].replace('\n', ' ')}...")
        else:
            print(f"[{doc}] -> NOT FOUND")
