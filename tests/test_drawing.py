import math

from painterbot.config import PaperConfig
from painterbot.drawing.path_sampler import (
    bounding_box,
    fit_to_paper,
    resample_stroke,
)
from painterbot.drawing.shapes import SHAPE_NAMES, generate_shape


def test_resample_respects_spacing():
    stroke = [(0, 0), (10, 0)]
    out = resample_stroke(stroke, 1.0)
    # 10mm at 1mm spacing -> at least 11 points, none farther apart than ~1mm.
    assert len(out) >= 11
    for (x0, y0), (x1, y1) in zip(out, out[1:]):
        assert math.hypot(x1 - x0, y1 - y0) <= 1.0 + 1e-6


def test_all_shapes_generate_nonempty():
    for name in SHAPE_NAMES:
        drawing = generate_shape(name)
        assert drawing and all(len(s) >= 2 for s in drawing)


def test_square_is_closed():
    [square] = generate_shape("square")
    assert square[0] == square[-1]


def test_fit_to_paper_stays_within_margins():
    paper = PaperConfig(width_mm=100, height_mm=100, margin_mm=10)
    drawing = generate_shape("circle")
    fitted = fit_to_paper(drawing, paper)
    min_x, min_y, max_x, max_y = bounding_box(fitted)
    assert min_x >= 10 - 1e-6
    assert min_y >= 10 - 1e-6
    assert max_x <= 90 + 1e-6
    assert max_y <= 90 + 1e-6


def test_fit_degenerate_axis_no_nan():
    # A perfectly vertical line has zero width; fitting must not produce NaN.
    paper = PaperConfig(width_mm=100, height_mm=100, margin_mm=10)
    vertical = [[(5, 0), (5, 10)]]
    for preserve in (True, False):
        fitted = fit_to_paper(vertical, paper, preserve_aspect=preserve)
        for x, y in fitted[0]:
            assert math.isfinite(x) and math.isfinite(y)


def test_fit_preserves_aspect_ratio():
    paper = PaperConfig(width_mm=200, height_mm=100, margin_mm=0)
    # A unit square should remain square (equal width/height) after fitting.
    drawing = [[(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]]
    fitted = fit_to_paper(drawing, paper)
    min_x, min_y, max_x, max_y = bounding_box(fitted)
    assert abs((max_x - min_x) - (max_y - min_y)) < 1e-6
