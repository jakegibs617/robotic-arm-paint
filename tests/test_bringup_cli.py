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
    # Must NOT send the operator to the power supply: this adapter powers the
    # servo's logic from USB, so silence is a baud/wiring/ID symptom.
    assert "baud-sweep" in out
    assert "cannot power a servo" not in out


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


def test_probing_subcommands_refuse_the_mock_protocol_instead_of_crashing(capsys):
    # The shipped config is protocol: mock / port: null, so with no flags at all
    # open_backend returned a MockSerialBackend, which has no register-level
    # methods -- the probing subcommands died on a raw AttributeError. This is
    # the silent-mock trap arriving through the no-port door.
    for argv in (["scan", "--ids", "0-2"], ["identify", "--id", "1"],
                 ["nudge", "--id", "1", "--counts", "0"]):
        assert bringup.main(argv) == 2, argv
        err = capsys.readouterr().err
        assert "mock" in err
        assert "--protocol sts3215" in err


def test_identify_and_nudge_reject_out_of_range_ids(capsys):
    # _sts_packet masks servo_id & 0xFF, so --id 300 silently addresses servo 44.
    assert bringup.main(["--mock", "identify", "--id", "300"]) == 2
    assert "0..253" in capsys.readouterr().err
    assert bringup.main(["--mock", "nudge", "--id", "254", "--counts", "0"]) == 2
    assert "broadcast" in capsys.readouterr().err


def test_ping_exits_nonzero_on_a_real_bus_when_no_servo_responds(monkeypatch, capsys):
    # scan/identify/nudge all return 1 on failure so the powered checklist is
    # scriptable; ping was the odd one out.
    from painterbot.control.serial_controller import (
        PySerialBackend,
        get_encoder,
        get_feedback,
    )
    from painterbot.testing.fake_sts3215 import FakeSTS3215Serial

    monkeypatch.setattr(
        bringup,
        "open_backend",
        lambda **kwargs: PySerialBackend(
            "/dev/fake",
            encoder=get_encoder("sts3215"),
            feedback=get_feedback("sts3215"),
            serial_obj=FakeSTS3215Serial({}),
        ),
    )

    rc = bringup.main(["--port", "/dev/fake", "--protocol", "sts3215", "ping"])

    assert rc == 1
    assert "0/6 servos responded" in capsys.readouterr().out


def test_mock_ping_stays_a_zero_exit_smoke_test():
    # The mock reports None for servos never commanded; that is the mock's
    # nature, not a hardware fault, so it must not read as a failed checklist.
    assert bringup.main(["--mock", "ping"]) == 0


def test_scan_reports_an_echoing_link_without_a_traceback(capsys, monkeypatch):
    from painterbot.control import bus_scan as bus_scan_module
    from painterbot.control.serial_controller import ServoEchoError

    def boom(*_args, **_kwargs):
        raise ServoEchoError("servo 1: reply is an echo of our own request")

    monkeypatch.setattr(bringup, "scan_bus", boom)

    assert bringup.main(["--mock", "scan", "--ids", "0-2"]) == 1
    assert "echo" in capsys.readouterr().out


def test_probe_timeout_zero_is_honoured_not_treated_as_absent():
    args = bringup.build_parser().parse_args(["scan", "--probe-timeout", "0"])
    assert args.probe_timeout == 0.0
