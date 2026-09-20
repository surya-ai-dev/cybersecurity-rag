import json
import math
import re
from pathlib import Path
from bm25_retriever import load_documents as load_bm25_documents

from rank_bm25 import BM25Okapi
from bm25_retriever import load_documents, BM25Retriever


# ============================================================
# CONFIGURATION
# ============================================================

TOP_K_BM25 = 20
TOP_K_FINAL = 5

EVALUATION_FILE = "evaluation_questions.json"
GROUND_TRUTH_FILE = "ground_truth.json"


# ============================================================
# LOAD JSON
# ============================================================

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# LOAD QUESTIONS
# ============================================================

def load_questions():
    data = load_json(EVALUATION_FILE)

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        if "questions" in data:
            return data["questions"]

        return list(data.values())

    raise ValueError("Unsupported evaluation_questions.json format")


# ============================================================
# LOAD GROUND TRUTH
# ============================================================

def load_ground_truth():
    return load_json(GROUND_TRUTH_FILE)


# ============================================================
# QUESTION EXTRACTION
# ============================================================

def get_question(item):
    if isinstance(item, str):
        return item

    if isinstance(item, dict):
        for key in ["question", "query", "text"]:
            if key in item:
                return item[key]

    raise ValueError(f"Cannot extract question from: {item}")


# ============================================================
# GROUND TRUTH EXTRACTION
# ============================================================

def get_relevant_ids(
    ground_truth,
    question,
    question_index
):
    # --------------------------------------------------------
    # Dictionary format
    #
    # {
    #   "Q1": ["chunk1", "chunk2"],
    #   "Q2": ["chunk3", "chunk4"]
    # }
    # --------------------------------------------------------

    if isinstance(ground_truth, dict):

        q_key = f"Q{question_index + 1}"

        if q_key in ground_truth:
            return ground_truth[q_key]

        if question in ground_truth:
            return ground_truth[question]

        # Some files may wrap the data
        if "questions" in ground_truth:
            data = ground_truth["questions"]

            if isinstance(data, list):
                if question_index < len(data):
                    item = data[question_index]

                    if isinstance(item, dict):
                        for key in [
                            "relevant_chunks",
                            "relevant_ids",
                            "chunks",
                            "ground_truth"
                        ]:
                            if key in item:
                                return item[key]

    # --------------------------------------------------------
    # List format
    # --------------------------------------------------------

    if isinstance(ground_truth, list):

        if question_index >= len(ground_truth):
            return []

        item = ground_truth[question_index]

        if isinstance(item, list):
            return item

        if isinstance(item, dict):

            for key in [
                "relevant_chunks",
                "relevant_ids",
                "chunks",
                "ground_truth"
            ]:
                if key in item:
                    return item[key]

    return []


# ============================================================
# TOKENIZATION
# ============================================================

def tokenize(text):
    """
    Simple BM25 tokenization.

    Lowercase + keep words/numbers.
    """

    return re.findall(
        r"\b\w+\b",
        text.lower()
    )


# ============================================================
# LOAD CORPUS
# ============================================================

def load_documents():
    """
    Use the exact same document loader as bm25_retriever.py.

    This guarantees that BM25 evaluation uses the
    same 7,703 chunks as the actual BM25 retriever.
    """

    documents = load_bm25_documents()

    if documents is None:
        raise RuntimeError(
            "bm25_retriever.load_documents() returned None."
        )

    if len(documents) == 0:
        raise RuntimeError(
            "bm25_retriever.load_documents() returned 0 documents."
        )

    print(f"Loaded {len(documents):,} documents/chunks.")

    return documents
    

# ============================================================
# BM25 SEARCH
# ============================================================

def bm25_search(
    bm25,
    documents,
    question,
    top_k=TOP_K_BM25
):
    """
    Run BM25 retrieval using the project's BM25Retriever.

    The retriever itself owns the BM25 implementation.
    Evaluation should only consume its retrieval results.
    """

    results = bm25.retrieve(
        question,
        top_k=top_k
    )

    return results


# ============================================================
# METRICS
# ============================================================

