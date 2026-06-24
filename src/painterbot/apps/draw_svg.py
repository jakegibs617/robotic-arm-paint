"""Draw an SVG file (Phase 6).

    python -m painterbot.apps.draw_svg ./examples/star.svg --mock
    python -m painterbot.apps.draw_svg ./examples/star.svg --preview out/star.png

The artwork is scaled into the configured drawing area with aspect ratio
preserved. With ``--preview`` it writes a PNG instead of moving the arm.
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
from painterbot.drawing.stroke_planner import StrokePlanner, summarize_drawing
from painterbot.drawing.svg_loader import load_svg


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Draw an SVG file.")
    parser.add_argument("svg", help="path to an .svg file")
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

    drawing = load_svg(args.svg)
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
        print(f"drew {args.svg}: {n} stroke(s)")
    finally:
        arm.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
