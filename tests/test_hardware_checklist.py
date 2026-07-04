"""Machine-readable hardware bring-up checklist tests."""

from __future__ import annotations

import json

from painterbot.config import REPO_ROOT


def test_hardware_checklist_is_machine_trackable():
    path = REPO_ROOT / "docs" / "hardware_bringup_checklist.json"
    data = json.loads(path.read_text(encoding="utf-8"))

    assert "docs/hardware_identification.md" in data["sources"]
    assert "docs/calibration.md" in data["sources"]
    ids = {item["id"] for item in data["items"]}
    assert {
        "HW-POWER-001",
        "HW-SERIAL-001",
        "HW-SERIAL-002",
        "HW-ID-001",
        "HW-PING-001",
        "HW-RANGE-001",
        "HW-CAL-001",
    } <= ids
    for item in data["items"]:
        assert item["status"] in data["status_values"]
        assert item["hardware_required"] is True
        assert item["source"].startswith("docs/")
        assert "record" in item


def test_hardware_checklist_tracks_ids_ranges_and_calibration_poses():
    data = json.loads(
        (REPO_ROOT / "docs" / "hardware_bringup_checklist.json").read_text(
            encoding="utf-8"
        )
    )
    by_id = {item["id"]: item for item in data["items"]}

    assert by_id["HW-SERIAL-002"]["expected"]["baud"] == 1000000
    assert by_id["HW-SERIAL-002"]["expected"]["protocol"] == "sts3215"
    assert by_id["HW-ID-001"]["expected"]["ids"] == {
        "base": 0,
        "shoulder": 1,
        "elbow": 2,
        "wrist_pitch": 3,
        "wrist_roll": 4,
        "gripper": 5,
    }
    assert "base" in by_id["HW-RANGE-001"]["record"]["ranges_deg"]
    assert by_id["HW-CAL-001"]["expected"]["poses"] == [
        "home",
        "pen_up",
        "pen_down",
        "corner_bl",
        "corner_br",
        "corner_tl",
        "corner_tr",
    ]
