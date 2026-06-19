"""Workspace calibration (Phase 7).

For the MVP, calibration is *manual pose capture* via the jog CLI (see
``apps.manual_jog``). The homography module here supports the later iPhone-photo
four-corner workflow that maps image pixels to paper coordinates.
"""

from painterbot.calibration.homography import (
    compute_homography,
    image_to_paper,
)

__all__ = ["compute_homography", "image_to_paper"]
