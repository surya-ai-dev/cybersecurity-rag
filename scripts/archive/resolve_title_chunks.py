import json
from pathlib import Path

# Load all chunks by doc
chunks_by_doc = {}
for p in Path('data').glob('chunks_*/**/*.jsonl'):
    with open(p, 'r', encoding='utf-8') as f:
        for line in f:
            c = json.loads(line)
            chunks_by_doc.setdefault(c['document_id'], []).append(c)

with open('data/evaluation/retrieval_ground_truth_100q_candidates.json', 'r', encoding='utf-8') as f:
    cand = json.load(f)

# The questions to inspect
questions_to_inspect = [
    'Q47', 'Q48', 'Q49', 'Q50', 'Q51',
    'Q55', 'Q56', 'Q57', 'Q58', 'Q59',
    'Q62', 'Q65', 'Q67', 'Q70', 'Q71',
    'Q73', 'Q74', 'Q76', 'Q77', 'Q78',
    'Q80', 'Q82', 'Q84', 'Q85', 'Q86',
    'Q87', 'Q88', 'Q89', 'Q93', 'Q95',
    'Q96', 'Q97', 'Q100', 'Q101', 'Q103', 'Q104'
]

print(f"Total questions to inspect: {len(questions_to_inspect)}")

def search_doc(doc_id, keywords, max_results=5):
    results = []
    doc_chunks = chunks_by_doc.get(doc_id, [])
    for c in doc_chunks:
        if c['chunk_id'].endswith('_txt_00001'):
            continue  # skip title chunk
        txt = c['text'].lower()
        score = sum(1 for kw in keywords if kw.lower() in txt)
        if score > 0:
            results.append((score, c))
    results.sort(key=lambda x: x[0], reverse=True)
    return results[:max_results]

# Let's inspect each question
for qid in questions_to_inspect:
    item = cand[qid]
    q = item['question']
    p_doc = item.get('primary_document') or item.get('document_ids', [''])[0]
    s_docs = item.get('supporting_documents', [])
    curr_chunks = item.get('relevant_chunks') or item.get('relevant_chunk_ids')
    print(f"\n==============================")
    print(f"[{qid}] Doc: {p_doc} | Supp: {s_docs}")
    print(f"Q: {q}")
    print(f"Current chunks: {curr_chunks}")
