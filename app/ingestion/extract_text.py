"""NIST PDF text and layout extraction entry point.

Provides modular, layout-aware extraction with preflight inspection, Docling primary parser,
PyMuPDF supporting parser, selective OCR fallback, table structure preservation, and quality audits.
"""

import argparse
from pathlib import Path
import sys
from typing import List, Optional

# Ensure UTF-8 output on Windows consoles where available
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Ensure project root is in sys.path for direct CLI execution
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from app.ingestion.extraction.config import ExtractionConfig
from app.ingestion.extraction.docling_parser import DoclingParser
from app.ingestion.extraction.ocr_engine import OCRFallbackManager
from app.ingestion.extraction.pipeline import DocumentExtractionPipeline
from app.ingestion.extraction.preflight import PreflightInspector

DOCUMENTS_DIR = PROJECT_ROOT / "documents"
LEGACY_OUTPUT_DIR = PROJECT_ROOT / "data" / "extracted_text"
PILOT_OUTPUT_DIR = PROJECT_ROOT / "data" / "extraction_pilot"


def extract_pdf_legacy(pdf_path: Path, output_dir: Optional[Path] = None) -> bool:
    """Legacy extractor dumping raw text with page markers for backward compatibility."""
    out_dir = output_dir or LEGACY_OUTPUT_DIR
    category = pdf_path.parent.name
    category_output = out_dir / category
    category_output.mkdir(parents=True, exist_ok=True)
    txt_path = category_output / f"{pdf_path.stem}.txt"

    try:
        doc = fitz.open(pdf_path)
        all_text = []
        for page_number, page in enumerate(doc, start=1):
            text = page.get_text()
            all_text.append(f"\n\n--- PAGE {page_number} ---\n\n{text}")

        final_text = "".join(all_text)
        txt_path.write_text(final_text, encoding="utf-8")
        doc.close()
        return True
    except Exception as error:
        print(f"[ERROR] Legacy extraction failed for {pdf_path}: {error}")
        return False


def extract_pdf(
    pdf_path: Path,
    output_dir: Optional[Path] = None,
    use_hybrid: bool = True,
) -> bool:
    """Extract a single PDF using modular extraction pipeline."""
    try:
        config = ExtractionConfig(
            output_dir=output_dir or PILOT_OUTPUT_DIR,
            use_hybrid_pymupdf4llm=use_hybrid,
        )
        pipeline = DocumentExtractionPipeline(config)
        pipeline.extract_document(pdf_path)
        return True
    except Exception as err:
        print(f"[ERROR] Modular extraction failed for {pdf_path}: {err}")
        return False



def print_system_diagnostics(config: ExtractionConfig) -> None:
    """Display dependency and parser readiness diagnostics."""
    docling_diag = DoclingParser.get_diagnostics()
    ocr_manager = OCRFallbackManager(config)
    ocr_diag = ocr_manager.get_diagnostics()

    print("=" * 78)
    print("DOCUMENT EXTRACTION ARCHITECTURE: DEPENDENCY & CAPABILITY AUDIT")
    print("=" * 78)
    print(f"PyMuPDF Supporting Parser : INSTALLED (pymupdf {getattr(fitz, '__version__', 'available')})")
    print(f"Hybrid Layout Parser      : {'ENABLED (PyMuPDF4LLM)' if getattr(config, 'use_hybrid_pymupdf4llm', False) else 'DISABLED (Block-based PyMuPDF)'}")
    print(f"Docling Primary Parser    : {'INSTALLED (' + str(docling_diag['version']) + ')' if docling_diag['installed'] else 'NOT INSTALLED (Boundary Active)'}")
    if not docling_diag["installed"]:
        print(f"  Note: {docling_diag['memory_and_storage_note']}")

    print(f"Selective OCR Engines     : {'AVAILABLE' if ocr_diag['any_engine_available'] else 'NOT CONFIGURED / MISSING TESSERACT'}")
    for eng in ocr_diag["engines"]:
        print(f"  - {eng['engine']}: {'READY' if eng['available'] else 'UNAVAILABLE'} ({eng['detail']})")

    print(f"Diagram Analysis (VLM)    : PASSTHROUGH READY (External VLM disabled to preserve 16GB RAM/storage)")
    print("=" * 78 + "\n")


