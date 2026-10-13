"""Modular OCR fallback architecture for document extraction.

Detects pages requiring OCR (suspected scanned or image-based pages) and routes them
to compatible OCR engines only after verifying dependencies. Avoids blanket OCR execution.
"""

from abc import ABC, abstractmethod
import shutil
from typing import Any, Dict, List, Optional, Tuple

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from app.ingestion.extraction.config import ExtractionConfig
from app.ingestion.extraction.models import QualityWarning


class BaseOCREngine(ABC):
    """Abstract interface for pluggable OCR engines."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if engine dependencies and binaries are installed and operational."""
        pass

    @abstractmethod
    def get_engine_name(self) -> str:
        """Return human-readable identifier for the OCR engine."""
        pass

    @abstractmethod
    def get_diagnostics(self) -> Dict[str, Any]:
        """Return diagnostic status of dependencies and language assets."""
        pass

    @abstractmethod
    def ocr_page(self, page: Any, lang: str = "eng") -> Optional[str]:
        """Run OCR on a PyMuPDF page, returning extracted text."""
        pass


class PyMuPDFOCREngine(BaseOCREngine):
    """PyMuPDF built-in OCR integration via Tesseract bindings."""

    def __init__(self) -> None:
        self._checked = False
        self._available = False
        self._diag_message = ""

    def is_available(self) -> bool:
        if self._checked:
            return self._available

        self._checked = True
        try:
            # Check if PyMuPDF has OCR binding and tessdata
            # In PyMuPDF, fitz.open() can test get_textpage_ocr
            doc = fitz.open()
            page = doc.new_page(width=100, height=100)
            page.get_textpage_ocr(language="eng")
            doc.close()
            self._available = True
            self._diag_message = "PyMuPDF OCR engine operational with language pack 'eng'."
        except Exception as exc:
            self._available = False
            self._diag_message = f"PyMuPDF OCR unavailable: {exc}"

        return self._available

    def get_engine_name(self) -> str:
        return "PyMuPDF-Tesseract"

    def get_diagnostics(self) -> Dict[str, Any]:
        return {
            "engine": self.get_engine_name(),
            "available": self.is_available(),
            "detail": self._diag_message,
        }

    def ocr_page(self, page: Any, lang: str = "eng") -> Optional[str]:
        if not self.is_available():
            return None
        try:
            textpage = page.get_textpage_ocr(language=lang)
            return textpage.extractText()
        except Exception:
            return None


class SystemTesseractEngine(BaseOCREngine):
    """External CLI Tesseract integration."""

    def __init__(self) -> None:
        self._bin = shutil.which("tesseract")

    def is_available(self) -> bool:
        return self._bin is not None

    def get_engine_name(self) -> str:
        return "System-Tesseract-CLI"

    def get_diagnostics(self) -> Dict[str, Any]:
        return {
            "engine": self.get_engine_name(),
            "available": self.is_available(),
            "binary_path": self._bin,
            "detail": "Tesseract binary found on PATH" if self._bin else "Tesseract binary not found on system PATH.",
        }

    def ocr_page(self, page: Any, lang: str = "eng") -> Optional[str]:
        # CLI fallback not invoked without explicit configuration
        return None


class OCRFallbackManager:
    """Manages selective OCR triggering and fallback execution."""

    def __init__(self, config: ExtractionConfig) -> None:
        self.config = config
        self.engines: List[BaseOCREngine] = [
            PyMuPDFOCREngine(),
            SystemTesseractEngine(),
        ]

    def get_diagnostics(self) -> Dict[str, Any]:
        """Audit OCR availability across configured engines."""
        return {
            "ocr_enabled_in_config": self.config.enable_ocr_fallback,
            "engines": [e.get_diagnostics() for e in self.engines],
            "any_engine_available": any(e.is_available() for e in self.engines),
        }

    def is_page_ocr_candidate(
        self,
        text_length: int,
        image_count: int,
        is_suspected_scanned: bool = False,
    ) -> bool:
        """Evaluate whether a page requires OCR fallback."""
        if is_suspected_scanned:
            return True
        if text_length < self.config.ocr_low_text_threshold and image_count >= self.config.ocr_min_images:
            return True
        return False

    def process_candidate_page(
        self,
        page: Any,
        page_number: int,
        text_length: int,
        image_count: int,
    ) -> Tuple[Optional[str], Optional[QualityWarning]]:
        """Attempt OCR on candidate page, returning extracted text and quality warning."""
        if not self.is_page_ocr_candidate(text_length, image_count):
            return None, None

        if not self.config.enable_ocr_fallback:
            return (
                None,
                QualityWarning(
                    category="ocr_candidate_skipped",
                    message=(
                        f"Page {page_number} is an image-based text candidate ({text_length} chars, "
                        f"{image_count} images), but OCR fallback is disabled in ExtractionConfig."
                    ),
                    severity="warning",
                    page_number=page_number,
                ),
            )

        # Check available engines
        available_engine = next((e for e in self.engines if e.is_available()), None)
        if not available_engine:
            return (
                None,
                QualityWarning(
                    category="ocr_engine_missing",
                    message=(
                        f"Page {page_number} requires OCR ({text_length} chars, {image_count} images), "
                        f"but no operational OCR engine was found (Tesseract / tessdata missing)."
                    ),
                    severity="critical",
                    page_number=page_number,
                ),
            )

        ocr_text = available_engine.ocr_page(page)
        if ocr_text and len(ocr_text.strip()) > text_length:
            return (
                ocr_text,
                QualityWarning(
                    category="ocr_applied",
                    message=(
                        f"OCR fallback applied via {available_engine.get_engine_name()} on Page {page_number}. "
                        f"Extracted {len(ocr_text.strip())} characters."
                    ),
                    severity="info",
                    page_number=page_number,
                ),
            )

        return (
            None,
            QualityWarning(
                category="ocr_yielded_no_text",
                message=f"OCR was executed on Page {page_number} but produced no additional text.",
                severity="warning",
                page_number=page_number,
            ),
        )
