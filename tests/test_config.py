import pytest
from pydantic import ValidationError

from painterbot.config import (
    JointConfig,
    WorkspaceConfig,
    load_arm_config,
    load_workspace_config,
)


def test_arm_config_loads_six_joints():
    cfg = load_arm_config()
    assert len(cfg.joints) == 6
    assert [j.name for j in cfg.joints] == [
        "base", "shoulder", "elbow", "wrist_pitch", "wrist_roll", "gripper",
    ]


def test_home_pose_matches_joint_homes():
    cfg = load_arm_config()
    assert cfg.home_pose == [j.home_deg for j in cfg.joints]


def test_joint_clamp_and_range():
    j = JointConfig(name="x", channel=0, min_deg=10, max_deg=170, home_deg=90)
    assert j.clamp(-5) == 10
    assert j.clamp(200) == 170
    assert j.clamp(45) == 45
    assert j.in_range(45)
    assert not j.in_range(5)


def test_max_must_exceed_min():
    with pytest.raises(ValueError):
        JointConfig(name="x", channel=0, min_deg=100, max_deg=50, home_deg=75)


def test_workspace_default_has_paper_size():
    ws = load_workspace_config()
    assert ws.paper.width_mm > 0
    assert ws.paper.height_mm > 0


def test_missing_pose_raises_helpful_error():
    ws = load_workspace_config()
    with pytest.raises(KeyError):
        ws.pose("pen_down")
    assert not ws.has_pose("pen_down")


def test_workspace_allows_missing_and_null_default_poses():
    ws = WorkspaceConfig.model_validate({"poses": {"home": None}})

    assert ws.poses == {"home": None}
    assert not ws.has_pose("home")


def test_workspace_rejects_too_short_pose():
    with pytest.raises(ValidationError, match="pose 'home': expected 6"):
        WorkspaceConfig.model_validate({"poses": {"home": [90, 90, 90]}})


def test_workspace_rejects_too_long_pose():
    with pytest.raises(ValidationError, match="pose 'home': expected 6"):
        WorkspaceConfig.model_validate({"poses": {"home": [1, 2, 3, 4, 5, 6, 7]}})


def test_workspace_rejects_nonnumeric_pose_value():
    with pytest.raises(ValidationError, match="pose 'pen_up': angle 2 is not numeric"):
        WorkspaceConfig.model_validate(
            {"poses": {"pen_up": [90, 90, "bad", 90, 90, 30]}}
        )


def test_workspace_accepts_valid_pose_shape():
    ws = WorkspaceConfig.model_validate(
        {"poses": {"home": [90, 90, 90, 90, 90, 30]}}
    )

    assert ws.pose("home") == [90, 90, 90, 90, 90, 30]
