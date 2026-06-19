"""Import an iPhone LiDAR scan mesh (Phase 8).

    python -m painterbot.iphone.import_scan ./scan.obj

Loads an exported mesh (OBJ/GLB/USDZ/STL/PLY) and prints basic stats. Requires
the optional ``scan`` dependencies (``pip install -e ".[scan]"``). This is a
later-phase feature; the MVP flat-drawing pipeline does not use it.
"""

from __future__ import annotations

import argparse
from pathlib import Path

ACCEPTED_SUFFIXES = {".obj", ".glb", ".gltf", ".usdz", ".stl", ".ply"}


def load_mesh(path: str | Path):
    """Load a mesh with trimesh. Returns a trimesh.Trimesh (or Scene)."""
    p = Path(path)
    if p.suffix.lower() not in ACCEPTED_SUFFIXES:
        raise ValueError(
            f"unsupported mesh format {p.suffix!r}; "
            f"accepted: {', '.join(sorted(ACCEPTED_SUFFIXES))}"
        )
    try:
        import trimesh
    except ImportError as exc:  # pragma: no cover - optional dep
        raise RuntimeError(
            "mesh import needs the optional scan deps: pip install -e \".[scan]\""
        ) from exc
    return trimesh.load(str(p))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Import and inspect a LiDAR scan mesh.")
    parser.add_argument("mesh", help="path to OBJ/GLB/USDZ/STL/PLY")
    args = parser.parse_args(argv)

    mesh = load_mesh(args.mesh)
    bounds = getattr(mesh, "bounds", None)
    print(f"loaded {args.mesh}")
    print(f"  type:   {type(mesh).__name__}")
    if bounds is not None:
        size = bounds[1] - bounds[0]
        print(f"  bounds: {bounds.tolist()}")
        print(f"  size:   {size.tolist()}")
    print(f"  watertight: {getattr(mesh, 'is_watertight', 'n/a')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
