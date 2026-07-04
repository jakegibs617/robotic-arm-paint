"""Preflight representation for fitted and resampled drawings."""

from __future__ import annotations

from dataclasses import dataclass

from painterbot.calibration.pose_calibration import REQUIRED_POSES
from painterbot.config import WorkspaceConfig
from painterbot.drawing.path_sampler import (
    Drawing,
    bounding_box,
    fit_to_paper,
    resample_stroke,
)


class DrawingPreflightError(ValueError):
    """Raised when a drawing cannot be safely executed."""


@dataclass(frozen=True)
class DrawingPlan:
    """A drawing fitted to paper, with resampled execution strokes."""

    fitted_strokes: Drawing
    resampled_strokes: Drawing
    spacing_mm: float

    @classmethod
    def from_drawing(cls, drawing: Drawing, workspace: WorkspaceConfig) -> "DrawingPlan":
        fitted = fit_to_paper(drawing, workspace.paper)
        spacing = workspace.drawing.point_spacing_mm
        resampled = [
            resample_stroke(stroke, spacing)
            for stroke in fitted
            if len(stroke) >= 2
        ]
        return cls(
            fitted_strokes=fitted,
            resampled_strokes=resampled,
            spacing_mm=spacing,
        )

    @property
    def stroke_count(self) -> int:
        return len(self.resampled_strokes)

    @property
    def point_count(self) -> int:
        return sum(len(stroke) for stroke in self.resampled_strokes)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return bounding_box(self.resampled_strokes)

    @property
    def estimated_pose_moves(self) -> int:
        if not self.resampled_strokes:
            return 0
        stroke_moves = sum(len(stroke) + 2 for stroke in self.resampled_strokes)
        return stroke_moves + 2

    @property
    def estimated_servo_commands(self) -> int:
        return self.estimated_pose_moves * 6

    def validate_for_execution(self, workspace: WorkspaceConfig) -> None:
        """Raise before arm connection when execution would be unsafe."""
        missing = [name for name in REQUIRED_POSES if not workspace.has_pose(name)]
        if missing:
            raise DrawingPreflightError(
                "missing calibration poses: " + ", ".join(missing)
            )
        if self.stroke_count == 0:
            raise DrawingPreflightError("drawing has no drawable strokes")
        min_x, min_y, max_x, max_y = self.bounds
        if min_x == max_x and min_y == max_y:
            raise DrawingPreflightError("drawing is degenerate after fitting")

    def summary(self, workspace: WorkspaceConfig) -> str:
        paper = workspace.paper
        lines = [
            f"dry run: {self.stroke_count} stroke(s), {self.point_count} point(s) "
            f"after resampling at {self.spacing_mm:g} mm spacing",
            f"paper: {paper.width_mm:g} x {paper.height_mm:g} mm",
            f"estimated servo commands: {self.estimated_servo_commands}",
        ]
        if self.point_count:
            min_x, min_y, max_x, max_y = self.bounds
            lines.append(
                f"drawing bounds: x {min_x:.1f}..{max_x:.1f} mm, "
                f"y {min_y:.1f}..{max_y:.1f} mm"
            )
        return "\n".join(lines)
