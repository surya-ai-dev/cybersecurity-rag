# Cybersecurity RAG — Chunking Implementation Plan

- This is the single source-of-truth plan for implementing Stage 4 chunking. Antigravity must read this file completely before modifying code or processing data.
- Project root: `C:\Users\Computer\Desktop\cybersecurity-rag`.
- Goal: create traceable, retrieval-ready chunks without losing security-critical meaning, table structure, figure relationships, page citations, or uncertainty markers.
- Treat this plan as the implementation contract. Inspect actual schemas and adapt field names only when evidence requires it.
- Do not modify original PDFs, extraction outputs, cleaned outputs, cleaning manifests, or cleaning checkpoints.
- Do not overwrite existing outputs. Use a new isolated output directory for the pilot.
- Do not run full-corpus chunking until the pilot is reviewed and explicitly approved by the user.
- Do not generate embeddings or write to Qdrant during this stage.
- Do not install packages or download models without explaining the need and getting approval.
- Do not commit or push changes.
- Do not claim a check passed unless it was actually executed.
- Prefer sequential processing and existing local dependencies because laptop resources are limited.
- Report uncertainty, missing fields, and deviations rather than silently guessing.

1. Known Project Context — Reconfirm Against Files

- The reported source corpus contains 73 NIST PDFs and 4,649 physical pages.
- The reported cleaning pilot contains 10 documents and 1,057 pages.
- The reported production cleaning cohort contains 63 documents and 3,592 pages.
- The reported cleaned pilot path is `data/cleaned_pilot/`.
- The reported production cleaned path is `data/cleaned_corpus/`.
- The proposed isolated chunk pilot path is `data/chunks_pilot/`.
- Inspect manifests to establish exact paths and filenames; do not assume the pilot contains the whole corpus.
- The extraction system reportedly produces structured JSON plus Markdown/TXT representations.
- The structured schema reportedly includes text representations, headings, blocks, tables, figures, and cleaning metadata; verify exact fields.
- The corpus reportedly contains 591 figure assets.
- The cleaning audit reportedly recorded 19 ambiguous replacement-character warnings.
- The duplicate pair is `NIST_SP_800-61.pdf` and `NIST.SP.800-61r3.pdf`; preserve both source files.
- Review `reports/post_cleaning_layout_integrity_audit.md` and `reports/full_corpus_cleaning_reconciliation.md` before implementation.
- Existing embedding and retrieval settings must remain unchanged during chunking.

2. Outcomes and Non-Goals

- Produce coherent chunks with reliable source-document and page provenance.
- Preserve headings, paragraphs, list hierarchy, technical identifiers, table relationships, and figure links.
- Keep chunk IDs deterministic for unchanged input and configuration.
- Make configuration explicit, documented, and versioned.
- Validate all pilot outputs before allowing full-corpus execution.
- Do not use the chunker to repair extraction defects silently.
- Do not guess missing table headers, captions, symbols, page numbers, or section titles.
- Do not discard original tables or figure assets after making retrieval representations.
- Do not treat successful chunk generation as proof of good retrieval quality.
- Do not physically delete duplicate source documents or merge their provenance.

3. Stage 0 — Repository and Schema Discovery

- Inspect repository structure, Python version, dependencies, CLI patterns, test conventions, and current ingestion modules.
- Read both audit reports and the cleaning manifests/checkpoint.
- Inspect at least one cleaned structured JSON document and its matching Markdown and TXT files.
- Inspect one normal-text page, one table-heavy page, one figure page, and one page with an encoding warning.
- Identify actual fields for document IDs, physical page numbers, printed page labels, headings, blocks, tables, figures, coordinates, and warnings.
- Determine whether table cells are structured arrays, Markdown, plain text, or multiple representations.
- Determine how figure assets are referenced and whether paths are relative to the document, output root, or another base.
- Determine whether page numbers are zero-based, one-based, or both.
- Record actual schema examples and exact paths in a discovery report.
- Establish read-only input hashes or other reliable baselines before processing.
- Check free disk space and stop if input/output mapping is ambiguous.
- Do not implement chunking until discovery is complete.

