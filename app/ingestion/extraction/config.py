"""Configuration for modular document extraction architecture."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


@dataclass
class ExtractionConfig:
    """Settings controlling document parsing, preflight, OCR, and output artifacts."""

    # Paths
    project_root: Path = field(default_factory=lambda: PROJECT_ROOT)
    documents_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "documents")
    output_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "extraction_pilot")
    inventory_json_path: Path = field(
        default_factory=lambda: PROJECT_ROOT / "data" / "document_inventory" / "document_inventory.json"
    )

    # Pilot execution settings
    pilot_mode: bool = True
    pilot_documents: List[str] = field(
        default_factory=lambda: [
            "documents/risk_management/NIST_SP_800-53.pdf",
            "documents/cryptography_security/NIST_SP_800-152.pdf",
            "documents/cryptography_security/NIST_SP_800-186.pdf",
            "documents/NIST_SP_800-236.pdf",
            "documents/risk_management/NIST_SP_800-39.pdf",
        ]
    )

    # Parser flags
    use_docling_primary: bool = True
    fallback_to_pymupdf: bool = True
    export_legacy_txt: bool = True  # Also writes .txt for backward compatibility

    # Hybrid parsing settings
    use_hybrid_pymupdf4llm: bool = True  # Enable PyMuPDF4LLM layout parsing when available
    enable_figure_filtering: bool = True  # Enable multi-criteria figure filtering
    enable_document_corrections: bool = True  # Enable guarded document-specific corrections

    # Figure filtering thresholds
    figure_min_file_size_bytes: int = 1000
    figure_min_width_px: int = 40
    figure_min_height_px: int = 40
    figure_max_aspect_ratio: float = 8.0
    figure_margin_threshold_pt: float = 30.0
    figure_preserve_security_symbols: bool = True

    # OCR settings (strictly selective, disabled by default without verified OCR engine)
    enable_ocr_fallback: bool = False
    ocr_low_text_threshold: int = 50
    ocr_min_images: int = 1

    # Table extraction settings
    extract_tables: bool = True
    table_horizontal_lines_threshold: int = 2
    table_snap_x_tolerance: float = 10.0

    # Figures and Diagrams
    extract_figures: bool = True
    save_figure_images: bool = True
    enable_vlm_diagram_understanding: bool = False  # Modular interface only; no local model download or paid API

    # Quality check thresholds
    low_text_threshold: int = 100
    garbled_replacement_ratio_threshold: float = 0.05
    garbled_control_char_threshold: float = 0.03
    garbled_min_alnum_ratio: float = 0.25
    garbled_max_token_length: int = 60

    def resolve_pdf_path(self, rel_or_abs_path: str) -> Path:
        """Resolve a PDF path relative to project root or documents dir."""
        p = Path(rel_or_abs_path)
        if p.is_absolute() and p.exists():
            return p
        candidate1 = self.project_root / p
        if candidate1.exists():
            return candidate1
        candidate2 = self.documents_dir / p
        if candidate2.exists():
            return candidate2
        return candidate1
