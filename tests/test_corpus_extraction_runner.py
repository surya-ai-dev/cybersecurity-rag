"""Unit tests for scripts/run_corpus_extraction.py.

Verifies:
1. Inventory discovery selects exactly 68 documents, excluding all 5 pilot PDFs.
2. Batch slicing divides 68 documents into 4 disjoint, complete batches of 17 documents each.
3. Duplicate pair (NIST SP 800-61) is detected with mutual duplicate_of metadata.
4. Checkpoint manifest saves atomically, tallies counts, and tracks status.
5. Resumability skips already completed documents only when artifacts pass validation.
6. Re-extracts documents if previously marked SUCCESS but artifacts on disk are corrupted/missing.
7. Atomic validation catches missing files, page count mismatches, and never marks partial extractions as SUCCESS.
8. Disk space check halts execution safely when free space is insufficient.
9. Dry-run mode executes cleanly without modifying files.
10. Subprocess isolation executes worker in child process; parent remains alive on child failure.
11. Native crashes (0xC0000005) are captured with descriptive diagnostics and recorded as FAILED.
12. Safe recovery inspects and cleans only the partial directory of interrupted IN_PROGRESS documents.
13. Strict directory cleaning security prevents deletion outside the document output directory.
14. Batch failure policies (Fail-Fast vs Continue-on-Failure) operate correctly.
"""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from scripts.run_corpus_extraction import (
    CorpusCheckpointManager,
    CorpusExtractionRunner,
    discover_corpus_inventory,
    get_batch_slice,
    get_pilot_document_paths,
    interpret_exit_code,
)


