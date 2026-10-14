"""Comprehensive unit and integration test suite for structure-aware chunking pipeline."""

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from app.ingestion.chunking.config import ChunkingConfig
from app.ingestion.chunking.figure_chunker import FigureChunker
from app.ingestion.chunking.models import ChunkRecord, FigureChunkMetadata, TableChunkMetadata
from app.ingestion.chunking.pipeline import DocumentChunkingPipeline
from app.ingestion.chunking.runner import CorpusChunkingRunner
from app.ingestion.chunking.table_chunker import TableChunker
from app.ingestion.chunking.text_chunker import StructureAwareTextChunker
from app.ingestion.chunking.tokenizer import (
    CharEstimatorAdapter,
    TiktokenAdapter,
    TokenizerAdapter,
    get_tokenizer_adapter,
)


class TestChunkingPipeline(unittest.TestCase):
    """Test suite validating all 19 structure-aware chunking requirements."""

    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp(prefix="test_chunking_"))
        # Use tiktoken adapter for fast, deterministic unit test token budgeting
        self.config = ChunkingConfig(
            tokenizer_backend="tiktoken",
            target_chunk_tokens=100,
            max_chunk_tokens=150,
            chunk_overlap_tokens=20,
            min_chunk_tokens=30,
            max_table_tokens=120,
            output_dir=self.tmp_dir / "chunks_out",
        )
        self.tokenizer = get_tokenizer_adapter(self.config)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. Stable chunk IDs and deterministic output
    # -------------------------------------------------------------------------
    def test_deterministic_chunk_ids(self):
        text_chunker = StructureAwareTextChunker(self.config, self.tokenizer)
        sample_pages = [{
            "page_number": 1,
            "citation_label": "[TEST Page 1]",
            "cleaned_text": "### 1. Introduction\n\nThis is paragraph one.\n\nThis is paragraph two.",
            "cleaning_metadata": {},
        }]

        run1 = text_chunker.chunk_document_text("TEST_DOC", "test_cat", "test.pdf", sample_pages)
        run2 = text_chunker.chunk_document_text("TEST_DOC", "test_cat", "test.pdf", sample_pages)

        self.assertEqual(len(run1), len(run2))
        for c1, c2 in zip(run1, run2):
            self.assertEqual(c1.chunk_id, c2.chunk_id)
            self.assertEqual(c1.content_hash, c2.content_hash)
            self.assertEqual(c1.text, c2.text)

    # -------------------------------------------------------------------------
    # 2. Heading and section preservation
    # -------------------------------------------------------------------------
    def test_heading_and_section_preservation(self):
        text_chunker = StructureAwareTextChunker(self.config, self.tokenizer)
        sample_pages = [{
            "page_number": 5,
            "citation_label": "[TEST Page 5]",
            "cleaned_text": "### AC-2 ACCOUNT MANAGEMENT\n\nThe organization manages information system accounts.",
            "cleaning_metadata": {},
        }]

        chunks = text_chunker.chunk_document_text("TEST_DOC", "test_cat", "test.pdf", sample_pages)
        self.assertGreaterEqual(len(chunks), 1)
        chunk = chunks[0]
        self.assertEqual(chunk.section_heading, "AC-2 ACCOUNT MANAGEMENT")
        self.assertIn("### AC-2 ACCOUNT MANAGEMENT", chunk.text)
        self.assertIn("The organization manages information system accounts.", chunk.text)

    # -------------------------------------------------------------------------
    # 3. Paragraph-aware splitting and recursive fallback
    # -------------------------------------------------------------------------
    def test_paragraph_splitting_and_recursive_fallback(self):
        # Configure tight max limit to force recursive sentence splitting
        tight_config = ChunkingConfig(
            tokenizer_backend="tiktoken",
            target_chunk_tokens=30,
            max_chunk_tokens=40,
            chunk_overlap_tokens=10,
        )
        tight_tokenizer = get_tokenizer_adapter(tight_config)
        chunker = StructureAwareTextChunker(tight_config, tight_tokenizer)

        long_paragraph = (
            "Sentence one discusses access control policies in federal environments. "
            "Sentence two discusses identification and authentication credentials. "
            "Sentence three elaborates on audit logging and monitoring requirements. "
            "Sentence four concludes the section with incident handling guidelines. "
            "Sentence five outlines configuration management and baseline verification. "
            "Sentence six establishes contingency planning and disaster recovery protocols."
        )
        sample_pages = [{
            "page_number": 1,
            "citation_label": "[TEST Page 1]",
            "cleaned_text": f"### 1. General\n\n{long_paragraph}",
            "cleaning_metadata": {},
        }]

        chunks = chunker.chunk_document_text("TEST_DOC", "test_cat", "test.pdf", sample_pages)
        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertLessEqual(c.token_count, tight_config.max_chunk_tokens)

    # -------------------------------------------------------------------------
    # 4. Token counts using configured tokenizer
    # -------------------------------------------------------------------------
    def test_token_counts_match_tokenizer(self):
        text = "NIST SP 800-53 Rev. 5 Security and Privacy Controls for Information Systems."
        tok_count = self.tokenizer.count_tokens(text)
        self.assertGreater(tok_count, 0)
        self.assertEqual(tok_count, len(self.tokenizer.tokenize(text)))

    # -------------------------------------------------------------------------
    # 5. Enforcement of chunk budget for ordinary text chunks
    # -------------------------------------------------------------------------
    def test_ordinary_text_budget_enforcement(self):
        chunker = StructureAwareTextChunker(self.config, self.tokenizer)
        paragraphs = ["Paragraph number %d with some descriptive cybersecurity text." % i for i in range(25)]
        sample_pages = [{
            "page_number": 2,
            "citation_label": "[TEST Page 2]",
            "cleaned_text": "### 2. Policies\n\n" + "\n\n".join(paragraphs),
            "cleaning_metadata": {},
        }]

        chunks = chunker.chunk_document_text("TEST_DOC", "test_cat", "test.pdf", sample_pages)
        for c in chunks:
            self.assertLessEqual(c.token_count, self.config.max_chunk_tokens)

    # -------------------------------------------------------------------------
    # 6. Overlap limited to related text within the same section
    # -------------------------------------------------------------------------
    def test_overlap_isolated_to_same_section(self):
        chunker = StructureAwareTextChunker(self.config, self.tokenizer)
        sec1_paras = ["Sec1 Para %d with detailed information regarding cryptographic key management." % i for i in range(8)]
        sec2_paras = ["Sec2 Para %d with risk management metrics and assessments." % i for i in range(8)]

        sample_pages = [
            {
                "page_number": 1,
                "citation_label": "[TEST Page 1]",
                "cleaned_text": "### Section 1. Crypto\n\n" + "\n\n".join(sec1_paras),
                "cleaning_metadata": {},
            },
            {
                "page_number": 2,
                "citation_label": "[TEST Page 2]",
                "cleaned_text": "### Section 2. Risk\n\n" + "\n\n".join(sec2_paras),
                "cleaning_metadata": {},
            },
        ]

        chunks = chunker.chunk_document_text("TEST_DOC", "test_cat", "test.pdf", sample_pages)
        sec2_chunks = [c for c in chunks if c.section_heading == "Section 2. Risk"]
        self.assertGreater(len(sec2_chunks), 0)
        # Verify first chunk of Section 2 does NOT inherit text from Section 1
        first_sec2_chunk = sec2_chunks[0]
        self.assertNotIn("cryptographic key management", first_sec2_chunk.text.lower())

    # -------------------------------------------------------------------------
    # 7. Complete preservation of table rows and cells
    # -------------------------------------------------------------------------
    def test_table_rows_and_cells_preservation(self):
        table_chunker = TableChunker(self.config, self.tokenizer)
        headers = ["ID", "Control Name", "Baseline"]
        rows = [
            ["AC-1", "Policy and Procedures", "LOW"],
            ["AC-2", "Account Management", "MODERATE"],
            ["AC-3", "Access Enforcement", "HIGH"],
        ]
        sample_pages = [{
            "page_number": 10,
            "citation_label": "[TEST Page 10]",
            "tables": [{
                "table_id": "tbl_p10_1",
                "headers": headers,
                "rows": rows,
                "caption": "Table 10-1: Access Controls",
                "bbox": {"left": 50.0, "top": 100.0, "right": 500.0, "bottom": 300.0},
            }],
        }]

        chunks = table_chunker.chunk_document_tables("TEST_DOC", "test_cat", "test.pdf", sample_pages)
        self.assertEqual(len(chunks), 1)
        chunk = chunks[0]
        self.assertIn("AC-1", chunk.text)
        self.assertIn("Account Management", chunk.text)
        self.assertIn("HIGH", chunk.text)
        self.assertEqual(chunk.table_metadata["rows_count"], 3)
        self.assertEqual(chunk.table_metadata["cols_count"], 3)

    # -------------------------------------------------------------------------
    # 8. Repeated table headers and titles in row-split chunks
    # -------------------------------------------------------------------------
    def test_repeated_headers_in_oversized_table(self):
        tight_config = ChunkingConfig(
            tokenizer_backend="tiktoken",
            max_table_tokens=50,  # Force row split
            table_split_by_rows=True,
        )
        tight_tok = get_tokenizer_adapter(tight_config)
        table_chunker = TableChunker(tight_config, tight_tok)

        headers = ["ParamSet", "Oid", "Value"]
        rows = [["Set_%d" % i, "0x000%d" % i, "Cryptographic_Constant_Value_%d" % i] for i in range(12)]
        sample_pages = [{
            "page_number": 20,
            "citation_label": "[TEST Page 20]",
            "tables": [{
                "table_id": "tbl_p20_1",
                "headers": headers,
                "rows": rows,
                "caption": "Table 4: Parameter Sets",
                "bbox": None,
            }],
        }]

        chunks = table_chunker.chunk_document_tables("TEST_DOC", "test_cat", "test.pdf", sample_pages)
        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertIn("| ParamSet | Oid | Value |", c.text)
            self.assertIn("Table 4: Parameter Sets", c.text)
            self.assertIn("(Part", c.text)

    # -------------------------------------------------------------------------
    # 9. Oversized single-row handling
    # -------------------------------------------------------------------------
    def test_oversized_single_row_handling(self):
        tight_config = ChunkingConfig(
            tokenizer_backend="tiktoken",
            max_table_tokens=30,  # Too small for full row
            table_split_by_rows=True,
        )
        tight_tok = get_tokenizer_adapter(tight_config)
        table_chunker = TableChunker(tight_config, tight_tok)

        headers = ["Level", "Activities"]
        massive_cell = "Executive stakeholders define enterprise risk governance " * 15
        rows = [["Level 1", massive_cell]]

        sample_pages = [{
            "page_number": 39,
            "citation_label": "[TEST Page 39]",
            "tables": [{
                "table_id": "tbl_p39_1",
                "headers": headers,
                "rows": rows,
                "caption": "Table 3: Monolithic Cell",
            }],
        }]

        chunks = table_chunker.chunk_document_tables("TEST_DOC", "test_cat", "test.pdf", sample_pages)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertIn("Executive stakeholders", chunks[0].text)
        self.assertIn("Level 1", chunks[0].text)
        self.assertIn("Level 1", chunks[1].text)
        self.assertEqual(chunks[0].table_metadata["parent_table_id"], "tbl_p39_1")

    # -------------------------------------------------------------------------
    # 10. Multi-page table continuation linking and false-link prevention
    # -------------------------------------------------------------------------
    def test_multipage_table_continuation_linking(self):
        table_chunker = TableChunker(self.config, self.tokenizer)
        headers = ["Levels", "Activities"]

        sample_pages = [
            {
                "page_number": 39,
                "citation_label": "[TEST Page 39]",
                "tables": [{
                    "table_id": "tbl_p39_1",
                    "headers": headers,
                    "rows": [["Level 1", "Strategic activities"]],
                    "caption": "Table 3: Generic C-SCRM Activities",
                    "bbox": {"top": 100.0},
                }],
            },
            {
                "page_number": 40,
                "citation_label": "[TEST Page 40]",
                "tables": [{
                    "table_id": "tbl_p40_1",
                    "headers": headers,
                    "rows": [["Level 3", "Operational activities"]],
                    "caption": "",  # Missing caption on continuation page
                    "bbox": {"top": 80.0},
                }],
            },
        ]

        chunks = table_chunker.chunk_document_tables("TEST_DOC", "test_cat", "test.pdf", sample_pages)
        self.assertEqual(len(chunks), 2)
        c1, c2 = chunks[0], chunks[1]

        self.assertFalse(c1.table_metadata["is_continuation"])
        self.assertTrue(c2.table_metadata["is_continuation"])
        self.assertEqual(c2.table_metadata["continuation_of_table_id"], "tbl_p39_1")
        self.assertEqual(c2.table_metadata["parent_table_id"], "tbl_p39_1")
        self.assertEqual(c2.table_metadata["caption"], "Table 3: Generic C-SCRM Activities")

    def test_false_link_prevention_on_non_consecutive_pages(self):
        table_chunker = TableChunker(self.config, self.tokenizer)
        headers = ["Levels", "Activities"]

        sample_pages = [
            {
                "page_number": 10,
                "citation_label": "[TEST Page 10]",
                "tables": [{"table_id": "tbl_p10_1", "headers": headers, "rows": [["A", "B"]], "caption": "Table 1"}],
            },
            {
                "page_number": 15,  # Non-consecutive!
                "citation_label": "[TEST Page 15]",
                "tables": [{"table_id": "tbl_p15_1", "headers": headers, "rows": [["C", "D"]], "caption": "Table 2"}],
            },
        ]

        chunks = table_chunker.chunk_document_tables("TEST_DOC", "test_cat", "test.pdf", sample_pages)
        self.assertEqual(len(chunks), 2)
        self.assertFalse(chunks[0].table_metadata["is_continuation"])
        self.assertFalse(chunks[1].table_metadata["is_continuation"])

    # -------------------------------------------------------------------------
    # 11. Figure path validation and metadata preservation
    # -------------------------------------------------------------------------
    def test_figure_metadata_and_path_validation(self):
        # Create a mock image asset on disk
        doc_dir = self.tmp_dir / "mock_doc"
        fig_dir = doc_dir / "figures"
        fig_dir.mkdir(parents=True, exist_ok=True)
        img_file = fig_dir / "figure_p40_1.png"
        img_file.write_bytes(b"\x89PNG\r\n\x1a\n...")

        fig_chunker = FigureChunker(self.config, self.tokenizer)
        sample_pages = [{
            "page_number": 40,
            "citation_label": "[TEST Page 40]",
            "cleaned_text": "**Fig. 7. C-SCRM Flowchart**\n\nFigure 7 illustrates multi-tier risk flows.",
            "figures": [{
                "figure_id": "fig_p40_1",
                "image_path": "figures/figure_p40_1.png",
                "caption": "Embedded image (xref 123)",
                "width": 800,
                "height": 600,
                "bbox": {"left": 100.0, "top": 200.0, "right": 500.0, "bottom": 600.0},
            }],
        }]

        chunks, errors = fig_chunker.chunk_document_figures("TEST_DOC", "test_cat", "test.pdf", sample_pages, doc_dir)
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(chunks), 1)
        chunk = chunks[0]
        self.assertEqual(chunk.content_type, "figure")
        self.assertEqual(chunk.figure_metadata["caption"], "Fig. 7. C-SCRM Flowchart")
        self.assertTrue(chunk.figure_metadata["caption_linked"])
        self.assertIn("figures/figure_p40_1.png", chunk.text)
        self.assertIn("Figure 7 illustrates multi-tier risk flows", chunk.figure_metadata["surrounding_context"])

    # -------------------------------------------------------------------------
    # 12. Missing captions and missing figure assets
    # -------------------------------------------------------------------------
    def test_missing_figure_asset_detection(self):
        doc_dir = self.tmp_dir / "mock_doc_no_asset"
        doc_dir.mkdir(parents=True, exist_ok=True)

        fig_chunker = FigureChunker(self.config, self.tokenizer)
        sample_pages = [{
            "page_number": 5,
            "citation_label": "[TEST Page 5]",
            "cleaned_text": "Narrative with no figures.",
            "figures": [{
                "figure_id": "fig_p5_1",
                "image_path": "figures/non_existent.png",
                "caption": "",
            }],
        }]

        chunks, errors = fig_chunker.chunk_document_figures("TEST_DOC", "test_cat", "test.pdf", sample_pages, doc_dir)
        self.assertEqual(len(errors), 1)
        self.assertIn("non_existent.png", errors[0])
        self.assertTrue(chunks[0].has_encoding_warning)

    # -------------------------------------------------------------------------
    # 13. Ambiguous-character preservation and warning metadata
    # -------------------------------------------------------------------------
    def test_ambiguous_character_preservation(self):
        chunker = StructureAwareTextChunker(self.config, self.tokenizer)
        sample_pages = [{
            "page_number": 15,
            "citation_label": "[TEST Page 15]",
            "cleaned_text": "Elliptic curve formula: | #E(Fp) - (p + 1) | \ufffd 2\u221ap satisfies bounds.",
            "cleaning_metadata": {"encoding_warnings": ["Preserved \\ufffd in formula"]},
        }]

        chunks = chunker.chunk_document_text("TEST_DOC", "test_cat", "test.pdf", sample_pages)
        self.assertEqual(len(chunks), 1)
        chunk = chunks[0]
        self.assertIn("\ufffd", chunk.text)
        self.assertTrue(chunk.has_encoding_warning)
        self.assertIn("Preserved \\ufffd in formula", chunk.encoding_warnings)

    # -------------------------------------------------------------------------
    # 14. Preservation of CVEs, NIST control IDs, URLs, hexadecimal values
    # -------------------------------------------------------------------------
    def test_security_tokens_preservation(self):
        chunker = StructureAwareTextChunker(self.config, self.tokenizer)
        technical_text = (
            "Vulnerability CVE-2021-44228 impacts Log4j. "
            "See NIST control AC-2(1) and IA-5(2). "
            "Address constant 0x00000001 and curve param q = 2^256 - 2^224 + 1. "
            "Visit https://csrc.nist.gov/publications for details."
        )
        sample_pages = [{
            "page_number": 1,
            "citation_label": "[TEST Page 1]",
            "cleaned_text": f"### Security Notice\n\n{technical_text}",
            "cleaning_metadata": {},
        }]

        chunks = chunker.chunk_document_text("TEST_DOC", "test_cat", "test.pdf", sample_pages)
        chunk_text = chunks[0].text
        self.assertIn("CVE-2021-44228", chunk_text)
        self.assertIn("AC-2(1)", chunk_text)
        self.assertIn("IA-5(2)", chunk_text)
        self.assertIn("0x00000001", chunk_text)
        self.assertIn("q = 2^256 - 2^224 + 1", chunk_text)
        self.assertIn("https://csrc.nist.gov/publications", chunk_text)

    # -------------------------------------------------------------------------
    # 15. Valid JSONL and manifest output
    # -------------------------------------------------------------------------
    def test_atomic_jsonl_and_manifest_generation(self):
        doc_dir = self.tmp_dir / "input_cohort" / "crypto" / "DOC_01"
        doc_dir.mkdir(parents=True, exist_ok=True)
        structured_json = doc_dir / "DOC_01_structured.json"
        structured_json.write_text(
            json.dumps({
                "document_id": "DOC_01",
                "category": "crypto",
                "file_path": "documents/crypto/DOC_01.pdf",
                "pages": [{
                    "page_number": 1,
                    "citation_label": "[DOC_01 Page 1]",
                    "cleaned_text": "### 1. Title\n\nSubstantive content paragraph.",
                    "tables": [],
                    "figures": [],
                }],
            }),
            encoding="utf-8",
        )

        out_dir = self.tmp_dir / "output_cohort"
        config = ChunkingConfig(
            tokenizer_backend="tiktoken",
            input_dir=self.tmp_dir / "input_cohort",
            output_dir=out_dir,
        )
        runner = CorpusChunkingRunner(config)
        report = runner.run_pilot()

        self.assertEqual(report.total_documents, 1)
        self.assertEqual(report.total_chunks, 1)

        jsonl_file = out_dir / "crypto" / "DOC_01_chunks.jsonl"
        self.assertTrue(jsonl_file.exists())
        lines = jsonl_file.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(record["document_id"], "DOC_01")

        manifest_file = out_dir / "chunks_manifest.json"
        self.assertTrue(manifest_file.exists())
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        self.assertEqual(manifest["total_documents"], 1)

    # -------------------------------------------------------------------------
    # 16. No collisions with existing output
    # -------------------------------------------------------------------------
    def test_no_overwrite_conflict_guard(self):
        out_dir = self.tmp_dir / "existing_cohort"
        existing_doc_dir = out_dir / "cat"
        existing_doc_dir.mkdir(parents=True, exist_ok=True)
        (existing_doc_dir / "old_doc_chunks.jsonl").write_text("{}", encoding="utf-8")

        in_dir = self.tmp_dir / "in_cohort"
        in_dir.mkdir(parents=True, exist_ok=True)

        config = ChunkingConfig(
            tokenizer_backend="tiktoken",
            input_dir=in_dir,
            output_dir=out_dir,
            dry_run=False,
        )
        runner = CorpusChunkingRunner(config)
        with self.assertRaises(RuntimeError) as ctx:
            runner.run_pilot()
        self.assertIn("already contains", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 17. Safe failure when disk space is insufficient
    # -------------------------------------------------------------------------
    def test_disk_space_guard_abort(self):
        config = ChunkingConfig(
            tokenizer_backend="tiktoken",
            min_free_disk_mb=999999999.0,  # Unattainable reserve
            input_dir=self.tmp_dir,
            output_dir=self.tmp_dir / "out",
        )
        runner = CorpusChunkingRunner(config)
        with self.assertRaises(RuntimeError) as ctx:
            runner.run_pilot()
        self.assertIn("below mandatory reserve", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 18. Correct handling of duplicate-document metadata
    # -------------------------------------------------------------------------
    def test_duplicate_document_metadata_handling(self):
        pipeline = DocumentChunkingPipeline(self.config, self.tokenizer)
        doc_dir = self.tmp_dir / "cohort" / "root" / "NIST.SP.800-61r3"
        doc_dir.mkdir(parents=True, exist_ok=True)
        (doc_dir / "NIST.SP.800-61r3_structured.json").write_text(
            json.dumps({
                "document_id": "NIST.SP.800-61r3",
                "category": "root",
                "pages": [{
                    "page_number": 1,
                    "citation_label": "[NIST.SP.800-61r3 Page 1]",
                    "cleaned_text": "### Incident Handling Guide\n\nIncident response procedures.",
                    "tables": [],
                    "figures": [],
                }],
            }),
            encoding="utf-8",
        )

        res = pipeline.process_document(doc_dir)
        self.assertGreater(len(res.chunks), 0)
        chunk = res.chunks[0]
        self.assertIn("NIST_SP_800-61", chunk.duplicate_of)

    # -------------------------------------------------------------------------
    # 19. No silent skipping or loss of source pages, tables, or figures
    # -------------------------------------------------------------------------
    def test_no_silent_loss_of_content(self):
        doc_dir = self.tmp_dir / "cohort" / "sec" / "FULL_DOC"
        fig_dir = doc_dir / "figures"
        fig_dir.mkdir(parents=True, exist_ok=True)
        (fig_dir / "fig_p2_1.png").write_bytes(b"dummy")

        structured_json = doc_dir / "FULL_DOC_structured.json"
        structured_json.write_text(
            json.dumps({
                "document_id": "FULL_DOC",
                "category": "sec",
                "file_path": "documents/sec/FULL_DOC.pdf",
                "pages": [
                    {
                        "page_number": 1,
                        "citation_label": "[FULL_DOC Page 1]",
                        "cleaned_text": "### Section 1\n\nPage 1 narrative.",
                        "tables": [],
                        "figures": [],
                    },
                    {
                        "page_number": 2,
                        "citation_label": "[FULL_DOC Page 2]",
                        "cleaned_text": "### Section 2\n\nPage 2 narrative.",
                        "tables": [{
                            "table_id": "tbl_p2_1",
                            "headers": ["ColA"],
                            "rows": [["Val1"]],
                            "caption": "Table 2-1",
                        }],
                        "figures": [{
                            "figure_id": "fig_p2_1",
                            "image_path": "figures/fig_p2_1.png",
                            "caption": "Figure 2-1",
                        }],
                    },
                ],
            }),
            encoding="utf-8",
        )

        pipeline = DocumentChunkingPipeline(self.config, self.tokenizer)
        res = pipeline.process_document(doc_dir)

        self.assertEqual(res.pages_processed, 2)
        self.assertGreaterEqual(res.chunks_text, 2)
        self.assertEqual(res.chunks_table, 1)
        self.assertEqual(res.chunks_figure, 1)
        self.assertEqual(res.total_chunks, res.chunks_text + res.chunks_table + res.chunks_figure)

    # -------------------------------------------------------------------------
    # 20. Hugging Face Tokenizer Adapter offline loading & accuracy
    # -------------------------------------------------------------------------
    def test_huggingface_tokenizer_adapter_offline(self):
        try:
            hf_adapter = get_tokenizer_adapter(
                ChunkingConfig(tokenizer_backend="hf_tokenizer", model_name_or_path="BAAI/bge-small-en-v1.5")
            )
            self.assertTrue(hf_adapter.is_exact)
            tokens = hf_adapter.count_tokens("NIST SP 800-53 Rev. 5: AC-2(1) Automated System Account Management")
            self.assertGreater(tokens, 0)
            token_list = hf_adapter.tokenize("AC-2(1)")
            self.assertGreater(len(token_list), 0)
            truncated = hf_adapter.truncate_tokens("One two three four five six seven eight nine ten", 5)
            self.assertLessEqual(hf_adapter.count_tokens(truncated), 5)
        except Exception as e:
            self.fail(f"Failed to load local HuggingFace tokenizer offline: {e}")

    # -------------------------------------------------------------------------
    # 21. CharEstimatorAdapter fallback behavior
    # -------------------------------------------------------------------------
    def test_char_estimator_adapter(self):
        char_adapter = CharEstimatorAdapter()
        self.assertFalse(char_adapter.is_exact)
        text = "Four score and seven years ago our fathers brought forth"
        self.assertGreater(char_adapter.count_tokens(text), 0)
        truncated = char_adapter.truncate_tokens(text, 5)
        self.assertLess(len(truncated), len(text))

    # -------------------------------------------------------------------------
    # 22. Fix 1: Oversized single table row semantic sub-split
    # -------------------------------------------------------------------------
    def test_oversized_table_row_semantic_subsplit(self):
        table_chunker = TableChunker(self.config, self.tokenizer)
        # Create a single massive row with 3 examples that exceeds max_table_tokens (120 tokens)
        long_cell = (
            "Example 1: Train the development team in threat modeling and analyze how to use a risk-based approach to software security. " * 3 +
            "Example 2: Perform more rigorous assessments for high-risk areas such as protecting sensitive customer data and credentials. " * 3 +
            "Example 3: Review vulnerability reports and statistics for previous software versions to inform the security risk assessment. " * 3
        )
        sample_pages = [{
            "page_number": 10,
            "citation_label": "[TEST Page 10]",
            "cleaned_text": "Narrative text before table.",
            "tables": [{
                "table_id": "table_p10_1",
                "headers": ["Practices", "Tasks", "NotionalExamples"],
                "rows": [["PW.1", "Threat Modeling", long_cell]],
                "caption": "SSDF Practice Matrix",
            }],
        }]

        chunks = table_chunker.chunk_document_tables("TEST_DOC", "test_cat", "test.pdf", sample_pages)
        self.assertGreaterEqual(len(chunks), 2)
        for c in chunks:
            self.assertEqual(c.content_type, "table")
            self.assertLessEqual(c.token_count, self.config.max_table_tokens)
            # Replicated context
            self.assertIn("PW.1", c.text)
            self.assertIn("Threat Modeling", c.text)
            self.assertIn("Practices", c.text)
            self.assertEqual(c.table_metadata["parent_table_id"], "table_p10_1")

        # Verify all 3 examples are preserved across chunks
        combined_text = " ".join(c.text for c in chunks)
        self.assertIn("Example 1", combined_text)
        self.assertIn("Example 2", combined_text)
        self.assertIn("Example 3", combined_text)

    # -------------------------------------------------------------------------
    # 23. Fix 2: Prevent draft line numbers and attach consecutive headings
    # -------------------------------------------------------------------------
    def test_draft_line_numbers_and_consecutive_headings(self):
        text_chunker = StructureAwareTextChunker(self.config, self.tokenizer)
        sample_pages = [
            {
                "page_number": 5,
                "citation_label": "[TEST Page 5]",
                "cleaned_text": (
                    "### 13\n\n"
                    "### **Keywords**\n\n"
                    "secure software development; Secure Software Development Framework (SSDF).\n\n"
                    "### 17\n\n"
                    "### **CHAPTER ONE**\n\n"
                    "## **INTRODUCTION**\n\n"
                    "Information technology is widely recognized as the engine of the economy.\n\n"
                    "#### **IDA**\n\n"
                    "481 Institute for Defense Analyses"
                ),
            }
        ]

        chunks = text_chunker.chunk_document_text("TEST_DOC", "test_cat", "test.pdf", sample_pages)

        # Verify bare draft lines 13 and 17 never became chunks
        for c in chunks:
            self.assertNotEqual(c.text.strip(), "### 13")
            self.assertNotEqual(c.text.strip(), "### 17")
            self.assertGreaterEqual(c.token_count, 10)

        # Verify CHAPTER ONE is attached with INTRODUCTION and not emitted as lone chunk
        lone_ch1 = [c for c in chunks if c.text.strip() == "### **CHAPTER ONE**"]
        self.assertEqual(len(lone_ch1), 0)

        intro_chunks = [c for c in chunks if "Information technology is widely recognized" in c.text]
        self.assertEqual(len(intro_chunks), 1)
        self.assertIn("CHAPTER ONE", intro_chunks[0].text)

        # Verify IDA acronym definition is preserved with its full definition
        ida_chunks = [c for c in chunks if "Institute for Defense Analyses" in c.text]
        self.assertEqual(len(ida_chunks), 1)
        self.assertIn("IDA", ida_chunks[0].text)

    # -------------------------------------------------------------------------
    # 24. Fix 3: Standardize root category metadata
    # -------------------------------------------------------------------------
    def test_root_category_metadata_standardization(self):
        doc_dir = self.tmp_dir / "cleaned_corpus" / "root" / "NIST_SP_800-236"
        doc_dir.mkdir(parents=True, exist_ok=True)

        json_path = doc_dir / "NIST_SP_800-236_structured.json"
        json_path.write_text(
            json.dumps({
                "document_id": "NIST_SP_800-236",
                "category": "documents",  # Raw extraction value
                "file_path": "documents/NIST_SP_800-236.pdf",
                "pages": [{
                    "page_number": 1,
                    "citation_label": "[NIST_SP_800-236 Page 1]",
                    "cleaned_text": "### 1. Overview\n\nThis is overview text for root document.",
                }],
            }),
            encoding="utf-8",
        )

        pipeline = DocumentChunkingPipeline(self.config, self.tokenizer)
        res = pipeline.process_document(doc_dir)

        self.assertGreater(len(res.chunks), 0)
        for c in res.chunks:
            self.assertEqual(c.category, "root")
            self.assertEqual(c.source_file, "documents/NIST_SP_800-236.pdf")


if __name__ == "__main__":
    unittest.main()
