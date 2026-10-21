"""실행 이벤트 → 위임 흐름(`Trace`).

연결 규칙(명시 id만, 시간상 이웃은 잇지 않는다 — agent_bench `link_events` 원칙):

- 노드 span: `node.*` 이벤트의 (`node_path == [노드]`, `attempt`, payload `iteration`).
  반복 회차마다 span 하나(design §5R.12).
- 호출 span(위임자가 부른 NodeRun, design §5R.6): `node.*` 이벤트의 `node_path`(= 위임자 경로 +
  대상)와 payload `call`. 부모는 `node_path`의 앞부분(= NodeRun `invoked_by`)이 가리키는 span.
  호출 회차마다 span 하나(자기 세션).
- 위임(서브에이전트) span의 부모: `agent.subagent_started.tool_use_id` = 부모 쪽
  `agent.tool_call.tool_use_id`, 없으면 `node_path`의 앞부분.
- 위임 span의 끝: `agent.subagent_stopped.subagent_id`(없으면 `tool_use_id`).
- 상호작용("사용자 대기") span: `interaction.*`의 `interaction_id`. 부모는 상호작용의
  `node_path`·`attempt`.
- 넘김 화살표: `edge.traversed`의 출발·도착 노드 id(사이클 연결도 같다, `kind` = 연결 종류).
- 자식 Run 묶음: `run.child_started.child_run_id`. 자식 Run의 trace를 부른 노드 span 아래에 붙인다.
"""

import json
import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from agent_console_contracts import (
    AgentSessionStartedPayload,
    AgentSubagentPayload,
    AgentToolCallPayload,
    AgentUsagePayload,
    EdgeTraversedPayload,
    InteractionAnsweredPayload,
    InteractionClosedPayload,
    InteractionRequestedPayload,
    NodeRun,
    NodeStatusPayload,
    RunChildStartedPayload,
    RunEvent,
    Trace,
    TraceLink,
    TraceSpan,
    Usage,
)

_log = logging.getLogger(__name__)

SPAN_KIND_NODE = "node"
"""자기 NodeRun이 있는 노드 실행(독립 세션). 위임자가 부른 호출 NodeRun도 이 종류(`call` 있음)."""

SPAN_KIND_DELEGATED = "delegated"
"""위 노드 세션 안에서 위임받은 서브에이전트 실행(같은 세션)."""

SPAN_KIND_INTERACTION = "interaction"
"""사용자 응답을 기다린 구간(상호작용 하나)."""

_NODE_END = frozenset({"node.completed", "node.failed", "node.cancelled", "node.skipped"})


@dataclass(slots=True)
class _Span:
    id: str
    kind: str
    node_id: str | None = None
    node_path: list[str] = field(default_factory=list)
    parent_id: str | None = None
    actor: str | None = None
    attempt: int | None = None
    iteration: int | None = None
    call: int | None = None
    status: str | None = None
    started_at: float | None = None
    ended_at: float | None = None
    usage: Usage | None = None
    session_id: str | None = None
    tool_use_id: str | None = None
    interaction_id: str | None = None
    order: int | None = None
    task_preview: str | None = None
    result_preview: str | None = None

    def build(self) -> TraceSpan:
        return TraceSpan(
            id=self.id,
            kind=self.kind,
            parent_id=self.parent_id,
            node_id=self.node_id,
            node_path=self.node_path,
            actor=self.actor,
            attempt=self.attempt,
            iteration=self.iteration,
            call=self.call,
            status=self.status,
            started_at=self.started_at,
            ended_at=self.ended_at,
            usage=self.usage,
            session_id=self.session_id,
            tool_use_id=self.tool_use_id,
            interaction_id=self.interaction_id,
            order=self.order,
            task_preview=self.task_preview,
            result_preview=self.result_preview,
        )


def node_span_id(node_id: str, attempt: int | None, iteration: int | None = None) -> str:
    """노드 span id(같은 노드·시도·회차는 같은 id). 회차 0(또는 모름)은 회차를 붙이지 않는다."""
    base = f"node:{node_id}#{attempt or 1}"
    return f"{base}@{iteration}" if iteration else base


def call_span_id(node_path: Iterable[str], call: int) -> str:
    """호출 span id(위임자 경로 + 대상, 호출 회차). 호출 회차는 Run 안에서 대상마다 유일하다."""
    return f"call:{'/'.join(node_path)}#{call}"


