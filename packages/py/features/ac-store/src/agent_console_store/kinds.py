"""정의 종류(kind) 등록. 새 종류는 `DefinitionKind` 하나를 만들어 저장소에 넘기면 된다."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from typing import Protocol

from pydantic import BaseModel

from agent_console_contracts import Agent, Graph, Resource, WorkspaceSettings

from .hashing import HashFn

SCOPE_FIELD = "project"
"""정의 범위 필드(계약 0.8.0 `Agent`·`Graph`·`Resource.project`, 생략 = 공용, design §UX-P.4).
기본 종류 셋은 목록 요약 `extra`에 이 값을 싣는다(웹이 범위로 거른다). 저장소는 값의 뜻을 모른다."""


@dataclass(frozen=True, slots=True)
class DefinitionKind:
    """정의 종류 하나의 저장 규칙.

    Attributes:
        name: 종류 이름(저장소 API의 `kind` 인자, 버전 테이블의 `kind` 컬럼).
        directory: 파일 저장소에서 `<root>/<directory>/<id>.yaml`. 단일 파일 종류는 비운다.
        model: 저장 전 검증에 쓰는 Pydantic 모델. None이면 검증 없이 dict를 그대로 저장한다.
        require_version: True면 `save()`에 기대 버전(If-Match)이 반드시 필요하다.
        singleton_file: 지정하면 종류당 문서가 하나이고 `<root>/<singleton_file>`에 저장한다.
            이때 id는 `name`과 같다.
        count_fields: 목록 요약에서 길이를 세어 줄 최상위 리스트 필드 이름(예: nodes, edges).
        hash_fn: 이 종류의 버전 해시 함수. None이면 저장소 기본값.
        content_field: 본문 파일을 가리키는 최상위 필드 이름(그 값은 `{file: 상대경로, ...}`).
            지정하면 본문이 `<root>/<directory>/<id>/<file>`에 함께 저장·삭제되고 버전 해시에
            본문이 들어간다. 싱글턴 종류에는 쓸 수 없다.
        multi_file: True면 본문 폴더(`<directory>/<id>/`) 아래 모든 파일이 정의의 본문이다
            (`list_files`·`write_file`·`delete_file`). `content_field`가 필요하다. 버전 해시에는
            모든 파일의 sha256이 들어간다(파일이 `content.file` 하나뿐이면 단일 파일 때와
            해시가 같다).
        summary_fields: 목록 요약(`DefinitionSummary.extra`)에 복사해 줄 최상위 문자열 필드.
        portable: True면 프로젝트 폴더의 사본 공간(`.agent-console/`)에 둘 수 있는 종류다
            (design §PI.4.2). 싱글턴 종류는 이 값과 상관없이 옮길 수 없다(`is_portable`).
            앱 등록부 같은 종류는 False로 등록한다.
        library: True면 라이브러리 공간(앱 workspace)에도 둘 수 있다. False면 프로젝트·단독 공간에만
            둔다(예: 프로젝트마다 따로인 문서, design §6R.3 X36). 저장소는 이 값을 보지 않는다 —
            라이브러리 저장소를 여는 쪽이 `library=False` 종류를 빼고 연다(그 종류의 라이브러리
            요청은 모르는 종류라 `NotFound`).
    """

    name: str
    directory: str = ""
    model: type[BaseModel] | None = None
    require_version: bool = False
    singleton_file: str | None = None
    count_fields: tuple[str, ...] = ()
    hash_fn: HashFn | None = None
    content_field: str | None = None
    multi_file: bool = False
    summary_fields: tuple[str, ...] = ()
    portable: bool = True
    library: bool = True

    def __post_init__(self) -> None:
        if self.content_field is not None and self.singleton_file is not None:
            raise ValueError(f"{self.name}: a singleton kind cannot have content files")
        if self.multi_file and self.content_field is None:
            raise ValueError(f"{self.name}: multi_file needs content_field")

    @property
    def is_portable(self) -> bool:
        """프로젝트 사본 공간에 둘 수 있나: `portable`이고 싱글턴이 아니다."""
        return self.portable and self.singleton_file is None

    @property
    def is_singleton(self) -> bool:
        return self.singleton_file is not None

    def with_summary_fields(self, *fields: str) -> "DefinitionKind":
        """목록 요약 필드를 더한 사본(이미 있는 이름은 건너뛴다, 순서 유지). 더할 것이 없으면 자기
        자신.

        >>> GRAPH_KIND.with_summary_fields("status", "project").summary_fields
        ('project', 'status')
        """
        extra = tuple(dict.fromkeys(f for f in fields if f not in self.summary_fields))
        if not extra:
            return self
        return replace(self, summary_fields=(*self.summary_fields, *extra))


GRAPH_KIND = DefinitionKind(
    name="graph",
    directory="graphs",
    model=Graph,
    require_version=True,
    count_fields=("nodes", "edges"),
    summary_fields=(SCOPE_FIELD,),
)
AGENT_KIND = DefinitionKind(
    name="agent", directory="agents", model=Agent, summary_fields=(SCOPE_FIELD,)
)
SETTINGS_KIND = DefinitionKind(
    name="settings", model=WorkspaceSettings, singleton_file="settings.yaml", portable=False
)
RESOURCE_KIND = DefinitionKind(
    name="resource",
    directory="resources",
    model=Resource,
    require_version=True,
    content_field="content",
    multi_file=True,
    summary_fields=("type", SCOPE_FIELD),
)
"""리소스(design §R12.1, §2R.3): `resources/<id>.yaml` + 본문 `resources/<id>/` 아래 파일들."""

DEFAULT_KINDS: tuple[DefinitionKind, ...] = (GRAPH_KIND, AGENT_KIND, SETTINGS_KIND, RESOURCE_KIND)
"""기본 종류. 다른 종류는 `kinds=`로 추가/대체한다."""


def kinds_by_name(kinds: Iterable[DefinitionKind]) -> dict[str, DefinitionKind]:
    """이름 -> 종류. 이름이 겹치면 `ValueError`."""
    result: dict[str, DefinitionKind] = {}
    for kind in kinds:
        if kind.name in result:
            raise ValueError(f"duplicate definition kind: {kind.name}")
        result[kind.name] = kind
    return result


class KindContributionLike(Protocol):
    """종류 기여 하나의 모양(`agent_console_modkit.KindContribution`과 같다, X44). 이 패키지는
    키트를 모르므로 모양만 맞춘다."""

    @property
    def kind(self) -> object: ...

    @property
    def summary_fields(self) -> tuple[str, ...]: ...


type KindSkipped = Callable[[str, str], None]
"""`(종류 이름, 이유)`: 기여를 건너뛰었다.

