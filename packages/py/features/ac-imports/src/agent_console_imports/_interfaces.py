"""가져오기 확장 지점(출처)과 주입 프로토콜(구조적 타이핑)."""

from __future__ import annotations

import builtins
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, Protocol, runtime_checkable

from agent_console_contracts import ImportCandidate, ImportSourceDescriptor, ImportWarning
from agent_console_secret_rules import SecretRules

IMPORT_SOURCES_GROUP: Final = "agent_console.import_sources"
"""entry point 그룹. 항목은 출처 공장(`ImportSourceFactory`)이다."""

IMPORT_SOURCES_EXTENSION: Final = "import_sources"
"""레지스트리 묶음(`Registries.extension(name)`)에서 쓰는 이름.

`new_import_source_factories()`가 만드는 레지스트리 이름과 같다.

앱이 이 이름으로 공장 레지스트리를 묶음에 넣으면 `plugins.modules`의 `register(registries)`
플러그인도 `registries.extension(IMPORT_SOURCES_EXTENSION)`로 출처 공장을 등록할 수 있다.
"""


@dataclass(frozen=True, slots=True)
class ImportItem:
    """가져올 수 있는 항목 하나: 화면용 후보 + 쓸 문서(+ 본문).

    Attributes:
        candidate: 계약 `ImportCandidate`(미리보기 화면에 그대로 나간다).
        document: 정의 문서(JSON 호환 dict). `id`는 쓸 때 대상 id로 바뀐다.
        content: 본문 파일 내용(한 파일 본문 종류만).
        files: 여러 파일 본문(경로 → 내용, `content.multi_file` 종류만). 한 버전으로 쓴다.
    """

    candidate: ImportCandidate
    document: dict[str, Any]
    content: bytes | None = None
    files: Mapping[str, bytes] | None = None


@dataclass(frozen=True, slots=True)
class ScanResult:
    """출처 하나를 읽은 결과. `root`는 표시용 위치. `warnings`는 후보가 되지 못한 항목의 경고
    (예: 링크라서 건너뜀, 위치만)."""

    root: str | None
    items: list[ImportItem] = field(default_factory=list)
    warnings: list[ImportWarning] = field(default_factory=list)


@runtime_checkable
class ImportSource(Protocol):
    """가져오기 출처(예: 사용자 `~/.claude`). **원본을 읽기만 한다.**

    `scan`은 파일을 쓰거나 지우거나 원본 위치를 바꾸지 않는다. 없는 위치는 빈 결과다.
    """

    @property
    def descriptor(self) -> ImportSourceDescriptor:
        """출처 디스크립터(`available`은 지금 읽을 수 있는지)."""
        ...

    def scan(self) -> ScanResult:
        """후보를 읽는다(쓰기 없음)."""
        ...


@dataclass(frozen=True, slots=True)
class ImportSourceContext:
    """출처 공장에 넘기는 환경 값(앱이 만든다).

    Attributes:
        home: 사용자 홈 폴더(없으면 사용자 전역 출처를 만들지 않는다).
        project_dir: 프로젝트(작업) 폴더(없으면 프로젝트 출처를 만들지 않는다).
        options: 설치자 설정(공장마다 해석, 키는 공장이 정한다).
        secret_rules: 지금의 비밀 의심 규칙을 돌려주는 함수(`ac-secret-rules`, 기본 + 사용자
            추가분). 없으면 출처가 기본 규칙을 쓴다. 함수인 이유: 출처는 시작 때 한 번 만들지만
            사용자 규칙은 그 뒤에 바뀔 수 있다.
    """

    home: Path | None = None
    project_dir: Path | None = None
    options: Mapping[str, Any] = field(default_factory=dict)
    secret_rules: Callable[[], SecretRules] | None = None


type ImportSourceFactory = Callable[[ImportSourceContext], Iterable[ImportSource]]
"""환경 값으로 출처들을 만든다(entry point `agent_console.import_sources`가 가리키는 것)."""


class StoredLike(Protocol):
    """저장소가 돌려주는 저장 결과(버전 해시만 쓴다)."""

    @property
    def version_hash(self) -> str: ...


class FileLike(Protocol):
    """여러 파일 본문의 파일 하나(경로만 쓴다)."""

    @property
    def path(self) -> str: ...


class DefinitionWriter(Protocol):
    """정의 저장소 중 가져오기가 쓰는 부분(`agent_console_store.DefinitionStore`가 만족)."""

    def list_ids(self, kind: str) -> builtins.list[str]: ...

    def get(self, kind: str, id: str) -> StoredLike: ...

    def create(
        self, kind: str, document: Mapping[str, Any], *, message: str = ""
    ) -> StoredLike: ...

    def save(
        self,
        kind: str,
        document: Mapping[str, Any],
        *,
        expected_version: str | None = None,
        message: str = "",
    ) -> StoredLike: ...

    def write_content(
        self,
        kind: str,
        id: str,
        data: bytes,
        *,
        file: str | None = None,
        media_type: str | None = None,
        expected_version: str | None = None,
        message: str = "본문 수정",
    ) -> StoredLike: ...

    def list_files(self, kind: str, id: str) -> Sequence[FileLike]: ...

    def write_files(
        self,
        kind: str,
        id: str,
        changes: Mapping[str, bytes | None],
        *,
        expected_version: str | None = None,
        message: str = "파일 수정",
    ) -> StoredLike: ...
