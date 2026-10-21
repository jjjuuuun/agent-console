"""서버 재시작 복구: 이전 프로세스에서 끝나지 않은 Run을 `interrupted`로 정리한다(design §4.5)."""

from __future__ import annotations

import time
import uuid

from pydantic import BaseModel

from agent_console_contracts import (
    ErrorInfo,
    Interaction,
    InteractionClosedPayload,
    NodeStatusPayload,
    RunEvent,
    RunStatusPayload,
)

from ._interactions import InteractionAnsweredBy, InteractionCloseReasons
from ._interfaces import Clock, EventSink, IdFactory, RunRecorder

_UNFINISHED_NODE = frozenset({"pending", "queued", "running", "waiting"})


def recover_unfinished_runs(
    recorder: RunRecorder,
    *,
    clock: Clock = time.time,
    ids: IdFactory = lambda: uuid.uuid4().hex,
    sink: EventSink | None = None,
    message: str = "서버가 재시작되어 실행이 중단되었습니다",
) -> list[str]:
    """끝나지 않은 Run(queued/running/paused/waiting)을 `interrupted`로 바꾸고 id 목록을 돌려준다.

    서버 시작 시 `GraphRuntime`을 만들기 전에 한 번 호출한다(동기). 각 Run에 대해(design §R14.5)
    - 대기 중(pending) 상호작용을 `expired`(close_reason `interrupted`)로 닫고 `interaction.closed`,
    - 끝나지 않은 NodeRun(pending/queued/running/waiting)은 `cancelled`(error.code=`interrupted`)로
      저장하고 `node.cancelled`(1R에는 재개할 parked wait가 없으므로 waiting 노드도 정리한다).
      반복 회차마다 NodeRun이 따로 있으므로 끝나지 않은 회차만 바뀌고 payload에 그 `iteration`이
      들어간다(design §5R.4). 위임자가 부른 호출 NodeRun도 같고, 이벤트
      `node_path`는 `invoked_by + [노드]`, payload에 `call`이 들어간다,
    - 마지막에 `run.interrupted`.
    이벤트는 그 Run의 마지막 seq 뒤에 이어 매겨 저장한 뒤 `sink`로 발행한다.
    끝난 Run에 남은 pending 상호작용도 같은 방식으로 닫는다(그 Run에는 `interaction.closed`만).
    """
    now = clock()
    error = ErrorInfo(code="interrupted", message=message)
    run_ids = recorder.runs.interrupt_unfinished(ended_at=now, error=error)
    closed = recorder.interactions.close_pending(
        status="expired",
        closed_at=now,
        answered_by=InteractionAnsweredBy.SYSTEM,
        close_reason=InteractionCloseReasons.INTERRUPTED,
    )
    by_run: dict[str, list[Interaction]] = {}
    for interaction in closed:
        by_run.setdefault(interaction.run_id, []).append(interaction)
    targets = list(run_ids) + [r for r in by_run if r not in run_ids]
    for run_id in targets:
        events = _interrupt_run(
            recorder,
            run_id,
            now=now,
            ids=ids,
            error=error,
            interactions=by_run.get(run_id, []),
            interrupted=run_id in run_ids,
        )
        recorder.events.append_many(events)
        if sink is not None:
            for event in events:
                sink.publish(event)
    return run_ids


def _interrupt_run(
    recorder: RunRecorder,
    run_id: str,
    *,
    now: float,
    ids: IdFactory,
    error: ErrorInfo,
    interactions: list[Interaction],
    interrupted: bool,
) -> list[RunEvent]:
    """한 Run의 상호작용·NodeRun을 정리하고 저장할 이벤트를 만든다."""
    seq = recorder.events.last_seq(run_id)
    events: list[RunEvent] = []

    def add(
        type: str,
        payload: BaseModel,
        node_path: list[str],
        attempt: int | None,
        actor: str | None = None,
    ) -> None:
        events.append(
            RunEvent(
                event_id=ids(),
                run_id=run_id,
                seq=seq + len(events) + 1,
                ts=now,
                type=type,
                node_path=node_path,
                attempt=attempt,
                actor=actor,
                payload=payload.model_dump(mode="json", by_alias=True),
            )
        )

    for interaction in interactions:
        add(
            "interaction.closed",
            InteractionClosedPayload(
                interaction_id=interaction.id,
                kind=interaction.kind,
                status="expired",
                reason=interaction.close_reason,
            ),
            list(interaction.node_path),
            interaction.attempt,
            interaction.actor,
        )
    if not interrupted:
        return events

    for node_run in recorder.runs.list_node_runs(run_id):
        if node_run.status not in _UNFINISHED_NODE:
            continue
        started = node_run.started_at
        fixed = node_run.model_copy(
            update={
                "status": "cancelled",
                "error": error,
                "ended_at": now,
                "duration_ms": round((now - started) * 1000) if started is not None else None,
            }
        )
        recorder.runs.save_node_run(fixed)
        invoked = fixed.invoked_by is not None
        add(
            "node.cancelled",
            NodeStatusPayload(
                status="cancelled",
                node_type=fixed.node_type,
                iteration=fixed.iteration,
                call=fixed.call if invoked else None,
                error=error,
            ),
            [*(fixed.invoked_by or []), fixed.node_id],
            fixed.attempt,
        )
    add("run.interrupted", RunStatusPayload(status="interrupted", error=error), [], None)
    return events
