import glob
import json
from collections import defaultdict
from pathlib import Path

def print_domain_table():
    domain_stats = defaultdict(lambda: {'docs': set(), 'pages': 0, 'chunks': 0, 'text': 0, 'table': 0, 'figure': 0})

    with open('data/document_inventory/document_inventory.json', 'r', encoding='utf-8') as f:
        inv = json.load(f)
    doc_pages = {d['file_name'].replace('.pdf', ''): d['page_count'] for d in inv['documents']}

    for fpath in glob.glob('data/chunks_*/**/*.jsonl', recursive=True):
        p = Path(fpath)
        domain = p.parent.name
        doc_id = p.stem.replace('_chunks', '')
        domain_stats[domain]['docs'].add(doc_id)
        with open(p, 'r', encoding='utf-8') as f:
            for line in f:
                c = json.loads(line)
                ctype = c.get('content_type', 'text')
                domain_stats[domain]['chunks'] += 1
                domain_stats[domain][ctype] += 1

    for domain, st in domain_stats.items():
        st['pages'] = sum(doc_pages.get(d, 0) for d in st['docs'])

    print("%-30s | %4s | %5s | %5s | %5s | %5s | %6s" % ("Domain", "Docs", "Pages", "Total", "Text", "Table", "Figure"))
    print("-" * 75)
    tot_docs = 0
    tot_pages = 0
    tot_chunks = 0
    tot_text = 0
    tot_table = 0
    tot_fig = 0
    for domain, st in sorted(domain_stats.items(), key=lambda x: -x[1]['chunks']):
        d_cnt = len(st['docs'])
        tot_docs += d_cnt
        tot_pages += st['pages']
        tot_chunks += st['chunks']
        tot_text += st['text']
        tot_table += st['table']
        tot_fig += st['figure']
        print("%-30s | %4d | %5d | %5d | %5d | %5d | %6d" % (domain, d_cnt, st['pages'], st['chunks'], st['text'], st['table'], st['figure']))
    print("-" * 75)
    print("%-30s | %4d | %5d | %5d | %5d | %5d | %6d" % ("Total", tot_docs, tot_pages, tot_chunks, tot_text, tot_table, tot_fig))

if __name__ == '__main__':
    print_domain_table()
