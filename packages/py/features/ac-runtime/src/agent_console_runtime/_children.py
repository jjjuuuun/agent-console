"""자식 Run(`ctx.run_child`, design §5R.7)의 공개 타입과 준비자 확장 지점.

노드(예: 중첩 팀 노드)가 실행 안에서 다른 그래프를 **자식 Run**으로 실행한다. 엔진은 노드 종류·팀
의미를 모른다. 자식 Run을 어떻게 준비할지(검증·허용 상호작용·설정 층·서비스)는 앱이 주입하는
`ChildRunPreparer`가 정하고, 없으면 부모 Run의 값을 물려받는다.
"""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from agent_console_contracts import (
    DelegationSettings,
    ErrorInfo,
    FlowSettings,
    Graph,
    InteractionGrant,
    InteractionSettings,
    Run,
    RunReplyPayload,
    RunStatus,
    Usage,
)

from ._services import Services


@dataclass(frozen=True, slots=True)
class ChildRunResult:
    """자식 Run 하나의 결과(`NodeContext.run_child`의 반환값, 런타임 전용 — 계약 타입 아님).

    Attributes:
        run_id: 자식 Run id. 자식 Run을 만들지 않고 거절했으면 None(중첩 한도·순환·검증 실패·
            이미 취소됨).
        status: 자식 Run의 최종 상태(`completed`·`failed`·`cancelled`·`interrupted`·`waiting`).
        replies: 자식 Run이 낸 답변(`run.reply` payload, 낸 순서, 비밀을 가린 저장본).
        totals: 자식 Run 사용량 합계(`Run.totals`). 엔진은 부모 Run `totals`에 자동으로 더하지
            않는다: 노드가 `NodeResult.usage`로 돌려줘야 부모 합계에 들어간다(이중 집계 방지).
        error: 실패·취소·거절 사유.
    """

    run_id: str | None
    status: RunStatus
    replies: tuple[RunReplyPayload, ...] = ()
    totals: Usage | None = None
    error: ErrorInfo | None = None


@dataclass(frozen=True, slots=True)
class ChildRunRequest:
    """자식 Run 준비자에게 주는 요청(엔진이 만든다).

    Attributes:
        graph: 실행할 자식 그래프(깊은 사본).
        input: 자식 Run 입력.
        parent: 부모 Run(요청 시점 사본).
        node_id: 자식 Run을 만든 부모 그래프의 노드 id(`Run.parent_node_id`).
        node_path: 그 노드 실행의 이벤트 경로(호출 실행이면 위임자 경로 포함).
        ancestors: 루트부터 부모까지의 Run(부모가 마지막). 길이 = 자식의 중첩 깊이.
        services: 자식 Run에 넘길 기본 서비스(부모 Run 서비스 + `run_child(services=)`).
    """

    graph: Graph
    input: Mapping[str, Any]
    parent: Run
    node_id: str
    node_path: tuple[str, ...]
    ancestors: tuple[Run, ...]
    services: Services


@dataclass(frozen=True, slots=True)
class ChildRunPreparation:
    """준비자가 정한 자식 Run 시작 옵션. None인 값은 부모 Run 값을 물려받는다.

    Attributes:
        services: 자식 Run 노드 서비스(None = `ChildRunRequest.services`).
        interaction_grants: 자식 그래프 노드 id → 허용 상호작용(None = 없음).
        interaction_settings, flow_settings, delegation_settings: 자식 팀 구성 층까지 해석한
            설정(None = 부모 Run 값).
        checked: 참이면 준비자가 이미 엔진 검증(`validate_graph_with`)을 했다 — 엔진이 다시
            검증하지 않는다(입구 확인은 언제나 한다).
        run_context: 자식 Run `run.started` payload에 더할 값(None = 부모 Run 값,
            `GraphRuntime.start(run_context=)` 참고).
    """

    services: Services | None = None
    interaction_grants: Mapping[str, InteractionGrant] | None = None
    interaction_settings: InteractionSettings | None = None
    flow_settings: FlowSettings | None = None
    delegation_settings: DelegationSettings | None = None
    checked: bool = False
    run_context: Mapping[str, Any] | None = None


class ChildRunPreparer(Protocol):
    """자식 Run 준비 확장 지점(`GraphRuntime(child_preparer=)`).

    앱(예: 실행 모듈)이 일반 Run과 같은 준비 과정(팀 규칙 검사·허용 상호작용·설정 층·노드
    서비스)을 자식 Run에도 적용할 때 구현한다. 실행을 막으려면 `GraphValidationError`를 던진다
    (노드는 `failed` 결과, `error.code = validation_failed`, `details.issues`).
    동기 함수도 되고 awaitable을 돌려줘도 된다.
    """

    def __call__(
        self, request: ChildRunRequest
    ) -> ChildRunPreparation | Awaitable[ChildRunPreparation]: ...


__all__ = [
    "ChildRunPreparation",
    "ChildRunPreparer",
    "ChildRunRequest",
    "ChildRunResult",
]
