import json

with open('data/evaluation/retrieval_ground_truth_100q_refined.json', 'r', encoding='utf-8') as f:
    d = json.load(f)

for qid, item in d.items():
    if item.get('verification_status') == 'candidate':
        doc = item.get('primary_document') or item.get('document_ids')
        chunks = item.get('relevant_chunks') or item.get('relevant_chunk_ids')
        print(f"{qid} ({item.get('category')}): doc={doc} chunks={chunks}")
