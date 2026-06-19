import pytest

from painterbot.drawing.path_sampler import fit_to_paper
from painterbot.drawing.shapes import generate_shape
from painterbot.drawing.stroke_planner import StrokePlanner


def test_corners_map_to_corner_poses(mock_arm, calibrated_workspace):
    ws = calibrated_workspace
    planner = StrokePlanner(mock_arm, ws)
    w, h = ws.paper.width_mm, ws.paper.height_mm

    assert planner.paper_to_pose((0, 0)) == ws.pose("corner_bl")
    assert planner.paper_to_pose((w, 0)) == ws.pose("corner_br")
    assert planner.paper_to_pose((0, h)) == ws.pose("corner_tl")
    assert planner.paper_to_pose((w, h)) == ws.pose("corner_tr")


def test_center_is_average_of_corners(mock_arm, calibrated_workspace):
    ws = calibrated_workspace
    planner = StrokePlanner(mock_arm, ws)
    center = planner.paper_to_pose((ws.paper.width_mm / 2, ws.paper.height_mm / 2))
    corners = [ws.pose(n) for n in ("corner_bl", "corner_br", "corner_tl", "corner_tr")]
    expected = [sum(vals) / 4 for vals in zip(*corners)]
    assert center == pytest.approx(expected)


def test_pen_up_applies_lift_delta(mock_arm, calibrated_workspace):
    ws = calibrated_workspace
    planner = StrokePlanner(mock_arm, ws)
    down = planner.paper_to_pose((0, 0), pen_down=True)
    up = planner.paper_to_pose((0, 0), pen_down=False)
    delta = [u - d for u, d in zip(up, down)]
    expected = [u - d for u, d in zip(ws.pose("pen_up"), ws.pose("pen_down"))]
    assert delta == pytest.approx(expected)


def test_execute_requires_calibration(mock_arm):
    from painterbot.config import load_workspace_config

    planner = StrokePlanner(mock_arm, load_workspace_config())
    with pytest.raises(RuntimeError):
        planner.execute(generate_shape("square"))


def test_execute_square_end_to_end(mock_arm, calibrated_workspace):
    ws = calibrated_workspace
    # Speed up the test: no settle/step delays.
    ws.drawing.pen_settle_s = 0.0
    mock_arm.config.motion.step_delay_s = 0.0

    drawing = fit_to_paper(generate_shape("square"), ws.paper)
    planner = StrokePlanner(mock_arm, ws)
    n = planner.execute(drawing)

    assert n == 1
    # Commands were issued and the arm returned home at the end.
    assert len(mock_arm.backend.history) > 0
    assert mock_arm.pose == pytest.approx(ws.pose("home"))
