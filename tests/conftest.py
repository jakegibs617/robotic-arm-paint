"""Shared fixtures: an arm on the mock backend and a fully-calibrated workspace."""

import pytest

from painterbot.config import load_arm_config, load_workspace_config
from painterbot.control.arm import Arm


@pytest.fixture
def arm_config():
    return load_arm_config()


@pytest.fixture
def mock_arm(arm_config):
    arm = Arm.connect(arm_config, mock=True)
    yield arm
    arm.close()


@pytest.fixture
def calibrated_workspace():
    """Workspace config with synthetic-but-valid calibration poses.

    Corner poses vary base/shoulder linearly across the sheet so bilinear
    interpolation produces distinct, monotonic poses; pen_up adds a wrist delta.
    """
    ws = load_workspace_config()
    home = [90, 90, 90, 90, 90, 30]
    ws.poses.update(
        {
            "home": home,
            "pen_down": [90, 90, 90, 80, 90, 30],
            "pen_up": [90, 90, 90, 95, 90, 30],  # +15 wrist_pitch lift
            "corner_bl": [70, 80, 90, 80, 90, 30],
            "corner_br": [110, 80, 90, 80, 90, 30],
            "corner_tl": [70, 100, 90, 80, 90, 30],
            "corner_tr": [110, 100, 90, 80, 90, 30],
        }
    )
    return ws
