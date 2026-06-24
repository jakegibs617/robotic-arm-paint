"""Homography tests. Skipped if OpenCV isn't installed (core dep, optional in CI)."""

import numpy as np
import pytest

pytest.importorskip("cv2")

from painterbot.calibration.homography import (  # noqa: E402
    compute_homography,
    image_to_paper,
)

# A4-ish sheet.
PAPER_W = 210.0
PAPER_H = 297.0

# Four clicked corners in image pixels, in BL, BR, TR, TL order. Image y grows
# downward, so the "bottom" corners have the larger y values.
IMAGE_CORNERS = [
    (100.0, 500.0),  # BL
    (700.0, 500.0),  # BR
    (700.0, 100.0),  # TR
    (100.0, 100.0),  # TL
]

# Paper-mm destinations the four corners must map to, same order.
PAPER_CORNERS = [
    (0.0, 0.0),
    (PAPER_W, 0.0),
    (PAPER_W, PAPER_H),
    (0.0, PAPER_H),
]


def test_corners_round_trip_to_paper_mm():
    """Each clicked image corner maps onto its known paper-mm corner."""
    h = compute_homography(IMAGE_CORNERS, PAPER_W, PAPER_H)
    for image_pt, expected_mm in zip(IMAGE_CORNERS, PAPER_CORNERS):
        got = image_to_paper(h, image_pt)
        np.testing.assert_allclose(got, expected_mm, atol=1e-3)


def test_image_center_maps_to_paper_center():
    """An interior point (the centroid) maps to the centre of the sheet."""
    h = compute_homography(IMAGE_CORNERS, PAPER_W, PAPER_H)
    center_px = (
        sum(x for x, _ in IMAGE_CORNERS) / 4,
        sum(y for _, y in IMAGE_CORNERS) / 4,
    )
    got = image_to_paper(h, center_px)
    np.testing.assert_allclose(got, (PAPER_W / 2, PAPER_H / 2), atol=1e-3)


def test_paper_y_points_up_from_image_y_down():
    """Image y increases downward; paper y increases upward.

    The image-bottom corners (large pixel y) sit at paper y == 0, and the
    image-top corners (small pixel y) sit at paper y == height.
    """
    h = compute_homography(IMAGE_CORNERS, PAPER_W, PAPER_H)
    bl_mm = image_to_paper(h, IMAGE_CORNERS[0])  # large pixel y
    tl_mm = image_to_paper(h, IMAGE_CORNERS[3])  # small pixel y
    assert bl_mm[1] == pytest.approx(0.0, abs=1e-3)
    assert tl_mm[1] == pytest.approx(PAPER_H, abs=1e-3)


def test_rejects_wrong_corner_count():
    with pytest.raises(ValueError, match="4 image corners"):
        compute_homography(IMAGE_CORNERS[:3], PAPER_W, PAPER_H)
