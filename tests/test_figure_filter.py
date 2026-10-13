"""Unit tests for the isolated FigureFilter module."""

import os
from pathlib import Path
import tempfile
import unittest

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from app.ingestion.extraction.figure_filter import (
    FigureFilter,
    FigureFilterConfig,
    FilterDecision,
    FilterResult,
    evaluate_asset,
)


def _create_test_png(
    file_path: Path,
    width: int,
    height: int,
    fill_mode: str = "solid",
) -> None:
    """Helper to create synthetic test PNG files with controlled color properties."""
    if fill_mode == "solid":
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, width, height), False)
        pix.clear_with(255)  # All white: 1 unique byte value
    elif fill_mode == "gradient":
        # Multi-color gradient to produce high byte variance
        samples = bytes(i % 256 for i in range(width * height * 3))
        pix = fitz.Pixmap(fitz.csRGB, width, height, samples, False)
    else:
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, width, height), False)
    pix.save(str(file_path))


class TestFigureFilter(unittest.TestCase):
    """Test suite validating all multi-criteria figure-filtering rules."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.config = FigureFilterConfig()
        self.filter = FigureFilter(self.config)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_solid_color_mask_rejected(self) -> None:
        """A solid-color rectangle (1 unique byte value) must be rejected."""
        img_path = self.temp_path / "solid_mask.png"
        _create_test_png(img_path, width=200, height=200, fill_mode="solid")
        meta = {"width": 200, "height": 200, "bbox": {"left": 100.0, "top": 100.0}}

        result = self.filter.evaluate(img_path, meta)
        self.assertFalse(result.is_retained)
        self.assertEqual(result.decision, FilterDecision.DISCARD)
        self.assertEqual(result.reason, "solid_color_mask_zero_variance")
        self.assertLessEqual(result.metrics["unique_colors"], 1)

    def test_decorative_margin_bar_rejected(self) -> None:
        """A high aspect-ratio bar positioned in the left page margin (<30 pt) must be rejected."""
        img_path = self.temp_path / "margin_bar.png"
        _create_test_png(img_path, width=10, height=120, fill_mode="gradient")
        meta = {"width": 10, "height": 120, "bbox": {"left": 15.0, "top": 100.0}}

        result = self.filter.evaluate(img_path, meta)
        self.assertFalse(result.is_retained)
        self.assertEqual(result.decision, FilterDecision.DISCARD)
        self.assertEqual(result.reason, "decorative_margin_bar")
        self.assertGreater(result.metrics["aspect_ratio"], 8.0)

    def test_extreme_aspect_ratio_hairline_rejected(self) -> None:
        """A hairline separator strip (aspect ratio > 8.0) located anywhere on the page must be rejected."""
        img_path = self.temp_path / "hairline_rule.png"
        _create_test_png(img_path, width=500, height=10, fill_mode="gradient")
        meta = {"width": 500, "height": 10, "bbox": {"left": 100.0, "top": 400.0}}

        result = self.filter.evaluate(img_path, meta)
        self.assertFalse(result.is_retained)
        self.assertEqual(result.decision, FilterDecision.DISCARD)
        self.assertEqual(result.reason, "extreme_aspect_ratio_hairline")
        self.assertGreater(result.metrics["aspect_ratio"], 8.0)

    def test_undersized_plain_icon_rejected(self) -> None:
        """A tiny sub-dimension icon (< 40x40 px) with low color entropy must be rejected."""
        img_path = self.temp_path / "tiny_plain_icon.png"
        _create_test_png(img_path, width=24, height=24, fill_mode="solid")
        meta = {"width": 24, "height": 24, "bbox": {"left": 200.0, "top": 200.0}}

        result = self.filter.evaluate(img_path, meta)
        self.assertFalse(result.is_retained)
        self.assertEqual(result.decision, FilterDecision.DISCARD)

    def test_small_rich_security_symbol_preserved(self) -> None:
        """A small badge/icon (< 40x40 px) with high color entropy (>=8 colors) must be preserved."""
        img_path = self.temp_path / "security_badge.png"
        _create_test_png(img_path, width=32, height=32, fill_mode="gradient")
        meta = {"width": 32, "height": 32, "bbox": {"left": 150.0, "top": 150.0}}

        result = self.filter.evaluate(img_path, meta)
        self.assertTrue(result.is_retained)
        self.assertEqual(result.decision, FilterDecision.KEEP)
        self.assertEqual(result.reason, "preserved_small_security_symbol")
        self.assertGreaterEqual(result.metrics["unique_colors"], 8)

    def test_normal_informative_figure_preserved(self) -> None:
        """A genuine diagram of standard size, low aspect ratio, and high color count must be preserved."""
        img_path = self.temp_path / "informative_chart.png"
        _create_test_png(img_path, width=400, height=300, fill_mode="gradient")
        meta = {"width": 400, "height": 300, "bbox": {"left": 80.0, "top": 200.0}}

        result = self.filter.evaluate(img_path, meta)
        self.assertTrue(result.is_retained)
        self.assertEqual(result.decision, FilterDecision.KEEP)
        self.assertEqual(result.reason, "retained_genuine_visual_diagram")

    def test_borderline_and_missing_inputs_handled_safely(self) -> None:
        """Missing files, None inputs, or empty metadata dictionaries must be handled gracefully without exceptions."""
        # 1. Non-existent file
        res_missing = self.filter.evaluate(Path("non_existent_image.png"), None)
        self.assertFalse(res_missing.is_retained)
        self.assertEqual(res_missing.reason, "file_missing_or_unreadable")

        # 2. None file path
        res_none = self.filter.evaluate(None, {})
        self.assertFalse(res_none.is_retained)
        self.assertEqual(res_none.reason, "file_missing_or_unreadable")

        # 3. Existing file but missing/empty metadata
        img_path = self.temp_path / "no_meta_diagram.png"
        _create_test_png(img_path, width=200, height=150, fill_mode="gradient")
        res_no_meta = self.filter.evaluate(img_path, {})
        self.assertTrue(res_no_meta.is_retained)
        self.assertEqual(res_no_meta.metrics["width"], 200)
        self.assertEqual(res_no_meta.metrics["height"], 150)

    def test_repeat_evaluation_deterministic(self) -> None:
        """Evaluating the exact same image multiple times must produce identical decisions and metrics."""
        img_path = self.temp_path / "deterministic_chart.png"
        _create_test_png(img_path, width=300, height=200, fill_mode="gradient")
        meta = {"width": 300, "height": 200, "bbox": {"left": 90.0, "top": 150.0}}

        res1 = self.filter.evaluate(img_path, meta)
        res2 = self.filter.evaluate(img_path, meta)
        self.assertEqual(res1, res2)
        self.assertEqual(res1.to_dict(), res2.to_dict())

    def test_evaluate_asset_legacy_unpacking_compatibility(self) -> None:
        """The evaluate_asset() convenience function supports 3-tuple unpacking: (is_retained, reason, metrics)."""
        img_path = self.temp_path / "unpack_test.png"
        _create_test_png(img_path, width=300, height=200, fill_mode="gradient")
        meta = {"width": 300, "height": 200, "bbox": {"left": 90.0, "top": 150.0}}

        is_retained, reason, metrics = evaluate_asset(img_path, meta, self.config)
        self.assertTrue(is_retained)
        self.assertEqual(reason, "retained_genuine_visual_diagram")
        self.assertIn("aspect_ratio", metrics)
        self.assertIn("unique_colors", metrics)


if __name__ == "__main__":
    unittest.main()
