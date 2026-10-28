"""`.gitignore` 기본 틀(패키지 데이터 `data/gitignore.template`)."""

from __future__ import annotations

from importlib import resources


def default_gitignore_template() -> str:
    """패키지에 들어 있는 `.gitignore` 기본 틀 텍스트(UTF-8, 마지막 줄바꿈 포함)."""
    return (
        resources.files("agent_console_project_space")
        .joinpath("data", "gitignore.template")
        .read_text(encoding="utf-8")
    )
