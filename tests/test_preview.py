"""Preview rendering tests. Skipped if matplotlib isn't installed."""

import pytest

pytest.importorskip("matplotlib")

import matplotlib.image as mpimg  # noqa: E402
import numpy as np  # noqa: E402

from painterbot.config import PaperConfig  # noqa: E402
from painterbot.drawing.preview import save_preview  # noqa: E402


def _square(side=50.0, origin=(10.0, 10.0)):
    x, y = origin
    return [[(x, y), (x + side, y), (x + side, y + side), (x, y + side), (x, y)]]


def test_save_preview_writes_png(tmp_path):
    out = tmp_path / "preview.png"
    paper = PaperConfig(width_mm=150.0, height_mm=150.0)
    result = save_preview(_square(), paper, out)

    assert result == out
    assert out.exists()
    assert out.stat().st_size > 0
    # PNG magic number.
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_save_preview_creates_parent_dirs(tmp_path):
    out = tmp_path / "nested" / "dir" / "preview.png"
    save_preview(_square(), PaperConfig(), out)
    assert out.exists()


def test_save_preview_handles_degenerate_strokes(tmp_path):
    """Strokes with fewer than two points are skipped, not fatal."""
    out = tmp_path / "preview.png"
    drawing = [[(5.0, 5.0)], _square()[0]]  # one single-point stroke, one square
    result = save_preview(drawing, PaperConfig(), out)
    assert result.exists()


def _rgb(path):
    img = mpimg.imread(path)
    return img[..., :3]


def _non_white_fraction(path) -> float:
    rgb = _rgb(path)
    return float(np.mean(np.any(rgb < 0.97, axis=2)))


def test_preview_for_representative_shape_is_non_empty(tmp_path):
    out = tmp_path / "square.png"
    save_preview(_square(side=80.0, origin=(20.0, 20.0)), PaperConfig(), out)

    assert _non_white_fraction(out) > 0.01


def test_preview_empty_drawing_still_shows_paper_bounds(tmp_path):
    out = tmp_path / "empty.png"
    save_preview([], PaperConfig(width_mm=120, height_mm=80, margin_mm=10), out)

    assert out.exists()
    assert _non_white_fraction(out) > 0.005


def test_preview_drawing_adds_colored_pixels_beyond_empty_paper(tmp_path):
    paper = PaperConfig(width_mm=120, height_mm=80, margin_mm=10)
    empty = tmp_path / "empty.png"
    drawn = tmp_path / "drawn.png"
    save_preview([], paper, empty)
    save_preview([[(10, 10), (110, 70), (10, 70)]], paper, drawn)

    empty_rgb = _rgb(empty)
    drawn_rgb = _rgb(drawn)
    empty_colored = empty_rgb[..., 2] > empty_rgb[..., 0] + 0.05
    drawn_colored = drawn_rgb[..., 2] > drawn_rgb[..., 0] + 0.05
    assert int(np.sum(drawn_colored)) > int(np.sum(empty_colored)) + 100
