import glob
import json
import re
from pathlib import Path

# Load corpus
print("Loading active corpus chunks...")
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

def verify_chunk(cid, min_len=50):
    assert cid in chunk_by_id, f"Chunk {cid} not found in corpus!"
    c = chunk_by_id[cid]
    text = c.get("text", "")
    assert len(text) >= min_len, f"Chunk {cid} text too short ({len(text)} chars)!"
    return c

print("Corpus verification helper ready.")
