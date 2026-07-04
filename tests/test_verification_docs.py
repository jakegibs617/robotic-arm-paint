"""Verification documentation checks."""

from __future__ import annotations

from painterbot.config import REPO_ROOT


def test_verification_docs_use_venv_python_and_no_hardware_commands():
    text = (REPO_ROOT / "docs" / "verification.md").read_text(encoding="utf-8")

    assert ".venv/bin/python -m pytest -q" in text
    assert ".venv/bin/python -m painterbot.apps.draw_shape --shape square --dry-run" in text
    assert ".venv/bin/python -m painterbot.apps.draw_shape --shape square --preview out/square.png" in text
    assert ".venv/bin/python -m painterbot.apps.draw_svg examples/star.svg --dry-run" in text
    assert ".[scan]" in text


def test_agent_handoff_references_verification_doc():
    text = (REPO_ROOT / "AGENT_HANDOFF.md").read_text(encoding="utf-8")

    assert "docs/verification.md" in text
    assert ".venv/bin/python -m pytest -q" in text
