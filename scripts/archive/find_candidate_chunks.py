import glob
import json
import re
from pathlib import Path

def search_chunks(doc_id=None, query_regex=None, content_type=None, limit=5):
    pattern = f"data/chunks_*/**/{doc_id}_chunks.jsonl" if doc_id else "data/chunks_*/**/*.jsonl"
    files = glob.glob(pattern, recursive=True)
    if not files:
        print(f"No files matching {doc_id}")
        return []

    regex = re.compile(query_regex, re.IGNORECASE) if query_regex else None
    results = []
    for fpath in files:
        with open(fpath, "r", encoding="utf-8") as f:
            for line in f:
                c = json.loads(line)
                if content_type and c.get("content_type") != content_type:
                    continue
                text = c.get("text", "")
                heading = c.get("section_heading", "") or ""
                path = c.get("section_path", "") or ""
                tmeta = str(c.get("table_metadata", ""))
                combined = f"{heading} {path} {tmeta} {text}"
                if regex and not regex.search(combined):
                    continue
                results.append(c)
                if len(results) >= limit:
                    return results
    return results

def print_results(results):
    for r in results:
        cid = r.get("chunk_id")
        doc = r.get("document_id")
        ctype = r.get("content_type")
        page = r.get("page_start")
        heading = r.get("section_heading")
        text = r.get("text", "")[:250].replace("\n", " ")
        print(f"[{cid}] (p.{page}, {ctype}) {heading}\n   -> {text}...\n")

if __name__ == "__main__":
    # Test search
    print("=== Search NIST_SP_800-131 for algorithm transition / security strength tables ===")
    res = search_chunks("NIST_SP_800-131", r"security strength|disallowed|legacy-use|deprecated", content_type="table", limit=3)
    print_results(res)

    print("=== Search NIST_SP_800-53 for control baselines / allocation tables ===")
    res2 = search_chunks("NIST_SP_800-53", r"Low|Moderate|High|control baseline", content_type="table", limit=3)
    print_results(res2)

    print("=== Search NIST_SP_800-218 for SSDF practice tasks ===")
    res3 = search_chunks("NIST_SP_800-218", r"PO\.|PS\.|PW\.|RV\.", content_type="table", limit=3)
    print_results(res3)
