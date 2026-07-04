"""Import an iPhone LiDAR scan mesh (Phase 8).

    python -m painterbot.iphone.import_scan ./scan.obj

Loads an exported mesh (OBJ/GLB/USDZ/STL/PLY) and prints basic stats. Requires
the optional ``scan`` dependencies (``pip install -e ".[scan]"``). This is a
later-phase feature; the MVP flat-drawing pipeline does not use it.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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


@dataclass(frozen=True)
class MeshSummary:
    path: str
    mesh_type: str
    vertex_count: int | None
    face_count: int | None
    bounds: list[list[float]] | None
    size: list[float] | None
    units: str | None
    watertight: bool | str

    def lines(self) -> list[str]:
        lines = [
            f"loaded {self.path}",
            f"  type:     {self.mesh_type}",
            f"  vertices: {self.vertex_count if self.vertex_count is not None else 'n/a'}",
            f"  faces:    {self.face_count if self.face_count is not None else 'n/a'}",
            f"  units:    {self.units or 'unknown'}",
        ]
        if self.bounds is not None:
            lines.append(f"  bounds:   {self.bounds}")
        if self.size is not None:
            lines.append(f"  size:     {self.size}")
        lines.append(f"  watertight: {self.watertight}")
        return lines


def summarize_mesh(mesh: Any, path: str | Path) -> MeshSummary:
    bounds = _bounds_list(getattr(mesh, "bounds", None))
    size = None
    if bounds is not None:
        size = [hi - lo for lo, hi in zip(bounds[0], bounds[1])]
    return MeshSummary(
        path=str(path),
        mesh_type=type(mesh).__name__,
        vertex_count=_count_mesh_attr(mesh, "vertices"),
        face_count=_count_mesh_attr(mesh, "faces"),
        bounds=bounds,
        size=size,
        units=_mesh_units(mesh),
        watertight=getattr(mesh, "is_watertight", "n/a"),
    )


def summarize_scan(path: str | Path) -> MeshSummary:
    return summarize_mesh(load_mesh(path), path)


def _count_mesh_attr(mesh: Any, attr: str) -> int | None:
    value = getattr(mesh, attr, None)
    if value is not None:
        return len(value)
    geometry = getattr(mesh, "geometry", None)
    if isinstance(geometry, dict):
        counts = [
            _count_mesh_attr(child, attr)
            for child in geometry.values()
        ]
        known = [count for count in counts if count is not None]
        return sum(known) if known else None
    return None


def _bounds_list(bounds) -> list[list[float]] | None:
    if bounds is None:
        return None
    return [[float(v) for v in row] for row in bounds]


def _mesh_units(mesh: Any) -> str | None:
    units = getattr(mesh, "units", None)
    if units:
        return str(units)
    metadata = getattr(mesh, "metadata", None)
    if isinstance(metadata, dict) and metadata.get("units"):
        return str(metadata["units"])
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Import and inspect a LiDAR scan mesh.")
    parser.add_argument("mesh", help="path to OBJ/GLB/USDZ/STL/PLY")
    args = parser.parse_args(argv)

    try:
        summary = summarize_scan(args.mesh)
    except RuntimeError as exc:
        print(str(exc))
        return 2
    for line in summary.lines():
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
