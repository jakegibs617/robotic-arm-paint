"""Headless tests for image workspace calibration helpers."""

from __future__ import annotations

import yaml
import pytest

from painterbot.apps.calibrate_workspace import (
    _read_calibration_image,
    build_calibration_payload,
    save_calibration_payload,
)
from painterbot.calibration.homography import (
    PAPER_CORNER_ORDER,
    paper_corners_mm,
    validate_image_corners,
)
from painterbot.config import load_workspace_config


def test_corner_order_is_named_and_maps_to_paper_corners():
    assert PAPER_CORNER_ORDER == (
        "bottom-left",
        "bottom-right",
        "top-right",
        "top-left",
    )
    assert paper_corners_mm(210, 297) == [
        (0.0, 0.0),
        (210, 0.0),
        (210, 297),
        (0.0, 297),
    ]


def test_validate_corners_reports_bad_counts():
    with pytest.raises(ValueError, match="need exactly 4 image corners"):
        validate_image_corners([(0, 0), (1, 1), (2, 2)])


def test_build_calibration_payload_includes_homography():
    ws = load_workspace_config()
    corners = [(100.0, 500.0), (700.0, 500.0), (700.0, 100.0), (100.0, 100.0)]

    payload = build_calibration_payload(ws, "photo.jpg", corners)

    assert payload["calibration"]["image"] == "photo.jpg"
    assert payload["calibration"]["image_corners_px"] == corners
    assert len(payload["calibration"]["homography"]) == 3
    assert len(payload["calibration"]["homography"][0]) == 3


def test_save_calibration_payload_writes_yaml(tmp_path):
    out = tmp_path / "nested" / "workspace.yaml"
    save_calibration_payload({"calibration": {"image": "photo.jpg"}}, out)

    assert yaml.safe_load(out.read_text(encoding="utf-8")) == {
        "calibration": {"image": "photo.jpg"}
    }


def test_invalid_image_path_fails_before_window(monkeypatch, tmp_path):
    cv2 = pytest.importorskip("cv2")

    def fake_imread(path):
        return None

    monkeypatch.setattr(cv2, "imread", fake_imread)

    with pytest.raises(FileNotFoundError, match="could not read calibration image"):
        _read_calibration_image(tmp_path / "missing.jpg")
