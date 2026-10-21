"""테스트 도우미(공개, 운영 코드에서 쓰지 않는다): 백엔드 어댑터(X3) 테스트용 sink.

백엔드 어댑터 테스트가 함께 쓰는 **유일한** 구현이다(claude-sdk·fake 등은 이것을 다시 내보낸다).

- `ValidatingSink`: 엔진 없이 `BackendEventSink`를 만족하고, `emit`된 이벤트를 `RunEvent`로 만들어
  `parse_run_event`로 계약 검증한 뒤 기록한다. `NodeContext`처럼 `child_path`를 제공하고 하위
  `node_path`가 이 노드 경로로 시작하는지 검사한다.
- `ListeningSink`: + 선택 능력 `SubagentResultListener`(서브에이전트 결과 알림을 `results`에).
- `InteractiveSink`: + 선택 능력 `InteractivePort`(정해 둔 응답 함수로 상호작용 결과를 준다).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from pydantic import BaseModel

from agent_console_contracts import RunEvent, parse_run_event

from ._interactions import InteractionOutcome, InteractionRequest

__all__ = ["Answer", "InteractiveSink", "ListeningSink", "ValidatingSink"]


class ValidatingSink:
    """`emit`된 이벤트를 계약으로 검증하며 기록하는 `BackendEventSink`.

    Args:
        node_path: 이 sink가 흉내 내는 노드 경로(기본 `["n1"]`). `node_path`를 생략한 이벤트의 경로.
        run_id: 이벤트 머리의 run id.
    """

    def __init__(self, node_path: Sequence[str] = ("n1",), *, run_id: str = "r1") -> None:
        self.node_path = list(node_path)
        self.run_id = run_id
        self.events: list[RunEvent] = []

    def child_path(self, node_id: str) -> list[str]:
        """이 노드 실행 안에서 부른 대상 노드의 경로(`NodeContext.child_path`와 같은 규칙)."""
        return [*self.node_path, node_id]

    async def emit(
        self,
        type: str,
        payload: Mapping[str, Any] | BaseModel | None = None,
        *,
        raw: Any = None,
        evidence: str = "observed",
        actor: str | None = None,
        node_path: Sequence[str] | None = None,
    ) -> RunEvent:
        """이벤트를 만들어 계약 검증 후 기록한다.

        Raises:
            ValueError: `node_path`가 이 노드 경로로 시작하지 않을 때.
            pydantic.ValidationError: 알려진 type의 payload가 계약과 다를 때.
        """
        path = list(node_path) if node_path is not None else list(self.node_path)
        if path[: len(self.node_path)] != self.node_path:
            raise ValueError(f"node_path {path!r}는 {self.node_path!r}로 시작해야 합니다")
        body = (
            payload.model_dump(mode="json", by_alias=True)
            if isinstance(payload, BaseModel)
            else dict(payload or {})
        )
        event = RunEvent(
            event_id=f"e{len(self.events) + 1}",
            run_id=self.run_id,
            seq=len(self.events) + 1,
            ts=0.0,
            node_path=path,
            attempt=1,
            actor=actor,
            type=type,
            payload=body,
            raw=raw,
            evidence=evidence,
        )
        parse_run_event(event)
        self.events.append(event)
        return event

    @property
    def types(self) -> list[str]:
        """기록된 이벤트 type 순서."""
        return [e.type for e in self.events]

    def of(self, type: str) -> list[dict[str, Any]]:
        """그 type 이벤트의 payload 목록."""
        return [e.payload for e in self.events if e.type == type]

    def at(self, *node_path: str) -> list[RunEvent]:
        """그 `node_path`로 나간 이벤트 목록."""
        return [e for e in self.events if e.node_path == list(node_path)]


class ListeningSink(ValidatingSink):
    """`ValidatingSink` + `SubagentResultListener`: 서브에이전트 결과 알림을 `results`에 모은다.

    Args:
        node_path: `ValidatingSink`와 같다.
        fail: True면 알림에서 예외를 던진다(백엔드가 경고 이벤트로 바꾸는지 확인용).
    """

    def __init__(
        self, node_path: Sequence[str] = ("n1",), *, fail: bool = False, run_id: str = "r1"
    ) -> None:
        super().__init__(node_path, run_id=run_id)
        self.fail = fail
        self.results: list[dict[str, Any]] = []

    async def on_subagent_result(
        self, name: str, *, text: str, status: str, actor: str | None, tool_use_id: str
    ) -> None:
        """알림 하나를 `{name, text, status, actor, tool_use_id}`로 기록한다."""
        if self.fail:
            raise RuntimeError("listener failed")
        self.results.append(
            {
                "name": name,
                "text": text,
                "status": status,
                "actor": actor,
                "tool_use_id": tool_use_id,
            }
        )


type Answer = Callable[[InteractionRequest], InteractionOutcome | dict[str, Any] | None]
"""요청 → 결과. dict면 그 응답으로 answered, None이면 cancelled(reason=cancelled)."""


class InteractiveSink(ListeningSink):
    """`ListeningSink` + `InteractivePort`: `request_input`을 기록하고 `answer`로 결과를 만든다.

    Args:
        answer: 요청 → 응답(dict = answered) / `InteractionOutcome` / None(Run 취소로 닫힘).
            기본은 항상 None.
        node_path: `ValidatingSink`와 같다.
    """

    def __init__(
        self,
        answer: Answer | None = None,
        node_path: Sequence[str] = ("n1",),
        *,
        run_id: str = "r1",
    ) -> None:
        super().__init__(node_path, run_id=run_id)
        self.answer: Answer = answer or (lambda _req: None)
        self.requests: list[InteractionRequest] = []

    async def request_input(self, req: InteractionRequest) -> InteractionOutcome:
        """요청을 기록하고 `answer` 결과를 돌려준다."""
        self.requests.append(req)
        out = self.answer(req)
        iid = f"i{len(self.requests)}"
        if isinstance(out, InteractionOutcome):
            return out
        if out is None:
            return InteractionOutcome(interaction_id=iid, status="cancelled", reason="cancelled")
        return InteractionOutcome(interaction_id=iid, status="answered", response=out)
