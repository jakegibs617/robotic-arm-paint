"""Drawing execution preflight safety tests."""

from __future__ import annotations

import pytest
import yaml

from painterbot.apps import draw_shape, draw_svg
from painterbot.config import load_workspace_config
from painterbot.drawing.plan import DrawingPlan, DrawingPreflightError
from painterbot.drawing.shapes import generate_shape


def test_preflight_detects_missing_calibration_names():
    ws = load_workspace_config()
    plan = DrawingPlan.from_drawing(generate_shape("square"), ws)

    with pytest.raises(DrawingPreflightError) as exc:
        plan.validate_for_execution(ws)

    text = str(exc.value)
    assert "missing calibration poses:" in text
    assert "home" in text
    assert "corner_tr" in text


def test_preflight_detects_empty_drawing(calibrated_workspace):
    plan = DrawingPlan.from_drawing([], calibrated_workspace)

    with pytest.raises(DrawingPreflightError, match="no drawable strokes"):
        plan.validate_for_execution(calibrated_workspace)


def test_preflight_detects_degenerate_path(calibrated_workspace):
    plan = DrawingPlan.from_drawing([[(1, 1), (1, 1)]], calibrated_workspace)

    with pytest.raises(DrawingPreflightError, match="degenerate"):
        plan.validate_for_execution(calibrated_workspace)


def test_plan_detects_unusable_paper_margin():
    ws = load_workspace_config()
    ws.paper.width_mm = 20
    ws.paper.height_mm = 20
    ws.paper.margin_mm = 10

    with pytest.raises(ValueError, match="paper margin leaves no usable drawing area"):
        DrawingPlan.from_drawing(generate_shape("square"), ws)


def test_draw_shape_preflight_failure_happens_before_connect(monkeypatch):
    def fail_connect(*args, **kwargs):
        raise AssertionError("preflight must fail before arm connection")

    monkeypatch.setattr("painterbot.control.arm.Arm.connect", fail_connect)

    with pytest.raises(DrawingPreflightError, match="missing calibration poses"):
        draw_shape.main(["--shape", "square", "--mock"])


def test_draw_svg_preflight_failure_happens_before_connect(tmp_path, monkeypatch):
    pytest.importorskip("svgpathtools")
    svg = tmp_path / "line.svg"
    svg.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg">'
        '<line x1="0" y1="0" x2="10" y2="10"/></svg>',
        encoding="utf-8",
    )

    def fail_connect(*args, **kwargs):
        raise AssertionError("preflight must fail before arm connection")

    monkeypatch.setattr("painterbot.control.arm.Arm.connect", fail_connect)

    with pytest.raises(DrawingPreflightError, match="missing calibration poses"):
        draw_svg.main([str(svg), "--mock"])


def test_draw_shape_with_custom_calibrated_workspace_can_connect(tmp_path):
    pose = [90, 90, 90, 90, 90, 30]
    workspace = tmp_path / "workspace.yaml"
    workspace.write_text(
        yaml.safe_dump(
            {
                "poses": {
                    "home": pose,
                    "pen_up": [90, 90, 90, 95, 90, 30],
                    "pen_down": pose,
                    "corner_bl": [70, 80, 90, 80, 90, 30],
                    "corner_br": [110, 80, 90, 80, 90, 30],
                    "corner_tl": [70, 100, 90, 80, 90, 30],
                    "corner_tr": [110, 100, 90, 80, 90, 30],
                }
            }
        ),
        encoding="utf-8",
    )

    assert draw_shape.main(
        [
            "--shape",
            "line",
            "--mock",
            "--workspace-config",
            str(workspace),
        ]
    ) == 0
