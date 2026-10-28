"""정의 종류(kind) 등록. 새 종류는 `DefinitionKind` 하나를 만들어 저장소에 넘기면 된다."""

from collections.abc import Iterable
from dataclasses import dataclass

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
