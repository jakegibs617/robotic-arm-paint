"""SVG loading tests. Skipped if svgpathtools isn't installed (optional in CI)."""

import pytest

from painterbot.config import REPO_ROOT
from painterbot.drawing.path_sampler import bounding_box

pytest.importorskip("svgpathtools")

from painterbot.drawing.svg_loader import load_svg  # noqa: E402

FIXTURES = REPO_ROOT / "tests" / "fixtures" / "svg"


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


def test_curve_fixture_is_flattened_deterministically():
    [stroke] = load_svg(FIXTURES / "curves.svg", samples_per_path=24)

    assert len(stroke) == 25
    min_x, min_y, max_x, max_y = bounding_box([stroke])
    assert min_x == pytest.approx(10)
    assert max_x == pytest.approx(110)
    assert min_y < max_y


def test_multiple_paths_become_multiple_strokes():
    drawing = load_svg(FIXTURES / "multi_path.svg", samples_per_path=8)

    assert len(drawing) == 2
    assert all(len(stroke) == 9 for stroke in drawing)


def test_path_transform_affects_loaded_bounds():
    drawing = load_svg(FIXTURES / "transformed.svg", samples_per_path=8)

    min_x, min_y, max_x, max_y = bounding_box(drawing)
    assert min_x == pytest.approx(20)
    assert max_x == pytest.approx(40)
    assert min_y == pytest.approx(-50)
    assert max_y == pytest.approx(-30)


def test_empty_and_text_only_fixtures_raise_helpfully():
    for name in ("empty.svg", "text_only.svg"):
        with pytest.raises(ValueError, match="no drawable paths"):
            load_svg(FIXTURES / name)
