"""내보내기 확장 지점(X8)과 주입 프로토콜(구조적 타이핑)."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Protocol, runtime_checkable

from agent_console_contracts import ExporterDescriptor, ExportSelection, Issue

__all__ = [
    "EXPORTERS_EXTENSION",
    "EXPORTERS_GROUP",
    "DependencyLike",
    "ExportCatalog",
    "ExportIssueCodes",
    "ExportOutput",
    "Exporter",
    "ExporterFactory",
    "OutputFile",
]

EXPORTERS_GROUP: Final = "agent_console.exporters"
"""entry point 그룹. 항목은 형식 공장(`ExporterFactory`)이다."""

EXPORTERS_EXTENSION: Final = "exporters"
"""레지스트리 묶음(`Registries.extension(name)`)에서 쓰는 이름.

`new_exporter_factories()`가 만드는 레지스트리 이름과 같다.
"""


class ExportIssueCodes:
    """내보내기 이슈 코드(문서 상수, 값은 싣지 않고 위치만).

    형식 플러그인은 다른 코드를 써도 된다.
    """

    SEMANTICS_APPROXIMATE: Final = "export.semantics_approximate"
    """산출물이 원래 정의와 똑같이 실행된다고 보장할 수 없다(팀 구성 등)."""
    FIELDS_DROPPED: Final = "export.fields_dropped"
    """형식이 표현하지 못해 빠진 설정(`details.keys`)."""
    TYPE_UNSUPPORTED: Final = "export.type_unsupported"
    """형식이 다루지 않는 리소스 종류(건너뜀)."""
    NOT_FOUND: Final = "export.not_found"
    """함께 쓰이는 정의를 찾지 못함(건너뜀)."""
    NAME_CONFLICT: Final = "export.name_conflict"
    """같은 이름의 산출물이 이미 있어 건너뜀."""
    SCOPE_WIDENED: Final = "export.scope_widened"
    """한 구성원에게 붙은 것을 프로젝트 전체에 적용되는 곳에 썼다."""
    SECRET_OMITTED: Final = "export.secret_omitted"
    """비밀 값(참조가 아니거나 `omit` 방식)을 쓰지 않았다."""
    SECRET_REDACTED: Final = "export.secret_redacted"
    """산출물에서 평문 비밀로 의심되는 값을 가렸다(마지막 검사)."""
    MAIN_NODE_NOT_FOUND: Final = "export.main_node_not_found"
    """옵션의 노드가 팀 구성에 없거나 에이전트 노드가 아니다."""
    KIND_UNSUPPORTED: Final = "export.kind_unsupported"
    """형식이 지원하지 않는 정의 종류(요청 거부)."""
    INVALID_OPTIONS: Final = "export.invalid_options"
    """옵션이 형식의 `config_schema`에 맞지 않는다(요청 거부)."""
    UNSAFE_PATH: Final = "export.unsafe_path"
    """경로가 안전하지 않다(탈출·링크·금지 이름·보호 위치)."""


@dataclass(frozen=True, slots=True)
class OutputFile:
    """내보낼 파일 하나(내용 포함).

    Attributes:
        path: 내보내기 루트 기준 상대 경로(`/` 구분).
        data: 내용.
        media_type: 형식(텍스트면 `text/…`·`application/json`).
    """

    path: str
    data: bytes
    media_type: str | None = None


@dataclass(frozen=True, slots=True)
class ExportOutput:
    """형식이 만든 산출물(파일 내용 + 경고). 쓰기는 `ExportService`가 한다."""

    files: list[OutputFile] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)


class DependencyLike(Protocol):
    """함께 쓰이는 정의 하나(`ac-teams.DefinitionDependency`가 구조적으로 만족).

    `node_id`: 팀 구성 안에서 묶이거나 붙은 노드(None = 팀 전체·공통). `shared`: 모든 구성원에게
    적용되는 층. `mode`: 첨부 방식. `config_override`: 첨부의 config 덮어쓰기.
    """

    @property
    def kind(self) -> str: ...

    @property
    def id(self) -> str: ...

    @property
    def node_id(self) -> str | None: ...

    @property
    def shared(self) -> bool: ...

    @property
    def mode(self) -> str: ...

    @property
    def config_override(self) -> Mapping[str, Any] | None: ...


class ExportCatalog(Protocol):
    """형식이 정의를 읽는 창구(앱이 저장소로 만든다). 읽기만 한다."""

    def document(self, kind: str, id: str) -> Mapping[str, Any] | None:
        """정의 원문(없으면 None)."""
        ...

    def files(self, kind: str, id: str) -> Mapping[str, bytes]:
        """본문 파일들(경로 → 내용). 본문이 없으면 빈 매핑."""
        ...

    def dependencies(self, kind: str, id: str) -> Sequence[DependencyLike]:
        """이 정의가 쓰는 정의(팀 구성 → 에이전트·리소스, 에이전트 → 리소스)."""
        ...


@runtime_checkable
class Exporter(Protocol):
    """내보내기 형식(X8). `plan`은 **순수**하다: 카탈로그를 읽기만 하고 파일을 쓰지 않는다
    (파일 내용을 만들어 돌려줄 뿐이다)."""

    @property
    def descriptor(self) -> ExporterDescriptor:
        """형식 디스크립터(id = 레지스트리 key, `config_schema` = 옵션 스키마)."""
        ...

    def plan(
        self,
        items: Sequence[ExportSelection],
        catalog: ExportCatalog,
        options: Mapping[str, Any],
    ) -> ExportOutput:
        """고른 정의 → 파일 내용 + 경고. `severity=error` 경고가 있으면 쓰지 않는다."""
        ...


type ExporterFactory = Callable[[Mapping[str, Any]], Exporter]
"""설치자 옵션(`exports.options.<형식>`) → 형식.

entry point `agent_console.exporters`가 가리키는 것이다.
"""
