"""SVG loading tests. Skipped if svgpathtools isn't installed (optional in CI)."""

import pytest

from painterbot.config import REPO_ROOT

pytest.importorskip("svgpathtools")

from painterbot.drawing.svg_loader import load_svg  # noqa: E402


def test_load_example_star():
    drawing = load_svg(REPO_ROOT / "examples" / "star.svg")
    assert len(drawing) == 1
    stroke = drawing[0]
    assert len(stroke) > 2


def test_y_axis_flipped_to_paper_convention(tmp_path):
    # A line going DOWN in SVG (y increases) should go UP in paper space.
    svg = tmp_path / "line.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<line x1="0" y1="0" x2="0" y2="10"/></svg>'
    )
    [stroke] = load_svg(str(svg))
    assert stroke[0][1] > stroke[-1][1]


def test_missing_paths_raises(tmp_path):
    svg = tmp_path / "empty.svg"
    svg.write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>')
    with pytest.raises(ValueError):
        load_svg(str(svg))
