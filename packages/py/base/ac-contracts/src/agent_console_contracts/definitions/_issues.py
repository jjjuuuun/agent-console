"""검증 이슈와 수정 제안(그래프 패치). 그래프 노드·엣지를 담으므로 정의 하위 모듈에 둔다."""

from typing import ClassVar, Literal

from pydantic import Field

from agent_console_contracts._base import (
    ContractModel,
    JsonObject,
    NonEmptyStr,
    OmitWhenUnsetContract,
)
from agent_console_contracts.common import Fix, JsonPointer

from ._models import EdgeSpec, NodeSpec

type IssueSeverity = Literal["error", "warning", "info"]
"""검증 이슈 심각도(고정 어휘)."""


class NodeFieldRef(ContractModel):
    """노드 config 안 위치 하나(`GraphPatch.unset_node_fields`, 0.12.2)."""

    node_id: NonEmptyStr = Field(description="노드 id.")
    path: JsonPointer = Field(
        description=(
            "노드 `config` 기준 JSON Pointer(예: `/settings/model`). 빈 문자열은 쓰지 않는다."
        )
    )


class GraphPatch(OmitWhenUnsetContract):
    """그래프 초안에 적용할 변경(노드·엣지 추가, 엣지 삭제, 노드 설정 값 지우기).

    적용은 클라이언트가 초안에 한다. 순서: 엣지 삭제 → 노드·엣지 추가 → 노드 값 지우기.
    """

    add_nodes: list[NodeSpec] = Field(default_factory=list)
    add_edges: list[EdgeSpec] = Field(default_factory=list)
    remove_edge_ids: list[str] = Field(default_factory=list)
    unset_node_fields: list[NodeFieldRef] = Field(
        default_factory=list,
        description=(
            "노드 config에서 지울 위치(0.12.2). 없는 위치는 무시한다. 지정했을 때만 직렬화한다."
        ),
    )

    # 지정했을 때만 직렬화한다: 0.12.1 이하 제안 형식과 같게.
    _OMIT_WHEN_UNSET: ClassVar[tuple[tuple[str, ...], ...]] = (("unset_node_fields",),)


class IssueSuggestion(ContractModel):
    """검증 이슈의 수정 제안 하나. 화면은 이슈 코드가 아니라 이 데이터로 제안 버튼을 그린다."""

    id: NonEmptyStr
    label: str = Field(description="버튼 문구.")
    patch: GraphPatch = Field(default_factory=GraphPatch)


class IssueGroup(ContractModel):
    """같은 원인의 이슈 묶음 표시(0.12.2). 화면은 `key`가 같은 이슈를 한 행으로 묶는다."""

    key: NonEmptyStr = Field(description="묶음 키(불투명 문자열, 같으면 한 행).")
    message: str = Field(description="묶음 행 문장(노드 이름 없는 문장, 사용자 언어).")


class Issue(OmitWhenUnsetContract):
    """검증 이슈(그래프·정의 검증 결과).

    대상: `node_id`가 있으면 그 노드, `edge_id`가 있으면 그 엣지, 둘 다 없으면 그래프 전체.
    `path`는 RFC 6901 JSON Pointer이며 기준은 대상에 따라 다르다:
    노드 → 노드의 `config`, 엣지 → 엣지의 `config`, 그래프 → 그래프 문서.
    빈 문자열은 기준 객체 자체.
    """

    severity: IssueSeverity
    code: NonEmptyStr
    message: str
    node_id: str | None = None
    edge_id: str | None = None
    path: JsonPointer | None = None
    details: JsonObject = Field(default_factory=dict)
    suggestions: list[IssueSuggestion] = Field(
        default_factory=list, description="서버가 계산한 수정 제안(없으면 제안 버튼 없음)."
    )
    blocks_run: bool | None = Field(
        default=None,
        description=(
            "이 이슈가 있으면 실행이 거부되는지. 검증한 쪽이 정한다. "
            "null = 정하지 않음(이 경우 severity가 error인 것만 실행을 막는다)."
        ),
    )
    fix: Fix | None = Field(
        default=None,
        description=(
            "해결 버튼(다른 화면으로 이동, 0.8.0). 그래프 안 수정은 suggestions. null = 없음."
        ),
    )
    hint: str | None = Field(
        default=None,
        description="해결 안내 한 줄(0.12.2, 사용자 언어). null = 없음.",
    )
    group: IssueGroup | None = Field(
        default=None,
        description=(
            "묶음 표시(0.12.2). 같은 `group.key`의 이슈는 한 행으로 묶고 `group.message`를 보인다. "
            "같은 묶음 안 제안의 `id`가 같으면 화면은 버튼 하나로 모두 적용한다. null = 묶지 않음."
        ),
    )

    # 지정했을 때만 직렬화한다: 0.7.0 이하 이슈 형식과 같게(`hint`·`group`은 0.12.1 이하와 같게).
    _OMIT_WHEN_UNSET: ClassVar[tuple[tuple[str, ...], ...]] = (("fix",), ("hint",), ("group",))
