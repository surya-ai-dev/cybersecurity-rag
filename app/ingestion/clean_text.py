"""CLI entry point and orchestrator for conservative document text cleaning."""

import argparse
import sys
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ingestion.cleaning.config import CleaningConfig
from app.ingestion.cleaning.pipeline import DocumentCleaningPipeline

PILOT_OUTPUT_DIR = PROJECT_ROOT / "data" / "cleaned_pilot"
CORPUS_OUTPUT_DIR = PROJECT_ROOT / "data" / "cleaned_corpus"

PILOT_TARGETS = [
    ("cryptography_security", "NIST_SP_800-152", PROJECT_ROOT / "data" / "extraction_pilot_v3" / "cryptography_security" / "NIST_SP_800-152"),
    ("cryptography_security", "NIST_SP_800-186", PROJECT_ROOT / "data" / "extraction_pilot_v3" / "cryptography_security" / "NIST_SP_800-186"),
    ("risk_management", "NIST_SP_800-39", PROJECT_ROOT / "data" / "extraction_pilot_v3" / "risk_management" / "NIST_SP_800-39"),
    ("risk_management", "NIST_SP_800-53", PROJECT_ROOT / "data" / "extraction_pilot_v3" / "risk_management" / "NIST_SP_800-53"),
    ("root", "NIST_SP_800-236", PROJECT_ROOT / "data" / "extraction_pilot_v3" / "root" / "NIST_SP_800-236"),
    ("identity_access", "NIST_SP_800-116", PROJECT_ROOT / "data" / "extraction_corpus_68" / "identity_access" / "NIST_SP_800-116"),
    ("root", "NIST_SP_800-234", PROJECT_ROOT / "data" / "extraction_corpus_68" / "root" / "NIST_SP_800-234"),
    ("vulnerability_management", "NIST_SP_800-218", PROJECT_ROOT / "data" / "extraction_corpus_68" / "vulnerability_management" / "NIST_SP_800-218"),
    ("root", "NIST_SP_800-238", PROJECT_ROOT / "data" / "extraction_corpus_68" / "root" / "NIST_SP_800-238"),
    ("root", "NIST.SP.800-61r3", PROJECT_ROOT / "data" / "extraction_corpus_68" / "root" / "NIST.SP.800-61r3"),
]


def clean_pilot() -> None:
    """Run Stage 2 cleaning on the 10 pilot documents."""
    config = CleaningConfig(output_dir=PILOT_OUTPUT_DIR, pilot_mode=True)
    pipeline = DocumentCleaningPipeline(config)

    print("=" * 78)
    print("STAGE 2: CONSERVATIVE TEXT CLEANING PILOT (10 TARGET DOCUMENTS)")
    print("=" * 78)
    print(f"Output Directory: {PILOT_OUTPUT_DIR.resolve()}\n")

    successful = 0
    failed = 0

    for idx, (cat, did, in_dir) in enumerate(PILOT_TARGETS, 1):
        print(f"[{idx}/10] Cleaning: {did} ({cat})")
        try:
            res = pipeline.clean_document_dir(in_dir, PILOT_OUTPUT_DIR, did, cat)
            summary = res["cleaning_summary"]
            print(f"       Status: SUCCESS | Pages: {res['total_pages']} | "
                  f"Chars: {res['original_char_count']:,} -> {res['cleaned_char_count']:,} ({summary['pct_change']:.2f}%) | "
                  f"Headers: {summary['total_headers_removed']} | Footers: {summary['total_footers_removed']}")
            successful += 1
        except Exception as ex:
            print(f"       Status: FAILED | Error: {ex}")
            failed += 1

    print("\n" + "=" * 78)
    print(f"CLEANING PILOT COMPLETE: Successful: {successful} | Failed: {failed}")
    print("=" * 78 + "\n")


def main() -> None:
    """CLI entry point for document cleaning."""
    parser = argparse.ArgumentParser(
        description="Conservative, evidence-based document text cleaning for Cybersecurity RAG."
    )
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument(
        "--pilot",
        action="store_true",
        help="Run Stage 2 cleaning on the 10 representative pilot documents.",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Run full-corpus cleaning on all 63 remaining documents across 4 batches.",
    )
    group.add_argument(
        "--batch",
        type=str,
        help="Run corpus cleaning for a specific batch: 1, 2, 3, 4, or '1-4' / 'all'.",
    )
    group.add_argument(
        "--doc",
        type=str,
        help="Run corpus cleaning on a single document by its document ID.",
    )
    group.add_argument(
        "--recover",
        action="store_true",
        help="Inspect and safely recover any interrupted IN_PROGRESS documents, then exit.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform pre-checks, display batch document lists, estimated storage, and checkpoint status without executing cleaning.",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry documents currently marked FAILED in the checkpoint manifest.",
    )
    parser.add_argument(
        "--continue-on-failure",
        action="store_true",
        help="Continue processing remaining documents if a document fails (default: fail-fast).",
    )
    parser.add_argument(
        "--min-free-disk-mb",
        type=int,
        default=500,
        help="Minimum free disk space in MB required to proceed (default: 500).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Custom output directory (default: data/cleaned_pilot in pilot mode, data/cleaned_corpus in corpus mode).",
    )

    args = parser.parse_args()

    if args.pilot:
        clean_pilot()
    elif args.all or args.batch or args.doc or args.recover or (args.dry_run and not args.pilot):
        from scripts.run_corpus_cleaning import CorpusCleaningRunner
        out_dir = args.output_dir or CORPUS_OUTPUT_DIR
        runner = CorpusCleaningRunner(
            output_dir=out_dir,
            min_free_disk_mb=args.min_free_disk_mb,
            dry_run=args.dry_run,
            continue_on_failure=args.continue_on_failure,
            retry_failed=args.retry_failed,
        )

        if args.recover:
            recovered = runner.recover_in_progress_documents()
            print(f"[RECOVERY COMPLETE] Recovered {len(recovered)} document(s).")
        elif args.doc:
            runner.run_doc(args.doc)
        elif args.batch:
            b_str = args.batch.strip().lower()
            if b_str in ("all", "1-4"):
                runner.run_all()
            elif b_str in ("1", "2", "3", "4"):
                runner.run_batch(int(b_str))
            else:
                print(f"[ERROR] Invalid batch argument: '{args.batch}'. Must be 1, 2, 3, 4, or '1-4' / 'all'.")
                sys.exit(1)
        elif args.all or args.dry_run:
            runner.run_all()
    else:
        print("[SAFETY NOTICE] Please specify a cleaning mode or target:")
        print("  --pilot                  Run Stage 2 cleaning pilot on 10 verified documents")
        print("  --dry-run --batch 1      Dry-run inspection of Batch 1 without modifying files")
        print("  --dry-run --all          Dry-run inspection of all 63 documents without modifying files")
        print("  --batch 1                Run cleaning for Batch 1 (16 documents)")
        print("  --doc <document_id>      Run cleaning for a single document")
        print("  --all                    Run cleaning for all 63 documents across 4 batches")
        print("  --recover                Recover any interrupted IN_PROGRESS documents")
        sys.exit(0)


if __name__ == "__main__":
    main()