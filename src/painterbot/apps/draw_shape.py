"""Draw a built-in shape (Phase 5).

    python -m painterbot.apps.draw_shape --shape square --mock
    python -m painterbot.apps.draw_shape --shape circle --preview out/circle.png

With ``--preview`` it writes a PNG of the planned paths and does not move the
arm — handy before you've captured calibration poses. Without it, the shape is
executed on the (real or mock) arm.
"""

from __future__ import annotations

import argparse

from painterbot.apps._common import (
    add_connection_args,
    connect,
    load_configs,
    setup_logging,
)
from painterbot.drawing.path_sampler import fit_to_paper
from painterbot.drawing.shapes import SHAPE_NAMES, generate_shape
from painterbot.drawing.stroke_planner import StrokePlanner, summarize_drawing


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Draw a built-in shape.")
    parser.add_argument("--shape", required=True, choices=SHAPE_NAMES)
    parser.add_argument(
        "--preview",
        metavar="PNG",
        default=None,
        help="render planned paths to a PNG and skip arm motion",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print stroke/point counts and corner poses, then exit "
        "(no arm connection, no calibration required)",
    )
    add_connection_args(parser)
    args = parser.parse_args(argv)
    setup_logging(args.verbose)

    arm_cfg, ws_cfg = load_configs(args)

    drawing = generate_shape(args.shape)
    drawing = fit_to_paper(drawing, ws_cfg.paper)

    if args.dry_run:
        print(summarize_drawing(ws_cfg, drawing))
        return 0

    if args.preview:
        from painterbot.drawing.preview import save_preview

        out = save_preview(drawing, ws_cfg.paper, args.preview)
        print(f"wrote preview to {out} ({len(drawing)} stroke(s))")
        return 0

    arm = connect(args, arm_cfg)
    try:
        planner = StrokePlanner(arm, ws_cfg)
        n = planner.execute(drawing)
        print(f"drew {args.shape}: {n} stroke(s)")
    finally:
        arm.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
