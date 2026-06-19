"""Import an overhead iPhone photo for workspace calibration (Phase 7).

Thin wrapper around OpenCV image loading; the actual four-corner calibration UI
lives in ``apps.calibrate_workspace``.
"""

from __future__ import annotations

from pathlib import Path


def load_image(path: str | Path):
    """Load an image as a BGR numpy array (OpenCV convention)."""
    import cv2

    img = cv2.imread(str(path))
    if img is None:
        raise FileNotFoundError(f"could not read image {path}")
    return img
