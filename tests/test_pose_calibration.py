"""Manual pose calibration session tests."""

from __future__ import annotations

import pytest

from painterbot.calibration.pose_calibration import (
    REQUIRED_POSES,
    CalibrationSession,
)
from painterbot.config import load_workspace_config


def test_session_reports_required_missing_and_complete(arm_config):
    ws = load_workspace_config()
    session = CalibrationSession(ws, arm_config)

    assert tuple(session.missing_poses()) == REQUIRED_POSES
    assert not session.is_complete

    for name in REQUIRED_POSES:
        session.capture(name, arm_config.home_pose)

    assert session.missing_poses() == []
    assert session.is_complete


def test_session_captures_current_arm_pose(mock_arm, arm_config):
    ws = load_workspace_config()
    session = CalibrationSession(ws, arm_config)
    mock_arm.move_to_pose([100, 100, 100, 100, 100, 40], interpolate=False)

    captured = session.capture_current("pen_up", mock_arm)

    assert captured == [100, 100, 100, 100, 100, 40]
    assert ws.poses["pen_up"] == captured


def test_session_accepts_custom_pose_names(arm_config):
    ws = load_workspace_config()
    session = CalibrationSession(ws, arm_config)

    session.capture("inspection_pose", arm_config.home_pose)

    assert ws.poses["inspection_pose"] == arm_config.home_pose


def test_session_validates_pose_length(arm_config):
    session = CalibrationSession(load_workspace_config(), arm_config)

    with pytest.raises(ValueError, match="needs 6 angles, got 3"):
        session.capture("home", [90, 90, 90])


def test_session_validates_numeric_and_safe_ranges(arm_config):
    session = CalibrationSession(load_workspace_config(), arm_config)

    with pytest.raises(ValueError, match="joint elbow is not numeric"):
        session.capture("home", [90, 90, "nope", 90, 90, 30])
    with pytest.raises(ValueError, match="joint base=200 outside safe range 0..180"):
        session.capture("home", [200, 90, 90, 90, 90, 30])


def test_session_reports_existing_pose_errors(arm_config):
    ws = load_workspace_config()
    ws.poses["home"] = [90, 90]
    ws.poses["pen_up"] = [90, 90, 90, 90, 90, 30]
    session = CalibrationSession(ws, arm_config)

    errors = session.validate_existing()

    assert len(errors) == 1
    assert "pose 'home' needs 6 angles" in errors[0]
