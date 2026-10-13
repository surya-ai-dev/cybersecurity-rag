"""Modular document extraction package for Cybersecurity RAG."""

from app.ingestion.extraction.config import ExtractionConfig
from app.ingestion.extraction.diagram_analyzer import (
    BaseDiagramAnalyzer,
    PassthroughDiagramAnalyzer,
)
from app.ingestion.extraction.document_corrections import (
    CorrectionResult,
    apply_document_corrections,
)
from app.ingestion.extraction.figure_filter import (
    FigureFilter,
    FigureFilterConfig,
    FilterDecision,
    FilterResult,
    evaluate_asset,
)
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
from app.ingestion.extraction.ocr_engine import (
    BaseOCREngine,
    OCRFallbackManager,
    PyMuPDFOCREngine,
    SystemTesseractEngine,
)
from app.ingestion.extraction.pipeline import DocumentExtractionPipeline
from app.ingestion.extraction.preflight import (
    PagePreflightInfo,
    PreflightInspector,
    PreflightReport,
)
from app.ingestion.extraction.pymupdf_parser import PyMuPDFParser
from app.ingestion.extraction.quality_checker import ExtractionQualityAssessor

__all__ = [
    "ExtractionConfig",
    "DocumentExtractionPipeline",
    "PreflightInspector",
    "PreflightReport",
    "PagePreflightInfo",
    "DoclingParser",
    "PyMuPDFParser",
    "BaseOCREngine",
    "PyMuPDFOCREngine",
    "SystemTesseractEngine",
    "OCRFallbackManager",
    "BaseDiagramAnalyzer",
    "PassthroughDiagramAnalyzer",
    "ExtractionQualityAssessor",
    "FigureFilter",
    "FigureFilterConfig",
    "FilterDecision",
    "FilterResult",
    "evaluate_asset",
    "CorrectionResult",
    "apply_document_corrections",
    "ExtractedDocument",
    "ExtractedPage",
    "TextBlock",
    "TableData",
    "TableCell",
    "FigureAsset",
    "QualityWarning",
    "BoundingBox",
    "BlockType",
    "ExtractionMethod",
]

