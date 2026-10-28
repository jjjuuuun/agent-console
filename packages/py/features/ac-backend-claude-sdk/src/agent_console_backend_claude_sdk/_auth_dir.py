"""앱 전용 Claude Code 자격 폴더(``CLAUDE_CONFIG_DIR``) — 5.7R.30·5.7R.30b, 사용자 결정 2026-10-28.

구독 로그인은 "앱 하나에 로그인 하나"다. 자격을 ``~/.claude``도 프로젝트(작업) 폴더도
아닌 **앱 workspace**(앱 데이터 폴더, 서버 ``--workspace``) 안 한 곳(기본
``<workspace>/.state/claude``)에 두고 모든 프로젝트가 함께 쓴다. 실행(SDK)·연결 테스트·구독
로그인 PTY·상태 점검이 모두 이 폴더를 ``CLAUDE_CONFIG_DIR``로 쓴다. 폴더에 자격이 없으면
"로그인 필요"이고 ``~/.claude``로 대신하지 않는다. 앱은 등록만으로 프로젝트 폴더에 아무것도
쓰지 않는다(``.gitignore`` 줄도 workspace 폴더에만).

- ``ClaudeSdkAuthDirOptions``: 설치자 설정 ``auth_dir``(폴더 위치·로그인 파일 이름·권한·
  ``.gitignore`` 줄). 전부 데이터다.
- ``resolve_auth_dir``: **경로 해석은 이 함수 한 곳**이다(기준 = 앱 workspace). 팀 모드(사람별
  자격)로 넓힐 때 여기에 키워드 인자(``person_id`` 등)를 더한다 — 지금은 만들지 않는다.
- ``prepare_auth_dir``: 폴더 만들기(700)·파일 권한(600)·``.gitignore`` 줄.
- ``secure_auth_dir``: 이미 있는 폴더·파일 권한만 좁힌다(만들지 않음).
- ``ensure_gitignore_entry``: ``.gitignore``에 줄 하나를 (없을 때만) 더한다.

이 모듈은 자격 파일의 **내용을 읽지 않는다**(있는지·권한만 본다).
"""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ._readiness import expand_path

DEFAULT_AUTH_DIR = ".state/claude"
"""앱 전용 자격 폴더 기본 위치(앱 workspace 기준 상대 경로, 5.7R.30b)."""

DEFAULT_AUTH_DIR_ENV = "CLAUDE_CONFIG_DIR"
"""Claude Code CLI가 설정·자격 폴더로 읽는 환경 변수."""

DEFAULT_LOGIN_FILES: tuple[str, ...] = (".credentials.json",)
"""자격 폴더 안에서 "로그인됨"으로 볼 파일(있는지만 본다)."""

PERSON_PLACEHOLDER = "{person}"
"""``config_dir`` 틀에서 사람 id로 바꿀 자리(팀 모드 틀, 예 ``.state/people/{person}/claude``).

개인 모드(지금)는 틀에 이 자리가 없고 ``person_id=None`` 하나뿐이다."""

_PERSON_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class ClaudeSdkAuthDirOptions(BaseModel):
    """설치자 설정 ``auth_dir``(``backends.claude-agent-sdk.auth_dir``): 앱 전용 자격 폴더."""

    model_config = ConfigDict(extra="forbid")

    config_dir: str | None = Field(
        default=DEFAULT_AUTH_DIR,
        title="자격 폴더",
        description="Claude Code 설정·구독 로그인 자격을 둘 앱 전용 폴더(CLAUDE_CONFIG_DIR). "
        "앱 하나에 로그인 하나이며 모든 프로젝트가 함께 쓴다. 상대 경로는 앱 workspace(서버 "
        "--workspace) 기준, ~ = 홈, ${이름} = 환경 변수. 비우면(null) 앱 전용 폴더를 쓰지 않고 "
        "서버 환경(CLAUDE_CONFIG_DIR 또는 ~/.claude)을 따른다.",
    )
    env_var: str = Field(
        default=DEFAULT_AUTH_DIR_ENV,
        min_length=1,
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
        title="환경 변수 이름",
        description="하위 프로세스(실행·로그인)에 자격 폴더를 알려 줄 환경 변수.",
    )
    login_files: list[str] = Field(
        default_factory=lambda: list(DEFAULT_LOGIN_FILES),
        min_length=1,
        title="로그인 파일",
        description="자격 폴더 안에서 로그인됨으로 볼 파일 이름(있는지만 본다, 내용은 읽지 않음).",
    )
    dir_mode: int = Field(
        default=0o700, ge=0, le=0o777, title="폴더 권한", description="자격 폴더 권한(POSIX)."
    )
    file_mode: int = Field(
        default=0o600,
        ge=0,
        le=0o777,
        title="파일 권한",
        description="자격 폴더 바로 아래 파일 권한(POSIX).",
    )
    gitignore: bool = Field(
        default=True,
        title=".gitignore에 더하기",
        description="자격 폴더를 준비할 때 앱 workspace 폴더 .gitignore에 제외 줄을 더한다"
        "(workspace가 git 저장소 안일 때 의미가 있다. 파일이 없으면 만들고, 이미 있으면 그대로). "
        "프로젝트 폴더에는 쓰지 않는다.",
    )
    gitignore_entry: str | None = Field(
        default=None,
        title=".gitignore 줄",
        description="더할 줄. 비우면 자격 폴더의 workspace 기준 첫 폴더(기본 .state/). "
        "자격 폴더가 workspace 밖이면 더하지 않는다.",
    )


