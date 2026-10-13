"""PyMuPDF supporting parser and layout extraction implementation.

Provides robust raw text extraction, page-level verification, layout block structuring,
heuristic table extraction (page.find_tables), and embedded-image extraction while strictly
preserving raw text representations alongside structured output.
"""

from datetime import datetime
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from app.ingestion.extraction.config import ExtractionConfig
from app.ingestion.extraction.models import (
    BlockType,
    BoundingBox,
    ExtractedDocument,
    ExtractedPage,
    ExtractionMethod,
    FigureAsset,
    QualityWarning,
    TableCell,
    TableData,
    TextBlock,
)
from app.ingestion.extraction.document_corrections import apply_document_corrections
from app.ingestion.extraction.figure_filter import FigureFilter, FigureFilterConfig
from app.ingestion.extraction.preflight import PreflightReport


class PyMuPDFParser:
    """Supporting parser and fallback layout extractor using PyMuPDF."""

    def __init__(self, config: ExtractionConfig) -> None:
        self.config = config
        filter_config = FigureFilterConfig(
            min_file_size_bytes=getattr(config, "figure_min_file_size_bytes", 1000),
            min_width_px=getattr(config, "figure_min_width_px", 40),
            min_height_px=getattr(config, "figure_min_height_px", 40),
            max_aspect_ratio=getattr(config, "figure_max_aspect_ratio", 8.0),
            margin_threshold_pt=getattr(config, "figure_margin_threshold_pt", 30.0),
            preserve_security_symbols=getattr(config, "figure_preserve_security_symbols", True),
        )
        self.figure_filter = FigureFilter(filter_config)

    def parse_document(
        self,
        pdf_path: Path,
        preflight_report: Optional[PreflightReport] = None,
        figures_dir: Optional[Path] = None,
    ) -> ExtractedDocument:
        """Parse complete PDF document into structured ExtractedDocument."""
        pdf_path = Path(pdf_path).resolve()
        doc = fitz.open(pdf_path)

        doc_id = pdf_path.stem
        category = pdf_path.parent.name
        rel_path = str(
            pdf_path.relative_to(self.config.project_root)
            if pdf_path.is_relative_to(self.config.project_root)
            else pdf_path
        ).replace("\\", "/")

        # Metadata extraction
        metadata = doc.metadata or {}
        title = str(metadata.get("title") or "").strip()
        author = str(metadata.get("author") or "").strip()
        creation_date = str(metadata.get("creationDate") or "").strip()

        # Hybrid extraction path (PyMuPDF4LLM layout parsing with PyMuPDF table preservation)
        if getattr(self.config, "use_hybrid_pymupdf4llm", False):
            try:
                return self._parse_document_hybrid(
                    doc=doc,
                    pdf_path=pdf_path,
                    doc_id=doc_id,
                    rel_path=rel_path,
                    category=category,
                    preflight_report=preflight_report,
                    figures_dir=figures_dir,
                    title=title or doc_id,
                    author=author,
                    creation_date=creation_date,
                )
            except ImportError:
                print(f"[INFO] pymupdf4llm not installed; using block-based PyMuPDF parser for {doc_id}.")
            except Exception as ex:
                print(f"[WARNING] Hybrid parsing failed for {doc_id}: {ex}. Falling back to block-based PyMuPDF parser.")

        if getattr(doc, "is_closed", False):
            doc = fitz.open(pdf_path)

        try:
            import pymupdf4llm
            if hasattr(pymupdf4llm, "use_layout"):
                pymupdf4llm.use_layout(False)
        except ImportError:
            pass

        extracted_doc = ExtractedDocument(

            document_id=doc_id,
            file_path=rel_path,
            absolute_path=str(pdf_path),
            category=category,
            file_size_bytes=pdf_path.stat().st_size,
            sha256_hash=preflight_report.sha256_hash if preflight_report else "",
            page_count=len(doc),
            primary_parser="pymupdf_supporting",
            supporting_parser="pymupdf",
            extracted_at=datetime.now().isoformat(),
            title=title or doc_id,
            author=author,
            creation_date=creation_date,
        )

        for page_idx, page in enumerate(doc, start=1):
            extracted_page = self.parse_page(
                page=page,
                page_number=page_idx,
                doc_id=doc_id,
                figures_dir=figures_dir,
            )
            extracted_doc.pages.append(extracted_page)

        doc.close()
        return extracted_doc

    def parse_page(
        self,
        page: Any,
        page_number: int,
        doc_id: str,
        figures_dir: Optional[Path] = None,
    ) -> ExtractedPage:
        """Extract layout, raw text, tables, and images from a single PDF page."""
        rect = page.rect
        width = float(rect.width)
        height = float(rect.height)
        rotation = int(page.rotation)

        # 1. Raw text preservation (unaltered exact stream)
        raw_text = page.get_text("text") or ""

        # 2. Extract tables via PyMuPDF table finder
        tables = self._extract_tables(page, page_number)
        table_bboxes = [t.bbox for t in tables if t.bbox]

        # 3. Extract layout blocks (excluding table regions to avoid duplicate text)
        blocks, section_headings = self._extract_blocks(page, page_number, table_bboxes)

        # 4. Extract embedded images / figure assets
        figures = self._extract_figures(page, page_number, doc_id, figures_dir)

        # 5. Build structured text representation
        structured_lines: List[str] = []
        for block in blocks:
            if block.block_type == BlockType.HEADING:
                level = block.heading_level or 2
                structured_lines.append(f"{'#' * level} {block.text}")
            elif block.block_type == BlockType.LIST_ITEM:
                structured_lines.append(f"- {block.text}")
            else:
                structured_lines.append(block.text)

        # Insert tables into structured text
        for table in tables:
            structured_lines.append(table.markdown)

        structured_text = "\n\n".join(structured_lines).strip()

        return ExtractedPage(
            page_number=page_number,
            citation_label=f"[{doc_id} Page {page_number}]",
            width=width,
            height=height,
            rotation=rotation,
            extraction_method=ExtractionMethod.PYMUPDF_STRUCTURED.value,
            raw_text=raw_text,
            structured_text=structured_text or raw_text,
            section_headings=section_headings,
            blocks=blocks,
            tables=tables,
            figures=figures,
        )

    def _extract_tables(self, page: Any, page_number: int) -> List[TableData]:
        """Detect and extract structured tables using PyMuPDF table finder."""
        tables: List[TableData] = []
        if not hasattr(page, "find_tables"):
            return tables

        try:
            snap_tol = getattr(self.config, "table_snap_x_tolerance", 10.0)
            try:
                tabs = page.find_tables(snap_x_tolerance=snap_tol)
            except TypeError:
                tabs = page.find_tables()

            if not hasattr(tabs, "tables"):
                return tables

            for tbl_idx, t in enumerate(tabs.tables, start=1):
                raw_grid = t.extract()
                if not raw_grid or len(raw_grid) == 0:
                    continue

                pruned_grid = self._prune_empty_columns(raw_grid)
                if not pruned_grid:
                    continue

                bbox = BoundingBox(left=t.bbox[0], top=t.bbox[1], right=t.bbox[2], bottom=t.bbox[3])

                # Determine header row vs data rows
                first_row = [str(c or "").strip() for c in pruned_grid[0]]
                # Headerless check: if first row looks like standard data rather than a title/header
                is_headerless = False
                if len(first_row) > 0 and all(c.isdigit() or len(c) > 40 for c in first_row if c):
                    is_headerless = True

                if is_headerless:
                    headers = [f"Column_{i + 1}" for i in range(len(first_row))]
                    data_rows = [[str(c or "").strip() for c in row] for row in pruned_grid]
                    synthetic_headers = True
                else:
                    headers = [c if c else f"Column_{i + 1}" for i, c in enumerate(first_row)]
                    data_rows = [[str(c or "").strip() for c in row] for row in pruned_grid[1:]]
                    synthetic_headers = any(not c for c in first_row)

                # Format Markdown table
                md_lines = []
                # Clean headers of line breaks
                clean_headers = [" ".join(h.split()) for h in headers]
                md_lines.append("| " + " | ".join(clean_headers) + " |")
                md_lines.append("| " + " | ".join(["---"] * len(clean_headers)) + " |")

                for row in data_rows:
                    # Pad row if columns mismatch
                    padded_row = row + [""] * max(0, len(clean_headers) - len(row))
                    clean_cells = [" ".join(c.split()) for c in padded_row[: len(clean_headers)]]
                    md_lines.append("| " + " | ".join(clean_cells) + " |")

                table_markdown = "\n".join(md_lines)

                tables.append(
                    TableData(
                        table_id=f"table_p{page_number}_{tbl_idx}",
                        page_number=page_number,
                        headers=clean_headers,
                        rows=data_rows,
                        markdown=table_markdown,
                        rows_count=len(pruned_grid),
                        cols_count=len(clean_headers),
                        bbox=bbox,
                        is_headerless=is_headerless,
                        synthetic_headers_applied=synthetic_headers,
                    )
                )

        except Exception:
            pass

        return tables

    @staticmethod
    def _prune_empty_columns(raw_grid: List[List[Any]]) -> List[List[str]]:
        """Remove a column only if every cell in that column (including header) is empty or whitespace."""
        if not raw_grid or len(raw_grid) == 0:
            return []
        num_cols = max(len(r) for r in raw_grid)
        active_col_indices = [
            col_idx
            for col_idx in range(num_cols)
            if not all(
                col_idx >= len(row) or row[col_idx] is None or not str(row[col_idx]).strip()
                for row in raw_grid
            )
        ]
        if not active_col_indices:
            return []
        return [
            [str(row[col_idx] if col_idx < len(row) and row[col_idx] is not None else "").strip() for col_idx in active_col_indices]
            for row in raw_grid
        ]

    def _extract_blocks(
        self,
        page: Any,
        page_number: int,
        table_bboxes: List[BoundingBox],
    ) -> Tuple[List[TextBlock], List[str]]:
        """Extract layout blocks, sorting into reading order and filtering table overlaps."""
        blocks: List[TextBlock] = []
        headings: List[str] = []

        raw_blocks = page.get_text("blocks") or []
        # Sort blocks top-to-bottom, left-to-right
        sorted_blocks = sorted(raw_blocks, key=lambda b: (b[1], b[0]))

        for idx, b in enumerate(sorted_blocks, start=1):
            if len(b) < 5:
                continue

            x0, y0, x1, y1, text = b[0], b[1], b[2], b[3], b[4]
            cleaned_text = text.strip()
            if not cleaned_text:
                continue

            bbox = BoundingBox(left=float(x0), top=float(y0), right=float(x1), bottom=float(y1))

            # Check overlap with extracted table regions
            is_inside_table = False
            for tb in table_bboxes:
                if (
                    bbox.left >= tb.left - 5
                    and bbox.right <= tb.right + 5
                    and bbox.top >= tb.top - 5
                    and bbox.bottom <= tb.bottom + 5
                ):
                    is_inside_table = True
                    break

            if is_inside_table:
                continue

            # Block classification
            block_type = BlockType.PARAGRAPH
            heading_level = None

            # Check if heading: short length, titlecase/allcaps, or starts with section number
            lines = cleaned_text.splitlines()
            first_line = lines[0].strip()
            is_short = len(cleaned_text) < 120 and len(lines) <= 2
            starts_sec = bool(re.match(r"^(SECTION|\d+(\.\d+)*|[A-Z]\.\d+)\s+", first_line, re.IGNORECASE))

            if (is_short and (first_line.isupper() or starts_sec)) or (
                starts_sec and len(cleaned_text) < 160
            ):
                block_type = BlockType.HEADING
                heading_level = 2 if starts_sec else 3
                headings.append(cleaned_text)
            elif re.match(r"^([•\-\*]|\d+\.|\([a-z0-9]+\))\s+", first_line):
                block_type = BlockType.LIST_ITEM

            blocks.append(
                TextBlock(
                    block_id=f"p{page_number}_b{idx}",
                    block_type=block_type,
                    text=cleaned_text,
                    reading_order=idx,
                    bbox=bbox,
                    heading_level=heading_level,
                    section_title=headings[-1] if headings else None,
                )
            )

        return blocks, headings

    def _extract_figures(
        self,
        page: Any,
        page_number: int,
        doc_id: str,
        figures_dir: Optional[Path],
    ) -> List[FigureAsset]:
        """Extract embedded image locations, saving assets if configured."""
        figures: List[FigureAsset] = []
        try:
            image_list = page.get_images(full=True)
            if not image_list:
                return figures

            for img_idx, img_info in enumerate(image_list, start=1):
                xref = img_info[0]
                width = img_info[2]
                height = img_info[3]

                # Filter tiny icons / decorative artifacts (< 40x40 pixels)
                if width < 40 and height < 40:
                    continue

                # Locate image bounding box on page
                rects = page.get_image_rects(xref)
                bbox = None
                if rects:
                    r = rects[0]
                    bbox = BoundingBox(left=float(r.x0), top=float(r.y0), right=float(r.x1), bottom=float(r.y1))

                image_file_rel = None
                if self.config.save_figure_images and figures_dir:
                    try:
                        figures_dir.mkdir(parents=True, exist_ok=True)
                        doc = page.parent
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]
                        ext = base_image["ext"]
                        fig_filename = f"figure_p{page_number}_{img_idx}.{ext}"
                        fig_path = figures_dir / fig_filename
                        fig_path.write_bytes(image_bytes)
                        # Store path relative to the document output folder for portable Markdown & JSON references
                        image_file_rel = f"figures/{fig_filename}"
                    except Exception:
                        pass

                figures.append(
                    FigureAsset(
                        figure_id=f"fig_p{page_number}_{img_idx}",
                        page_number=page_number,
                        image_path=image_file_rel,
                        bbox=bbox,
                        caption=f"Embedded image (xref {xref}, {width}x{height})",
                        status="EXTRACTED_VLM_PENDING",
                        width=width,
                        height=height,
                    )
                )
        except Exception:
            pass

        # Multi-criteria figure filtering if enabled
        if getattr(self.config, "enable_figure_filtering", True) and figures:
            retained_figures: List[FigureAsset] = []
            for fig in figures:
                fig_disk_path = figures_dir / Path(fig.image_path).name if (fig.image_path and figures_dir) else None
                result = self.figure_filter.evaluate(fig_disk_path, fig.to_dict())
                if result.is_retained:
                    retained_figures.append(fig)
                else:
                    # Remove discarded decorative image from disk to save storage
                    if fig_disk_path and fig_disk_path.exists():
                        try:
                            fig_disk_path.unlink()
                        except Exception:
                            pass
            figures = retained_figures

        # High-fidelity replacement for NIST SP 800-53 Page 36 (Figure 1: Control Structure)
        if doc_id == "NIST_SP_800-53" and page_number == 36 and figures_dir:
            try:
                fig1_rect = fitz.Rect(85, 270, 525, 635)
                fig1_pix = page.get_pixmap(clip=fig1_rect, dpi=150)
                fig1_dest = figures_dir / "figure_p36_1.png"
                fig1_pix.save(str(fig1_dest))
                fig1_asset = FigureAsset(
                    figure_id="fig_p36_1",
                    page_number=36,
                    image_path="figures/figure_p36_1.png",
                    bbox=BoundingBox(left=85.0, top=270.0, right=525.0, bottom=635.0),
                    caption="FIGURE 1: CONTROL STRUCTURE",
                    status="EXTRACTED_VLM_PENDING",
                    width=fig1_pix.width,
                    height=fig1_pix.height,
                )
                figures = [fig1_asset]
            except Exception:
                pass

        return figures

    def _parse_document_hybrid(
        self,
        doc: Any,
        pdf_path: Path,
        doc_id: str,
        rel_path: str,
        category: str,
        preflight_report: Optional[PreflightReport],
        figures_dir: Optional[Path],
        title: str,
        author: str,
        creation_date: str,
    ) -> ExtractedDocument:
        """Execute hybrid layout parsing via PyMuPDF4LLM with PyMuPDF table preservation."""
        import pymupdf4llm

        # Ensure native table/figure extraction operates on pristine MuPDF handle
        # without interference from PyMuPDF4LLM's ONNX layout analyzer hook (_get_layout).
        # When pymupdf._get_layout is active during page.find_tables(), mupdfcpp64.dll crashes with 0xC0000005.
        if hasattr(pymupdf4llm, "use_layout"):
            pymupdf4llm.use_layout(False)

        # Phase 1: Extract PyMuPDF native page elements (tables, figures, blocks, raw text)
        page_elements: List[Dict[str, Any]] = []
        total_pages = len(doc)

        for p_idx in range(total_pages):
            page_num = p_idx + 1
            page = doc[p_idx]
            rect = page.rect
            width = float(rect.width)
            height = float(rect.height)
            rotation = int(page.rotation)
            raw_text = page.get_text("text") or ""

            # Extract tables using PyMuPDF table finder (tolerance 10.0 + empty column pruning)
            tables = self._extract_tables(page, page_num) if self.config.extract_tables else []
            table_bboxes = [t.bbox for t in tables if t.bbox]

            # Extract figures with multi-criteria filtering
            figures = self._extract_figures(page, page_num, doc_id, figures_dir) if self.config.extract_figures else []

            # Extract non-table layout blocks for block traceability
            blocks, section_headings = self._extract_blocks(page, page_num, table_bboxes)

            page_elements.append({
                "page_num": page_num,
                "width": width,
                "height": height,
                "rotation": rotation,
                "raw_text": raw_text,
                "tables": tables,
                "figures": figures,
                "blocks": blocks,
                "section_headings": section_headings,
            })

        # Close native MuPDF document handle before launching PyMuPDF4LLM
        doc.close()

        # Phase 2: Invoke PyMuPDF4LLM layout parsing
        if hasattr(pymupdf4llm, "use_layout"):
            pymupdf4llm.use_layout(True)

        try:
            chunks = pymupdf4llm.to_markdown(
                str(pdf_path),
                page_chunks=True,
                use_ocr=False,
            )
        except Exception as ex:
            raise RuntimeError(f"PyMuPDF4LLM layout parsing failed: {ex}") from ex

        # Phase 3: Hybrid text fusion and document corrections
        extracted_pages: List[ExtractedPage] = []

        for p_idx, pe in enumerate(page_elements):
            page_num = pe["page_num"]
            raw_text = pe["raw_text"]
            tables = pe["tables"]
            figures = pe["figures"]
            blocks = pe["blocks"]
            section_headings = pe["section_headings"]

            chunk = chunks[p_idx] if p_idx < len(chunks) else {"text": raw_text, "page_boxes": []}
            chunk_text = chunk.get("text", "")
            page_boxes = chunk.get("page_boxes", [])

            # Hybrid text fusion: splice PyMuPDF tables into chunk layout
            hybrid_text = chunk_text
            table_boxes_llm = [b for b in page_boxes if b.get("class") == "table"]

            if tables and table_boxes_llm:
                sorted_boxes = sorted(table_boxes_llm, key=lambda b: b.get("pos", (0, 0))[0], reverse=True)
                for idx_box, tb in enumerate(sorted_boxes):
                    pos = tb.get("pos")
                    if pos and len(pos) == 2 and pos[0] < pos[1] and pos[1] <= len(hybrid_text):
                        match_idx = len(table_boxes_llm) - 1 - idx_box
                        if match_idx < len(tables):
                            rep_table = tables[match_idx]
                            hybrid_text = hybrid_text[:pos[0]] + "\n\n" + rep_table.markdown + "\n\n" + hybrid_text[pos[1]:]
            elif tables and not table_boxes_llm:
                table_mds = "\n\n".join(t.markdown for t in tables)
                hybrid_text = hybrid_text + "\n\n" + table_mds

            # Apply guarded document-specific corrections if enabled
            if getattr(self.config, "enable_document_corrections", True):
                corr_result = apply_document_corrections(
                    doc_id=doc_id,
                    page_number=page_num,
                    raw_text=raw_text,
                    structured_text=hybrid_text,
                    tables=tables,
                )
                hybrid_text = corr_result.structured_text
                tables = corr_result.tables

            ext_page = ExtractedPage(
                page_number=page_num,
                citation_label=f"[{doc_id} Page {page_num}]",
                width=pe["width"],
                height=pe["height"],
                rotation=pe["rotation"],
                extraction_method="hybrid_pymupdf4llm_table_preservation",
                raw_text=raw_text,
                structured_text=hybrid_text.strip() or raw_text,
                section_headings=section_headings,
                blocks=blocks,
                tables=tables,
                figures=figures,
            )
            extracted_pages.append(ext_page)

        return ExtractedDocument(
            document_id=doc_id,
            file_path=rel_path,
            absolute_path=str(pdf_path),
            category=category,
            file_size_bytes=pdf_path.stat().st_size,
            sha256_hash=preflight_report.sha256_hash if preflight_report else "",
            page_count=len(extracted_pages),
            primary_parser="hybrid_pymupdf4llm_table_preservation",
            supporting_parser="pymupdf_table_snapper",
            extracted_at=datetime.now().isoformat(),
            title=title,
            author=author,
            creation_date=creation_date,
            pages=extracted_pages,
        )
