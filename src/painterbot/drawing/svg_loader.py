"""Load an SVG file into flattened paper-space strokes (Phase 6).

Supports the primitives listed in the plan — line, polyline, polygon, rect,
circle, ellipse, and path — by delegating to ``svgpathtools``, which parses all
of these into ``Path`` objects. Curves are flattened by sampling each path at a
fixed number of points per unit length; ``resample_stroke`` downstream enforces
the final spacing.

Note: SVG's y-axis points down. We flip y so the loaded drawing matches our
paper convention (+y up) before it gets fit to the paper.
"""

from __future__ import annotations

from pathlib import Path as FilePath

from painterbot.drawing.path_sampler import Drawing, Stroke


def load_svg(path: str | FilePath, *, samples_per_path: int = 200) -> Drawing:
    """Parse an SVG into a list of strokes (one per continuous subpath).

    ``samples_per_path`` controls curve flattening resolution; the result is
    resampled to the configured spacing later, so a generous value is fine.
    """
    try:
        from svgpathtools import svg2paths
    except ImportError as exc:  # pragma: no cover - depends on env
        raise RuntimeError(
            "svgpathtools is required to load SVGs; `pip install svgpathtools`"
        ) from exc

    paths, _attrs = svg2paths(str(path))

    drawing: Drawing = []
    for sub in paths:
        # Split into continuous runs so disjoint subpaths become separate strokes.
        for continuous in sub.continuous_subpaths():
            length = continuous.length()
            if length == 0:
                continue
            n = max(2, samples_per_path)
            stroke: Stroke = []
            for i in range(n + 1):
                pt = continuous.point(i / n)
                # Flip y: SVG y grows downward, paper y grows upward.
                stroke.append((pt.real, -pt.imag))
            drawing.append(stroke)

    if not drawing:
        raise ValueError(f"no drawable paths found in {path}")
    return drawing
