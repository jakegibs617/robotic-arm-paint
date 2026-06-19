"""Built-in test shapes for Phase 5 (flat drawing without a camera).

Each generator returns a :data:`Drawing` (list of strokes) in an arbitrary unit
square-ish space; ``fit_to_paper`` rescales it to the real drawing area, so the
absolute size here only sets relative proportions.
"""

from __future__ import annotations

import math

from painterbot.drawing.path_sampler import Drawing, Stroke

_SIZE = 100.0  # nominal extent; scaled to paper later


def _square() -> Drawing:
    s = _SIZE
    stroke: Stroke = [(0, 0), (s, 0), (s, s), (0, s), (0, 0)]
    return [stroke]


def _circle(segments: int = 72) -> Drawing:
    r = _SIZE / 2
    cx = cy = r
    stroke: Stroke = [
        (cx + r * math.cos(2 * math.pi * i / segments),
         cy + r * math.sin(2 * math.pi * i / segments))
        for i in range(segments + 1)
    ]
    return [stroke]


def _spiral(turns: int = 4, segments_per_turn: int = 60) -> Drawing:
    r_max = _SIZE / 2
    cx = cy = r_max
    n = turns * segments_per_turn
    stroke: Stroke = []
    for i in range(n + 1):
        t = i / n
        theta = 2 * math.pi * turns * t
        r = r_max * t
        stroke.append((cx + r * math.cos(theta), cy + r * math.sin(theta)))
    return [stroke]


def _star(points: int = 5) -> Drawing:
    r_outer = _SIZE / 2
    r_inner = r_outer * 0.38
    cx = cy = r_outer
    stroke: Stroke = []
    # Start at top, alternate outer/inner vertices.
    for i in range(points * 2 + 1):
        r = r_outer if i % 2 == 0 else r_inner
        theta = math.pi / 2 + math.pi * i / points
        stroke.append((cx + r * math.cos(theta), cy + r * math.sin(theta)))
    return [stroke]


def _line() -> Drawing:
    return [[(0, 0), (_SIZE, _SIZE)]]


_SHAPES = {
    "line": _line,
    "square": _square,
    "circle": _circle,
    "spiral": _spiral,
    "star": _star,
}

SHAPE_NAMES = tuple(_SHAPES)


def generate_shape(name: str) -> Drawing:
    """Return the drawing for a built-in shape name."""
    try:
        return _SHAPES[name]()
    except KeyError:
        raise ValueError(
            f"unknown shape {name!r}; choose from {', '.join(SHAPE_NAMES)}"
        ) from None