4. Stage 1 — Architecture and Configuration

- Create a reusable chunking package that follows the repository's existing conventions.
- Separate orchestration, normal-text splitting, table processing, figure records, validation, and output writing.
- Reuse existing data models and helpers where appropriate.
- Use explicit configuration rather than scattered hard-coded values.
- Provide dry-run, single-document, pilot, and later full-corpus modes.
- Default to sequential processing.
- Use atomic output writes and validate outputs before marking a document complete.
- If checkpointing is added, make it safe, idempotent, and bounded to the intended output directory.
- Never delete valid output because a run was interrupted.
- Record the input cohort, configuration, code/version information, and per-document status in a manifest.
- Keep full-corpus execution blocked until explicit pilot approval.

5. Stage 2 — Common Chunk Record

- Define one normalized chunk schema after inspecting existing schemas.
- Include a stable `chunk_id` and `document_id`.
- Include the source-relative PDF path and document title when available.
- Include `page_start` and `page_end` using physical PDF page numbering.
- Keep printed page labels separate if they exist.
- Include the section path/hierarchy when available.
- Include a content type such as `text`, `table`, `figure`, or `mixed`.
- Include the retrieval text separately from structured table/figure metadata.
- Include table parent IDs and part numbers where applicable.
- Include figure references and asset paths where applicable.
- Include source block IDs and coordinates when available.
- Include encoding warnings and duplicate relationships when applicable.
- Include configuration version and content hash where useful.
- Do not invent unavailable metadata; use explicit unknown/null values.
- Validate every serialized record against the selected schema.

6. Stage 3 — Normal Text Strategy

- Use structure-aware chunking as the primary normal-text strategy.
- Split first at section/subsection boundaries.
- Keep each heading attached to the content it introduces.
- Keep paragraphs intact whenever they fit the target size.
- Keep numbered procedures and related bullet lists together where practical.
- Keep security control identifiers attached to their requirements and explanations.
- Preserve URLs, paths, commands, inline code, formulas, CVEs, NIST identifiers, and cryptographic values exactly.
- Do not combine unrelated sections just to fill a chunk.
- For oversized sections, use recursive splitting: subsection, paragraph, sentence, then smaller safe units.
- Do not split by raw character count when a safe semantic boundary exists.
- Do not silently truncate content.
- Verify the configured BGE-small tokenizer/input limit before finalizing token limits.
- Start with 400–600 tokens as a pilot target, not a proven optimum.
- Test 50–100 tokens of overlap; apply it only where continuity benefits retrieval.
- Avoid overlap that duplicates full paragraphs or tables.
- Store the exact section path even if a heading is not repeated in the chunk body.
- Keep accurate page ranges for chunks spanning pages.
- Do not create empty semantic chunks from genuinely blank pages.
- Retain meaningful low-text pages as figure or metadata records when appropriate.
- Flag chunks exceeding the configured maximum and explain why.
- Report token counts if the tokenizer is available; otherwise report character counts as a proxy.
- Test deterministic IDs across repeated runs.

7. Stage 4 — Table-Aware Strategy

- Treat tables as structured objects, not ordinary prose alone.
- Inspect the actual `TableData` schema before coding.
- Preserve source table ID or generate a deterministic ID linked to the source.
- Preserve document, physical page, section, caption/title, and bounding box where available.
- Preserve column headers, row order, cell order, empty cells, and numeric values.
- Do not shift values when a cell is empty or missing.
- Preserve percentages, units, bounds, hexadecimal values, equations, and symbols exactly.
- Keep small/medium tables intact when the model input limit permits.
- Use 500 tokens as an initial atomic-table heuristic, then validate against actual data and model limits.
- For oversized tables, split only between complete rows wherever possible.
- Repeat the original column headers in each row-based table chunk.
- Repeat table title and essential section context in each split chunk.
- Keep one parent table ID across all parts and give each part a stable index.
- Do not split a row unless it cannot otherwise fit; if unavoidable, retain row identity and column labels.
- Never invent generic headers to hide missing headers.
- If a header is blank or suspicious, preserve it and add a review warning.
- Investigate `AssetImportance`, `Column_3`, `Column_4`, and `Defini on` against the source PDF.
- Do not silently correct these strings without source evidence.
- Keep structured cells available for validation and future table-specific retrieval.
- Generate or retain a readable Markdown representation for text retrieval where appropriate.
- Do not index a full table and all row chunks redundantly without a documented policy.
- For multi-page tables, consider adjacent pages, matching headers, table title, section, and layout evidence together.
- Do not link tables across pages based on matching headers alone.
- Keep original page-level table records and add a parent/continuation relationship when supported.
- If continuation confidence is low, keep separate records and add a warning.
- Compare row counts, column counts, headers, and cell values before/after chunking.
- Test simple, wide, multiline, identifier-heavy, and multi-page tables.

