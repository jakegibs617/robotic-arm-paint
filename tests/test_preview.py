"""Preview rendering tests. Skipped if matplotlib isn't installed."""

import pytest

pytest.importorskip("matplotlib")

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
