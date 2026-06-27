"""Dry-run summary tests: counts + corner poses without needing calibration."""

import pytest

from painterbot.apps import draw_shape
from painterbot.config import load_workspace_config
from painterbot.drawing.path_sampler import fit_to_paper
from painterbot.drawing.shapes import generate_shape
from painterbot.drawing.stroke_planner import summarize_drawing


def test_summary_reports_counts_without_calibration():
    ws = load_workspace_config()  # no poses captured
    drawing = fit_to_paper(generate_shape("square"), ws.paper)
    text = summarize_drawing(ws, drawing)

    assert "1 stroke(s)" in text
    assert "point(s)" in text
    assert "drawing bounds:" in text
    # Uncalibrated workspace must not raise and must say so.
    assert "not calibrated" in text


def test_summary_shows_corner_poses_when_calibrated(calibrated_workspace):
    ws = calibrated_workspace
    drawing = fit_to_paper(generate_shape("square"), ws.paper)
    text = summarize_drawing(ws, drawing)

    assert "corner poses:" in text
    for name in ("corner_bl", "corner_br", "corner_tl", "corner_tr"):
        assert name in text
    # Renders the actual captured pose values.
    assert "70, 80, 90, 80, 90, 30" in text
    assert "not calibrated" not in text


def test_draw_shape_dry_run_exits_clean_without_arm(capsys):
    """--dry-run returns 0 and prints a summary without connecting an arm."""
    rc = draw_shape.main(["--shape", "star", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "dry run:" in out
    assert "stroke(s)" in out