def main() -> None:
    """CLI entry point for document extraction."""
    parser = argparse.ArgumentParser(
        description="Modular, quality-first document extraction architecture for NIST cybersecurity PDFs."
    )
    parser.add_argument(
        "--pilot",
        action="store_true",
        help="Run Phase 1 extraction on the 5 verified pilot PDFs (831 pages).",
    )
    parser.add_argument(
        "--files",
        nargs="+",
        type=str,
        default=None,
        help="Specific PDF file paths to extract.",
    )
    parser.add_argument(
        "--max-docs",
        type=int,
        default=None,
        help="Maximum number of documents to extract.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Custom output directory (default: data/extraction_pilot for pilot mode).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Execute preflight inspection only without writing extracted text artifacts.",
    )
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="Use legacy raw text dumper to data/extracted_text/ instead of modular pipeline.",
    )
    parser.add_argument(
        "--no-hybrid",
        action="store_true",
        help="Disable hybrid PyMuPDF4LLM layout parsing and use block-based PyMuPDF extraction.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Explicitly allow processing all discovered PDFs (safety guard against unintended full corpus runs).",
    )

    args = parser.parse_args()

    # Determine target files
    config = ExtractionConfig(
        output_dir=args.output_dir or (PILOT_OUTPUT_DIR if args.pilot else LEGACY_OUTPUT_DIR),
        pilot_mode=args.pilot,
        use_hybrid_pymupdf4llm=not args.no_hybrid,
    )


    print_system_diagnostics(config)

    target_files: List[Path] = []
    if args.files:
        for f_str in args.files:
            p = config.resolve_pdf_path(f_str)
            if p.is_file():
                target_files.append(p)
            else:
                print(f"[WARNING] Specified file not found: {f_str}")
    elif args.pilot:
        for f_str in config.pilot_documents:
            p = config.resolve_pdf_path(f_str)
            if p.is_file():
                target_files.append(p)
            else:
                print(f"[WARNING] Pilot file not found: {f_str}")
    elif args.all:
        target_files = sorted(list(DOCUMENTS_DIR.rglob("*.pdf")))
    else:
        print("[SAFETY NOTICE] No target specified.")
        print("To run the Phase 1 pilot on the 5 verified documents, use: --pilot")
        print("To run a dry-run preflight check, use: --pilot --dry-run")
        print("To specify individual documents, use: --files <path1> <path2>")
        sys.exit(0)

    if args.max_docs and args.max_docs > 0:
        target_files = target_files[: args.max_docs]

    print(f"Target Documents to Process: {len(target_files)}")
    print(f"Output Directory            : {config.output_dir.resolve()}")
    print(f"Dry Run Mode                : {args.dry_run}\n")

    if args.dry_run:
        print("=" * 78)
        print("PREFLIGHT DRY-RUN INSPECTION")
        print("=" * 78)
        inspector = PreflightInspector(config)
        total_pages = 0
        total_ocr_candidates = 0
        total_rotated = 0
        total_tables = 0

        for idx, pdf_path in enumerate(target_files, start=1):
            report = inspector.inspect_pdf(pdf_path)
            total_pages += report.page_count
            total_ocr_candidates += report.ocr_candidate_pages_count
            total_rotated += report.rotated_pages_count
            total_tables += report.likely_table_pages_count
            print(f"[{idx}/{len(target_files)}] {report.file_name}: {report.page_count} pages | "
                  f"Reused Inventory: {report.reused_inventory} | Rotated: {report.rotated_pages_count} | "
                  f"OCR Candidates: {report.ocr_candidate_pages_count} | Tables: {report.likely_table_pages_count}")

        print("-" * 78)
        print(f"Total Pages Analyzed    : {total_pages:,}")
        print(f"Total Rotated Pages     : {total_rotated}")
        print(f"Total OCR Candidates    : {total_ocr_candidates}")
        print(f"Total Table Pages       : {total_tables}")
        print("=" * 78)
        print("Dry run completed. No files modified or generated.")
        return

    # Execute extraction
    pipeline = DocumentExtractionPipeline(config)
    successful = 0
    failed = 0

    for idx, pdf_path in enumerate(target_files, start=1):
        print(f"[{idx}/{len(target_files)}] Extracting: {pdf_path.name}")
        try:
            if args.legacy:
                success = extract_pdf_legacy(pdf_path, config.output_dir)
            else:
                doc = pipeline.extract_document(pdf_path)
                success = len(doc.pages) > 0 and len(doc.errors) == 0

            if success:
                successful += 1
                print(f"     Status: SUCCESS (Artifacts saved in {config.output_dir / pdf_path.parent.name / pdf_path.stem})")
            else:
                failed += 1
                print(f"     Status: FAILED")
        except Exception as exc:
            failed += 1
            print(f"     Status: EXCEPTION ({exc})")

    print("\n" + "=" * 78)
    print("EXTRACTION EXECUTION COMPLETE")
    print("=" * 78)
    print(f"Documents Attempted : {len(target_files)}")
    print(f"Successful          : {successful}")
    print(f"Failed              : {failed}")
    print(f"Output Directory    : {config.output_dir.resolve()}")
    print("=" * 78 + "\n")


if __name__ == "__main__":
    main()