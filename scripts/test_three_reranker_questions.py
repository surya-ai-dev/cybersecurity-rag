import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))




import json
import time
from pathlib import Path
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient

from evaluation.evaluate_retrieval_metrics import (
    QUESTIONS_FILE,
    BASELINE_GROUND_TRUTH_FILE,
    retrieve_dense,
)
from app.retrieval.reranker import CrossEncoderReranker


QUESTION_IDS = ["Q10", "Q13", "Q19"]
COLLECTION = "cybersecurity_chunks_bge_m3"
CANDIDATE_COUNT = 20
FINAL_TOP_K = 5
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"


def main():
    questions_data = json.loads(
        QUESTIONS_FILE.read_text(encoding="utf-8")
    )
    ground_truth = json.loads(
        BASELINE_GROUND_TRUTH_FILE.read_text(encoding="utf-8")
    )

    questions = {
        item["id"]: item
        for item in questions_data
        if item.get("id") in QUESTION_IDS
    }

    missing = [qid for qid in QUESTION_IDS if qid not in questions]
    if missing:
        raise ValueError(f"Questions not found: {missing}")

    print("Loading BGE-M3...")
    model = SentenceTransformer("BAAI/bge-m3")

    client = QdrantClient(path=str(PROJECT_ROOT / "data" / "qdrant"))
    reranker = None

    try:
        print(f"Loading reranker: {RERANKER_MODEL}")
        reranker = CrossEncoderReranker(
            model_name=RERANKER_MODEL,
            lazy_load=False,
        )

        for qid in QUESTION_IDS:
            item = questions[qid]
            question = item["question"]
            gt_entry = ground_truth.get(qid, {})
            relevant = set(gt_entry.get("relevant_chunks", []))

            print("\n" + "=" * 80)
            print(f"{qid}: {question}")
            print("Expected:", sorted(relevant))

            # Retrieve top 20 dense candidates.
            started = time.perf_counter()
            candidates = retrieve_dense(
                client, model, question, limit=CANDIDATE_COUNT
            )
            retrieval_ms = (time.perf_counter() - started) * 1000

            # Baseline: original dense ranking, top 5.
            baseline = candidates[:FINAL_TOP_K]

            # Rerank the same top 20 candidates, then take top 5.
            started = time.perf_counter()
            reranked = reranker.rerank(
                question, candidates, top_n=CANDIDATE_COUNT
            )
            rerank_ms = (time.perf_counter() - started) * 1000
            final_results = reranked[:FINAL_TOP_K]

            for label, results in (
                ("DENSE BASELINE TOP 5", baseline),
                ("RERANKED TOP 5", final_results),
            ):
                found = [c.chunk_id for c in results if c.chunk_id in relevant]
                print(f"\n--- {label} ---")
                print(f"Relevant chunks found: {len(found)}/{len(relevant)}")
                print(f"Hit@5: {bool(found)}")
                for rank, chunk in enumerate(results, 1):
                    marker = " [RELEVANT]" if chunk.chunk_id in relevant else ""
                    print(f"\n{rank}. {chunk.chunk_id}{marker}")
                    print(f"   Score: {getattr(chunk, 'score', 'N/A')}")
                    print(f"   Text: {getattr(chunk, 'text', '')[:500]}")

            print(f"\nRetrieval latency: {retrieval_ms:.1f} ms")
            print(f"Reranking latency: {rerank_ms:.1f} ms")

    finally:
        if reranker is not None:
            reranker.close()
        client.close()


if __name__ == "__main__":
    main()