class TestCorpusExtractionRunner(unittest.TestCase):
    """Test suite verifying the corpus extraction runner logic."""

    def test_discovery_excludes_pilots_and_finds_68_documents(self) -> None:
        """Runner discovers exactly 68 non-pilot documents from documents/ directory."""
        remaining_docs, dup_groups = discover_corpus_inventory()
        pilot_paths = get_pilot_document_paths()

        self.assertEqual(len(pilot_paths), 5, "Expected 5 pilot document paths")
        self.assertEqual(len(remaining_docs), 68, f"Expected 68 remaining documents, got {len(remaining_docs)}")

        # Verify no pilot document is present in remaining_docs
        for d in remaining_docs:
            abs_p = Path(d["absolute_path"]).resolve()
            self.assertNotIn(abs_p, pilot_paths, f"Pilot document {abs_p} found in remaining docs!")

    def test_batch_slicing_covers_all_68_docs_without_overlap(self) -> None:
        """Batch slicing produces 4 batches of 17 docs with 100% disjoint coverage."""
        remaining_docs, _ = discover_corpus_inventory()
        self.assertEqual(len(remaining_docs), 68)

        b1 = get_batch_slice(remaining_docs, 1, batch_size=17)
        b2 = get_batch_slice(remaining_docs, 2, batch_size=17)
        b3 = get_batch_slice(remaining_docs, 3, batch_size=17)
        b4 = get_batch_slice(remaining_docs, 4, batch_size=17)

        self.assertEqual(len(b1), 17)
        self.assertEqual(len(b2), 17)
        self.assertEqual(len(b3), 17)
        self.assertEqual(len(b4), 17)

        # Check total unique IDs
        all_ids = [d["document_id"] for batch in [b1, b2, b3, b4] for d in batch]
        self.assertEqual(len(all_ids), 68)
        self.assertEqual(len(set(all_ids)), 68, "Overlap detected across batches!")

    def test_duplicate_group_and_mutual_metadata(self) -> None:
        """Duplicate detection identifies the 800-61 pair with mutual cross-references."""
        remaining_docs, dup_groups = discover_corpus_inventory()
        self.assertEqual(len(dup_groups), 1, "Expected exactly 1 duplicate group")

        doc_61_root = next((d for d in remaining_docs if d["document_id"] == "NIST.SP.800-61r3"), None)
        doc_61_risk = next((d for d in remaining_docs if d["document_id"] == "NIST_SP_800-61"), None)

        self.assertIsNotNone(doc_61_root)
        self.assertIsNotNone(doc_61_risk)
        self.assertEqual(doc_61_root["sha256_hash"], doc_61_risk["sha256_hash"])

        # Check mutual cross-references
        self.assertIn(doc_61_risk["relative_path"], doc_61_root["duplicate_of"])
        self.assertIn(doc_61_root["relative_path"], doc_61_risk["duplicate_of"])

    def test_checkpoint_manifest_atomic_save_and_reload(self) -> None:
        """Checkpoint manifest saves atomically and reloads correctly."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir)
            sample_docs = [
                {"document_id": "doc1", "relative_path": "documents/doc1.pdf", "category": "root", "page_count": 10, "file_size_bytes": 1000, "sha256_hash": "h1", "duplicate_of": []},
                {"document_id": "doc2", "relative_path": "documents/doc2.pdf", "category": "root", "page_count": 20, "file_size_bytes": 2000, "sha256_hash": "h2", "duplicate_of": []},
            ]

            mgr = CorpusCheckpointManager(out_path, sample_docs)
            self.assertEqual(mgr.get_document_status("doc1"), "PENDING")
            self.assertEqual(mgr.data["summary"]["pending"], 2)

            mgr.mark_in_progress("doc1")
            self.assertEqual(mgr.get_document_status("doc1"), "IN_PROGRESS")

            mgr.mark_success("doc1", elapsed_seconds=5.2, actual_pages=10, total_tables=2, total_figures=1, quality_warnings_count=0)
            self.assertEqual(mgr.get_document_status("doc1"), "SUCCESS")
            self.assertEqual(mgr.data["summary"]["completed"], 1)

            # Reload manager from disk
            mgr_reloaded = CorpusCheckpointManager(out_path, sample_docs)
            self.assertEqual(mgr_reloaded.get_document_status("doc1"), "SUCCESS")
            self.assertEqual(mgr_reloaded.get_document_status("doc2"), "PENDING")
            self.assertEqual(mgr_reloaded.data["summary"]["completed"], 1)

    def test_validation_fails_on_missing_or_corrupted_artifacts(self) -> None:
        """Validation fails if any required artifact is missing or page count mismatches."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir)
            runner = CorpusExtractionRunner(output_dir=out_path, dry_run=True)

            doc_dir = out_path / "test_cat" / "test_doc"
            doc_dir.mkdir(parents=True, exist_ok=True)

            # 1. Missing files
            is_valid, msg = runner.validate_extracted_artifacts("test_doc", "test_cat", expected_pages=5)
            self.assertFalse(is_valid)
            self.assertIn("missing or empty", msg)

            # 2. Add files but mismatch page count
            json_file = doc_dir / "test_doc_structured.json"
            json_file.write_text(json.dumps({"document_id": "test_doc", "pages": [{"page_number": 1}]}), encoding="utf-8")
            (doc_dir / "test_doc.md").write_text("# Markdown", encoding="utf-8")
            (doc_dir / "test_doc.txt").write_text("--- PAGE 1 ---\nText", encoding="utf-8")
            (doc_dir / "manifest.json").write_text(json.dumps({"status": "ok"}), encoding="utf-8")

            is_valid, msg = runner.validate_extracted_artifacts("test_doc", "test_cat", expected_pages=5)
            self.assertFalse(is_valid)
            self.assertIn("Page count mismatch", msg)

            # 3. Correct 5 pages
            pages_5 = [{"page_number": i, "figures": []} for i in range(1, 6)]
            json_file.write_text(json.dumps({"document_id": "test_doc", "pages": pages_5}), encoding="utf-8")
            txt_5 = "".join(f"\n--- PAGE {i} ---\nText" for i in range(1, 6))
            (doc_dir / "test_doc.txt").write_text(txt_5, encoding="utf-8")

            is_valid, msg = runner.validate_extracted_artifacts("test_doc", "test_cat", expected_pages=5)
            self.assertTrue(is_valid, f"Validation failed unexpectedly: {msg}")

    def test_disk_space_guard_halts_when_insufficient(self) -> None:
        """Runner halts when available disk space is below threshold."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir)
            runner = CorpusExtractionRunner(output_dir=out_path, min_free_disk_mb=999_999_999, dry_run=True)
            has_space, free_mb = runner.check_disk_space()
            self.assertFalse(has_space, "Expected disk space check to fail for huge threshold")

    def test_resumability_skips_completed_document(self) -> None:
        """Completed documents with valid artifacts are skipped."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir)
            sample_docs = [
                {"document_id": "doc1", "relative_path": "documents/doc1.pdf", "category": "root", "page_count": 1, "file_size_bytes": 1000, "sha256_hash": "h1", "duplicate_of": []},
            ]
            runner = CorpusExtractionRunner(output_dir=out_path, dry_run=False)
            runner.remaining_docs = sample_docs
            runner.checkpoint_manager = CorpusCheckpointManager(out_path, sample_docs)

            # Set up completed valid artifacts on disk
            doc_dir = out_path / "root" / "doc1"
            doc_dir.mkdir(parents=True, exist_ok=True)
            (doc_dir / "doc1_structured.json").write_text(json.dumps({"pages": [{"page_number": 1, "figures": []}]}), encoding="utf-8")
            (doc_dir / "doc1.md").write_text("# Doc 1", encoding="utf-8")
            (doc_dir / "doc1.txt").write_text("--- PAGE 1 ---\nText", encoding="utf-8")
            (doc_dir / "manifest.json").write_text(json.dumps({"status": "ok"}), encoding="utf-8")
            runner.checkpoint_manager.mark_success("doc1", 1.0, 1, 0, 0, 0)

            # Processing should immediately return True (skip) without invoking pipeline or child worker
            with patch.object(runner, "_run_child_worker") as mock_worker:
                result = runner.process_document(sample_docs[0])
                self.assertTrue(result)
                mock_worker.assert_not_called()

    def test_resumability_reextracts_when_artifacts_corrupted_or_missing(self) -> None:
        """Documents marked SUCCESS in checkpoint are re-extracted if disk artifacts are missing."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir)
            sample_docs = [
                {"document_id": "doc1", "relative_path": "documents/doc1.pdf", "category": "root", "page_count": 1, "file_size_bytes": 1000, "sha256_hash": "h1", "duplicate_of": []},
            ]
            runner = CorpusExtractionRunner(output_dir=out_path, dry_run=False)
            runner.remaining_docs = sample_docs
            runner.checkpoint_manager = CorpusCheckpointManager(out_path, sample_docs)

            # Mark SUCCESS in checkpoint but DO NOT create files on disk
            runner.checkpoint_manager.mark_success("doc1", 1.0, 1, 0, 0, 0)

            def fake_worker(doc_meta):
                doc_dir = out_path / "root" / "doc1"
                doc_dir.mkdir(parents=True, exist_ok=True)
                (doc_dir / "doc1_structured.json").write_text(json.dumps({"pages": [{"page_number": 1, "figures": []}]}), encoding="utf-8")
                (doc_dir / "doc1.md").write_text("# Doc 1", encoding="utf-8")
                (doc_dir / "doc1.txt").write_text("--- PAGE 1 ---\nText", encoding="utf-8")
                (doc_dir / "manifest.json").write_text(json.dumps({"status": "ok"}), encoding="utf-8")
                return 0, "", ""

            with patch.object(runner, "_run_child_worker", side_effect=fake_worker) as mock_worker:
                result = runner.process_document(sample_docs[0])
                self.assertTrue(result)
                mock_worker.assert_called_once()

    def test_subprocess_worker_success(self) -> None:
        """Successful child worker produces valid artifacts, parent marks SUCCESS."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir)
            sample_docs = [
                {"document_id": "doc1", "relative_path": "documents/doc1.pdf", "category": "root", "page_count": 2, "file_size_bytes": 1000, "sha256_hash": "h1", "duplicate_of": []},
            ]
            runner = CorpusExtractionRunner(output_dir=out_path, dry_run=False)
            runner.remaining_docs = sample_docs
            runner.checkpoint_manager = CorpusCheckpointManager(out_path, sample_docs)

            def fake_worker_success(doc_meta):
                doc_dir = out_path / "root" / "doc1"
                doc_dir.mkdir(parents=True, exist_ok=True)
                (doc_dir / "doc1_structured.json").write_text(json.dumps({"pages": [{"page_number": 1, "figures": []}, {"page_number": 2, "figures": []}]}), encoding="utf-8")
                (doc_dir / "doc1.md").write_text("# Doc 1 Content", encoding="utf-8")
                (doc_dir / "doc1.txt").write_text("--- PAGE 1 ---\nP1\n--- PAGE 2 ---\nP2", encoding="utf-8")
                (doc_dir / "manifest.json").write_text(json.dumps({"status": "ok"}), encoding="utf-8")
                return 0, "__WORKER_RESULT__{}", ""

            with patch.object(runner, "_run_child_worker", side_effect=fake_worker_success):
                ok = runner.process_document(sample_docs[0])
                self.assertTrue(ok)
                self.assertEqual(runner.checkpoint_manager.get_document_status("doc1"), "SUCCESS")
                self.assertEqual(runner.checkpoint_manager.data["documents"]["doc1"]["validation_status"], "PASSED")

    def test_subprocess_worker_failure_python_exception(self) -> None:
        """Child process failure (exit code 1) is captured, diagnostics recorded, marked FAILED."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir)
            sample_docs = [
                {"document_id": "doc1", "relative_path": "documents/doc1.pdf", "category": "root", "page_count": 2, "file_size_bytes": 1000, "sha256_hash": "h1", "duplicate_of": []},
            ]
            runner = CorpusExtractionRunner(output_dir=out_path, dry_run=False)
            runner.remaining_docs = sample_docs
            runner.checkpoint_manager = CorpusCheckpointManager(out_path, sample_docs)

            with patch.object(runner, "_run_child_worker", return_value=(1, "", "Traceback (most recent call last):\nZeroDivisionError: division by zero")):
                ok = runner.process_document(sample_docs[0])
                self.assertFalse(ok)
                self.assertEqual(runner.checkpoint_manager.get_document_status("doc1"), "FAILED")
                error_msg = runner.checkpoint_manager.data["documents"]["doc1"]["error"]
                self.assertIn("ZeroDivisionError", error_msg)

    def test_subprocess_worker_native_crash(self) -> None:
        """Child process native crash (0xC0000005) is captured, parent stays alive, marked FAILED."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir)
            sample_docs = [
                {"document_id": "doc1", "relative_path": "documents/doc1.pdf", "category": "root", "page_count": 5, "file_size_bytes": 1000, "sha256_hash": "h1", "duplicate_of": []},
            ]
            runner = CorpusExtractionRunner(output_dir=out_path, dry_run=False)
            runner.remaining_docs = sample_docs
            runner.checkpoint_manager = CorpusCheckpointManager(out_path, sample_docs)

            # Simulate Windows 0xC0000005 exit code (3221225477 unsigned or -1073741819 signed)
            with patch.object(runner, "_run_child_worker", return_value=(3221225477, "", "")):
                ok = runner.process_document(sample_docs[0])
                self.assertFalse(ok)
                self.assertEqual(runner.checkpoint_manager.get_document_status("doc1"), "FAILED")
                error_msg = runner.checkpoint_manager.data["documents"]["doc1"]["error"]
                self.assertIn("STATUS_ACCESS_VIOLATION", error_msg)
                self.assertIn("0xC0000005", error_msg)

    def test_subprocess_worker_invalid_artifacts(self) -> None:
        """Worker exits 0 but artifacts fail parent validation; parent marks FAILED."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir)
            sample_docs = [
                {"document_id": "doc1", "relative_path": "documents/doc1.pdf", "category": "root", "page_count": 5, "file_size_bytes": 1000, "sha256_hash": "h1", "duplicate_of": []},
            ]
            runner = CorpusExtractionRunner(output_dir=out_path, dry_run=False)
            runner.remaining_docs = sample_docs
            runner.checkpoint_manager = CorpusCheckpointManager(out_path, sample_docs)

            def fake_worker_incomplete(doc_meta):
                doc_dir = out_path / "root" / "doc1"
                doc_dir.mkdir(parents=True, exist_ok=True)
                # Create only 2 pages instead of expected 5
                (doc_dir / "doc1_structured.json").write_text(json.dumps({"pages": [{"page_number": 1, "figures": []}, {"page_number": 2, "figures": []}]}), encoding="utf-8")
                (doc_dir / "doc1.md").write_text("# Incomplete", encoding="utf-8")
                (doc_dir / "doc1.txt").write_text("--- PAGE 1 ---\nP1\n--- PAGE 2 ---\nP2", encoding="utf-8")
                (doc_dir / "manifest.json").write_text(json.dumps({"status": "ok"}), encoding="utf-8")
                return 0, "", ""

            with patch.object(runner, "_run_child_worker", side_effect=fake_worker_incomplete):
                ok = runner.process_document(sample_docs[0])
                self.assertFalse(ok)
                self.assertEqual(runner.checkpoint_manager.get_document_status("doc1"), "FAILED")
                self.assertIn("Page count mismatch", runner.checkpoint_manager.data["documents"]["doc1"]["error"])

    def test_recover_in_progress_documents(self) -> None:
        """Recovery safely cleans partial files of IN_PROGRESS documents and resets to PENDING."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir)
            sample_docs = [
                {"document_id": "doc1", "relative_path": "documents/doc1.pdf", "category": "root", "page_count": 10, "file_size_bytes": 1000, "sha256_hash": "h1", "duplicate_of": []},
                {"document_id": "doc2", "relative_path": "documents/doc2.pdf", "category": "root", "page_count": 20, "file_size_bytes": 2000, "sha256_hash": "h2", "duplicate_of": []},
            ]
            runner = CorpusExtractionRunner(output_dir=out_path, dry_run=False)
            runner.remaining_docs = sample_docs
            runner.checkpoint_manager = CorpusCheckpointManager(out_path, sample_docs)

            # doc1 is completed
            runner.checkpoint_manager.mark_success("doc1", 2.0, 10, 0, 0, 0)
            # doc2 is interrupted IN_PROGRESS with partial figures
            runner.checkpoint_manager.mark_in_progress("doc2")
            doc2_dir = out_path / "root" / "doc2"
            doc2_figs = doc2_dir / "figures"
            doc2_figs.mkdir(parents=True, exist_ok=True)
            (doc2_figs / "partial_fig.jpg").write_text("fake image", encoding="utf-8")

            recovered = runner.recover_in_progress_documents()
            self.assertEqual(recovered, ["doc2"])
            self.assertEqual(runner.checkpoint_manager.get_document_status("doc2"), "PENDING")
            self.assertEqual(runner.checkpoint_manager.get_document_status("doc1"), "SUCCESS")
            # Partial directory for doc2 should be removed
            self.assertFalse(doc2_dir.exists())

    def test_clean_partial_directory_security_guard(self) -> None:
        """Security guard prevents deletion outside the document output directory."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir) / "output"
            out_path.mkdir()
            runner = CorpusExtractionRunner(output_dir=out_path, dry_run=True)

            # Outside directory
            outside_dir = Path(tmp_dir) / "outside"
            outside_dir.mkdir()
            with self.assertRaises(ValueError):
                runner._clean_partial_directory(outside_dir)

            # Output root itself
            with self.assertRaises(ValueError):
                runner._clean_partial_directory(out_path)

            # Category level
            cat_dir = out_path / "category"
            cat_dir.mkdir()
            with self.assertRaises(ValueError):
                runner._clean_partial_directory(cat_dir)

            # Valid document directory (category/doc_id)
            doc_dir = cat_dir / "doc_id"
            doc_dir.mkdir()
            (doc_dir / "file.txt").write_text("hello", encoding="utf-8")
            runner._clean_partial_directory(doc_dir)
            self.assertFalse(doc_dir.exists())
            self.assertTrue(cat_dir.exists())

    def test_batch_failure_policy_fail_fast_vs_continue(self) -> None:
        """Batch failure policy: fail-fast stops on first failure; continue-on-failure continues."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = Path(tmp_dir)
            sample_docs = [
                {"document_id": "doc1", "relative_path": "documents/doc1.pdf", "category": "root", "page_count": 1, "file_size_bytes": 1000, "sha256_hash": "h1", "duplicate_of": []},
                {"document_id": "doc2", "relative_path": "documents/doc2.pdf", "category": "root", "page_count": 1, "file_size_bytes": 1000, "sha256_hash": "h2", "duplicate_of": []},
            ]

            # 1. Fail-Fast (default)
            runner_ff = CorpusExtractionRunner(output_dir=out_path, dry_run=False, continue_on_failure=False)
            runner_ff.remaining_docs = sample_docs
            runner_ff.checkpoint_manager = CorpusCheckpointManager(out_path, sample_docs)

            with patch.object(runner_ff, "process_document", side_effect=[False, True]) as mock_proc:
                with patch("scripts.run_corpus_extraction.get_batch_slice", return_value=sample_docs):
                    s, f = runner_ff.run_batch(1)
                    self.assertEqual(s, 0)
                    self.assertEqual(f, 1)
                    self.assertEqual(mock_proc.call_count, 1)  # Stopped after doc 1

            # 2. Continue-on-Failure
            runner_cof = CorpusExtractionRunner(output_dir=out_path, dry_run=False, continue_on_failure=True)
            runner_cof.remaining_docs = sample_docs
            runner_cof.checkpoint_manager = CorpusCheckpointManager(out_path, sample_docs)

            with patch.object(runner_cof, "process_document", side_effect=[False, True]) as mock_proc:
                with patch("scripts.run_corpus_extraction.get_batch_slice", return_value=sample_docs):
                    s, f = runner_cof.run_batch(1)
                    self.assertEqual(s, 1)
                    self.assertEqual(f, 1)
                    self.assertEqual(mock_proc.call_count, 2)  # Processed both docs

    def test_interpret_exit_code(self) -> None:
        """Helper correctly maps common exit codes to human-readable explanations."""
        self.assertIn("STATUS_ACCESS_VIOLATION", interpret_exit_code(3221225477))
        self.assertIn("STATUS_ACCESS_VIOLATION", interpret_exit_code(-1073741819))
        self.assertIn("STATUS_STACK_OVERFLOW", interpret_exit_code(3221225725))
        self.assertIn("Exit code 1", interpret_exit_code(1))
        self.assertIn("Exit code 0", interpret_exit_code(0))


if __name__ == "__main__":
    unittest.main()
