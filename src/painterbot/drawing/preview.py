"""Render a drawing to a PNG so you can sanity-check paths without hardware."""

from __future__ import annotations

from pathlib import Path

from painterbot.config import PaperConfig
from painterbot.drawing.path_sampler import Drawing


def save_preview(drawing: Drawing, paper: PaperConfig, out_path: str | Path) -> Path:
    """Plot strokes over the paper outline and save to ``out_path``."""
    import matplotlib

    matplotlib.use("Agg")  # headless; no display needed
    import matplotlib.pyplot as plt

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(6, 6))
    # Paper outline + usable area (inside margins).
    ax.add_patch(
        plt.Rectangle((0, 0), paper.width_mm, paper.height_mm,
                      fill=False, edgecolor="black", linewidth=1)
    )
    m = paper.margin_mm
    ax.add_patch(
        plt.Rectangle((m, m), paper.width_mm - 2 * m, paper.height_mm - 2 * m,
                      fill=False, edgecolor="gray", linestyle="--", linewidth=0.6)
    )
    for stroke in drawing:
        if len(stroke) < 2:
            continue
        xs = [p[0] for p in stroke]
        ys = [p[1] for p in stroke]
        ax.plot(xs, ys, linewidth=1.2)

    ax.set_aspect("equal")
    ax.set_xlim(-5, paper.width_mm + 5)
    ax.set_ylim(-5, paper.height_mm + 5)
    ax.set_xlabel("x (mm)")
    ax.set_ylabel("y (mm)")
    ax.set_title("painterbot drawing preview")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path
