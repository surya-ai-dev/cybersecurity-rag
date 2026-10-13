"""Replaceable interface and passthrough handler for diagram and figure understanding.

Preserves figure assets, page regions, and detected captions without downloading
heavy local vision-language models or invoking external paid APIs.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from app.ingestion.extraction.config import ExtractionConfig
from app.ingestion.extraction.models import FigureAsset


class BaseDiagramAnalyzer(ABC):
    """Abstract interface for multimodal figure and diagram analysis."""

    @abstractmethod
    def analyze_diagram(
        self,
        figure: FigureAsset,
        page_context: str = "",
    ) -> FigureAsset:
        """Process figure asset and return enriched FigureAsset with structured description."""
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Return operational status and engine configuration."""
        pass


class PassthroughDiagramAnalyzer(BaseDiagramAnalyzer):
    """Default diagram analyzer preserving image assets without claiming unverified understanding."""

    def __init__(self, config: ExtractionConfig) -> None:
        self.config = config

    def analyze_diagram(
        self,
        figure: FigureAsset,
        page_context: str = "",
    ) -> FigureAsset:
        """Preserve asset references while explicitly marking analysis status as pending."""
        # Never claim a diagram is understood just because its image was extracted
        figure.status = "EXTRACTED_VLM_PENDING"
        figure.diagram_analysis = (
            f"Image asset preserved at '{figure.image_path}'. "
            "Vision-Language Model (VLM) diagram understanding is pending. "
            "No local weights or external APIs were invoked."
        )
        return figure

    def get_status(self) -> Dict[str, Any]:
        return {
            "mode": "passthrough",
            "vlm_model": None,
            "status": "ASSETS_PRESERVED_VLM_PENDING",
            "note": "Diagram understanding interface ready. VLM inference is deliberately disabled to preserve RAM/storage.",
        }


class VLMDiagramAnalyzerStub(BaseDiagramAnalyzer):
    """Stub demonstrating pluggable integration for future Vision-Language Models."""

    def __init__(self, model_name: str = "future-vlm") -> None:
        self.model_name = model_name

    def analyze_diagram(
        self,
        figure: FigureAsset,
        page_context: str = "",
    ) -> FigureAsset:
        figure.status = "VLM_STUB_UNCONFIGURED"
        figure.diagram_analysis = f"Stub ready for {self.model_name}; model execution deferred."
        return figure

    def get_status(self) -> Dict[str, Any]:
        return {
            "mode": "stub",
            "vlm_model": self.model_name,
            "status": "UNCONFIGURED",
        }
