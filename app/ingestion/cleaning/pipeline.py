"""Orchestrator pipeline for conservative document text cleaning."""

import json
from pathlib import Path
from typing import Dict, Any, List

from app.ingestion.cleaning.config import CleaningConfig
from app.ingestion.cleaning.header_footer import HeaderFooterDetector
from app.ingestion.cleaning.hyphenation import HyphenationCleaner
from app.ingestion.cleaning.encoding import EncodingCleaner
from app.ingestion.cleaning.boilerplate import BoilerplateDetector


class DocumentCleaningPipeline:
    """Cleans extracted document text conservatively while preserving structure and domain semantics."""

    def __init__(self, config: CleaningConfig):
        self.config = config
        self.header_footer = HeaderFooterDetector(config)
        self.hyphenation = HyphenationCleaner(config)
        self.encoding = EncodingCleaner(config)
        self.boilerplate = BoilerplateDetector(config)

    def clean_document_dir(self, input_dir: Path, output_dir: Path, doc_id: str, category: str) -> Dict[str, Any]:
        """
        Clean an extracted document directory and save cleaned artifacts to output_dir.
        """
        json_path = input_dir / f"{doc_id}_structured.json"
        if not json_path.is_file():
            raise FileNotFoundError(f"Structured JSON not found: {json_path}")

        with open(json_path, "r", encoding="utf-8") as jf:
            doc_data = json.load(jf)

        pages = doc_data.get("pages", [])

        # 1. Discover document-level running headers & footers
        verified_headers, verified_text_footers = self.header_footer.discover_document_headers_footers(pages)

        total_headers_removed = 0
        total_footers_removed = 0
        total_hyphens_repaired = 0
        total_hyphen_warnings = 0
        total_encoding_transforms = 0
        total_encoding_warnings = 0
        total_boilerplate_blocks = 0

        orig_char_count = 0
        cleaned_char_count = 0

        cleaned_pages = []
        cleaned_md_pages = []
        cleaned_txt_pages = []

        for p_idx, page in enumerate(pages):
            p_num = page.get("page_number", p_idx + 1)
            raw_text = page.get("raw_text", "")
            orig_struct = page.get("structured_text", "")
            orig_char_count += len(orig_struct)

            # Step A: Header & footer stripping
            txt_after_hf, h_removed, f_removed = self.header_footer.clean_page(
                orig_struct, verified_headers, verified_text_footers
            )
            total_headers_removed += len(h_removed)
            total_footers_removed += len(f_removed)

            # Step B: Hyphenation repair
            txt_after_hyphen, h_repairs, h_warns = self.hyphenation.clean_text(txt_after_hf)
            total_hyphens_repaired += len(h_repairs)
            total_hyphen_warnings += len(h_warns)

            # Step C: Encoding & whitespace normalization
            cleaned_text, enc_transforms, enc_warns = self.encoding.clean_text(txt_after_hyphen)
            total_encoding_transforms += len(enc_transforms)
            total_encoding_warnings += len(enc_warns)

            # Step D: Boilerplate detection & tagging
            bp_tags = self.boilerplate.tag_page_boilerplate(cleaned_text)
            total_boilerplate_blocks += len(bp_tags)

            cleaned_char_count += len(cleaned_text)

            # Build cleaned page object
            cleaned_page = dict(page)
            cleaned_page["raw_text"] = raw_text  # Keep raw text immutable
            cleaned_page["structured_text"] = cleaned_text
            cleaned_page["cleaned_text"] = cleaned_text
            cleaned_page["cleaning_metadata"] = {
                "headers_removed": h_removed,
                "footers_removed": f_removed,
                "hyphens_repaired": h_repairs,
                "hyphen_warnings": h_warns,
                "encoding_transforms": enc_transforms,
                "encoding_warnings": enc_warns,
                "boilerplate_tags": bp_tags,
                "original_char_count": len(orig_struct),
                "cleaned_char_count": len(cleaned_text),
                "delta_chars": len(cleaned_text) - len(orig_struct)
            }
            cleaned_pages.append(cleaned_page)

            # MD and TXT representations
            cleaned_txt_pages.append(f"--- PAGE {p_num} ---\n\n{cleaned_text}\n")
            cleaned_md_pages.append(f"## Page {p_num}\n\n{cleaned_text}\n")

        # Prepare cleaned document data structure
        cleaned_doc = dict(doc_data)
        cleaned_doc["pages"] = cleaned_pages
        cleaned_doc["cleaning_summary"] = {
            "verified_headers_discovered": list(verified_headers),
            "verified_text_footers_discovered": list(verified_text_footers),
            "total_headers_removed": total_headers_removed,
            "total_footers_removed": total_footers_removed,
            "total_hyphens_repaired": total_hyphens_repaired,
            "total_hyphen_warnings": total_hyphen_warnings,
            "total_encoding_transforms": total_encoding_transforms,
            "total_encoding_warnings": total_encoding_warnings,
            "total_boilerplate_blocks_tagged": total_boilerplate_blocks,
            "original_char_count": orig_char_count,
            "cleaned_char_count": cleaned_char_count,
            "delta_chars": cleaned_char_count - orig_char_count,
            "pct_change": ((cleaned_char_count - orig_char_count) / max(orig_char_count, 1)) * 100.0
        }

        # Save to output directory
        target_dir = output_dir / category / doc_id
        target_dir.mkdir(parents=True, exist_ok=True)

        # 1. Cleaned JSON
        out_json = target_dir / f"{doc_id}_structured.json"
        with open(out_json, "w", encoding="utf-8") as jf:
            json.dump(cleaned_doc, jf, indent=2)

        # 2. Cleaned MD
        out_md = target_dir / f"{doc_id}.md"
        out_md.write_text(f"# {doc_id}\n\n" + "\n".join(cleaned_md_pages), encoding="utf-8")

        # 3. Cleaned TXT
        out_txt = target_dir / f"{doc_id}.txt"
        out_txt.write_text("\n".join(cleaned_txt_pages), encoding="utf-8")

        # 4. Manifest
        manifest_data = {
            "document_id": doc_id,
            "category": category,
            "source_dir": str(input_dir),
            "cleaned_dir": str(target_dir),
            "total_pages": len(pages),
            "original_char_count": orig_char_count,
            "cleaned_char_count": cleaned_char_count,
            "cleaning_summary": cleaned_doc["cleaning_summary"]
        }
        out_manifest = target_dir / "manifest.json"
        with open(out_manifest, "w", encoding="utf-8") as mf:
            json.dump(manifest_data, mf, indent=2)

        return manifest_data
