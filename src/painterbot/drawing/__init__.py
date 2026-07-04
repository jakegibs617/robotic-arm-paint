"""Drawing pipeline: shapes/SVG -> sampled paper-space strokes -> servo poses."""

from painterbot.drawing.shapes import generate_shape
from painterbot.drawing.path_sampler import Point, Stroke, Drawing, fit_to_paper
from painterbot.drawing.plan import DrawingPlan
from painterbot.drawing.stroke_planner import StrokePlanner

__all__ = [
    "Point",
    "Stroke",
    "Drawing",
    "DrawingPlan",
    "generate_shape",
    "fit_to_paper",
    "StrokePlanner",
]
