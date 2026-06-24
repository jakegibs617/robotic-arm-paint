"""Map paper-space strokes onto servo poses and execute them on the arm.

The MVP deliberately avoids inverse kinematics. Instead we rely on manual pose
calibration: the user jogs the arm to the four corners of the drawing area (at
pen-down height) and to ``pen_up`` / ``pen_down`` reference poses, saved in the
workspace config. Any paper coordinate is then mapped to a servo pose by
**bilinear interpolation** between the four corner poses, and the pen is raised
by adding the captured ``pen_up - pen_down`` delta.

This is approximate (servo angle is not linear in cartesian space), but for a
small flat drawing area it is good enough to get the first square on paper, and
it needs no kinematic model of the specific arm kit.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from painterbot.config import WorkspaceConfig
from painterbot.control.arm import Arm
from painterbot.drawing.path_sampler import Drawing, Point, resample_stroke

logger = logging.getLogger("painterbot.planner")

_CORNERS = ("corner_bl", "corner_br", "corner_tl", "corner_tr")
_REQUIRED_POSES = (*_CORNERS, "pen_up", "pen_down", "home")


def summarize_drawing(workspace: WorkspaceConfig, drawing: Drawing) -> str:
    """Human-readable dry-run summary of a planned drawing.

    Reports stroke and (resampled) point counts, the drawing's bounding box,
    and the servo pose mapped to each paper corner. Intentionally does **not**
    require calibration: if poses are missing it says so instead of raising, so
    you can sanity-check artwork before capturing poses on real hardware.
    """
    spacing = workspace.drawing.point_spacing_mm
    strokes = [s for s in drawing if len(s) >= 2]
    n_points = sum(len(resample_stroke(s, spacing)) for s in strokes)

    paper = workspace.paper
    lines = [
        f"dry run: {len(strokes)} stroke(s), {n_points} point(s) "
        f"after resampling at {spacing:g} mm spacing",
        f"paper: {paper.width_mm:g} x {paper.height_mm:g} mm",
    ]

    pts = [p for s in strokes for p in s]
    if pts:
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        lines.append(
            f"drawing bounds: x {min(xs):.1f}..{max(xs):.1f} mm, "
            f"y {min(ys):.1f}..{max(ys):.1f} mm"
        )

    missing = [n for n in _REQUIRED_POSES if not workspace.has_pose(n)]
    if missing:
        lines.append("corner poses: not calibrated (missing " + ", ".join(missing) + ")")
    else:
        corners = {
            "corner_bl": (0.0, 0.0),
            "corner_br": (paper.width_mm, 0.0),
            "corner_tl": (0.0, paper.height_mm),
            "corner_tr": (paper.width_mm, paper.height_mm),
        }
        lines.append("corner poses:")
        for name, (x, y) in corners.items():
            pose_str = ", ".join(f"{a:g}" for a in workspace.pose(name))
            lines.append(f"  {name} ({x:g}, {y:g}) -> [{pose_str}]")
    return "\n".join(lines)


class StrokePlanner:
    """Plans and executes a drawing on the arm using calibrated reference poses."""

    def __init__(self, arm: Arm, workspace: WorkspaceConfig) -> None:
        self.arm = arm
        self.ws = workspace

    # -- calibration access --------------------------------------------------

    def require_poses(self) -> None:
        """Raise a clear error if calibration poses are missing."""
        missing = [n for n in _REQUIRED_POSES if not self.ws.has_pose(n)]
        if missing:
            raise RuntimeError(
                "missing calibration poses: "
                + ", ".join(missing)
                + ". Capture them with the jog CLI (e.g. `save corner_bl`) and "
                "save the workspace config before drawing."
            )

    @property
    def _pen_delta(self) -> list[float]:
        up = self.ws.pose("pen_up")
        down = self.ws.pose("pen_down")
        return [u - d for u, d in zip(up, down)]

    # -- coordinate mapping --------------------------------------------------

    def paper_to_pose(self, point: Point, *, pen_down: bool = True) -> list[float]:
        """Bilinear-interpolate a servo pose for a paper-mm coordinate."""
        x, y = point
        w = self.ws.paper.width_mm
        h = self.ws.paper.height_mm
        u = x / w if w else 0.0
        v = y / h if h else 0.0

        bl = self.ws.pose("corner_bl")
        br = self.ws.pose("corner_br")
        tl = self.ws.pose("corner_tl")
        tr = self.ws.pose("corner_tr")

        pose = []
        for i in range(len(bl)):
            bottom = bl[i] + (br[i] - bl[i]) * u
            top = tl[i] + (tr[i] - tl[i]) * u
            pose.append(bottom + (top - bottom) * v)

        if not pen_down:
            pose = [p + d for p, d in zip(pose, self._pen_delta)]
        return pose

    # -- execution -----------------------------------------------------------

    def execute(self, drawing: Drawing) -> int:
        """Draw ``drawing`` on the arm. Returns the number of strokes drawn.

        For a hardware-free run, connect the arm with the mock backend: every
        move is mapped and logged but nothing is sent over serial.
        """
        self.require_poses()
        spacing = self.ws.drawing.point_spacing_mm
        settle = self.ws.drawing.pen_settle_s

        self.arm.home()
        strokes_drawn = 0
        for s_idx, stroke in enumerate(drawing):
            if len(stroke) < 2:
                continue
            pts = resample_stroke(stroke, spacing)
            logger.info("stroke %d: %d points", s_idx, len(pts))

            # Move above the start with the pen up, then lower.
            self.arm.move_to_pose(self.paper_to_pose(pts[0], pen_down=False))
            self.arm.move_to_pose(self.paper_to_pose(pts[0], pen_down=True))
            time.sleep(settle)

            for pt in pts[1:]:
                self.arm.move_to_pose(self.paper_to_pose(pt, pen_down=True))

            # Lift the pen before travelling to the next stroke.
            self.arm.move_to_pose(self.paper_to_pose(pts[-1], pen_down=False))
            time.sleep(settle)
            strokes_drawn += 1

        self.arm.home()
        logger.info("drawing complete: %d strokes", strokes_drawn)
        return strokes_drawn