def calculate_metrics(
    ranked_results,
    relevant_ids
):

    if not ranked_results:

        return {
            "hit1": 0,
            "hit3": 0,
            "hit5": 0,
            "precision5": 0.0,
            "mrr": 0.0
        }

    relevant_ids = {
        str(x)
        for x in relevant_ids
    }

    retrieved_ids = [
        str(result["chunk_id"])
        for result in ranked_results
    ]

    relevant = [
        chunk_id in relevant_ids
        for chunk_id in retrieved_ids
    ]

    # --------------------------------------------------------
    # Hit@1
    # --------------------------------------------------------

    hit1 = (
        1
        if any(relevant[:1])
        else 0
    )

    # --------------------------------------------------------
    # Hit@3
    # --------------------------------------------------------

    hit3 = (
        1
        if any(relevant[:3])
        else 0
    )

    # --------------------------------------------------------
    # Hit@5
    # --------------------------------------------------------

    hit5 = (
        1
        if any(relevant[:5])
        else 0
    )

    # --------------------------------------------------------
    # Precision@5
    # --------------------------------------------------------

    top5 = relevant[:5]

    precision5 = (
        sum(top5) / len(top5)
        if top5
        else 0.0
    )

    # --------------------------------------------------------
    # MRR
    # --------------------------------------------------------

    mrr = 0.0

    for rank, is_relevant in enumerate(
        relevant,
        start=1
    ):

        if is_relevant:

            mrr = 1.0 / rank

            break

    return {
        "hit1": hit1,
        "hit3": hit3,
        "hit5": hit5,
        "precision5": precision5,
        "mrr": mrr
    }


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("BM25 RETRIEVAL EVALUATION")
    print("=" * 70)

    # --------------------------------------------------------
    # QUESTIONS
    # --------------------------------------------------------

    print(
        "\nLoading evaluation questions..."
    )

    questions = load_questions()

    print(
        f"Loaded {len(questions)} questions."
    )

    # --------------------------------------------------------
    # GROUND TRUTH
    # --------------------------------------------------------

    print(
        "\nLoading ground truth..."
    )

    ground_truth = load_ground_truth()

    print(
        "Ground truth loaded."
    )

    # --------------------------------------------------------
    # DOCUMENTS
    # --------------------------------------------------------

    print(
        "\nLoading documents..."
    )

    documents = load_documents()

    # --------------------------------------------------------
    # BM25
    # --------------------------------------------------------

    bm25 = BM25Retriever(documents)

    # --------------------------------------------------------
    # METRIC STORAGE
    # --------------------------------------------------------

    all_metrics = []

    # ========================================================
    # EVALUATION LOOP
    # ========================================================

    for index, item in enumerate(
        questions
    ):

        question = get_question(item)

        relevant_ids = get_relevant_ids(
            ground_truth,
            question,
            index
        )

        print("\n")
        print("=" * 70)
        print(
            f"Q{index + 1}"
        )
        print("=" * 70)

        print("\nQuestion:")
        print(question)

        print(
            "\nGround-truth relevant chunks:"
        )

        if relevant_ids:

            for chunk_id in relevant_ids:
                print(
                    f"  {chunk_id}"
                )

        else:

            print(
                "  ⚠️ NO GROUND TRUTH FOUND"
            )

        # ----------------------------------------------------
        # BM25 SEARCH
        # ----------------------------------------------------

        results = bm25_search(
            bm25,
            documents,
            question,
            TOP_K_BM25
        )

        print(
            f"\nBM25 retrieval → Top-{TOP_K_BM25}"
        )

        print(
            f"Retrieved {len(results)} candidates."
        )

        # ----------------------------------------------------
        # TOP-5
        # ----------------------------------------------------

        top5 = results[
            :TOP_K_FINAL
        ]

        print("\n")
        print("-" * 70)
        print("BM25 TOP-5")
        print("-" * 70)

        for rank, result in enumerate(
            top5,
            start=1
        ):

            chunk_id = result[
                "chunk_id"
            ]

            score = result[
                "score"
            ]

            is_relevant = (
                str(chunk_id)
                in {
                    str(x)
                    for x in relevant_ids
                }
            )

            label = (
                "RELEVANT"
                if is_relevant
                else "NOT RELEVANT"
            )

            print(
                f"{rank}. "
                f"{chunk_id:<35} "
                f"score={score:.4f} "
                f"{label}"
            )

        # ----------------------------------------------------
        # METRICS
        # ----------------------------------------------------

        metrics = calculate_metrics(
            top5,
            relevant_ids
        )

        all_metrics.append(
            metrics
        )

        print("\nMetrics:")

        print(
            f"  Hit@1       : "
            f"{'YES' if metrics['hit1'] else 'NO'}"
        )

        print(
            f"  Hit@3       : "
            f"{'YES' if metrics['hit3'] else 'NO'}"
        )

        print(
            f"  Hit@5       : "
            f"{'YES' if metrics['hit5'] else 'NO'}"
        )

        print(
            f"  Precision@5 : "
            f"{metrics['precision5']:.4f}"
        )

        print(
            f"  MRR         : "
            f"{metrics['mrr']:.4f}"
        )

    # ========================================================
    # OVERALL RESULTS
    # ========================================================

    if not all_metrics:

        print(
            "\n❌ No metrics calculated."
        )

        return

    count = len(all_metrics)

    avg_hit1 = (
        sum(
            x["hit1"]
            for x in all_metrics
        )
        / count
    )

    avg_hit3 = (
        sum(
            x["hit3"]
            for x in all_metrics
        )
        / count
    )

    avg_hit5 = (
        sum(
            x["hit5"]
            for x in all_metrics
        )
        / count
    )

    avg_precision5 = (
        sum(
            x["precision5"]
            for x in all_metrics
        )
        / count
    )

    avg_mrr = (
        sum(
            x["mrr"]
            for x in all_metrics
        )
        / count
    )

    print("\n")
    print("=" * 70)
    print("OVERALL BM25 RESULTS")
    print("=" * 70)

    print()

    print(
        f"Hit@1          : "
        f"{avg_hit1:.2%}"
    )

    print(
        f"Hit@3          : "
        f"{avg_hit3:.2%}"
    )

    print(
        f"Hit@5          : "
        f"{avg_hit5:.2%}"
    )

    print(
        f"Precision@5    : "
        f"{avg_precision5:.2%}"
    )

    print(
        f"MRR            : "
        f"{avg_mrr:.4f}"
    )

    print("\n")
    print("=" * 70)
    print("BM25 EVALUATION COMPLETE")
    print("=" * 70)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()