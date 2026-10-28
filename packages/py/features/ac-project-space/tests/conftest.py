"""공용 fixture."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_console_contracts import ProjectManifest


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    path = tmp_path / "project"
    path.mkdir()
    return path


@pytest.fixture
def manifest() -> ProjectManifest:
    return ProjectManifest(id="payments", name="결제 서비스")