8. Stage 5 — Figure-Aware Strategy

- Treat each meaningful figure as an image asset plus a linked searchable record.
- Inspect the actual `FigureAsset` schema and path rules.
- Preserve the original image unchanged during chunking.
- Preserve figure ID, document ID, page, path, dimensions, and bounding box when available.
- Preserve the source caption exactly when present.
- Link the figure to its section and nearby explanatory paragraphs only when evidence supports the relationship.
- Use layout coordinates, caption markers, reading order, and section hierarchy where available.
- Do not assume the nearest paragraph describes the figure.
- Create a dedicated figure record with caption, short contextual text/reference, and source citation.
- Keep the image path separate from the text passed to the text embedding model.
- Never pass raw image bytes to a text-only embedding model.
- Never use the filename as the only description.
- Never invent captions or visual interpretations.
- Mark uncaptioned figures for review if their meaning is important and not captured in text.
- Keep figure relationships linked to normal text chunks without copying long paragraphs repeatedly.
- Preserve architecture diagrams, workflows, charts, technical illustrations, and meaningful screenshots.
- Do not automatically discard uncertain assets as decorative.
- Use OCR only if already installed and if important visible text is absent from extracted text.
- Mark OCR-derived content and retain uncertainty; OCR alone cannot describe arrows or spatial relationships.
- Do not install or download a vision model during this stage.
- Use a status such as `EXTRACTED_VLM_PENDING` for complex diagrams lacking visual descriptions, if compatible with the schema.
- Validate that every referenced image exists and every figure ID is unique in its intended scope.
- Detect missing, orphaned, or unexpected duplicate references.
- Test captioned figures, uncaptioned figures, multiple figures per page, and figure-only pages.

9. Stage 6 — Ambiguous Text and Security Tokens

- Preserve all 19 known ambiguous-character warnings and their source metadata.
- Never guess the intended symbol or replace `�` based only on context.
- Keep warning metadata linked to the affected document and page.
- If exact character offsets exist, preserve/remap them carefully; otherwise retain page-level warning only.
- Preserve NIST control IDs and CVE identifiers exactly.
- Preserve algorithm names, parameters, hexadecimal values, numeric bounds, units, percentages, and equations.
- Preserve technical URLs, paths, commands, code snippets, hyphens, underscores, and slashes within identifiers.
- Do not apply aggressive Unicode normalization to security-sensitive strings without evidence and tests.
- Do not remove bullets when they convey sequence or relationship.
- Distinguish an ambiguous character from an empty table cell or missing value.
- Test against representative actual tokens from the corpus.
- Keep warning-bearing chunks available, but expose warnings to downstream generation.
- Do not silently omit a chunk because it contains an uncertainty marker.
- If content is unreadable, retain its source reference and flag it for later review.

10. Stage 7 — Relationships and Provenance

- Represent content relationships explicitly when source evidence supports them.
- Link table chunks to their parent table and containing section.
- Link figure records to their section and relevant explanatory text.
- Link normal-text chunks to the section hierarchy that governs them.
- Keep a source page range for every chunk or record.
- Use stable IDs rather than array positions alone.
- Preserve source coordinates when available for future citation highlighting.
- Do not infer a relationship merely because objects occur on the same page.
- Use coordinates, captions, heading hierarchy, and reading order as evidence.
- If the schema cannot represent a relationship, document the limitation rather than modifying cleaned source files.
- Test mixed-content pages containing text plus a table or figure.
- Test pages with multiple figures and content spanning page boundaries.

