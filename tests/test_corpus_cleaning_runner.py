"""Automated tests for the production corpus cleaning runner and checkpoint coordinator."""

import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts.run_corpus_cleaning import (
    discover_cleaning_inventory,
    get_cleaning_batch_slice,
    get_all_cleaning_batches,
    CleaningCheckpointManager,
    CorpusCleaningRunner,
    PILOT_DOCUMENT_IDS,
    BATCH_SIZES,
)


class TestCorpusCleaningRunner(unittest.TestCase):
    """Test suite verifying safe batching, checkpointing, recovery, and guards for corpus cleaning."""

    def setUp(self):
        self.test_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.test_dir.name)
        self.mock_output_dir = self.temp_path / "cleaned_corpus"
        self.mock_output_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.test_dir.cleanup()

    def test_deterministic_batch_assignment(self):
        """Eligible 63 documents are partitioned into exactly 4 deterministic, non-overlapping batches."""
        docs, batches_map = discover_cleaning_inventory()
        self.assertEqual(len(docs), 63, f"Expected 63 eligible documents, found {len(docs)}")

        # Verify batch counts: 16, 16, 16, 15
        self.assertEqual(len(batches_map["1"]), 16)
        self.assertEqual(len(batches_map["2"]), 16)
        self.assertEqual(len(batches_map["3"]), 16)
        self.assertEqual(len(batches_map["4"]), 15)

        # Verify page counts
        b1_pages = sum(d["expected_pages"] for d in batches_map["1"])
        b2_pages = sum(d["expected_pages"] for d in batches_map["2"])
        b3_pages = sum(d["expected_pages"] for d in batches_map["3"])
        b4_pages = sum(d["expected_pages"] for d in batches_map["4"])
        total_pages = b1_pages + b2_pages + b3_pages + b4_pages
        self.assertEqual(total_pages, 3592, f"Expected 3,592 total pages, found {total_pages}")
        self.assertEqual(b1_pages, 871)
        self.assertEqual(b2_pages, 776)
        self.assertEqual(b3_pages, 1339)
        self.assertEqual(b4_pages, 606)

        # Verify batches are pairwise disjoint
        seen_ids = set()
        for b_num in ["1", "2", "3", "4"]:
            for d in batches_map[b_num]:
                did = d["document_id"]
                self.assertNotIn(did, seen_ids, f"Document {did} appears in multiple batches")
                seen_ids.add(did)

        self.assertEqual(len(seen_ids), 63)

        # Invalid batch number raises ValueError
        with self.assertRaises(ValueError):
            get_cleaning_batch_slice(docs, 0)
        with self.assertRaises(ValueError):
            get_cleaning_batch_slice(docs, 5)

    def test_pilot_exclusion_all_10_documents(self):
        """All 10 Stage 2 pilot documents are strictly excluded from the corpus cleaning inventory."""
        docs, batches_map = discover_cleaning_inventory()
        discovered_ids = {d["document_id"] for d in docs}

        for pilot_id in PILOT_DOCUMENT_IDS:
            self.assertNotIn(
                pilot_id,
                discovered_ids,
                f"Pilot document {pilot_id} was NOT excluded from cleaning inventory",
            )
            for b_num, b_docs in batches_map.items():
                b_ids = {d["document_id"] for d in b_docs}
                self.assertNotIn(
                    pilot_id,
                    b_ids,
                    f"Pilot document {pilot_id} found in Batch {b_num}",
                )

    def test_atomic_checkpointing(self):
        """Checkpoint manager writes atomically and accurately updates document states and summaries."""
        mock_docs = [
            {
                "document_id": "test_doc_1",
                "category": "root",
                "batch_number": 1,
                "relative_path": "documents/test_doc_1.pdf",
                "input_dir": str(self.temp_path / "in" / "test_doc_1"),
                "expected_pages": 10,
                "file_size_bytes": 1024,
                "sha256_hash": "dummyhash1",
                "duplicate_of": [],
            },
            {
                "document_id": "test_doc_2",
                "category": "root",
                "batch_number": 1,
                "relative_path": "documents/test_doc_2.pdf",
                "input_dir": str(self.temp_path / "in" / "test_doc_2"),
                "expected_pages": 20,
                "file_size_bytes": 2048,
                "sha256_hash": "dummyhash2",
                "duplicate_of": [],
            },
        ]
        mgr = CleaningCheckpointManager(self.mock_output_dir, mock_docs)
        manifest_file = self.mock_output_dir / "corpus_cleaning_checkpoint.json"
        self.assertTrue(manifest_file.is_file())

        # Verify initial summary
        self.assertEqual(mgr.data["summary"]["pending"], 2)
        self.assertEqual(mgr.data["summary"]["completed"], 0)
        self.assertEqual(mgr.data["summary"]["failed"], 0)
        self.assertEqual(mgr.data["summary"]["in_progress"], 0)

        # Mark in progress
        mgr.mark_in_progress("test_doc_1")
        self.assertEqual(mgr.get_document_status("test_doc_1"), "IN_PROGRESS")
        self.assertEqual(mgr.data["summary"]["in_progress"], 1)
        self.assertEqual(mgr.data["summary"]["pending"], 1)

        # Mark success
        cleaning_summary = {
            "original_char_count": 5000,
            "cleaned_char_count": 4800,
            "delta_chars": -200,
            "total_headers_removed": 10,
            "total_footers_removed": 10,
            "total_hyphens_repaired": 0,
            "total_encoding_transforms": 5,
        }
        mgr.mark_success("test_doc_1", elapsed_seconds=1.23, actual_pages=10, cleaning_summary=cleaning_summary)
        self.assertEqual(mgr.get_document_status("test_doc_1"), "SUCCESS")
        self.assertEqual(mgr.data["summary"]["completed"], 1)
        self.assertEqual(mgr.data["summary"]["in_progress"], 0)

        # Mark failed
        mgr.mark_failed("test_doc_2", error_msg="Simulated syntax error", elapsed_seconds=0.45)
        self.assertEqual(mgr.get_document_status("test_doc_2"), "FAILED")
        self.assertEqual(mgr.data["summary"]["failed"], 1)

        # Reload from disk and verify persistence
        reloaded_mgr = CleaningCheckpointManager(self.mock_output_dir, mock_docs)
        self.assertEqual(reloaded_mgr.get_document_status("test_doc_1"), "SUCCESS")
        self.assertEqual(reloaded_mgr.get_document_status("test_doc_2"), "FAILED")
        self.assertEqual(reloaded_mgr.data["summary"]["completed"], 1)
        self.assertEqual(reloaded_mgr.data["summary"]["failed"], 1)

    def test_success_output_validation(self):
        """validate_cleaned_artifacts enforces presence and integrity of all required files."""
        runner = CorpusCleaningRunner(output_dir=self.mock_output_dir, dry_run=True)
        doc_id = "test_doc_val"
        category = "cryptography_security"
        expected_pages = 3

        doc_dir = self.mock_output_dir / category / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        input_dir = self.temp_path / "mock_in" / doc_id
        input_dir.mkdir(parents=True, exist_ok=True)

        # Missing files -> Fail
        is_val, reason = runner.validate_cleaned_artifacts(doc_id, category, expected_pages, input_dir)
        self.assertFalse(is_val)
        self.assertIn("Missing required artifact", reason)

        # Write valid files
        structured_data = {
            "document_id": doc_id,
            "pages": [{"page_number": i + 1, "cleaned_text": "sample text"} for i in range(expected_pages)],
        }
        with open(doc_dir / f"{doc_id}_structured.json", "w", encoding="utf-8") as f:
            json.dump(structured_data, f)
        (doc_dir / f"{doc_id}.md").write_text("# Test Title\n\nSample markdown", encoding="utf-8")
        (doc_dir / f"{doc_id}.txt").write_text("--- PAGE 1 ---\n\nSample text", encoding="utf-8")
        manifest_data = {
            "document_id": doc_id,
            "category": category,
            "total_pages": expected_pages,
            "cleaning_summary": {"total_headers_removed": 2},
        }
        with open(doc_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest_data, f)

        # Valid files -> Pass
        is_val, reason = runner.validate_cleaned_artifacts(doc_id, category, expected_pages, input_dir)
        self.assertTrue(is_val, f"Validation failed unexpectedly: {reason}")

        # Page count mismatch in JSON -> Fail
        structured_data["pages"].pop()
        with open(doc_dir / f"{doc_id}_structured.json", "w", encoding="utf-8") as f:
            json.dump(structured_data, f)
        is_val, reason = runner.validate_cleaned_artifacts(doc_id, category, expected_pages, input_dir)
        self.assertFalse(is_val)
        self.assertIn("Page count mismatch", reason)

    def test_interrupted_document_recovery(self):
        """Interrupted IN_PROGRESS documents have their partial directories cleaned and status reset to PENDING."""
        doc_id = "test_interrupted_doc"
        category = "risk_management"
        mock_docs = [{
            "document_id": doc_id,
            "category": category,
            "batch_number": 1,
            "relative_path": f"documents/{doc_id}.pdf",
            "input_dir": str(self.temp_path / "in" / doc_id),
            "expected_pages": 5,
        }]

        runner = CorpusCleaningRunner(output_dir=self.mock_output_dir, dry_run=True)
        runner.remaining_docs = mock_docs
        runner.checkpoint_manager = CleaningCheckpointManager(self.mock_output_dir, mock_docs)

        # Mark in progress and create partial directory
        runner.checkpoint_manager.mark_in_progress(doc_id)
        partial_dir = self.mock_output_dir / category / doc_id
        partial_dir.mkdir(parents=True, exist_ok=True)
        (partial_dir / "partial.json").write_text("incomplete content", encoding="utf-8")
        self.assertTrue(partial_dir.is_dir())

        # Recover
        recovered = runner.recover_in_progress_documents()
        self.assertEqual(recovered, [doc_id])
        self.assertFalse(partial_dir.is_dir(), "Partial directory was not removed during recovery")
        self.assertEqual(runner.checkpoint_manager.get_document_status(doc_id), "PENDING")

        # Second recovery call is idempotent
        second_recovered = runner.recover_in_progress_documents()
        self.assertEqual(second_recovered, [])

    def test_failed_document_retry(self):
        """Failed documents are safely reset to PENDING when retry is requested."""
        doc_id = "test_failed_doc"
        category = "threats_malware"
        mock_docs = [{
            "document_id": doc_id,
            "category": category,
            "batch_number": 4,
            "relative_path": f"documents/{doc_id}.pdf",
            "input_dir": str(self.temp_path / "in" / doc_id),
            "expected_pages": 8,
        }]

        runner = CorpusCleaningRunner(output_dir=self.mock_output_dir, dry_run=True, retry_failed=True)
        runner.remaining_docs = mock_docs
        runner.checkpoint_manager = CleaningCheckpointManager(self.mock_output_dir, mock_docs)

        runner.checkpoint_manager.mark_failed(doc_id, "Test failure", 1.0)
        self.assertEqual(runner.checkpoint_manager.get_document_status(doc_id), "FAILED")

        # Recover specific document
        ok = runner.recover_document(doc_id)
        self.assertTrue(ok)
        self.assertEqual(runner.checkpoint_manager.get_document_status(doc_id), "PENDING")

    def test_output_path_containment_security_guard(self):
        """Security guard prevents partial directory cleanup outside output root or at dangerous levels."""
        runner = CorpusCleaningRunner(output_dir=self.mock_output_dir, dry_run=True)

        # Path outside output root
        outside_path = self.temp_path / "outside_dir" / "doc1"
        outside_path.mkdir(parents=True, exist_ok=True)
        with self.assertRaises(ValueError) as ctx:
            runner._clean_partial_directory(outside_path, "doc1")
        self.assertIn("Security violation: attempt to clean path outside output directory", str(ctx.exception))

        # Root output directory itself
        with self.assertRaises(ValueError) as ctx:
            runner._clean_partial_directory(self.mock_output_dir, self.mock_output_dir.name)
        self.assertIn("Security violation: attempt to clean output directory or category level", str(ctx.exception))

        # Category level directory
        cat_dir = self.mock_output_dir / "risk_management"
        cat_dir.mkdir(parents=True, exist_ok=True)
        with self.assertRaises(ValueError) as ctx:
            runner._clean_partial_directory(cat_dir, "risk_management")
        self.assertIn("Security violation: attempt to clean output directory or category level", str(ctx.exception))

        # Basename mismatch
        mismatch_dir = self.mock_output_dir / "risk_management" / "doc_alpha"
        mismatch_dir.mkdir(parents=True, exist_ok=True)
        with self.assertRaises(ValueError) as ctx:
            runner._clean_partial_directory(mismatch_dir, "doc_beta")
        self.assertIn("does not match target doc_id", str(ctx.exception))

    def test_insufficient_disk_space_handling(self):
        """Runner halts safely when available disk space is below required reserve."""
        runner = CorpusCleaningRunner(output_dir=self.mock_output_dir, min_free_disk_mb=500, dry_run=False)

        # Mock disk_usage returning 300 MB free (less than 500 MB reserve)
        with patch("shutil.disk_usage", return_value=(100 * 1024**3, 99 * 1024**3, 300 * 1024**2)):
            has_space, free_mb = runner.check_disk_space(required_mb=0)
            self.assertFalse(has_space)
            self.assertAlmostEqual(free_mb, 300.0, places=1)

            doc_meta = {
                "document_id": "test_space_doc",
                "category": "root",
                "expected_pages": 10,
                "input_dir": str(self.temp_path),
            }
            runner.remaining_docs = [doc_meta]
            runner.checkpoint_manager = CleaningCheckpointManager(self.mock_output_dir, [doc_meta])

            ok = runner.clean_single_document(doc_meta)
            self.assertFalse(ok)
            self.assertEqual(runner.checkpoint_manager.get_document_status("test_space_doc"), "FAILED")
            err = runner.checkpoint_manager.data["documents"]["test_space_doc"]["error"]
            self.assertIn("[DISK GUARD]", err)

    def test_duplicate_source_document_cross_references(self):
        """Duplicate source documents retain mutual cross-references in cleaning inventory."""
        docs, _ = discover_cleaning_inventory()
        doc_61 = next((d for d in docs if d["document_id"] == "NIST_SP_800-61"), None)
        self.assertIsNotNone(doc_61, "NIST_SP_800-61 not found in cleaning inventory")
        self.assertIn(
            "documents/NIST.SP.800-61r3.pdf",
            doc_61["duplicate_of"],
            "Duplicate cross-reference to NIST.SP.800-61r3 missing",
        )

    def test_idempotent_reruns(self):
        """Completed documents with valid artifacts are skipped without re-cleaning."""
        doc_id = "test_completed_doc"
        category = "identity_access"
        expected_pages = 2

        doc_dir = self.mock_output_dir / category / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        input_dir = self.temp_path / "mock_in" / doc_id
        input_dir.mkdir(parents=True, exist_ok=True)

        # Create valid artifacts
        structured_data = {
            "document_id": doc_id,
            "pages": [{"page_number": 1, "cleaned_text": "t1"}, {"page_number": 2, "cleaned_text": "t2"}],
        }
        with open(doc_dir / f"{doc_id}_structured.json", "w", encoding="utf-8") as f:
            json.dump(structured_data, f)
        (doc_dir / f"{doc_id}.md").write_text("# Title\n\nBody", encoding="utf-8")
        (doc_dir / f"{doc_id}.txt").write_text("Body text", encoding="utf-8")
        with open(doc_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump({"document_id": doc_id, "category": category, "total_pages": expected_pages, "cleaning_summary": {}}, f)

        doc_meta = {
            "document_id": doc_id,
            "category": category,
            "expected_pages": expected_pages,
            "input_dir": str(input_dir),
        }

        runner = CorpusCleaningRunner(output_dir=self.mock_output_dir, dry_run=False)
        runner.remaining_docs = [doc_meta]
        runner.checkpoint_manager = CleaningCheckpointManager(self.mock_output_dir, [doc_meta])
        runner.checkpoint_manager.mark_success(doc_id, 0.5, expected_pages, {})

        # Calling clean_single_document should skip and return True immediately
        ok = runner.clean_single_document(doc_meta)
        self.assertTrue(ok)
        self.assertEqual(runner.checkpoint_manager.get_document_status(doc_id), "SUCCESS")

    def test_no_accidental_overwriting_of_valid_outputs(self):
        """Recovery never removes a directory belonging to a document marked SUCCESS with valid artifacts."""
        doc_id = "test_protected_doc"
        category = "cloud_application_security"
        expected_pages = 1

        doc_dir = self.mock_output_dir / category / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        (doc_dir / f"{doc_id}_structured.json").write_text(json.dumps({"pages": [{"cleaned_text": "ok"}]}), encoding="utf-8")
        (doc_dir / f"{doc_id}.md").write_text("# Heading", encoding="utf-8")
        (doc_dir / f"{doc_id}.txt").write_text("Text", encoding="utf-8")
        (doc_dir / "manifest.json").write_text(json.dumps({"document_id": doc_id, "total_pages": 1, "cleaning_summary": {}}), encoding="utf-8")

        mock_docs = [{
            "document_id": doc_id,
            "category": category,
            "batch_number": 1,
            "expected_pages": expected_pages,
            "input_dir": str(self.temp_path),
        }]

        runner = CorpusCleaningRunner(output_dir=self.mock_output_dir, dry_run=True)
        runner.remaining_docs = mock_docs
        runner.checkpoint_manager = CleaningCheckpointManager(self.mock_output_dir, mock_docs)
        runner.checkpoint_manager.mark_success(doc_id, 1.0, expected_pages, {})

        # Running recovery of in-progress documents should not touch this doc
        recovered = runner.recover_in_progress_documents()
        self.assertEqual(recovered, [])
        self.assertTrue(doc_dir.is_dir(), "Valid completed directory was improperly deleted")
        self.assertEqual(runner.checkpoint_manager.get_document_status(doc_id), "SUCCESS")


if __name__ == "__main__":
    unittest.main()
