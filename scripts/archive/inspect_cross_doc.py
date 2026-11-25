import sys
sys.path.append('.')
from scripts.build_candidate_definitions import chunk_by_id

cross_pairs = [
    ('Q46', 'NIST_SP_800-204_txt_00054', 'NIST_SP_800-190_txt_00076'),
    ('Q47', 'NIST_SP_800-207_txt_00030', 'NIST_SP_800-210_txt_00001'),
    ('Q48', 'NIST_SP_800-63_txt_00081', 'NIST_SP_800-116_txt_00001'),
    ('Q49', 'NIST_SP_800-130_txt_00001', 'NIST_SP_800-57_txt_00033'),
    ('Q50', 'NIST_SP_800-216_txt_00001', 'NIST_SP_800-218_txt_00029'),
    ('Q51', 'NIST_SP_800-61_txt_00087', 'NIST_SP_800-101_txt_00001')
]

for qid, c1, c2 in cross_pairs:
    print("=== %s ===" % qid)
    chunk1 = chunk_by_id[c1]
    chunk2 = chunk_by_id[c2]
    print("Chunk 1 (%s, %s p.%s):" % (c1, chunk1['document_id'], chunk1.get('page_start')))
    print("  ", chunk1['text'][:220].replace('\n', ' ').encode('ascii', 'ignore').decode('ascii'))
    print("Chunk 2 (%s, %s p.%s):" % (c2, chunk2['document_id'], chunk2.get('page_start')))
    print("  ", chunk2['text'][:220].replace('\n', ' ').encode('ascii', 'ignore').decode('ascii'))
