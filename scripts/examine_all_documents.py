import glob
import json
import os
from collections import defaultdict

def examine_all():
    docs_summary = {}
    for fpath in glob.glob("data/chunks_*/**/*.jsonl", recursive=True):
        doc_id = None
        chunks = []
        with open(fpath, "r", encoding="utf-8") as f:
            for line in f:
                c = json.loads(line)
                doc_id = c["document_id"]
                chunks.append(c)
        if doc_id:
            # find title/intro chunk
            intro_chunks = [c for c in chunks if c.get("page_start", 0) <= 5 and c.get("content_type") == "text"]
            intro_text = " ".join(c.get("text", "")[:100].replace("\n", " ") for c in intro_chunks[:3])
            # sample section headings
            headings = [c.get("section_heading", "") for c in chunks if c.get("section_heading") and not c.get("section_heading").startswith("Table")]
            unique_headings = []
            for h in headings:
                if h and h not in unique_headings:
                    unique_headings.append(h)
            docs_summary[doc_id] = {
                "chunk_count": len(chunks),
                "text_count": sum(1 for c in chunks if c.get("content_type") == "text"),
                "table_count": sum(1 for c in chunks if c.get("content_type") == "table"),
                "figure_count": sum(1 for c in chunks if c.get("content_type") == "figure"),
                "headings": unique_headings[:10],
                "intro": intro_text[:200]
            }

    output_path = "data/corpus_metadata/docs_summary.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as out:
        json.dump(docs_summary, out, indent=2)

    print("Saved docs_summary.json with %d documents to %s." % (len(docs_summary), output_path))

if __name__ == '__main__':
    examine_all()