def delegated_span_id(subagent_id: str) -> str:
    """위임 span id."""
    return f"delegated:{subagent_id}"


def interaction_span_id(interaction_id: str) -> str:
    """상호작용 span id."""
    return f"interaction:{interaction_id}"


def child_span_id(run_id: str, span_id: str) -> str:
    """자식 Run의 span을 부모 trace에 붙일 때의 id(Run id로 범위를 나눈다)."""
    return f"run:{run_id}/{span_id}"


def _clip(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    return text if len(text) <= limit else text[: max(limit - 1, 0)] + "…"


def _inputs_preview(inputs: Mapping[str, Any]) -> str | None:
    """NodeRun 입력 미리보기: 값이 문자열 하나면 그 문자열, 아니면 JSON."""
    if not inputs:
        return None
    values = list(inputs.values())
    if len(values) == 1 and isinstance(values[0], str):
        return values[0]
    return json.dumps(dict(inputs), ensure_ascii=False, default=str)


def _attach_child(child: Trace, owner: str | None) -> tuple[list[TraceSpan], list[TraceLink]]:
    """자식 Run trace를 부모 trace에 붙일 모양으로 바꾼다.

    자식 Run 자신의 span(=`run_id`가 비었거나 자식 Run id)은 id를 `child_span_id`로 바꾸고
    `run_id`를 싣는다. 맨 위 span(부모 없음)은 `owner`(부른 노드 span) 아래로 간다. 손자 Run의
    span은 이미 범위가 나뉘어 있어 id를 두고 부모 참조만 맞춘다.
    """
    rid = child.run_id
    own = {s.id for s in child.spans if s.run_id in (None, rid)}

    def scoped(span_id: str | None) -> str | None:
        if span_id is None:
            return None
        return child_span_id(rid, span_id) if span_id in own else span_id

    spans: list[TraceSpan] = []
    for span in child.spans:
        if span.id in own:
            parent = scoped(span.parent_id) if span.parent_id is not None else owner
            spans.append(
                span.model_copy(update={"id": scoped(span.id), "parent_id": parent, "run_id": rid})
            )
        else:
            spans.append(span.model_copy(update={"parent_id": scoped(span.parent_id)}))
    links: list[TraceLink] = []
    for link in child.links:
        if link.run_id in (None, rid):
            links.append(
                link.model_copy(
                    update={
                        "source": scoped(link.source),
                        "target": scoped(link.target),
                        "run_id": rid,
                    }
                )
            )
        else:
            links.append(link)
    return spans, links


class _Builder:
    def __init__(
        self,
        edge_kinds: Mapping[str, str],
        call_edges: Mapping[tuple[str, str], str],
        call_inputs: Mapping[tuple[tuple[str, ...], int], Mapping[str, Any]],
        preview_chars: int,
    ) -> None:
        self.edge_kinds = edge_kinds
        self.call_edges = call_edges
        self.call_inputs = call_inputs
        self.preview_chars = preview_chars
        self.spans: dict[str, _Span] = {}
        # (노드 id, 시도) → 가장 최근에 만든 회차 span. 한 노드는 한 번에 한 회차만 돈다.
        self.node_latest: dict[tuple[str, int], str] = {}
        # 노드 id → 가장 최근에 만든 span(넘김 화살표의 출발).
        self.node_last: dict[str, str] = {}
        # 경로 → 열려 있는 호출 span. 같은 대상은 엔진이 직렬로 돌려 경로마다 하나뿐이다.
        self.open_calls: dict[tuple[str, ...], str] = {}
        self.call_links: list[TraceLink] = []
        self.delegated_by_path: dict[tuple[int, tuple[str, ...]], list[str]] = {}
        self.delegated_by_tool: dict[str, str] = {}
        self.tool_owner: dict[str, str] = {}
        self.node_starts: dict[str, list[tuple[int, str]]] = {}  # 노드 id → (seq, span id) 시작 순
        # (edge seq, 출발 span, 도착 노드, edge id, kind)
        self.pending_links: list[tuple[int, str, str, str, str | None]] = []
        self.child_owner: dict[str, str | None] = {}  # 자식 Run id → 부른 노드 span
        self.skipped = 0

    # ---------------------------------------------------------------- 도우미

    def _payload[M: BaseModel](self, model: type[M], event: RunEvent) -> M | None:
        try:
            return model.model_validate(event.payload)
        except ValidationError:
            self.skipped += 1
            _log.debug("형식이 틀린 이벤트 건너뜀: %s seq=%s", event.type, event.seq)
            return None

    def _node_span(
        self, node_id: str, attempt: int | None, iteration: int | None, *, create: bool
    ) -> _Span | None:
        sid = node_span_id(node_id, attempt, iteration)
        span = self.spans.get(sid)
        if span is None and create:
            span = _Span(id=sid, kind=SPAN_KIND_NODE, node_id=node_id, node_path=[node_id])
            span.attempt = attempt or 1
            span.iteration = iteration
            self.spans[sid] = span
            self.node_latest[(node_id, attempt or 1)] = sid
            self.node_last[node_id] = sid
        return span

    def _latest_node(self, node_id: str, attempt: int | None) -> _Span | None:
        sid = self.node_latest.get((node_id, attempt or 1))
        return self.spans.get(sid) if sid is not None else None

    def _open_call(self, path: list[str]) -> _Span | None:
        sid = self.open_calls.get(tuple(path))
        return self.spans.get(sid) if sid is not None else None

    def _session_span(self, path: list[str], attempt: int | None) -> _Span | None:
        """자기 세션이 있는 span(노드 span 또는 열린 호출 span)."""
        if len(path) == 1:
            return self._latest_node(path[0], attempt)
        if len(path) >= 2:
            return self._open_call(path)
        return None

    def _owner_of_path(self, path: list[str], attempt: int | None) -> str | None:
        """`node_path`가 가리키는 span(명시 경로). 후보가 여럿이라 모호하면 한 단계 위로."""
        if not path:
            return None
        if len(path) == 1:
            span = self._latest_node(path[0], attempt)
            return span.id if span is not None else None
        candidates = list(self.delegated_by_path.get((attempt or 1, tuple(path)), []))
        call = self.open_calls.get(tuple(path))
        if call is not None:
            candidates.append(call)
        if len(candidates) == 1:
            return candidates[0]
        return self._owner_of_path(path[:-1], attempt)

    # ---------------------------------------------------------------- 이벤트별

    def feed(self, event: RunEvent) -> None:
        handler = _HANDLERS.get(event.type)
        if handler is None and event.type.startswith("node."):
            handler = _Builder._on_node
        if handler is not None:
            handler(self, event)

    def _on_node(self, event: RunEvent) -> None:
        if not event.node_path:
            return
        payload = self._payload(NodeStatusPayload, event)
        if payload is None:
            return
        if len(event.node_path) == 1:
            self._on_scheduled_node(event, payload)
        elif payload.call is not None:
            self._on_call_node(event, payload)
        # 그 밖의 긴 경로(호출 회차 없는 하위 노드)는 범위 밖

    def _on_scheduled_node(self, event: RunEvent, payload: NodeStatusPayload) -> None:
        node_id = event.node_path[0]
        iteration = payload.iteration
        create = event.type != "node.queued" and not (
            event.type == "node.skipped"
            and node_span_id(node_id, event.attempt, iteration) not in self.spans
        )
        span = self._node_span(node_id, event.attempt, iteration, create=create)
        if span is None:
            return
        first_start = event.type == "node.started" and span.started_at is None
        self._apply_status(span, event, payload)
        if first_start:
            self.node_starts.setdefault(node_id, []).append((event.seq, span.id))

    def _on_call_node(self, event: RunEvent, payload: NodeStatusPayload) -> None:
        path = list(event.node_path)
        call = payload.call or 0
        sid = call_span_id(path, call)
        span = self.spans.get(sid)
        if span is None:
            if event.type == "node.queued" or event.type == "node.skipped":
                return
            caller = path[:-1]
            span = _Span(
                id=sid,
                kind=SPAN_KIND_NODE,
                node_id=path[-1],
                node_path=path,
                parent_id=self._owner_of_path(caller, event.attempt),
                attempt=event.attempt or 1,
                iteration=payload.iteration,
                call=call,
            )
            task = self.call_inputs.get((tuple(path), call))
            if task is not None:
                span.task_preview = _clip(_inputs_preview(task), self.preview_chars)
            self.spans[sid] = span
            if span.parent_id is not None:
                edge_id = self.call_edges.get((caller[-1], path[-1]))
                self.call_links.append(
                    TraceLink(
                        source=span.parent_id,
                        target=sid,
                        edge_id=edge_id,
                        kind=self.edge_kinds.get(edge_id) if edge_id is not None else None,
                    )
                )
        self._apply_status(span, event, payload)
        if event.type in _NODE_END:
            if self.open_calls.get(tuple(path)) == sid:
                del self.open_calls[tuple(path)]
        else:
            self.open_calls[tuple(path)] = sid

    def _apply_status(self, span: _Span, event: RunEvent, payload: NodeStatusPayload) -> None:
        if event.actor is not None:
            span.actor = event.actor
        span.status = payload.status
        if event.type == "node.started" and span.started_at is None:
            span.started_at = event.ts
        if event.type in _NODE_END:
            span.ended_at = event.ts
            if payload.usage is not None:
                span.usage = payload.usage
            span.result_preview = _clip(payload.outputs_preview, self.preview_chars)

    def _on_session(self, event: RunEvent) -> None:
        payload = self._payload(AgentSessionStartedPayload, event)
        if payload is None:
            return
        span = self._session_span(list(event.node_path), event.attempt)
        if span is not None:
            span.session_id = payload.session_id

    def _on_usage(self, event: RunEvent) -> None:
        payload = self._payload(AgentUsagePayload, event)
        if payload is None:
            return
        span = self._session_span(list(event.node_path), event.attempt)
        if span is not None and span.ended_at is None:
            span.usage = payload.usage  # 누적값(교체)

    def _on_tool_call(self, event: RunEvent) -> None:
        payload = self._payload(AgentToolCallPayload, event)
        if payload is None:
            return
        owner = self._owner_of_path(event.node_path, event.attempt)
        if owner is not None:
            self.tool_owner.setdefault(payload.tool_use_id, owner)

    def _on_subagent_started(self, event: RunEvent) -> None:
        payload = self._payload(AgentSubagentPayload, event)
        if payload is None:
            return
        sid = delegated_span_id(payload.subagent_id)
        if sid in self.spans:
            return
        # 위임 대상 이벤트는 node_path=[위임자, 대상]. 위임자 경로로 왔으면 대상 이름을 붙인다.
        path = list(event.node_path)
        if len(path) < 2 and payload.name:
            path = [*path, payload.name]
        node_id = payload.name or (path[-1] if len(path) >= 2 else None)
        parent = self.tool_owner.get(payload.tool_use_id) if payload.tool_use_id else None
        if parent is None and len(path) >= 2:
            parent = self._owner_of_path(path[:-1], event.attempt)
        span = _Span(
            id=sid,
            kind=SPAN_KIND_DELEGATED,
            node_id=node_id,
            node_path=path,
            parent_id=parent,
            actor=event.actor,
            attempt=event.attempt or 1,
            status="running",
            started_at=event.ts,
            tool_use_id=payload.tool_use_id,
            task_preview=_clip(payload.task_preview, self.preview_chars),
        )
        self.spans[sid] = span
        if len(path) >= 2:
            self.delegated_by_path.setdefault((span.attempt or 1, tuple(path)), []).append(sid)
        if payload.tool_use_id:
            self.delegated_by_tool.setdefault(payload.tool_use_id, sid)

    def _on_subagent_stopped(self, event: RunEvent) -> None:
        payload = self._payload(AgentSubagentPayload, event)
        if payload is None:
            return
        span = self.spans.get(delegated_span_id(payload.subagent_id))
        if span is None and payload.tool_use_id:
            sid = self.delegated_by_tool.get(payload.tool_use_id)
            span = self.spans.get(sid) if sid is not None else None
        if span is None:
            return  # 시작을 못 본 종료는 어디에도 잇지 않는다
        span.status = payload.status or "completed"
        span.ended_at = event.ts
        if payload.usage is not None:
            span.usage = payload.usage
        if payload.result_preview is not None:
            span.result_preview = _clip(payload.result_preview, self.preview_chars)

    def _on_interaction_requested(self, event: RunEvent) -> None:
        payload = self._payload(InteractionRequestedPayload, event)
        if payload is None:
            return
        item = payload.interaction
        sid = interaction_span_id(item.id)
        if sid in self.spans:
            return
        path = list(item.node_path) or [item.node_id]
        span = _Span(
            id=sid,
            kind=SPAN_KIND_INTERACTION,
            node_id=item.node_id,
            node_path=path,
            parent_id=self._owner_of_path(path, item.attempt),
            actor=item.actor,
            attempt=item.attempt,
            status=item.status,
            started_at=item.created_at,
            ended_at=item.closed_at,
            interaction_id=item.id,
            task_preview=_clip(item.title or item.message or item.kind, self.preview_chars),
        )
        self.spans[sid] = span

    def _on_interaction_answered(self, event: RunEvent) -> None:
        payload = self._payload(InteractionAnsweredPayload, event)
        if payload is None:
            return
        span = self.spans.get(interaction_span_id(payload.interaction_id))
        if span is not None:
            span.status = "answered"
            span.ended_at = event.ts
            span.result_preview = _clip(payload.response_preview, self.preview_chars)

    def _on_interaction_closed(self, event: RunEvent) -> None:
        payload = self._payload(InteractionClosedPayload, event)
        if payload is None:
            return
        span = self.spans.get(interaction_span_id(payload.interaction_id))
        if span is not None:
            span.status = payload.status
            span.ended_at = event.ts
            span.result_preview = payload.reason

    def _on_edge(self, event: RunEvent) -> None:
        payload = self._payload(EdgeTraversedPayload, event)
        if payload is None:
            return
        source = self.node_last.get(payload.source.node)
        if source is None:
            return  # 출발 노드 실행을 못 봤으면 잇지 않는다
        # 연결 종류: 이벤트에 실렸으면(4R.18 이후) 그것, 없으면(옛 이벤트) 실행 당시 그래프에서.
        kind = payload.kind or self.edge_kinds.get(payload.edge_id)
        self.pending_links.append((event.seq, source, payload.target.node, payload.edge_id, kind))

    def _on_child_started(self, event: RunEvent) -> None:
        payload = self._payload(RunChildStartedPayload, event)
        if payload is None:
            return
        # 이벤트 node_path = 자식 Run을 만든 노드의 경로(호출 안이면 위임자 경로 포함).
        path = list(event.node_path) or [payload.node_id]
        self.child_owner.setdefault(payload.child_run_id, self._owner_of_path(path, event.attempt))

    # ---------------------------------------------------------------- 마무리

    def _session_root(self, span: _Span) -> _Span | None:
        """위임 span이 도는 세션의 주인(부모 사슬에서 처음 만나는 위임 아닌 span)."""
        seen: set[str] = set()
        current = span
        while current.parent_id is not None and current.parent_id not in seen:
            seen.add(current.parent_id)
            parent = self.spans.get(current.parent_id)
            if parent is None:
                break
            if parent.kind != SPAN_KIND_DELEGATED:
                return parent
            current = parent
        if span.node_path:
            return self._latest_node(span.node_path[0], span.attempt)
        return None

    def finish(self, run_id: str, children: Mapping[str, Trace]) -> Trace:
        # 서브에이전트는 위임자 세션 안에서 돈다("같은 세션" 표시).
        for span in self.spans.values():
            if span.kind == SPAN_KIND_DELEGATED and span.session_id is None:
                root = self._session_root(span)
                if root is not None:
                    span.session_id = root.session_id
        links: list[TraceLink] = []
        order = 0
        for edge_seq, source, target_node, edge_id, kind in self.pending_links:
            # 도착 = 이 엣지를 지난 뒤 도착 노드에서 처음 시작된 시도·회차
            # (node.started seq > edge seq).
            # 그런 시도가 없으면(답변 연결 등 실행 안 됨) 잇지 않는다. 시도 번호로 추측하지 않는다.
            target_id = next(
                (sid for seq, sid in self.node_starts.get(target_node, []) if seq > edge_seq), None
            )
            if target_id is None:
                continue
            target = self.spans[target_id]
            links.append(TraceLink(source=source, target=target.id, edge_id=edge_id, kind=kind))
            if target.order is None:
                order += 1
                target.order = order
        links.extend(self.call_links)
        spans = [s.build() for s in self.spans.values()]
        known = list(self.child_owner) + sorted(c for c in children if c not in self.child_owner)
        for child_id in known:
            child = children.get(child_id)
            if child is None:
                continue
            child_spans, child_links = _attach_child(child, self.child_owner.get(child_id))
            spans.extend(child_spans)
            links.extend(child_links)
        return Trace(run_id=run_id, spans=spans, links=links)


_HANDLERS: dict[str, Callable[[_Builder, RunEvent], None]] = {
    "agent.session_started": _Builder._on_session,
    "agent.usage": _Builder._on_usage,
    "agent.tool_call": _Builder._on_tool_call,
    "agent.subagent_started": _Builder._on_subagent_started,
    "agent.subagent_stopped": _Builder._on_subagent_stopped,
    "interaction.requested": _Builder._on_interaction_requested,
    "interaction.answered": _Builder._on_interaction_answered,
    "interaction.closed": _Builder._on_interaction_closed,
    "edge.traversed": _Builder._on_edge,
    "run.child_started": _Builder._on_child_started,
}


def build_trace(
    events: Iterable[RunEvent],
    *,
    run_id: str | None = None,
    edge_kinds: Mapping[str, str] | None = None,
    call_edges: Mapping[tuple[str, str], str] | None = None,
    node_runs: Iterable[NodeRun] | None = None,
    children: Mapping[str, Trace] | None = None,
    preview_chars: int = 200,
) -> Trace:
    """한 실행의 이벤트로 위임 흐름을 만든다.

    - 노드 실행 = `node` span(자기 NodeRun·세션). 반복 회차마다 span 하나(`iteration`).
    - 위임자가 부른 호출 NodeRun = 위임자 span의 **자식** `node` span(별도 세션, `call`).
      호출 회차마다 span 하나. 위임자 span → 호출 span 링크(`kind` = 호출 연결 종류, 알 때만)를
      함께 싣는다(부모-자식이라 화면은 화살표로 그리지 않고 집계가 연결 종류를 읽는다).
    - 서브에이전트 = 위임자 span의 **자식** `delegated` span(같은 세션).
    - 넘기기 = 형제 `node` span 사이의 `TraceLink`(`edge.traversed`). 도착 span에 넘김 순번 `order`.
      사이클 연결로 앞 단계가 다시 열리면 다음 회차 span으로 가는 링크다.
    - 상호작용 = 요청한 노드(또는 위임·호출) span의 자식 `interaction` span("사용자 대기").
    - 자식 Run(`children`) = 자식 Run trace를 `run.child_started`를 낸 노드 span 아래에 붙인다.
      자식 Run의 span·링크에는 `run_id`가 실리고 span id는 `child_span_id`로 범위가 나뉜다.
    - 관계는 명시 id로만 잇는다. 같은 시각·바로 다음에 일어났다는 이유로 잇지 않으며,
      연결 키가 없는 span은 부모 없이(`parent_id=None`) 남는다.
    - 형식이 틀린 이벤트와 모르는 type은 건너뛴다.

    Args:
        events: 한 Run의 이벤트(순서 무관, `seq`로 정렬한다).
        run_id: 결과의 Run id. 생략하면 첫 이벤트의 `run_id`.
        edge_kinds: 엣지 id → 연결 종류 id(그래프 정의에서). 이벤트 payload에 `kind`가 있으면 그것이
            먼저다(4R.18). 없는 옛 이벤트는 이 표로 `TraceLink.kind`를 채운다.
        call_edges: (위임자 노드 id, 대상 노드 id) → 호출 연결 id(그래프 정의에서, 그 쌍의 연결이
            하나일 때만). 호출 span 링크의 `edge_id`·`kind`(`edge_kinds`로)를 채운다.
        node_runs: 이 Run의 NodeRun 기록. 호출 NodeRun(`invoked_by`)의 입력으로 호출 span의
            `task_preview`(위임 과제)를 채운다. 키 = (`invoked_by` + 노드, `call`).
        children: 자식 Run id → 그 Run의 trace(먼저 만들어 넘긴다, 손자는 이미 붙어 있어야 한다).
            이 Run의 `run.child_started`가 가리키지 않는 자식도 부모 없이 붙인다.
        preview_chars: 과제·결과 미리보기 최대 길이.

    Raises:
        ValueError: 이벤트가 없고 `run_id`도 없을 때, 또는 다른 Run의 이벤트가 섞였을 때.
    """
    ordered = sorted(events, key=lambda e: e.seq)
    rid = run_id or (ordered[0].run_id if ordered else None)
    if rid is None:
        raise ValueError("이벤트가 없으면 run_id가 필요합니다")
    if any(e.run_id != rid for e in ordered):
        raise ValueError(f"Run {rid!r}가 아닌 이벤트가 섞여 있습니다")
    call_inputs: dict[tuple[tuple[str, ...], int], Mapping[str, Any]] = {}
    for node_run in node_runs or ():
        if node_run.invoked_by is not None:
            key = (tuple([*node_run.invoked_by, node_run.node_id]), node_run.call)
            call_inputs[key] = node_run.inputs
    builder = _Builder(edge_kinds or {}, call_edges or {}, call_inputs, preview_chars)
    for event in ordered:
        builder.feed(event)
    return builder.finish(rid, children or {})
