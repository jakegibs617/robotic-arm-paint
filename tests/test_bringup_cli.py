"""Bring-up CLI tests: config inspection without serial hardware."""

from __future__ import annotations

from painterbot.apps import bringup


def test_bringup_lists_configured_servo_ids_without_connection(capsys, monkeypatch):
    def fail_connect(*args, **kwargs):
        raise AssertionError("bring-up list must not connect to serial")

    monkeypatch.setattr("painterbot.control.arm.Arm.connect", fail_connect)
    rc = bringup.main(["list-joints"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "protocol: mock" in out
    assert "feedback: no" in out
    assert "configured servo IDs:" in out
    assert "0: base" in out
    assert "5: gripper" in out


def test_bringup_defaults_to_list_joints(capsys):
    assert bringup.main([]) == 0
    out = capsys.readouterr().out
    assert "configured servo IDs:" in out


def test_bringup_protocols_reports_feedback_support(capsys):
    assert bringup.main(["protocols"]) == 0
    out = capsys.readouterr().out
    assert "mock feedback=no" in out
    assert "ascii_servo feedback=no" in out
    assert "sts3215 feedback=yes" in out


def test_bringup_ping_reads_configured_servos_in_mock_mode(capsys):
    rc = bringup.main(["--mock", "ping"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "0: base" in out
    assert "servos responded" in out


def test_bringup_assign_id_succeeds_in_mock_mode(capsys):
    rc = bringup.main(["--mock", "assign-id", "--old-id", "1", "--new-id", "0"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "connect exactly ONE servo" in out
    assert "[OK]" in out
    assert "servo 1 -> 0" in out
    assert "verify with `bringup ping`" in out


def test_bringup_assign_id_reports_invalid_id_without_raising(capsys):
    rc = bringup.main(["--mock", "assign-id", "--old-id", "1", "--new-id", "9001"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "[FAIL]" in out
    assert "out of range" in out


def test_bringup_mock_session_prints_no_hardware_workflow(capsys):
    assert bringup.main(["mock-session", "--shape", "square"]) == 0

    out = capsys.readouterr().out
    assert "mock hardware session transcript:" in out
    assert "painterbot-calibrate --dry-run" in out
    assert "painterbot-draw-shape --shape square --dry-run" in out
    assert "painterbot-draw-shape --shape square --preview out/mock-session.png" in out
    assert "--mock --workspace-config out/mock-calibrated-workspace.yaml" in out
    assert "expected output:" in out
    assert "real configs are not modified" in out


# -- bus scan / identification / motion probe subcommands ---------------------


def test_ports_lists_serial_devices(capsys, monkeypatch):
    from painterbot.control import serial_link

    monkeypatch.setattr(
        serial_link,
        "list_serial_ports",
        lambda comports=None: (
            serial_link.SerialPortInfo(
                device="/dev/cu.usbmodem5B790320481",
                description="USB Single Serial",
                vid=0x1A86,
                pid=0x55D3,
            ),
        ),
    )

    assert bringup.main(["ports"]) == 0
    out = capsys.readouterr().out
    assert "/dev/cu.usbmodem5B790320481" in out
    assert "1a86:55d3" in out


def test_mock_scan_reports_the_simulated_servo(capsys):
    # --mock deliberately runs the real sts3215 framing against a fake port, so
    # the scan exercises encode/parse end to end rather than a stubbed backend.
    assert bringup.main(["--mock", "scan", "--ids", "0-5"]) == 0
    out = capsys.readouterr().out
    assert "id 1:" in out
    assert "model=" in out
    assert "1/6 IDs answered" in out


def test_mock_scan_prints_the_effective_connection_settings(capsys):
    bringup.main(["--mock", "scan", "--ids", "1"])
    out = capsys.readouterr().out
    # A silent mock must never again masquerade as a successful hardware run.
    assert "protocol=sts3215" in out
    assert "mock" in out.lower()


def test_scan_on_a_silent_bus_exits_nonzero_with_a_power_hint(capsys):
    assert bringup.main(["--mock", "--mock-empty-bus", "scan", "--ids", "0-5"]) == 1
    out = capsys.readouterr().out
    assert "no servo answered" in out
    assert "7.4V" in out


def test_mock_scan_baud_sweep_reports_each_attempt(capsys):
    assert bringup.main(["--mock", "scan", "--ids", "1", "--baud-sweep"]) == 0
    out = capsys.readouterr().out
    assert "1000000" in out


def test_mock_identify_reports_one_servo(capsys):
    assert bringup.main(["--mock", "identify", "--id", "1"]) == 0
    assert "id 1:" in capsys.readouterr().out


def test_identify_reports_a_missing_servo_and_exits_nonzero(capsys):
    assert bringup.main(["--mock", "identify", "--id", "3"]) == 1
    assert "did not answer" in capsys.readouterr().out


def test_mock_nudge_reports_the_achieved_delta(capsys):
    assert bringup.main(["--mock", "nudge", "--id", "1", "--counts", "100"]) == 0
    out = capsys.readouterr().out
    assert "success" in out
    assert "+100" in out


def test_nudge_refuses_a_delta_above_the_cap(capsys):
    assert bringup.main(["--mock", "nudge", "--id", "1", "--counts", "9999"]) == 1
    assert "cap" in capsys.readouterr().out


def test_nudge_defaults_to_a_small_delta():
    parser = bringup.build_parser()
    args = parser.parse_args(["nudge", "--id", "1"])
    assert 0 < args.counts <= 60


def test_baud_and_protocol_flags_override_the_config():
    parser = bringup.build_parser()
    args = parser.parse_args(
        ["--baud", "115200", "--protocol", "sts3215", "--port", "/dev/cu.x", "ping"]
    )
    assert args.baud == 115200
    assert args.protocol == "sts3215"


def test_connection_flags_default_to_none_so_config_wins():
    args = bringup.build_parser().parse_args(["list-joints"])
    assert args.baud is None
    assert args.protocol is None


def test_scan_rejects_the_broadcast_id(capsys):
    assert bringup.main(["--mock", "scan", "--ids", "254"]) == 2
    assert "broadcast" in capsys.readouterr().err
