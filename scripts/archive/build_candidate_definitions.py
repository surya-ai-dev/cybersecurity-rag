import glob
import json
import re
from pathlib import Path

# Load corpus
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

print(f"Loaded {len(chunk_by_id)} chunks across {len(chunks_by_doc)} documents.")

def get_chunk(cid):
    assert cid in chunk_by_id, f"Chunk {cid} does not exist in active corpus!"
    return chunk_by_id[cid]

def make_candidate(qid, qtext, category, pdoc, sdocs, cids, answer_summary, notes=""):
    # Verify chunks exist
    chunks = [get_chunk(c) for c in cids]
    # Extract source sections and pages
    sections = [c.get("section_heading") or c.get("section_path") or "" for c in chunks]
    pages = [c.get("page_start") for c in chunks if c.get("page_start") is not None]
    
    clean_sections = " | ".join(dict.fromkeys([s for s in sections if s]))
    page_str = ", ".join(str(p) for p in sorted(set(pages))) if pages else "N/A"

    return {
        "question_id": qid,
        "question": qtext,
        "category": category,
        "primary_document": pdoc,
        "supporting_documents": sdocs,
        "relevant_chunk_ids": cids,
        "expected_answer_summary": answer_summary,
        "source_section": clean_sections,
        "source_page": page_str,
        "verification_status": "candidate",
        "verification_notes": notes
    }

print("Helper functions defined successfully.")
