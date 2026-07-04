"""iPhone-photo workspace calibration (Phase 7).

    python -m painterbot.apps.calibrate_workspace --image ./iphone_photo.jpg

Opens the overhead photo, lets you click the four paper corners (BL, BR, TR,
TL), computes the image->paper homography, and writes the result into
``configs/workspace.calibrated.yaml``.

This is a Phase 7 feature and is not required for the first flat-drawing demo,
which uses manual pose capture from the jog CLI instead. The clicking UI needs a
display (it won't run headless).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from painterbot.calibration.homography import (
    PAPER_CORNER_ORDER,
    compute_homography,
    validate_image_corners,
)
from painterbot.calibration.pose_calibration import CalibrationSession
from painterbot.config import (
    default_workspace_save_path,
    load_arm_config,
    load_workspace_config,
    resolve_workspace_config_path,
)


def _click_corners(image_path: Path) -> list[tuple[float, float]]:
    import cv2

    img = _read_calibration_image(image_path)

    corners: list[tuple[float, float]] = []

    def on_click(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(corners) < 4:
            corners.append((float(x), float(y)))
            cv2.circle(img, (x, y), 6, (0, 0, 255), -1)
            cv2.imshow("calibrate", img)

    cv2.namedWindow("calibrate")
    cv2.setMouseCallback("calibrate", on_click)
    print("Click the four paper corners in order: " + ", ".join(PAPER_CORNER_ORDER))
    cv2.imshow("calibrate", img)
    while len(corners) < 4:
        if cv2.waitKey(20) & 0xFF == 27:  # Esc to abort
            break
    cv2.destroyAllWindows()

    return validate_image_corners(corners)


def _read_calibration_image(image_path: Path):
    import cv2

    img = cv2.imread(str(image_path))
    if img is None:
        raise FileNotFoundError(f"could not read calibration image {image_path}")
    return img


def build_calibration_payload(ws, image_path: Path, corners: list[tuple[float, float]]):
    corners = validate_image_corners(corners)
    h = compute_homography(corners, ws.paper.width_mm, ws.paper.height_mm)
    payload = ws.model_dump()
    payload["calibration"] = {
        "image": str(image_path),
        "image_corners_px": corners,
        "homography": h.tolist(),
    }
    return payload


def save_calibration_payload(payload: dict, out: Path) -> Path:
    import yaml

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, sort_keys=False)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="iPhone-photo workspace calibration.")
    parser.add_argument("--image", type=Path)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print manual calibration steps and current completion state",
    )
    parser.add_argument(
        "--arm-config",
        type=Path,
        default=None,
        help="path to arm config YAML (default: configs/arm.default.yaml)",
    )
    parser.add_argument(
        "--workspace-config",
        type=Path,
        default=None,
        help="workspace config to inspect or save",
    )
    args = parser.parse_args(argv)

    if args.dry_run:
        return _dry_run(args)
    if args.image is None:
        parser.error("--image is required unless --dry-run is set")

    ws = load_workspace_config(args.workspace_config)
    corners = _click_corners(args.image)

    payload = build_calibration_payload(ws, args.image, corners)
    out = default_workspace_save_path(args.workspace_config)
    save_calibration_payload(payload, out)
    print(f"wrote calibration to {out}")
    return 0


def _dry_run(args) -> int:
    arm_cfg = load_arm_config(args.arm_config)
    ws_cfg = load_workspace_config(args.workspace_config)
    session = CalibrationSession(ws_cfg, arm_cfg)
    source = resolve_workspace_config_path(args.workspace_config)
    target = default_workspace_save_path(args.workspace_config)

    print("manual calibration dry run:")
    print(f"workspace source: {source}")
    print(f"save target: {target}")
    print("required poses:")
    for name in session.required_poses:
        marker = "set" if ws_cfg.has_pose(name) else "missing"
        print(f"  {name}: {marker}")
    missing = session.missing_poses()
    if missing:
        print("complete: no")
        print("missing: " + ", ".join(missing))
    else:
        print("complete: yes")
    errors = session.validate_existing()
    if errors:
        print("validation errors:")
        for error in errors:
            print(f"  {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