이유: `not_a_kind`·`reserved`·`duplicate`·`not_library`."""


def contributed_kinds(
    contributions: Iterable[KindContributionLike],
    *,
    reserved: Iterable[str] = (),
    library_only: bool = False,
    on_skip: KindSkipped | None = None,
) -> list[DefinitionKind]:
    """종류 기여 목록 → 더할 종류(기여의 `summary_fields`를 더한 사본, 들어온 순서).

    Args:
        contributions: 기여 목록(제공 모듈 id 순).
        reserved: 이미 있는 종류 이름(이 이름의 기여는 건너뛴다 — 기존 종류를 바꾸지 않는다).
        library_only: 참이면 `library=False` 종류를 뺀다(라이브러리 저장소용).
        on_skip: 건너뛴 기여 알림(로그용). 종류 값이 `DefinitionKind`가 아니면 이름은 `repr`.

    같은 이름이 두 번 오면 먼저 온 것만 쓴다.

    >>> from types import SimpleNamespace as C
    >>> note = DefinitionKind(name="note", directory="notes", library=False)
    >>> [k.name for k in contributed_kinds([C(kind=note, summary_fields=())])]
    ['note']
    >>> contributed_kinds([C(kind=note, summary_fields=())], library_only=True)
    []
    """
    taken = set(reserved)
    out: list[DefinitionKind] = []
    for item in contributions:
        kind = item.kind
        if not isinstance(kind, DefinitionKind):
            reason, name = "not_a_kind", repr(kind)
        elif kind.name in taken:
            dup = any(k.name == kind.name for k in out)
            reason, name = ("duplicate" if dup else "reserved"), kind.name
        elif library_only and not kind.library:
            reason, name = "not_library", kind.name
        else:
            taken.add(kind.name)
            out.append(kind.with_summary_fields(*item.summary_fields))
            continue
        if on_skip is not None:
            on_skip(name, reason)
    return out
