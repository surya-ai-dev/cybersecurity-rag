"""Multi-criteria image and figure filtering module for document extraction.

Evaluates extracted image assets using dimensional, geometric, spatial, and color-entropy
heuristics to discard decorative artifacts (solid masks, template margin bars, hairline
rules, and blank spacers) while preserving meaningful diagrams and rich security symbols.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union

try:
    import pymupdf as fitz
except ImportError:
    import fitz


class FilterDecision(str, Enum):
    """Decision indicating whether an image asset should be kept or discarded."""

    KEEP = "keep"
    DISCARD = "discard"


@dataclass
class FigureFilterConfig:
    """Configurable multi-criteria image filtering thresholds."""

    min_file_size_bytes: int = 1000
    min_width_px: int = 40
    min_height_px: int = 40
    min_unique_colors: int = 2
    max_aspect_ratio: float = 8.0
    margin_threshold_pt: float = 30.0
    preserve_security_symbols: bool = True
    rich_symbol_min_colors: int = 8


class FilterResult:
    """Evaluation result for an individual figure asset."""

    def __init__(
        self,
        is_retained: bool,
        reason: str,
        metrics: Dict[str, Any],
        decision: Optional[FilterDecision] = None,
    ) -> None:
        self.is_retained = is_retained
        self.decision = decision or (FilterDecision.KEEP if is_retained else FilterDecision.DISCARD)
        self.reason = reason
        self.metrics = metrics

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to a serialized dictionary."""
        return {
            "decision": self.decision.value if isinstance(self.decision, FilterDecision) else str(self.decision),
            "is_retained": self.is_retained,
            "reason": self.reason,
            "metrics": self.metrics,
        }

    def __iter__(self) -> Iterator[Any]:
        """Support legacy 3-tuple unpacking: is_retained, reason, metrics = evaluate_asset(...)."""
        return iter((self.is_retained, self.reason, self.metrics))

    def __repr__(self) -> str:
        return f"FilterResult(decision={self.decision.value}, is_retained={self.is_retained}, reason='{self.reason}')"

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, FilterResult):
            return (
                self.is_retained == other.is_retained
                and self.decision == other.decision
                and self.reason == other.reason
                and self.metrics == other.metrics
            )
        return False


