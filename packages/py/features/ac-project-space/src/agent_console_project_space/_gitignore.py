"""`.gitignore` 기본 틀(패키지 데이터 `data/gitignore.template`).

틀에는 폴더 안 이름 자리(`{state_dir}`·`{memory_file}`·`{records_file}`·`{sessions_dir}`)가 있다.
틀을 쓰는 곳(`init_space`·`missing_gitignore_lines`·`append_gitignore`)은 그 공간의 배치
(`SpaceLayout`) 값으로 채워 쓴다. 그래서 기록 DB 파일 이름·세션 보관 폴더 이름을 바꾸면 git 제외
줄도 따라간다. 사용자가 준 틀에도 같은 자리를 쓸 수 있다(모르는 중괄호는 그대로 둔다).
"""

from __future__ import annotations

from importlib import resources
from typing import TYPE_CHECKING, Final

from ._errors import ConfigReadonly
from ._layout import SpaceLayout

if TYPE_CHECKING:
    from ._space import ProjectSpace

GITIGNORE_FIELDS: Final = ("state_dir", "memory_file", "records_file", "sessions_dir")
"""틀에서 `{이름}`으로 쓸 수 있는 `SpaceLayout` 필드."""

_GLOB_SPECIALS: Final = "\\*?["


def _escape(name: str) -> str:
    """gitignore 패턴에서 글자 그대로 읽히게 한다(`\\`·`*`·`?`·`[`, 끝 공백)."""
    out = "".join(f"\\{ch}" if ch in _GLOB_SPECIALS else ch for ch in name)
    stripped = out.rstrip(" ")
    return stripped + "\\ " * (len(out) - len(stripped))


def _raw_template() -> str:
    return (
        resources.files("agent_console_project_space")
        .joinpath("data", "gitignore.template")
        .read_text(encoding="utf-8")
    )


def render_gitignore_template(template: str, layout: SpaceLayout | None = None) -> str:
    """틀의 이름 자리(`GITIGNORE_FIELDS`)를 `layout` 값으로 채운다(gitignore 특수 문자는
    이스케이프).

    >>> render_gitignore_template("/{records_file}\\n/{sessions_dir}/\\n", SpaceLayout(
    ...     records_file="rec.db", sessions_dir="archive"))
    '/rec.db\\n/archive/\\n'
    """
    values = layout if layout is not None else SpaceLayout()
    text = template
    for name in GITIGNORE_FIELDS:
        text = text.replace("{" + name + "}", _escape(getattr(values, name)))
    return text


def default_gitignore_template(layout: SpaceLayout | None = None) -> str:
    """The default `.gitignore` template text shipped in the package (UTF-8, ends with a newline).

    Args:
        layout: 이름 자리를 채울 배치. 생략하면 기본 배치(`SpaceLayout()`).
    """
    return render_gitignore_template(_raw_template(), layout)


def _template_for(space: ProjectSpace, template: str | None) -> str:
    return render_gitignore_template(
        template if template is not None else _raw_template(), space.layout
    )


def _managed_lines(template: str) -> list[str]:
    """틀에서 앱이 관리하는 줄: `/`로 시작하는 줄(주석·빈 줄 제외)."""
    return [t for t in (line.strip() for line in template.splitlines()) if t.startswith("/")]


def missing_gitignore_lines(space: ProjectSpace, template: str | None = None) -> list[str]:
    """`.gitignore`에 빠진 틀의 줄(`/`로 시작하는 줄만, 틀의 순서). 파일이 없으면 전부.

    틀의 이름 자리는 공간 배치(`space.layout` — 기록 DB 파일·세션 보관 폴더 이름 등)로 채운 뒤
    비교한다. 사용자가 줄을 지우거나 고쳐도 되므로 알려 주기만 한다(`append_gitignore`는 사용자가
    누를 때만). 비교는 앞뒤 공백을 뺀 줄 그대로다.

    Args:
        space: 열린 프로젝트 공간.
        template: 틀 텍스트. 생략하면 패키지 데이터 `gitignore.template`.

    Raises:
        OSError: 파일을 읽을 수 없다.
    """
    wanted = _managed_lines(_template_for(space, template))
    raw = space.files.read_bytes(space.gitignore_path)
    have = (
        set()
        if raw is None
        else {line.strip() for line in raw.decode("utf-8", errors="replace").splitlines()}
    )
    return [line for line in wanted if line not in have]


def append_gitignore(space: ProjectSpace, template: str | None = None) -> list[str]:
    """빠진 틀의 줄을 `.gitignore` 끝에 덧붙인다(있는 줄은 건드리지 않는다). 더한 줄을 돌려준다.

    파일이 없으면 틀 전체로 만든다(이름 자리는 공간 배치로 채움). 더할 줄이 없으면 아무것도 쓰지
    않고 빈 목록.

    Raises:
        ConfigReadonly: 구성 폴더에 쓸 수 없다.
        OSError: 읽거나 쓸 수 없다.
    """
    text = _template_for(space, template)
    missing = missing_gitignore_lines(space, template)
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
