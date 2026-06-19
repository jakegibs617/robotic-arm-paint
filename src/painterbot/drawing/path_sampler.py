"""Geometry types and helpers for turning paths into sampled paper-space strokes.

Conventions
-----------
* A ``Point`` is an ``(x, y)`` tuple in **paper millimeters**, origin at the
  bottom-left corner of the drawing area, +x right, +y up.
* A ``Stroke`` is an ordered list of points drawn with the pen down.
* A ``Drawing`` is a list of strokes; the pen lifts between them.
"""

from __future__ import annotations

import math
from typing import Iterable

from painterbot.config import PaperConfig

Point = tuple[float, float]
Stroke = list[Point]
Drawing = list[Stroke]


def resample_stroke(stroke: Stroke, spacing_mm: float) -> Stroke:
    """Resample a polyline so consecutive points are <= ``spacing_mm`` apart.

    Keeps endpoints; inserts points along long segments. Curves should already
    be flattened into many short segments before calling this.
    """
    if spacing_mm <= 0 or len(stroke) < 2:
        return list(stroke)

    out: Stroke = [stroke[0]]
    for (x0, y0), (x1, y1) in zip(stroke, stroke[1:]):
        seg = math.hypot(x1 - x0, y1 - y0)
        if seg <= spacing_mm:
            out.append((x1, y1))
            continue
        n = int(math.ceil(seg / spacing_mm))
        for i in range(1, n + 1):
            t = i / n
            out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    return out


def bounding_box(drawing: Iterable[Stroke]) -> tuple[float, float, float, float]:
    """Return ``(min_x, min_y, max_x, max_y)`` over all points."""
    xs: list[float] = []
    ys: list[float] = []
    for stroke in drawing:
        for x, y in stroke:
            xs.append(x)
            ys.append(y)
    if not xs:
        return (0.0, 0.0, 0.0, 0.0)
    return (min(xs), min(ys), max(xs), max(ys))


def fit_to_paper(
    drawing: Drawing,
    paper: PaperConfig,
    *,
    preserve_aspect: bool = True,
) -> Drawing:
    """Scale + center a drawing to fit the usable paper area (inside margins).

    Returns a new drawing in paper millimeters. Aspect ratio is preserved by
    default so artwork isn't distorted.
    """
    min_x, min_y, max_x, max_y = bounding_box(drawing)
    src_w = max_x - min_x
    src_h = max_y - min_y
    usable_w = paper.width_mm - 2 * paper.margin_mm
    usable_h = paper.height_mm - 2 * paper.margin_mm
    if usable_w <= 0 or usable_h <= 0:
        raise ValueError("paper margin leaves no usable drawing area")

    if src_w == 0 and src_h == 0:
        return [list(s) for s in drawing]

    # A degenerate axis (zero span, e.g. a perfectly vertical line) has no
    # meaningful scale of its own; leave it None and borrow the other axis's
    # scale so we never multiply 0 by infinity (which yields NaN).
    sx = usable_w / src_w if src_w > 0 else None
    sy = usable_h / src_h if src_h > 0 else None
    if preserve_aspect:
        finite = [s for s in (sx, sy) if s is not None]
        sx = sy = min(finite) if finite else 1.0
    else:
        sx = sx if sx is not None else (sy if sy is not None else 1.0)
        sy = sy if sy is not None else (sx if sx is not None else 1.0)

    out_w = src_w * sx
    out_h = src_h * sy
    # Offset to center within the usable area, then shift past the margin.
    off_x = paper.margin_mm + (usable_w - out_w) / 2
    off_y = paper.margin_mm + (usable_h - out_h) / 2

    scaled: Drawing = []
    for stroke in drawing:
        scaled.append(
            [
                (off_x + (x - min_x) * sx, off_y + (y - min_y) * sy)
                for x, y in stroke
            ]
        )
    return scaled