@dataclass(frozen=True)
class AuthDirLocation:
    """해석한 자격 폴더.

    Attributes:
        path: 절대 경로.
        display: 화면에 보일 위치(workspace 안이면 workspace 기준 상대 경로, 밖이면 절대 경로).
        workspace: 기준 앱 workspace(없으면 None).
        env_var: 하위 프로세스 환경 변수 이름.
        login_files: 로그인 파일 절대 경로.
    """

    path: Path
    display: str
    workspace: Path | None
    env_var: str
    login_files: tuple[Path, ...]

    def env(self) -> dict[str, str]:
        """하위 프로세스에 줄 환경(``{CLAUDE_CONFIG_DIR: 경로}``)."""
        return {self.env_var: str(self.path)}

    def display_file(self, name: str) -> str:
        """폴더 안 파일의 화면 위치."""
        return f"{self.display.rstrip('/')}/{name}"


def resolve_auth_dir(
    options: ClaudeSdkAuthDirOptions,
    *,
    workspace: Path | str | None,
    environ: Mapping[str, str],
    person_id: str | None = None,
) -> AuthDirLocation | None:
    """자격 폴더 위치를 푼다(**경로 해석은 이 함수 한 곳**, 파일 시스템을 건드리지 않는다).

    앱 하나에 로그인 하나다(5.7R.30b): 기준은 프로젝트 폴더가 아니라 앱 workspace이고
    프로젝트 인자는 없다. 팀 모드(사람별 자격)는 ``config_dir`` 틀의 ``{person}`` 자리와
    ``person_id``로만 넓힌다(틀에 자리가 없으면 사람과 무관하게 같은 폴더, 자리가 있는데
    ``person_id``가 없으면 None).

    Raises:
        ValueError: ``person_id``가 폴더 이름으로 안전하지 않을 때(영문자·숫자·``._-``만).

    - ``config_dir``가 null이면 None(앱 전용 폴더를 쓰지 않음).
    - ``~``·``${이름}``을 주입한 환경으로 풀고, 풀 수 없으면 None.
    - 상대 경로는 ``workspace`` 기준. ``workspace``가 없으면 상대 경로는 풀 수 없어 None이다
      (단독 사용 — 이때 백엔드는 하위 프로세스 환경을 그대로 따른다).

    >>> loc = resolve_auth_dir(
    ...     ClaudeSdkAuthDirOptions(), workspace="/data/agent-console", environ={}
    ... )
    >>> loc.path.as_posix(), loc.display
    ('/data/agent-console/.state/claude', '.state/claude')
    >>> loc.env() == {"CLAUDE_CONFIG_DIR": str(loc.path)}
    True
    >>> resolve_auth_dir(ClaudeSdkAuthDirOptions(), workspace=None, environ={}) is None
    True
    """
    if options.config_dir is None:
        return None
    template = options.config_dir
    if person_id is not None and (not _PERSON_ID.match(person_id) or ".." in person_id):
        raise ValueError("person_id는 영문자·숫자·._-만 쓸 수 있습니다")
    if PERSON_PLACEHOLDER in template:
        if person_id is None:
            return None
        template = template.replace(PERSON_PLACEHOLDER, person_id)
    text = expand_path(template, environ)
    if not text:
        return None
    base = Path(os.path.abspath(workspace)) if workspace is not None else None
    raw = Path(text)
    if not raw.is_absolute():
        if base is None:
            return None
        raw = base / raw
    path = Path(os.path.normpath(raw))
    display = str(path)
    if base is not None:
        try:
            display = path.relative_to(base).as_posix() or "."
        except ValueError:
            display = str(path)
    return AuthDirLocation(
        path=path,
        display=display,
        workspace=base,
        env_var=options.env_var,
        login_files=tuple(path / name for name in options.login_files),
    )


def gitignore_entry_for(location: AuthDirLocation, options: ClaudeSdkAuthDirOptions) -> str | None:
    """workspace ``.gitignore``에 더할 줄. 설정 값이 있으면 그것, 없으면 workspace 기준 첫
    폴더 + ``/``.

    >>> loc = resolve_auth_dir(ClaudeSdkAuthDirOptions(), workspace="/ws", environ={})
    >>> gitignore_entry_for(loc, ClaudeSdkAuthDirOptions())
    '.state/'
    """
    if options.gitignore_entry:
        return options.gitignore_entry
    if location.workspace is None:
        return None
    try:
        rel = location.path.relative_to(location.workspace)
    except ValueError:
        return None
    parts = rel.parts
    if not parts:
        return None
    return parts[0] + "/"


def _normalized(line: str) -> str:
    return line.strip().lstrip("/").rstrip("/")


