import json
import glob
import os
from pathlib import Path
from collections import Counter, defaultdict

def main():
    pilot_manifest_path = Path("data/chunks_pilot/chunks_manifest.json")
    corpus_manifest_path = Path("data/chunks_corpus/chunks_manifest.json")

    with open(pilot_manifest_path, "r", encoding="utf-8") as f:
        pilot_manifest = json.load(f)
    with open(corpus_manifest_path, "r", encoding="utf-8") as f:
        corpus_manifest = json.load(f)

    print("=== CORPUS MANIFESTS ===")
    print("PILOT:")
    print(f"  docs: {pilot_manifest.get('total_documents')}, chunks: {pilot_manifest.get('total_chunks')}, "
          f"text: {pilot_manifest.get('chunks_text')}, table: {pilot_manifest.get('chunks_table')}, "
          f"figure: {pilot_manifest.get('chunks_figure')}")
    print("CORPUS:")
    print(f"  docs: {corpus_manifest.get('total_documents')}, chunks: {corpus_manifest.get('total_chunks')}, "
          f"text: {corpus_manifest.get('chunks_text')}, table: {corpus_manifest.get('chunks_table')}, "
          f"figure: {corpus_manifest.get('chunks_figure')}")

    total_docs = pilot_manifest.get('total_documents') + corpus_manifest.get('total_documents')
    total_chunks = pilot_manifest.get('total_chunks') + corpus_manifest.get('total_chunks')
    total_text = pilot_manifest.get('chunks_text') + corpus_manifest.get('chunks_text')
    total_table = pilot_manifest.get('chunks_table') + corpus_manifest.get('chunks_table')
    total_figure = pilot_manifest.get('chunks_figure') + corpus_manifest.get('chunks_figure')
    print("COMBINED:")
    print(f"  docs: {total_docs}, chunks: {total_chunks}, text: {total_text}, table: {total_table}, figure: {total_figure}")

    # Inspect all chunks in both directories to get domain distribution and document list
    all_jsonl = glob.glob("data/chunks_pilot/**/*.jsonl", recursive=True) + glob.glob("data/chunks_corpus/**/*.jsonl", recursive=True)

    domain_chunks = Counter()
    domain_docs = defaultdict(set)
    doc_chunk_counts = Counter()
    doc_type_counts = defaultdict(Counter)
    doc_domain = {}
    content_type_counter = Counter()

    all_chunk_ids = set()
    all_chunks_list = []

    for fpath in all_jsonl:
        p = Path(fpath)
        domain = p.parent.name
        doc_filename = p.stem.replace("_chunks", "")
        domain_docs[domain].add(doc_filename)
        doc_domain[doc_filename] = domain

        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                chunk = json.loads(line)
                cid = chunk.get("chunk_id")
                ctype = chunk.get("content_type", "text")
                all_chunk_ids.add(cid)
                domain_chunks[domain] += 1
                doc_chunk_counts[doc_filename] += 1
                doc_type_counts[doc_filename][ctype] += 1
                content_type_counter[ctype] += 1
                all_chunks_list.append((cid, doc_filename, domain, ctype, chunk.get("token_count", 0)))

    print(f"\nTotal parsed chunks from jsonl files: {len(all_chunks_list)}")
    print(f"Total unique chunk IDs: {len(all_chunk_ids)}")
    print(f"Content types breakdown: {dict(content_type_counter)}")

    print("\n=== DOMAIN BREAKDOWN ===")
    for domain, d_chunks in domain_chunks.most_common():
        docs = domain_docs[domain]
        t_txt = sum(doc_type_counts[d]["text"] for d in docs)
        t_tbl = sum(doc_type_counts[d]["table"] for d in docs)
        t_fig = sum(doc_type_counts[d]["figure"] for d in docs)
        print(f"  Domain: {domain:30s} | Docs: {len(docs):2d} | Chunks: {d_chunks:5d} (txt: {t_txt:4d}, tbl: {t_tbl:4d}, fig: {t_fig:3d})")

    # Now inspect the 36 questions
    gt_path = Path("data/evaluation/retrieval_ground_truth_v2.json")
    with open(gt_path, "r", encoding="utf-8") as f:
        gt_v2 = json.load(f)
    print(f"\n=== EXISTING 36 QUESTIONS IN {gt_path.name} ===")
    print(f"Total questions: {len(gt_v2)}")

    q_doc_counts = Counter()
    q_domain_counts = Counter()
    q_content_types = Counter()
    chunk_usage = Counter()
    q_chunk_counts = Counter()
    multi_doc_questions = []
    single_doc_questions = []

    # Map chunk id to content type
    cid_to_type = {c[0]: c[3] for c in all_chunks_list}
    cid_to_doc = {c[0]: c[1] for c in all_chunks_list}

    for qid, item in gt_v2.items():
        q = item.get("question")
        chunks = item.get("relevant_chunks", [])
        q_chunk_counts[len(chunks)] += 1

        docs_in_q = set()
        for cid in chunks:
            chunk_usage[cid] += 1
            ctype = cid_to_type.get(cid, "unknown")
            q_content_types[ctype] += 1
            doc_id = cid_to_doc.get(cid)
            if not doc_id:
                for d in doc_domain:
                    if cid.startswith(d):
                        doc_id = d
                        break
            if doc_id:
                docs_in_q.add(doc_id)
                q_domain_counts[doc_domain.get(doc_id, "unknown")] += 1
            else:
                docs_in_q.add("unknown")
                q_domain_counts["unknown"] += 1

        for d in docs_in_q:
            q_doc_counts[d] += 1

        if len(docs_in_q) > 1:
            multi_doc_questions.append((qid, q, docs_in_q))
        else:
            single_doc_questions.append((qid, q, docs_in_q))

    print(f"\nRelevant chunks per question distribution:")
    for num_chunks, q_count in sorted(q_chunk_counts.items()):
        print(f"  {num_chunks} chunk(s): {q_count} questions")

    print(f"\nGround-truth chunk content types:")
    for ctype, count in q_content_types.items():
        print(f"  {ctype}: {count}")

    print(f"\nQuestion counts per referenced document:")
    for doc, count in q_doc_counts.most_common():
        print(f"  {doc:25s} | Domain: {doc_domain.get(doc, 'unknown'):26s} | Questions: {count:2d}")

    print(f"\nCross-document questions ({len(multi_doc_questions)} total):")
    for qid, q, dset in multi_doc_questions:
        print(f"  {qid}: {q[:60]}... -> {dset}")

    print(f"\nDomain representations in existing 36 questions (references count):")
    for domain, count in q_domain_counts.most_common():
        print(f"  {domain:30s} | References: {count:2d}")

    print(f"\nUnique documents referenced in 36 questions: {len(q_doc_counts)} out of 73 total documents")
    unrepresented_docs = set(doc_domain.keys()) - set(q_doc_counts.keys())
    print(f"Unrepresented documents count: {len(unrepresented_docs)} out of 73")
    print(f"Unrepresented documents list: {sorted(list(unrepresented_docs))}")

if __name__ == "__main__":
    main()
