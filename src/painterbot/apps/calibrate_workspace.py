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


def _click_corners(image_path: Path) -> list[tuple[float, float]]:
    import cv2

    img = cv2.imread(str(image_path))
    if img is None:
        raise FileNotFoundError(f"could not read image {image_path}")

    corners: list[tuple[float, float]] = []
    labels = ["bottom-left", "bottom-right", "top-right", "top-left"]

    def on_click(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(corners) < 4:
            corners.append((float(x), float(y)))
            cv2.circle(img, (x, y), 6, (0, 0, 255), -1)
            cv2.imshow("calibrate", img)

    cv2.namedWindow("calibrate")
    cv2.setMouseCallback("calibrate", on_click)
    print("Click the four paper corners in order: " + ", ".join(labels))
    cv2.imshow("calibrate", img)
    while len(corners) < 4:
        if cv2.waitKey(20) & 0xFF == 27:  # Esc to abort
            break
    cv2.destroyAllWindows()

    if len(corners) != 4:
        raise RuntimeError("calibration aborted before 4 corners were clicked")
    return corners


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="iPhone-photo workspace calibration.")
    parser.add_argument("--image", required=True, type=Path)
    args = parser.parse_args(argv)

    from painterbot.calibration.homography import compute_homography
    from painterbot.config import load_workspace_config

    ws = load_workspace_config()
    corners = _click_corners(args.image)
    h = compute_homography(corners, ws.paper.width_mm, ws.paper.height_mm)

    # Persist the workspace config plus the captured homography so drawing can
    # place artwork on the detected sheet.
    extra = ws.model_dump()
    extra["calibration"] = {
        "image": str(args.image),
        "image_corners_px": corners,
        "homography": h.tolist(),
    }
    out = Path("configs") / "workspace.calibrated.yaml"
    import yaml

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        yaml.safe_dump(extra, f, sort_keys=False)
    print(f"wrote calibration to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
