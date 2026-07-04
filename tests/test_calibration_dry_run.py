"""Calibration dry-run command tests."""

from __future__ import annotations

import yaml

from painterbot.apps import calibrate_workspace


def test_calibration_dry_run_runs_without_image_or_hardware(capsys, monkeypatch):
    def fail_click(*args, **kwargs):
        raise AssertionError("dry run must not open the image click UI")

    monkeypatch.setattr(calibrate_workspace, "_click_corners", fail_click)

    assert calibrate_workspace.main(["--dry-run"]) == 0

    out = capsys.readouterr().out
    assert "manual calibration dry run:" in out
    assert "workspace source:" in out
    assert "save target:" in out
    assert "home: missing" in out
    assert "corner_tr: missing" in out
    assert "complete: no" in out


def test_calibration_dry_run_reports_existing_completion(tmp_path, capsys):
    workspace = tmp_path / "workspace.yaml"
    pose = [90, 90, 90, 90, 90, 30]
    workspace.write_text(
        yaml.safe_dump(
            {
                "poses": {
                    "home": pose,
                    "pen_up": pose,
                    "pen_down": pose,
                    "corner_bl": pose,
                    "corner_br": pose,
                    "corner_tl": pose,
                    "corner_tr": pose,
                }
            }
        ),
        encoding="utf-8",
    )

    assert calibrate_workspace.main(
        ["--dry-run", "--workspace-config", str(workspace)]
    ) == 0

    out = capsys.readouterr().out
    assert f"workspace source: {workspace}" in out
    assert f"save target: {workspace}" in out
    assert "home: set" in out
    assert "complete: yes" in out


def test_calibration_requires_image_without_dry_run():
    try:
        calibrate_workspace.main([])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("missing --image should exit via argparse")