11. Stage 8 — Duplicate-Document Policy

- Preserve both identical NIST SP 800-61 source PDFs and their cleaned outputs.
- Keep the documented duplicate relationship in chunk metadata where supported.
- Do not physically delete or merge either document.
- For the pilot, retain source-specific chunk records so citation provenance can be tested.
- Use deterministic IDs that include stable source identity, not text hash alone.
- Document whether duplicate chunks will both be emitted in the pilot.
- Do not index duplicate copies twice in production without an explicit policy.
- If future indexing deduplicates content, preserve all source-document references for citations.
- Test that duplicate handling cannot create ID collisions.

12. Stage 9 — Pilot Scope and Outputs

- Start with the 10 cleaned pilot documents, not the 63-document production cohort.
- Write only to a new isolated directory such as `data/chunks_pilot/`.
- Inspect whether that directory already exists; if it does, use a new versioned path instead of overwriting.
- Choose a representative sample that includes text-heavy, table-heavy, figure-heavy, and multi-page content.
- Include audited table archetypes and warning-bearing pages where present in the pilot cohort.
- Record the exact input documents and pages processed.
- Use JSONL or the repository's established standard after inspecting existing conventions.
- Write a manifest mapping input documents to output artifacts.
- Store chunking configuration with pilot outputs.
- Produce a human-readable report under `reports/`.
- Provide dry-run and single-document commands.
- Do not process all 73 documents in this stage.
- Do not generate embeddings or touch Qdrant.

13. Stage 10 — Validation and Tests

- Verify every selected input document is accounted for.
- Verify every chunk has a valid document ID and source-relative path.
- Verify every page range refers to valid source pages.
- Verify all figure references resolve to existing assets.
- Verify table chunks have parent IDs or a documented equivalent.
- Verify split table chunks preserve headers and row/cell order.
- Verify multi-page table relationships are linked only when evidence supports them.
- Verify text chunks retain section paths when available.
- Verify encoding warnings remain traceable.
- Verify chunk IDs are stable for identical inputs/configuration.
- Verify source and cleaned files remain unchanged.
- Verify no chunk is silently truncated.
- Report all chunks exceeding configured limits.
- Handle empty chunks according to documented rules.
- Validate JSON/JSONL parsing and schema.
- Compare table row/cell counts and technical identifiers before and after chunking.
- Validate figure-to-page and figure-to-document associations.
- Run unit tests for each content type and integration tests for mixed pages.
- Run the existing test suite and report actual pass/fail counts.
- Fix failures before marking the pilot as passed.
- Do not suppress warnings to obtain a green result.
- Do not claim visual verification unless the source PDF was actually inspected visually.

14. Stage 11 — Pilot Report

- Report documents and pages processed.
- Report total chunks by content type.
- Report normal-text chunk count, table chunk count, parent-table count, and figure-record count.
- Report chunks carrying encoding warnings.
- Report min, median, mean, and max token sizes when token counts are available.
- Otherwise report character counts and clearly label them as a proxy.
- Report chunks below/above target sizes and all oversized chunks.
- Report oversized table rows and sections that could not be split safely.
- Report figures lacking captions or contextual links.
- Report missing source metadata and table-header anomalies.
- Report duplicate-document handling.
- Report output size and remaining disk space.
- List known limitations and checks that could not be performed.
- Conclude with `PASS — Pilot is ready for review` or `NEEDS REVIEW — Fix issues before approval`.
- Do not label the pilot production-ready merely because the CLI exited successfully.

15. Stage 12 — Approval Gates

- Gate A: repository/schema discovery is complete.
- Gate B: design and configuration are documented.
- Gate C: text, table, figure, and ambiguous-text handling are implemented.
- Gate D: pilot outputs are isolated from all source and cleaned data.
- Gate E: validation and test results are reported.
- Gate F: the user has reviewed and explicitly approved the pilot.
- Do not start full-corpus chunking until all required gates pass.
- If critical content loss is detected, stop and report it.
- If table structure is unreliable, flag affected tables rather than emitting misleading chunks.
- If figure associations are uncertain, preserve assets and mark the relationship uncertain.
- If page citations cannot be traced, resolve provenance before proceeding.

