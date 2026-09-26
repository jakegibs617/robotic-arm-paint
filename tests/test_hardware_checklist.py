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


def test_hardware_checklist_pins_the_measured_usb_adapter_facts():
    # These were guesses (CH34x, /dev/tty.usbserial-*) and were wrong. Pin the
    # measured values so a doc regression fails a test instead of costing
    # another bring-up session.
    data = json.loads(
        (REPO_ROOT / "docs" / "hardware_bringup_checklist.json").read_text(
            encoding="utf-8"
        )
    )
    serial_item = {item["id"]: item for item in data["items"]}["HW-SERIAL-001"]

    assert serial_item["expected"]["usb_vid"] == 0x1A86
    assert serial_item["expected"]["usb_pid"] == 0x55D3
    assert "CH343" in serial_item["expected"]["usb_chip_family"]
    assert "/dev/cu.usbmodem*" in serial_item["expected"]["device_globs"]
    assert serial_item["expected"]["use_callout_node"] is True
    # No /dev/tty.* glob should ever come back: that node blocks on open.
    assert not any(
        glob.startswith("/dev/tty") for glob in serial_item["expected"]["device_globs"]
    )


def test_hardware_checklist_tracks_the_scan_and_motion_probes():
    data = json.loads(
        (REPO_ROOT / "docs" / "hardware_bringup_checklist.json").read_text(
            encoding="utf-8"
        )
    )
    by_id = {item["id"]: item for item in data["items"]}

    assert by_id["HW-SCAN-001"]["expected"]["model_number"] == 777
    assert by_id["HW-SCAN-001"]["record"]["answered_ids"] == [1]
    # The motion probe stays blocked while the bench servo is under-voltage.
    assert by_id["HW-MOTION-001"]["status"] == "blocked"
    assert by_id["HW-MOTION-001"]["expected"]["max_delta_counts"] == 200
    assert by_id["HW-MOTION-001"]["expected"]["start_with_zero_delta"] is True


def test_hardware_checklist_warns_that_a_full_2s_lipo_exceeds_the_servo_limit():
    # The servo's own max-voltage protection reads 8.0V; a 2S LiPo off the
    # charger is 8.4V. This is the kind of fact that costs a servo if it is
    # only ever written in prose.
    data = json.loads(
        (REPO_ROOT / "docs" / "hardware_bringup_checklist.json").read_text(
            encoding="utf-8"
        )
    )
    power = {item["id"]: item for item in data["items"]}["HW-POWER-001"]

    assert power["expected"]["servo_protection_window_v"] == [4.0, 8.0]
    assert power["expected"]["lipo_2s_full_charge_exceeds_limit"] is True
