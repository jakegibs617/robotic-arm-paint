"""Workspace calibration (Phase 7).

For the MVP, calibration is *manual pose capture* via the jog CLI (see
``apps.manual_jog``). The homography module here supports the later iPhone-photo
four-corner workflow that maps image pixels to paper coordinates.
"""

from painterbot.calibration.homography import (
    PAPER_CORNER_ORDER,
    compute_homography,
    image_to_paper,
    paper_corners_mm,
    validate_image_corners,
)
from painterbot.calibration.pose_calibration import (
    REQUIRED_POSES,
    CalibrationSession,
    is_calibrated,
    missing_poses,
)

__all__ = [
    "CalibrationSession",
    "PAPER_CORNER_ORDER",
    "REQUIRED_POSES",
    "compute_homography",
    "image_to_paper",
    "is_calibrated",
    "missing_poses",
    "paper_corners_mm",
    "validate_image_corners",
]
