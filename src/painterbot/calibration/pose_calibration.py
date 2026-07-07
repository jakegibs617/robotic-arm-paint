"""Helpers for the MVP manual pose-calibration workflow (Phase 5).

The actual capture happens interactively in ``apps.manual_jog`` (``save
corner_bl`` etc.). This module just documents the required poses and validates a
workspace config has everything the stroke planner needs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from painterbot.config import ArmConfig, WorkspaceConfig

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


@dataclass
class CalibrationSession:
    """Stateful manual calibration workflow around a workspace config."""

    workspace: WorkspaceConfig
    arm_config: ArmConfig
    required_poses: tuple[str, ...] = REQUIRED_POSES

    def missing_poses(self) -> list[str]:
        return [name for name in self.required_poses if not self.workspace.has_pose(name)]

    @property
    def is_complete(self) -> bool:
        return not self.missing_poses()

    def capture_current(self, name: str, arm) -> list[float]:
        """Capture ``arm.pose`` under ``name`` after validating it."""
        return self.capture(name, arm.pose)

    def capture(self, name: str, pose: Sequence[float]) -> list[float]:
        """Capture a required or custom pose into the workspace config."""
        validated = self.validate_pose(name, pose)
        self.workspace.poses[name] = validated
        return validated

    def validate_pose(self, name: str, pose: Sequence[float]) -> list[float]:
        expected = len(self.arm_config.joints)
        if len(pose) != expected:
            raise ValueError(f"pose {name!r} needs {expected} angles, got {len(pose)}")
        values: list[float] = []
        for joint, raw in zip(self.arm_config.joints, pose):
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise ValueError(f"pose {name!r} joint {joint.name} is not numeric")
            angle = float(raw)
            if not math.isfinite(angle):
                raise ValueError(f"pose {name!r} joint {joint.name} is not finite")
            if not joint.in_range(angle):
                raise ValueError(
                    f"pose {name!r} joint {joint.name}={angle:g} outside safe range "
                    f"{joint.min_deg:g}..{joint.max_deg:g}"
                )
            values.append(angle)
        return values

    def validate_existing(self) -> list[str]:
        """Return validation errors for captured poses without mutating them."""
        errors: list[str] = []
        for name, pose in self.workspace.poses.items():
            if pose is None:
                continue
            try:
                self.validate_pose(name, pose)
            except ValueError as exc:
                errors.append(str(exc))
        return errors
