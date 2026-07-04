"""Image-pixel -> paper-mm homography (Phase 7).

Given the four clicked paper corners in an overhead iPhone photo and the known
physical paper size, compute the 3x3 homography that warps image pixels into
paper millimeters. This lets artwork be positioned relative to the real sheet.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np

# Corners are provided in this order to match iphone.default.yaml.
Corner = tuple[float, float]
PAPER_CORNER_ORDER = ("bottom-left", "bottom-right", "top-right", "top-left")


def paper_corners_mm(
    paper_width_mm: float,
    paper_height_mm: float,
) -> list[Corner]:
    """Paper destination corners in BL, BR, TR, TL order."""
    return [
        (0.0, 0.0),
        (paper_width_mm, 0.0),
        (paper_width_mm, paper_height_mm),
        (0.0, paper_height_mm),
    ]


def validate_image_corners(image_corners: Sequence[Corner]) -> list[Corner]:
    """Return four clicked corners or raise with the expected click order."""
    if len(image_corners) != 4:
        raise ValueError(
            "need exactly 4 image corners "
            f"({', '.join(PAPER_CORNER_ORDER)}), got {len(image_corners)}"
        )
    return [(float(x), float(y)) for x, y in image_corners]


def compute_homography(
    image_corners: Sequence[Corner],
    paper_width_mm: float,
    paper_height_mm: float,
) -> np.ndarray:
    """Return the 3x3 homography mapping image pixels to paper millimeters.

    ``image_corners`` must be four ``(x_px, y_px)`` points clicked in the order
    bottom-left, bottom-right, top-right, top-left.
    """
    import cv2

    src = np.asarray(validate_image_corners(image_corners), dtype=np.float32)
    # Paper destination corners in mm, same BL, BR, TR, TL order. Paper y is up.
    dst = np.asarray(paper_corners_mm(paper_width_mm, paper_height_mm), dtype=np.float32)
    return cv2.getPerspectiveTransform(src, dst)


def image_to_paper(homography: np.ndarray, point_px: Corner) -> Corner:
    """Apply a homography to map one image pixel to paper millimeters."""
    x, y = point_px
    vec = homography @ np.array([x, y, 1.0])
    return (float(vec[0] / vec[2]), float(vec[1] / vec[2]))
