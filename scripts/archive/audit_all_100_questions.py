import json
from pathlib import Path
from collections import Counter, defaultdict

# Load candidate 100 questions
with open('data/evaluation/retrieval_ground_truth_100q_candidates.json', 'r', encoding='utf-8') as f:
    data_100 = json.load(f)

# Load chunk index
import sys
sys.path.append('.')
from scripts.build_candidate_definitions import chunk_by_id

print(f"Loaded {len(data_100)} questions.")

# Audit each question
audit_results = []

for qid, q in data_100.items():
    qtext = q.get('question', '')
    cids = q.get('relevant_chunks') or q.get('relevant_chunk_ids') or []
    status = q.get('verification_status')
    
    # 1. Chunk existence and length
    chunks_found = []
    chunks_missing = []
    chunk_details = []
    for cid in cids:
        if cid in chunk_by_id:
            c = chunk_by_id[cid]
            chunks_found.append(c)
            chunk_details.append({
                "cid": cid,
                "doc": c["document_id"],
                "type": c.get("content_type", "text"),
                "page": c.get("page_start"),
                "heading": c.get("section_heading", "") or "",
                "len": len(c.get("text", "")),
                "text_snippet": c.get("text", "")[:150].replace("\n", " ")
            })
        else:
            chunks_missing.append(cid)

    audit_results.append({
        "qid": qid,
        "question": qtext,
        "category": q.get("category", "unspecified"),
        "primary_doc": q.get("primary_document") or (q.get("document_ids")[0] if "document_ids" in q else "N/A"),
        "supporting_docs": q.get("supporting_documents") or (q.get("document_ids")[1:] if "document_ids" in q and len(q["document_ids"]) > 1 else []),
        "cids": cids,
        "chunks_missing": chunks_missing,
        "chunk_details": chunk_details,
        "current_status": status,
        "notes": q.get("rationale") or q.get("verification_notes") or q.get("expected_answer_summary") or ""
    })

print(f"Audited {len(audit_results)} questions.")
missing_any = [a for a in audit_results if a["chunks_missing"]]
print(f"Questions with missing chunks: {len(missing_any)}")
