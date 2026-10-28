"""프로젝트 공간 열기: 폴더 하나의 `.agent-console/` 정의 저장소와 경로 모음."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypedDict, Unpack

from agent_console_secret_rules import SecretRules, default_rules
from agent_console_store import (
    DEFAULT_KINDS,
    DEFAULT_MAX_CONTENT_BYTES,
    DefinitionKind,
    DefinitionStore,
    FileDefinitionStore,
    HashFn,
    VersionRepository,
    default_hash,
)

from ._errors import ConfigReadonly, FolderMissing, SecretFinding, SecretRejected, UnsafeConfigDir
from ._files import LocalFiles, SpaceFiles
from ._layout import DEFAULT_CONFIG_DIR, SpaceLayout, check_relative


class SpaceOptions(TypedDict, total=False):
    """`open_space`·`init_space`가 같이 받는 선택 인자."""

    kinds: Iterable[DefinitionKind]
    """다룰 정의 종류 전체. 이 중 `is_portable`인 것만 공간에 들어간다. 기본 `DEFAULT_KINDS`."""
    versions: VersionRepository | None
    """버전 기록 저장소(보통 그 폴더 기록 DB의 것). 생략하면 메모리(프로세스 동안만)."""
    config_dir: str
    """프로젝트 폴더 안 구성 폴더 이름. 기본 `.agent-console`."""
    layout: SpaceLayout
    """구성 폴더 안 파일 이름."""
    files: SpaceFiles
    """파일 시스템 주입(기본 `LocalFiles`)."""
    secret_rules: SecretRules
    """비밀 의심 규칙(기본 secret-rules 기본 규칙). 앱의 사용자 규칙을 주입한다."""
    scan_bodies: bool
    """True면 본문 파일(UTF-8 텍스트)도 비밀 검사한다. 기본 False(문서만)."""
    clock: Callable[[], float]
    hash_fn: HashFn
    max_content_bytes: int | None
    max_versions: int | None


@dataclass(frozen=True)
class ProjectSpace:
    """열린 프로젝트 공간. 폴더 하나의 구성 사본이다.

    Attributes:
        folder: 프로젝트 폴더.
        root: 구성 폴더(`<folder>/<config_dir>`). 정의 저장소의 root다.
        definitions: 정의 저장소(`DefinitionStore`). 쓰기는 비밀 검사·읽기 전용 검사를 지난다.
        manifest_path: `project.yaml` 경로.
        gitignore_path: 구성 폴더의 `.gitignore` 경로.
        memory_db_path: 프로젝트 메모리 DB 경로(파일은 만들지 않는다).
        records_db_path: 프로젝트 기록 DB 경로(파일은 만들지 않는다, 33w2가 연다).
        sessions_dir: 세션 기록 보관 폴더 경로.
        state_dir: 이 폴더용 캐시·임시 파일 폴더 경로.
        portable_kinds: 공간에 들어가는 종류 이름.
        config_writable: 구성 폴더에 쓸 수 있나. 아니면 정의·매니페스트 쓰기는 `ConfigReadonly`.
    """

    folder: Path
    root: Path
    definitions: DefinitionStore
    manifest_path: Path
    gitignore_path: Path
    memory_db_path: Path
    records_db_path: Path
    sessions_dir: Path
    state_dir: Path
    portable_kinds: tuple[str, ...]
    config_writable: bool
    layout: SpaceLayout = field(repr=False)
    files: SpaceFiles = field(repr=False)
    secret_rules: SecretRules = field(repr=False)


def portable_kinds(kinds: Iterable[DefinitionKind]) -> tuple[DefinitionKind, ...]:
    """프로젝트 공간에 둘 수 있는 종류만(`DefinitionKind.is_portable`).

    >>> from agent_console_store import DEFAULT_KINDS
    >>> [k.name for k in portable_kinds(DEFAULT_KINDS)]
    ['graph', 'agent', 'resource']
    """
    return tuple(k for k in kinds if k.is_portable)


def scan_secrets(
    rules: SecretRules, document: Mapping[str, Any], path: str = ""
) -> list[SecretFinding]:
    """문서 안 평문 비밀 의심 위치(값 없음). `secret://` 참조는 통과한다."""
    return [
        SecretFinding(f.path, f.reason) for f in rules.find_suspected(dict(document), path=path)
    ]


def _make_guard(
    *, writable: bool, rules: SecretRules, scan_bodies: bool
) -> Callable[[DefinitionKind, str, Mapping[str, Any], Mapping[str, bytes]], None]:
    def guard(
        kind: DefinitionKind, id: str, document: Mapping[str, Any], put: Mapping[str, bytes]
    ) -> None:
        if not writable:
            raise ConfigReadonly(f"{kind.name}/{id}: the project folder is read-only")
        findings = scan_secrets(rules, document)
        if scan_bodies:
            for name, data in put.items():
                try:
                    text = data.decode("utf-8")
                except UnicodeDecodeError:
                    continue
                findings += [
                    SecretFinding(f.path, f.reason)
                    for f in rules.find_suspected(text, path=f"/$content/{name}")
                ]
        if findings:
            raise SecretRejected(tuple(findings))

    return guard


def build_space(
    folder: Path, *, writable: bool | None = None, **options: Unpack[SpaceOptions]
) -> ProjectSpace:
    """폴더를 열어 `ProjectSpace`를 만든다(쓰기 없음). `writable`을 주면 판정을 건너뛴다."""
    files = options.get("files") or LocalFiles()
    layout = options.get("layout") or SpaceLayout()
    config_dir = check_relative(options.get("config_dir", DEFAULT_CONFIG_DIR), what="config_dir")
    rules = options.get("secret_rules") or default_rules()
    if not files.is_dir(folder):
        raise FolderMissing(f"project folder is missing: {folder.name}")
    root = folder / config_dir
    probe = folder
    for part in Path(config_dir).parts:
        probe = probe / part
        if files.is_link(probe):
            raise UnsafeConfigDir(f"{config_dir} is a link; links are not followed")
    if writable is None:
        writable = files.is_writable(root)
    kinds = portable_kinds(options.get("kinds", DEFAULT_KINDS))
    max_bytes = options.get("max_content_bytes", DEFAULT_MAX_CONTENT_BYTES)
    store = FileDefinitionStore(
        root,
        kinds,
        versions=options.get("versions"),
        hash_fn=options.get("hash_fn", default_hash),
        clock=options.get("clock", time.time),
        max_content_bytes=max_bytes,
        max_versions=options.get("max_versions"),
        write_guard=_make_guard(
            writable=writable, rules=rules, scan_bodies=options.get("scan_bodies", False)
        ),
    )
    return ProjectSpace(
        folder=folder,
        root=root,
        definitions=store,
        manifest_path=root / layout.manifest_file,
        gitignore_path=root / layout.gitignore_file,
        memory_db_path=root / layout.memory_file,
        records_db_path=root / layout.records_file,
        sessions_dir=root / layout.sessions_dir,
        state_dir=root / layout.state_dir,
        portable_kinds=tuple(k.name for k in kinds),
        config_writable=writable,
        layout=layout,
        files=files,
        secret_rules=rules,
    )


def open_space(folder: str | Path, **options: Unpack[SpaceOptions]) -> ProjectSpace:
    """프로젝트 폴더의 구성 사본 공간을 연다. 아무것도 만들거나 쓰지 않는다.

    서버 없이 폴더 하나만으로 정의 목록·저장이 된다(`space.definitions`). 구성 폴더가 아직 없어도
    열 수 있고(비어 있는 공간), 처음 저장할 때 만들어진다. 매니페스트·`.gitignore`를 만드는 것은
    `init_space`다.

    Args:
        folder: 프로젝트 폴더.
        **options: `SpaceOptions` 참고(`kinds`·`versions`·`config_dir`·`files` 등).

    Returns:
        `ProjectSpace`.

    Raises:
        FolderMissing: 폴더가 없다.
        UnsafeConfigDir: 구성 폴더 이름이 폴더 밖을 가리키거나 링크다.
        ValueError: 구성 폴더·파일 이름이 상대 경로가 아니다.
    """
    return build_space(Path(folder), **options)
