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
