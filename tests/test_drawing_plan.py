"""DrawingPlan preflight tests."""

from __future__ import annotations

import pytest

from painterbot.apps import draw_shape, draw_svg
from painterbot.config import REPO_ROOT, load_workspace_config
from painterbot.drawing.plan import DrawingPlan
from painterbot.drawing.shapes import generate_shape
from painterbot.drawing.svg_loader import load_svg


def test_drawing_plan_reports_shape_metrics():
    ws = load_workspace_config()
    plan = DrawingPlan.from_drawing(generate_shape("square"), ws)

    assert plan.fitted_strokes
    assert plan.resampled_strokes
    assert plan.stroke_count == 1
    assert plan.point_count > len(plan.fitted_strokes[0])
    assert plan.estimated_pose_moves == plan.point_count + 4
    assert plan.estimated_servo_commands == plan.estimated_pose_moves * 6
    min_x, min_y, max_x, max_y = plan.bounds
    assert min_x >= ws.paper.margin_mm - 1e-6
    assert min_y >= ws.paper.margin_mm - 1e-6
    assert max_x <= ws.paper.width_mm - ws.paper.margin_mm + 1e-6
    assert max_y <= ws.paper.height_mm - ws.paper.margin_mm + 1e-6


def test_drawing_plan_can_be_built_from_svg_fixture():
    pytest.importorskip("svgpathtools")
    ws = load_workspace_config()
    drawing = load_svg(REPO_ROOT / "examples" / "star.svg")
    plan = DrawingPlan.from_drawing(drawing, ws)

    assert plan.stroke_count == 1
    assert plan.point_count > 2
    assert "estimated servo commands:" in plan.summary(ws)


def test_draw_shape_dry_run_uses_plan_without_connecting(capsys, monkeypatch):
    def fail_connect(*args, **kwargs):
        raise AssertionError("dry run must not connect an arm")

    monkeypatch.setattr("painterbot.control.arm.Arm.connect", fail_connect)

    assert draw_shape.main(["--shape", "line", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "dry run:" in out
    assert "estimated servo commands:" in out


def test_draw_svg_dry_run_uses_plan_without_connecting(capsys, monkeypatch):
    pytest.importorskip("svgpathtools")

    def fail_connect(*args, **kwargs):
        raise AssertionError("dry run must not connect an arm")

    monkeypatch.setattr("painterbot.control.arm.Arm.connect", fail_connect)

    assert draw_svg.main([str(REPO_ROOT / "examples" / "star.svg"), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "dry run:" in out
    assert "estimated servo commands:" in out
