"""Unit tests for the evaluation runner in evaluation/run_full_evaluation.py.

Verifies:
- Ground-truth parsing (dict, list, empty, invalid).
- Eligibility filtering (verified + eligible vs. candidate/unresolved/ineligible).
- Safe handling of missing ground-truth entries and empty chunk lists.
- Exact question ID alignment (no broken positional index lookups).
- Retrieval evaluation across Dense, BM25, RRF, and CrossEncoder with mock retrievers.
- Equal question counts across all retrieval stages.
- No dependency on deleted ground_truth.json.
- Real corpus ground-truth file eligibility alignment (35 verified questions).
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.models import ChunkMetadata, RetrievedChunk
from evaluation.run_full_evaluation import (
    calc_hit_at_k,
    calc_mrr,
    calc_precision_at_k,
    filter_eligible_questions,
    parse_ground_truth_ids,
    run_retrieval_evaluation,
)


# ============================================================
# 1. GROUND TRUTH PARSING TESTS
# ============================================================

def test_parse_ground_truth_ids_relevant_chunks():
    """Extract IDs from dict with 'relevant_chunks'."""
    gt = {"relevant_chunks": ["chunk_001", "chunk_002"]}
    assert parse_ground_truth_ids(gt) == {"chunk_001", "chunk_002"}


def test_parse_ground_truth_ids_relevant_chunk_ids():
    """Extract IDs from dict with 'relevant_chunk_ids'."""
    gt = {"relevant_chunk_ids": ["chunk_003"]}
    assert parse_ground_truth_ids(gt) == {"chunk_003"}


def test_parse_ground_truth_ids_list_format():
    """Extract IDs from a simple list format."""
    gt = ["chunk_004", "chunk_005"]
    assert parse_ground_truth_ids(gt) == {"chunk_004", "chunk_005"}


def test_parse_ground_truth_ids_empty_and_invalid():
    """Return empty set for empty or malformed ground truth."""
    assert parse_ground_truth_ids({}) == set()
    assert parse_ground_truth_ids([]) == set()
    assert parse_ground_truth_ids(None) == set()
    assert parse_ground_truth_ids("chunk_001") == set()
    assert parse_ground_truth_ids({"relevant_chunks": []}) == set()


# ============================================================
# 2. ELIGIBILITY FILTERING TESTS
# ============================================================

def test_filter_eligible_questions_verified_and_eligible():
    """Only questions marked evaluation_eligible: True and verification_status: 'verified' pass."""
    questions = [
        {"id": "Q1", "question": "What is MFA?"},
        {"id": "Q2", "question": "What is zero trust?"},
    ]
    ground_truth = {
        "Q1": {
            "evaluation_eligible": True,
            "verification_status": "verified",
            "relevant_chunks": ["NIST_SP_800-63B_txt_00010"],
        },
        "Q2": {
            "evaluation_eligible": True,
            "verification_status": "verified",
            "relevant_chunks": ["NIST_SP_800-207_txt_00020"],
        },
    }
    result = filter_eligible_questions(questions, ground_truth)
    assert len(result) == 2
    assert [q["id"] for q in result] == ["Q1", "Q2"]


def test_filter_eligible_questions_excludes_ineligible_flag():
    """Questions with evaluation_eligible: False are excluded."""
    questions = [
        {"id": "Q1", "question": "Question 1"},
        {"id": "Q2", "question": "Question 2"},
    ]
    ground_truth = {
        "Q1": {
            "evaluation_eligible": True,
            "verification_status": "verified",
            "relevant_chunks": ["chunk_1"],
        },
        "Q2": {
            "evaluation_eligible": False,
            "verification_status": "verified",
            "relevant_chunks": ["chunk_2"],
        },
    }
    result = filter_eligible_questions(questions, ground_truth)
    assert len(result) == 1
    assert result[0]["id"] == "Q1"


def test_filter_eligible_questions_excludes_unverified_statuses():
    """Questions with verification_status 'candidate' or 'unresolved' are excluded."""
    questions = [
        {"id": "Q1", "question": "Verified question"},
        {"id": "Q2", "question": "Candidate question"},
        {"id": "Q3", "question": "Unresolved question"},
        {"id": "Q4", "question": "No status question"},
    ]
    ground_truth = {
        "Q1": {
            "evaluation_eligible": True,
            "verification_status": "verified",
            "relevant_chunks": ["chunk_1"],
        },
        "Q2": {
            "evaluation_eligible": True,
            "verification_status": "candidate",
            "relevant_chunks": ["chunk_2"],
        },
        "Q3": {
            "evaluation_eligible": True,
            "verification_status": "unresolved",
            "relevant_chunks": ["chunk_3"],
        },
        "Q4": {
            "evaluation_eligible": True,
            "relevant_chunks": ["chunk_4"],
        },
    }
    result = filter_eligible_questions(questions, ground_truth)
    assert len(result) == 1
    assert result[0]["id"] == "Q1"


def test_filter_eligible_questions_handles_missing_gt_safely():
    """Questions missing in ground_truth are skipped without throwing errors."""
    questions = [
        {"id": "Q1", "question": "Known question"},
        {"id": "Q999", "question": "Missing question"},
    ]
    ground_truth = {
        "Q1": {
            "evaluation_eligible": True,
            "verification_status": "verified",
            "relevant_chunks": ["chunk_1"],
        },
    }
    result = filter_eligible_questions(questions, ground_truth)
    assert len(result) == 1
    assert result[0]["id"] == "Q1"


def test_filter_eligible_questions_excludes_empty_chunks():
    """Questions with empty relevant_chunks are excluded to prevent metric distortion."""
    questions = [
        {"id": "Q1", "question": "Question with chunks"},
        {"id": "Q2", "question": "Question without chunks"},
    ]
    ground_truth = {
        "Q1": {
            "evaluation_eligible": True,
            "verification_status": "verified",
            "relevant_chunks": ["chunk_1"],
        },
        "Q2": {
            "evaluation_eligible": True,
            "verification_status": "verified",
            "relevant_chunks": [],
        },
    }
    result = filter_eligible_questions(questions, ground_truth)
    assert len(result) == 1
    assert result[0]["id"] == "Q1"


def test_filter_eligible_questions_handles_missing_qid():
    """Items without a valid 'id' or 'question_id' are skipped cleanly."""
    questions = [
        {"question": "No ID here"},
        {"id": "Q1", "question": "Has ID"},
    ]
    ground_truth = {
        "Q1": {
            "evaluation_eligible": True,
            "verification_status": "verified",
            "relevant_chunks": ["chunk_1"],
        },
    }
    result = filter_eligible_questions(questions, ground_truth)
    assert len(result) == 1
    assert result[0]["id"] == "Q1"


def test_filter_eligible_questions_preserves_qid_alignment():
    """Non-contiguous question lists match by exact ID, not index."""
    questions = [
        {"id": "Q1", "question": "First"},
        {"id": "Q3", "question": "Third (index 1)"},
        {"id": "Q7", "question": "Seventh (index 2)"},
    ]
    ground_truth = {
        "Q1": {
            "evaluation_eligible": True,
            "verification_status": "verified",
            "relevant_chunks": ["chunk_q1"],
        },
        "Q2": {
            "evaluation_eligible": True,
            "verification_status": "verified",
            "relevant_chunks": ["chunk_q2"],
        },
        "Q3": {
            "evaluation_eligible": True,
            "verification_status": "verified",
            "relevant_chunks": ["chunk_q3"],
        },
        "Q7": {
            "evaluation_eligible": True,
            "verification_status": "verified",
            "relevant_chunks": ["chunk_q7"],
        },
    }
    result = filter_eligible_questions(questions, ground_truth)
    assert [q["id"] for q in result] == ["Q1", "Q3", "Q7"]


# ============================================================
# 3. METRIC COMPUTATION TESTS
# ============================================================

def test_metric_calculations():
    """Test Hit@k, Precision@k, and MRR calculations."""
    retrieved = ["c1", "c2", "c3", "c4", "c5"]
    relevant = {"c2", "c4"}

    assert calc_hit_at_k(retrieved, relevant, 1) == 0
    assert calc_hit_at_k(retrieved, relevant, 2) == 1
    assert calc_hit_at_k(retrieved, relevant, 5) == 1

    assert calc_precision_at_k(retrieved, relevant, 5) == 2 / 5
    assert calc_precision_at_k(retrieved, relevant, 2) == 1 / 2

    # MRR: first hit is at rank 2 -> 1/2 = 0.5
    assert calc_mrr(retrieved, relevant) == 0.5

    # No match
    assert calc_mrr(["x1", "x2"], relevant) == 0.0


# ============================================================
# 4. RETRIEVAL EVALUATION RUNNER (MOCKED)
# ============================================================

def _make_mock_chunk(chunk_id: str, score: float = 1.0) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        text=f"Text for {chunk_id}",
        score=score,
        metadata=ChunkMetadata(
            document_id="NIST_TEST",
            category="Test Category",
            section="1.0",
            source_file="test.pdf",
            token_count=100,
        ),
    )


@patch("evaluation.run_full_evaluation.CrossEncoderReranker")
@patch("evaluation.run_full_evaluation.BM25Retriever")
@patch("evaluation.run_full_evaluation.DenseRetriever")
def test_run_retrieval_evaluation_mocked(
    mock_dense_cls,
    mock_bm25_cls,
    mock_reranker_cls,
):
    """Run retrieval evaluation with mocked retrievers; verify all 4 methods evaluate identical questions."""
    # Setup mock retrievers
    mock_dense = MagicMock()
    mock_bm25 = MagicMock()
    mock_reranker = MagicMock()

    mock_dense_cls.return_value = mock_dense
    mock_bm25_cls.return_value = mock_bm25
    mock_reranker_cls.return_value = mock_reranker

    # Mock retrieve returns
    mock_dense.retrieve.return_value = [
        _make_mock_chunk("chunk_1", 0.9),
        _make_mock_chunk("chunk_2", 0.8),
    ]
    mock_bm25.retrieve.return_value = [
        _make_mock_chunk("chunk_2", 12.0),
        _make_mock_chunk("chunk_3", 10.0),
    ]
    mock_reranker.rerank.return_value = [
        _make_mock_chunk("chunk_1", 2.5),
        _make_mock_chunk("chunk_2", 1.8),
    ]

    questions = [
        {"id": "Q1", "question": "Question 1?"},
        {"id": "Q3", "question": "Question 3?"},
        {"id": "Q14", "question": "Ineligible question 14?"},
    ]
    ground_truth = {
        "Q1": {
            "evaluation_eligible": True,
            "verification_status": "verified",
            "relevant_chunks": ["chunk_1"],
        },
        "Q3": {
            "evaluation_eligible": True,
            "verification_status": "verified",
            "relevant_chunks": ["chunk_2"],
        },
        "Q14": {
            "evaluation_eligible": False,
            "verification_status": "unresolved",
            "relevant_chunks": ["chunk_99"],
        },
    }

    results = run_retrieval_evaluation(
        questions=questions,
        ground_truth=ground_truth,
        verbose=False,
    )

    # All 4 stages must be present
    assert "dense" in results
    assert "bm25" in results
    assert "rrf" in results
    assert "reranker" in results

    # Exactly 2 eligible questions evaluated across all 4 stages
    assert results["dense"]["count"] == 2.0
    assert results["bm25"]["count"] == 2.0
    assert results["rrf"]["count"] == 2.0
    assert results["reranker"]["count"] == 2.0

    # Verify Dense retriever was closed
    mock_dense.close.assert_called_once()

    # Verify BM25 was called exactly 2 times (once per eligible question, no duplicate calls)
    assert mock_bm25.retrieve.call_count == 2
    assert mock_dense.retrieve.call_count == 2
    assert mock_reranker.rerank.call_count == 2


@patch("evaluation.run_full_evaluation.CrossEncoderReranker")
@patch("evaluation.run_full_evaluation.BM25Retriever")
@patch("evaluation.run_full_evaluation.DenseRetriever")
def test_run_retrieval_evaluation_with_max_questions(
    mock_dense_cls,
    mock_bm25_cls,
    mock_reranker_cls,
):
    """Verify max_questions parameter uniformly limits all retrieval stages."""
    mock_dense = MagicMock()
    mock_bm25 = MagicMock()
    mock_reranker = MagicMock()

    mock_dense_cls.return_value = mock_dense
    mock_bm25_cls.return_value = mock_bm25
    mock_reranker_cls.return_value = mock_reranker

    mock_dense.retrieve.return_value = [_make_mock_chunk("c1")]
    mock_bm25.retrieve.return_value = [_make_mock_chunk("c1")]
    mock_reranker.rerank.return_value = [_make_mock_chunk("c1")]

    questions = [
        {"id": f"Q{i}", "question": f"Question {i}?"}
        for i in range(1, 10)
    ]
    ground_truth = {
        f"Q{i}": {
            "evaluation_eligible": True,
            "verification_status": "verified",
            "relevant_chunks": ["c1"],
        }
        for i in range(1, 10)
    }

    # Limit to 3 questions
    results = run_retrieval_evaluation(
        questions=questions,
        ground_truth=ground_truth,
        verbose=False,
        max_questions=3,
    )

    assert results["dense"]["count"] == 3.0
    assert results["bm25"]["count"] == 3.0
    assert results["rrf"]["count"] == 3.0
    assert results["reranker"]["count"] == 3.0
    assert mock_dense.retrieve.call_count == 3
    assert mock_bm25.retrieve.call_count == 3


def test_run_retrieval_evaluation_no_eligible_questions():
    """Return zeroed metrics safely when no eligible questions exist."""
    questions = [{"id": "Q1", "question": "Unverified?"}]
    ground_truth = {
        "Q1": {
            "evaluation_eligible": False,
            "verification_status": "candidate",
            "relevant_chunks": ["c1"],
        }
    }
    results = run_retrieval_evaluation(
        questions=questions,
        ground_truth=ground_truth,
        verbose=False,
    )
    for method in ["dense", "bm25", "rrf", "reranker"]:
        assert results[method]["count"] == 0.0
        assert results[method]["hit1"] == 0.0
        assert results[method]["mrr"] == 0.0


# ============================================================
# 5. REAL BENCHMARK DATASET ALIGNMENT TEST
# ============================================================

def test_real_benchmark_files_eligibility_filtering():
    """Verify that filtering real project evaluation files yields exactly 35 verified questions."""
    eval_q_path = Path("data/evaluation/evaluation_questions.json")
    eval_gt_path = Path("data/evaluation/retrieval_ground_truth_current.json")

    assert eval_q_path.exists(), f"Missing {eval_q_path}"
    assert eval_gt_path.exists(), f"Missing {eval_gt_path}"

    with open(eval_q_path, "r", encoding="utf-8") as f:
        questions = json.load(f)

    with open(eval_gt_path, "r", encoding="utf-8") as f:
        ground_truth = json.load(f)

    eligible = filter_eligible_questions(questions, ground_truth)

    # In evaluation_questions.json, there are 36 questions (Q1, Q3..Q14, Q16, Q17, Q19..Q40).
    # Q14 has verification_status='unresolved' and evaluation_eligible=False.
    # Exactly 35 questions must be eligible and verified.
    assert len(eligible) == 35

    eligible_ids = [q["id"] for q in eligible]
    assert "Q14" not in eligible_ids
    assert "Q2" not in eligible_ids
    assert "Q6" not in eligible_ids
    assert "Q15" not in eligible_ids
    assert "Q18" not in eligible_ids

    # Verify all 35 eligible questions have non-empty relevant chunks
    for q in eligible:
        qid = q["id"]
        rel = parse_ground_truth_ids(ground_truth[qid])
        assert len(rel) > 0, f"Question {qid} has empty relevant chunks"
