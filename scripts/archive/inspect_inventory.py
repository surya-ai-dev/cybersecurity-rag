import json

with open('data/document_inventory/document_inventory.json', 'r', encoding='utf-8') as f:
    inv = json.load(f)

docs = inv.get('documents', [])
print(f'Total documents: {len(docs)}')
print('Sample doc keys:', list(docs[0].keys()))

by_cat = {}
for d in docs:
    cat = d.get('category') or 'other'
    by_cat.setdefault(cat, []).append(d)

for cat, doclist in by_cat.items():
    print(f'=== {cat} ({len(doclist)} docs) ===')
    for d in doclist:
        doc_id = d.get('document_id') or d.get('file_name') or d.get('relative_path')
        title = d.get('title', '')
        # sanitize for windows console
        clean_title = title.encode('ascii', 'ignore').decode('ascii')
        print(f"  {doc_id}: {clean_title[:70]}")