16. Stage 13 — Full-Corpus Run After Approval Only

- After explicit approval, process the production cleaned corpus in small recoverable batches.
- Keep the 10-document pilot cohort separate from production to avoid accidental double-processing.
- Reconcile the intended document inventory before choosing batch sizes.
- Use atomic checkpointing and output validation if a safe repository pattern exists.
- Make recovery idempotent and bounded to the designated output directory.
- Check free disk space before each batch.
- Preserve at least the 500 MB free-space reserve unless a new constraint is approved.
- Validate each batch before proceeding to the next.
- Reconcile all production documents, pages, and chunks at completion.
- Confirm all expected chunks appear in the final manifest.
- Confirm source PDFs, extraction outputs, and cleaned outputs remain unchanged.
- Do not generate embeddings until full-corpus chunk validation passes.
- Do not write to Qdrant until the user approves the chunk dataset.

17. Stage 14 — Later Retrieval Evaluation

- After chunking is approved, generate embeddings with the existing configured model.
- Do not change embedding model, chunking, and reranking settings simultaneously.
- Use the existing retrieval evaluation set as the baseline if available.
- Compare Hit@K, Recall@K, Precision@K, MRR, and context quality where supported.
- Inspect queries whose retrieval quality declines.
- Investigate whether failures arise from chunk boundaries, missing metadata, table representation, figure context, or embedding behavior.
- Change one major variable at a time.
- Keep prior validated outputs and metrics for comparison.
- Record the final configuration and rationale.

18. Commands and Communication Rules

- Inspect CLI conventions before deciding command names.
- Provide a dry-run command, pilot execution command, and validation command where appropriate.
- Explain each command in simple language before asking the user to run it.
- After each run, summarize actual results and the current stage.
- Ask for explicit approval before full-corpus processing.
- Never request secrets or API keys in reports.
- Do not assume cloud credits are available.
- Prefer the current Python environment and existing dependencies.
- Do not claim a file was inspected if only a summary was read.
- Do not claim all figures were visually interpreted when only asset existence was checked.

19. Immediate First Action for Antigravity

- Read this complete plan and the actual post-cleaning audit report.
- Perform Stage 0 discovery only, without modifying corpus files.
- Inspect exact input paths, schemas, current modules, and tests.
- Produce a concise discovery report with evidence and unresolved questions.
- Propose the exact implementation files and configuration before coding.
- After discovery, implement the isolated 10-document pilot in small reviewable steps.
- Stop after the pilot validation report and wait for user approval.
- Update this plan only when an implementation decision formally changes; record date, evidence, reason, and approval.
- Priority order: data integrity, provenance, security-critical meaning, content relationships, reproducibility, then performance.

20. Acceptance Checklist

[ ] Actual schemas and paths inspected before coding.
[ ] Cleaned inputs remain unchanged.
[ ] Normal text uses section-aware boundaries and safe recursive fallback.
[ ] Table headers, rows, cells, and parent table relationships are preserved.
[ ] Multi-page table continuation is linked only when evidence supports it.
[ ] Figure assets, captions, page citations, and contextual links are retained where available.
[ ] No unsupported visual description is invented.
[ ] All 19 known ambiguous-character warnings remain traceable.
[ ] Security identifiers and technical tokens survive chunking.
[ ] Chunk IDs are deterministic.
[ ] Page ranges and document IDs validate.
[ ] Pilot outputs are isolated and reproducible.
[ ] Automated and existing tests were actually run and results reported.
[ ] Pilot report documents counts, limitations, warnings, and a final decision.
[ ] No full-corpus chunking, embedding generation, or Qdrant changes occurred before approval.

Decision Log

| Date | Decision/change | Evidence and reason | Approved by |
|---|---|---|---|
| Pending | Initial implementation plan | This document | User approval required for full-corpus execution |
