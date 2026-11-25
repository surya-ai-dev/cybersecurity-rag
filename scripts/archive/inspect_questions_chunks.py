import glob
import json
import re

def load_chunks():
    chunks_by_doc = {}
    chunk_by_id = {}
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
    return chunks_by_doc, chunk_by_id

def search(chunks_by_doc, doc_id, query, ctype=None, limit=3):
    doc_chunks = chunks_by_doc.get(doc_id, [])
    regex = re.compile(query, re.IGNORECASE)
    matches = []
    for c in doc_chunks:
        if ctype and c.get("content_type") != ctype:
            continue
        text = c.get("text", "")
        heading = c.get("section_heading", "") or ""
        path = c.get("section_path", "") or ""
        if regex.search(f"{heading} {path} {text}"):
            matches.append(c)
            if len(matches) >= limit:
                break
    return matches

def show(matches):
    for m in matches:
        cid = m["chunk_id"]
        page = m.get("page_start")
        ctype = m.get("content_type")
        heading = m.get("section_heading")
        txt = m.get("text", "")[:200].replace("\n", " ")
        print(f"  [{cid}] p.{page} ({ctype}) {heading} -> {txt}...")

if __name__ == "__main__":
    by_doc, by_id = load_chunks()
    print("Chunks loaded successfully.")

    print("\n--- Group 1: Table Questions ---")
    print("Q41 (SP 800-131 table):")
    show(search(by_doc, "NIST_SP_800-131", r"Table on Page", ctype="table", limit=2))

    print("Q42 (SP 800-53 table):")
    show(search(by_doc, "NIST_SP_800-53", r"CONTROL BASELINE|Table on Page 19", ctype="table", limit=2))

    print("Q43 (SP 800-152 table):")
    show(search(by_doc, "NIST_SP_800-152", r"Table on Page 37|PR:4|AC-2", ctype="table", limit=2))

    print("Q44 (SP 800-218 table):")
    show(search(by_doc, "NIST_SP_800-218", r"PO1|PreparetheOrganization", ctype="table", limit=2))

    print("Q45 (SP 800-146 table):")
    show(search(by_doc, "NIST_SP_800-146", r"Table on Page 45|Recommendations|SaaS", ctype="table", limit=2))
