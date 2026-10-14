#!/usr/bin/env python3
"""CLI runner for structure-aware, content-aware document chunking."""

import argparse
from pathlib import Path
import sys

# Ensure repository root is on PYTHONPATH
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ingestion.chunking.config import ChunkingConfig
from app.ingestion.chunking.runner import CorpusChunkingRunner


def parse_args():
    parser = argparse.ArgumentParser(
        description="Execute structure-aware chunking on cleaned NIST publications.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--pilot",
        action="store_true",
        default=True,
        help="Process the 10-document cleaned pilot cohort.",
    )
    parser.add_argument(
        "--doc",
        type=str,
        default=None,
        help="Target a single specific document ID (e.g. NIST_SP_800-53).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Simulate chunking without writing output files or consuming disk space.",
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        default="data/cleaned_pilot",
        help="Directory containing cleaned publication folders.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/chunks_pilot",
        help="Directory where chunk JSONL files and manifest will be written.",
    )
    parser.add_argument(
        "--tokenizer",
        type=str,
        default="hf_tokenizer",
        choices=["hf_tokenizer", "tiktoken", "char_estimate"],
        help="Tokenizer backend for token budgeting.",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="BAAI/bge-small-en-v1.5",
        help="Model name or local path for tokenizer.",
    )
    parser.add_argument(
        "--target-tokens",
        type=int,
        default=400,
        help="Nominal target chunk token size.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=500,
        help="Strict maximum token ceiling.",
    )
    parser.add_argument(
        "--overlap-tokens",
        type=int,
        default=50,
        help="Sliding window token overlap within same section.",
    )
    parser.add_argument(
        "--max-table-tokens",
        type=int,
        default=500,
        help="Token budget for atomic tables before row splitting.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        default=False,
        help="Halt immediately if any document encounters an error.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        default=False,
        help="Overwrite existing files in output directory.",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    config = ChunkingConfig(
        tokenizer_backend=args.tokenizer,
        model_name_or_path=args.model,
        target_chunk_tokens=args.target_tokens,
        max_chunk_tokens=args.max_tokens,
        chunk_overlap_tokens=args.overlap_tokens,
        max_table_tokens=args.max_table_tokens,
        input_dir=Path(args.input_dir),
        output_dir=Path(args.output_dir),
        fail_fast=args.fail_fast,
        dry_run=args.dry_run,
        overwrite_existing=args.overwrite,
    )

    try:
        runner = CorpusChunkingRunner(config=config)
        report = runner.run_pilot(target_doc_id=args.doc)

        if report.failures:
            print(f"\n[WARNING] {len(report.failures)} document(s) encountered failures.")
            sys.exit(1)
        else:
            print("\n[SUCCESS] Chunking completed successfully with zero failures.")
            sys.exit(0)

    except Exception as e:
        print(f"\n[FATAL ERROR] Chunking runner failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