def ensure_gitignore_entry(folder: Path, entry: str) -> bool:
    """``folder/.gitignore``에 ``entry`` 줄이 없으면 더한다(없으면 파일을 만든다).

    앞뒤 ``/``만 다른 줄(``.agent-console``·``/.agent-console/``)은 같은 줄로 본다. 사용자 파일의
    다른 줄은 바꾸지 않고 끝에 한 줄만 더한다.

    Returns:
        줄을 더했으면 True, 이미 있으면 False.

    Raises:
        OSError: 읽기·쓰기 실패.
    """
    path = folder / ".gitignore"
    want = _normalized(entry)
    try:
        current = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        current = ""
    if any(_normalized(line) == want for line in current.splitlines() if line.strip()):
        return False
    prefix = "" if not current or current.endswith("\n") else "\n"
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(f"{prefix}{entry}\n")
    return True


@dataclass(frozen=True)
class PermissionReport:
    """권한 점검 결과.

    Attributes:
        checked: 점검했는지(폴더가 없거나 POSIX가 아니면 False).
        ok: 폴더·파일이 모두 그룹·다른 사용자에게 닫혀 있다(점검 안 했으면 True).
        loose: 좁히지 못한 항목(폴더 기준 상대 이름, ``.`` = 폴더 자신).
    """

    checked: bool
    ok: bool
    loose: tuple[str, ...] = ()


def _posix() -> bool:
    return os.name == "posix"


def secure_auth_dir(
    location: AuthDirLocation,
    options: ClaudeSdkAuthDirOptions,
    *,
    chmod: Callable[[Path, int], None] | None = None,
    posix: bool | None = None,
) -> PermissionReport:
    """이미 있는 자격 폴더와 바로 아래 파일 권한을 좁힌다(폴더를 만들지 않는다).

    파일 시스템이 권한을 지원하지 않으면(예: WSL의 ``/mnt/c``) 좁혀지지 않은 항목을 ``loose``로
    알린다. 하위 폴더 안은 폴더 권한(700)이 막는다.
    """
    if not (_posix() if posix is None else posix):
        return PermissionReport(checked=False, ok=True)
    do_chmod = chmod or (lambda p, m: os.chmod(p, m))
    folder = location.path
    try:
        if not folder.is_dir():
            return PermissionReport(checked=False, ok=True)
        targets: list[tuple[Path, str, int]] = [(folder, ".", options.dir_mode)]
        targets += [
            (entry, entry.name, options.file_mode)
            for entry in sorted(folder.iterdir())
            if entry.is_file() and not entry.is_symlink()
        ]
    except OSError:
        return PermissionReport(checked=True, ok=False, loose=(".",))
    loose: list[str] = []
    for path, name, mode in targets:
        try:
            current = stat.S_IMODE(path.stat().st_mode)
            if current & ~mode & 0o777:
                do_chmod(path, current & mode)
                current = stat.S_IMODE(path.stat().st_mode)
        except OSError:
            loose.append(name)
            continue
        if current & ~mode & 0o777:
            loose.append(name)
    return PermissionReport(checked=True, ok=not loose, loose=tuple(loose))


@dataclass(frozen=True)
class PrepareReport:
    """``prepare_auth_dir`` 결과(값 없음)."""

    created: bool
    gitignore_added: bool
    permissions: PermissionReport


def prepare_auth_dir(
    location: AuthDirLocation,
    options: ClaudeSdkAuthDirOptions,
    *,
    chmod: Callable[[Path, int], None] | None = None,
    posix: bool | None = None,
) -> PrepareReport:
    """자격 폴더를 준비한다: 만들기(700) → workspace ``.gitignore`` 줄 → 권한 좁히기(600).

    실행·연결 테스트·로그인 시작 전에 부른다(멱등). ``.gitignore``는 폴더를 새로 만들 때뿐 아니라
    매번 확인한다(이미 있으면 그대로). 쓰는 곳은 자격 폴더와 앱 workspace의 ``.gitignore``뿐이다
    (프로젝트 폴더에는 쓰지 않는다).

    Raises:
        OSError: 폴더를 만들 수 없을 때(권한 등). 메시지에 자격 내용은 없다.
    """
    folder = location.path
    created = not folder.exists()
    folder.mkdir(parents=True, exist_ok=True, mode=options.dir_mode)
    added = False
    if options.gitignore and location.workspace is not None:
        entry = gitignore_entry_for(location, options)
        if entry and location.workspace.is_dir():
            added = ensure_gitignore_entry(location.workspace, entry)
    report = secure_auth_dir(location, options, chmod=chmod, posix=posix)
    return PrepareReport(created=created, gitignore_added=added, permissions=report)


__all__ = [
    "DEFAULT_AUTH_DIR",
    "DEFAULT_AUTH_DIR_ENV",
    "DEFAULT_LOGIN_FILES",
    "PERSON_PLACEHOLDER",
    "AuthDirLocation",
    "ClaudeSdkAuthDirOptions",
    "PermissionReport",
    "PrepareReport",
    "ensure_gitignore_entry",
    "gitignore_entry_for",
    "prepare_auth_dir",
    "resolve_auth_dir",
    "secure_auth_dir",
]
