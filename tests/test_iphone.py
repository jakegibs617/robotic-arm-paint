"""Error-path tests for the iPhone import stubs.

These exercise the deterministic failure modes that do *not* depend on the
optional ``[scan]`` extras: the suffix validation in ``load_mesh`` runs before
the trimesh import, and ``load_image`` fails fast on an unreadable path.
"""

import pytest

from painterbot.iphone.import_scan import ACCEPTED_SUFFIXES, load_mesh


def test_load_mesh_rejects_unsupported_suffix():
    """Unsupported formats fail before any optional dependency is imported."""
    with pytest.raises(ValueError, match="unsupported mesh format"):
        load_mesh("scan.txt")


def test_load_mesh_rejects_extensionless_path():
    with pytest.raises(ValueError, match="unsupported mesh format"):
        load_mesh("scan")


@pytest.mark.parametrize("suffix", sorted(ACCEPTED_SUFFIXES))
def test_load_mesh_accepts_known_suffixes_past_validation(monkeypatch, suffix):
    """Accepted suffixes pass validation and reach the loader, regardless of case."""
    import painterbot.iphone.import_scan as mod

    sentinel = object()
    fake_trimesh = type("T", (), {"load": staticmethod(lambda path: sentinel)})
    monkeypatch.setitem(__import__("sys").modules, "trimesh", fake_trimesh)

    assert mod.load_mesh(f"scan{suffix.upper()}") is sentinel


def test_load_mesh_missing_trimesh_raises_runtime_error(monkeypatch):
    """When the optional dep is absent the error names the install extra."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "trimesh":
            raise ImportError("no trimesh")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(RuntimeError, match=r"scan deps"):
        load_mesh("scan.obj")


def test_load_image_missing_file_raises(tmp_path):
    pytest.importorskip("cv2")
    from painterbot.iphone.import_image import load_image

    with pytest.raises(FileNotFoundError):
        load_image(tmp_path / "does_not_exist.jpg")