class FigureFilter:
    """Evaluates image assets against multi-criteria quality thresholds."""

    def __init__(self, config: Optional[FigureFilterConfig] = None) -> None:
        self.config = config or FigureFilterConfig()

    def evaluate(
        self,
        file_path: Optional[Union[str, Path]],
        fig_meta: Optional[Dict[str, Any]] = None,
    ) -> FilterResult:
        """Evaluate an extracted image file and its layout metadata.

        Returns a FilterResult containing the decision (keep/discard), a machine-readable
        reason code, and the computed metrics.
        """
        path_obj = Path(file_path) if file_path else None
        meta = fig_meta or {}

        # 1. Missing or unreadable file validation
        if not path_obj or not path_obj.is_file():
            metrics = {
                "file_size": 0,
                "width": meta.get("width", 0),
                "height": meta.get("height", 0),
                "aspect_ratio": 0.0,
                "unique_colors": 0,
            }
            return FilterResult(
                is_retained=False,
                reason="file_missing_or_unreadable",
                metrics=metrics,
                decision=FilterDecision.DISCARD,
            )

        try:
            size = path_obj.stat().st_size
        except OSError:
            size = 0

        # 2. Extract dimensions from metadata, falling back to pixmap dimensions
        width = int(meta.get("width", 0) or 0)
        height = int(meta.get("height", 0) or 0)

        # 3. Read image samples for color-entropy analysis
        pix = None
        unique_bytes = 0
        try:
            pix = fitz.Pixmap(str(path_obj))
            unique_bytes = len(set(pix.samples))
            if width <= 0:
                width = int(pix.width)
            if height <= 0:
                height = int(pix.height)
        except Exception:
            unique_bytes = 0
        finally:
            pix = None

        # 4. Resolve spatial bounding box coordinates
        bbox = meta.get("bbox")
        left = 999.0
        if bbox is not None:
            if isinstance(bbox, dict):
                left = float(bbox.get("left", 999.0))
            elif hasattr(bbox, "left"):
                left = float(getattr(bbox, "left", 999.0))

        # 5. Compute aspect ratio
        min_dim = min(width, height)
        max_dim = max(width, height)
        if min_dim > 0:
            aspect_ratio = round(max_dim / min_dim, 2)
        else:
            aspect_ratio = 999.0

        metrics = {
            "file_size": size,
            "width": width,
            "height": height,
            "aspect_ratio": aspect_ratio,
            "unique_colors": unique_bytes,
        }

        # ---------------------------------------------------------------------
        # Evaluation Rules
        # ---------------------------------------------------------------------

        # Rule 1: Solid-color rectangle check (pure masks with 0 or 1 unique byte value)
        if unique_bytes <= 1:
            return FilterResult(
                is_retained=False,
                reason="solid_color_mask_zero_variance",
                metrics=metrics,
                decision=FilterDecision.DISCARD,
            )

        # Rule 2: Decorative margin bar (placed in page template margin with high aspect ratio)
        if left < self.config.margin_threshold_pt and aspect_ratio > self.config.max_aspect_ratio:
            return FilterResult(
                is_retained=False,
                reason="decorative_margin_bar",
                metrics=metrics,
                decision=FilterDecision.DISCARD,
            )

        # Rule 3: Extreme aspect ratio hairline strip (> max_aspect_ratio)
        if aspect_ratio > self.config.max_aspect_ratio:
            return FilterResult(
                is_retained=False,
                reason="extreme_aspect_ratio_hairline",
                metrics=metrics,
                decision=FilterDecision.DISCARD,
            )

        # Rule 4: Sub-dimension tiny icon (< min_width or < min_height)
        if width < self.config.min_width_px or height < self.config.min_height_px:
            if self.config.preserve_security_symbols and unique_bytes >= self.config.rich_symbol_min_colors:
                return FilterResult(
                    is_retained=True,
                    reason="preserved_small_security_symbol",
                    metrics=metrics,
                    decision=FilterDecision.KEEP,
                )
            return FilterResult(
                is_retained=False,
                reason="sub_dimension_decorative_icon",
                metrics=metrics,
                decision=FilterDecision.DISCARD,
            )

        # Rule 5: File size check (< min_file_size_bytes)
        if size < self.config.min_file_size_bytes:
            if self.config.preserve_security_symbols and unique_bytes >= self.config.rich_symbol_min_colors:
                return FilterResult(
                    is_retained=True,
                    reason="preserved_small_rich_symbol",
                    metrics=metrics,
                    decision=FilterDecision.KEEP,
                )
            return FilterResult(
                is_retained=False,
                reason=f"file_size_under_{self.config.min_file_size_bytes}_bytes",
                metrics=metrics,
                decision=FilterDecision.DISCARD,
            )

        # Rule 6: Retained genuine visual diagram / chart
        return FilterResult(
            is_retained=True,
            reason="retained_genuine_visual_diagram",
            metrics=metrics,
            decision=FilterDecision.KEEP,
        )


def evaluate_asset(
    file_path: Optional[Union[str, Path]],
    fig_meta: Optional[Dict[str, Any]] = None,
    config: Optional[FigureFilterConfig] = None,
) -> FilterResult:
    """Convenience module function for evaluating an image asset.

    Returns a FilterResult that can be accessed via attributes (.is_retained, .decision, .reason)
    or unpacked as a 3-tuple (is_retained, reason, metrics).
    """
    filter_instance = FigureFilter(config)
    return filter_instance.evaluate(file_path, fig_meta)
