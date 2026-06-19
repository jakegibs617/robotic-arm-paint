"""Helpers for the MVP manual pose-calibration workflow (Phase 5).

The actual capture happens interactively in ``apps.manual_jog`` (``save
corner_bl`` etc.). This module just documents the required poses and validates a
workspace config has everything the stroke planner needs.
"""

from __future__ import annotations

from painterbot.config import WorkspaceConfig

# Poses the flat-drawing pipeline depends on.
REQUIRED_POSES = (
    "home",
    "pen_up",
    "pen_down",
    "corner_bl",
    "corner_br",
    "corner_tl",
    "corner_tr",
)


def missing_poses(ws: WorkspaceConfig) -> list[str]:
    """Return the names of calibration poses not yet captured."""
    return [name for name in REQUIRED_POSES if not ws.has_pose(name)]


def is_calibrated(ws: WorkspaceConfig) -> bool:
    return not missing_poses(ws)
