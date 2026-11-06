"""`.gitignore` 기본 틀(패키지 데이터 `data/gitignore.template`)."""

from __future__ import annotations

from importlib import resources
from typing import TYPE_CHECKING

from ._errors import ConfigReadonly

if TYPE_CHECKING:
    from ._space import ProjectSpace


def default_gitignore_template() -> str:
    """패키지에 들어 있는 `.gitignore` 기본 틀 텍스트(UTF-8, 마지막 줄바꿈 포함)."""
    return (
        resources.files("agent_console_project_space")
        .joinpath("data", "gitignore.template")
        .read_text(encoding="utf-8")
    )


def _managed_lines(template: str) -> list[str]:
    """틀에서 앱이 관리하는 줄: `/`로 시작하는 줄(주석·빈 줄 제외)."""
    return [t for t in (line.strip() for line in template.splitlines()) if t.startswith("/")]


def missing_gitignore_lines(space: ProjectSpace, template: str | None = None) -> list[str]:
    """`.gitignore`에 빠진 틀의 줄(`/`로 시작하는 줄만, 틀의 순서). 파일이 없으면 전부.

    사용자가 줄을 지우거나 고쳐도 되므로 알려 주기만 한다(`append_gitignore`는 사용자가 누를 때만).
    비교는 앞뒤 공백을 뺀 줄 그대로다.

    Args:
        space: 열린 프로젝트 공간.
        template: 틀 텍스트. 생략하면 패키지 데이터 `gitignore.template`.

    Raises:
        OSError: 파일을 읽을 수 없다.
    """
    wanted = _managed_lines(template if template is not None else default_gitignore_template())
    raw = space.files.read_bytes(space.gitignore_path)
    have = (
        set()
        if raw is None
        else {line.strip() for line in raw.decode("utf-8", errors="replace").splitlines()}
    )
    return [line for line in wanted if line not in have]


def append_gitignore(space: ProjectSpace, template: str | None = None) -> list[str]:
    """빠진 틀의 줄을 `.gitignore` 끝에 덧붙인다(있는 줄은 건드리지 않는다). 더한 줄을 돌려준다.

    파일이 없으면 틀 전체로 만든다. 더할 줄이 없으면 아무것도 쓰지 않고 빈 목록.

    Raises:
        ConfigReadonly: 구성 폴더에 쓸 수 없다.
        OSError: 읽거나 쓸 수 없다.
    """
    text = template if template is not None else default_gitignore_template()
    missing = missing_gitignore_lines(space, text)
    if not missing:
        return []
    if not space.config_writable:
        raise ConfigReadonly("the project folder is read-only; .gitignore was not changed")
    raw = space.files.read_bytes(space.gitignore_path)
    if raw is None:
        space.files.write_bytes(space.gitignore_path, text.encode("utf-8"))
        return missing
    current = raw.decode("utf-8", errors="replace")
    prefix = "" if not current or current.endswith("\n") else "\n"
    block = "\n".join(["# Agent Console가 더한 줄", *missing]) + "\n"
    space.files.write_bytes(space.gitignore_path, (current + prefix + block).encode("utf-8"))
    return missing
