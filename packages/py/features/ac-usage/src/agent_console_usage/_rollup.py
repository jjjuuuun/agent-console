"""플랫폼 실행분 토큰 집계(design §R4.3): 에이전트·팀 구성·모델·일 단위.

재료는 NodeRun `usage`(노드 시도 하나의 최종값)와 `agent.subagent_stopped.usage`(위임 대상의 값)다.
에이전트(actor)·모델은 그 노드 시도의 `agent.session_started` 이벤트에서 찾는다(명시 id로만 잇고,
못 찾으면 `None`). 값이 없는 필드는 더하지 않고 `None`으로 남긴다.
"""

from __future__ import annotations

import builtins
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo
from typing import Any, Literal, Protocol, get_args

from pydantic import ValidationError

from agent_console_contracts import (
    AgentSubagentPayload,
    NodeRun,
    Run,
    RunEvent,
    TokenRollupRow,
    Usage,
)

__all__ = [
    "DEFAULT_PRECISION_TEXT",
    "ROLLUP_DIMENSIONS",
    "RollupDimension",
    "RollupEventSource",
    "RollupRunSource",
    "UsageRecord",
    "counts_toward_usage",
    "load_usage_records",
    "sum_usage",
    "token_rollup",
    "usage_records",
]

type RollupDimension = Literal["agent_id", "graph_id", "model", "day"]
"""집계 차원(`TokenRollupRow`의 필드 이름)."""

ROLLUP_DIMENSIONS: tuple[RollupDimension, ...] = get_args(RollupDimension.__value__)

SESSION_STARTED = "agent.session_started"
SUBAGENT_STOPPED = "agent.subagent_stopped"

DEFAULT_PRECISION_TEXT: Mapping[str, str] = {
    "total_only": "총 토큰만 있음(입력·출력 구분 없음)",
    "mixed": "일부 값은 총 토큰만 있음",
}
"""정밀도 메모 문구(키 `total_only`·`mixed`). `token_rollup(precision_text=…)`로 바꾼다."""

_SPLIT_FIELDS = ("input_tokens", "output_tokens", "cache_read_tokens", "cache_creation_tokens")


@dataclass(frozen=True, slots=True)
class UsageRecord:
    """사용량 한 건(집계 재료). 모르는 차원은 `None`."""

    run_id: str
    usage: Usage
    at: float | None = None
    agent_id: str | None = None
    graph_id: str | None = None
    model: str | None = None
    origin: str = "node"
    """`node`(NodeRun) 또는 `subagent`(위임 대상 종료 이벤트)."""


class RollupRunSource(Protocol):
    """Run·NodeRun 조회(저장소 `RunRepository`가 구조적으로 만족한다)."""

    def list(
        self,
        *,
        graph_id: str | None = None,
        root_only: bool = False,
        limit: int | None = None,
    ) -> builtins.list[Run]:
        """최신 생성순. `root_only`면 루트 Run만이고 `limit`은 그 조건을 건 뒤에 적용된다."""
        ...

    def list_node_runs(self, run_id: str) -> builtins.list[NodeRun]: ...


class RollupEventSource(Protocol):
    """Run 이벤트 조회(저장소 `EventRepository`가 구조적으로 만족한다)."""

    def list(
        self,
        run_id: str,
        *,
        since_seq: int = 0,
        limit: int | None = None,
        actor: str | None = None,
        type_prefix: str | None = None,
    ) -> builtins.list[RunEvent]: ...


def usage_records(
    run: Run, node_runs: Iterable[NodeRun], events: Iterable[RunEvent]
) -> list[UsageRecord]:
    """Run 하나 → 사용량 기록.

    - NodeRun마다(`usage`가 있으면) 한 건. actor·model = 같은 노드(`node_path == [node_id]`)·
      같은 attempt의 `agent.session_started`.
    - `agent.subagent_stopped`(`usage`가 있으면) 한 건. actor = 이벤트 actor(위임 대상),
      모델은 모름.
    """
    sessions: dict[tuple[str, int], tuple[str | None, str | None]] = {}
    subagents: list[UsageRecord] = []
    for event in events:
        if event.type == SESSION_STARTED and len(event.node_path) == 1:
            model = event.payload.get("model")
            key = (event.node_path[0], event.attempt or 1)
            sessions.setdefault(key, (event.actor, model if isinstance(model, str) else None))
        elif event.type == SUBAGENT_STOPPED:
            try:
                payload = AgentSubagentPayload.model_validate(event.payload)
            except ValidationError:
                continue
            if payload.usage is not None:
                subagents.append(
                    UsageRecord(
                        run_id=run.id,
                        usage=payload.usage,
                        at=event.ts,
                        agent_id=event.actor,
                        graph_id=run.graph_id,
                        origin="subagent",
                    )
                )
    records: list[UsageRecord] = []
    for nr in node_runs:
        if nr.usage is None:
            continue
        actor, model = sessions.get((nr.node_id, nr.attempt), (None, None))
        records.append(
            UsageRecord(
                run_id=run.id,
                usage=nr.usage,
                at=nr.started_at or nr.ended_at or run.started_at or run.created_at,
                agent_id=actor,
                graph_id=run.graph_id,
                model=model,
            )
        )
    return records + subagents


def counts_toward_usage(run: Run) -> bool:
    """이 Run을 토큰 집계에 넣는가: 루트 Run만(design §5R.7).

    자식 Run(중첩 팀, `root_run_id`가 있음)의 사용량은 그 Run을 부른 부모 노드의 NodeRun
    `usage`(= 자식 `totals`)로 이미 루트 Run에 들어가 있어, 따로 세면 두 번 센다.
    """
    return run.root_run_id is None


def load_usage_records(
    runs: RollupRunSource,
    events: RollupEventSource,
    *,
    graph_id: str | None = None,
    limit: int | None = None,
    since: float | None = None,
) -> list[UsageRecord]:
    """저장소에서 최근 Run `limit`개의 사용량 기록을 모은다(`since`보다 이전에 만든 Run은 뺀다).

    자식 Run은 건너뛴다(`counts_toward_usage`, 이중 집계 방지).
    """
    out: list[UsageRecord] = []
    for run in runs.list(graph_id=graph_id, root_only=True, limit=limit):
        if not counts_toward_usage(run):
            continue
        if since is not None and run.created_at < since:
            continue
        evs = events.list(run.id, type_prefix=SESSION_STARTED) + events.list(
            run.id, type_prefix=SUBAGENT_STOPPED
        )
        out += usage_records(run, runs.list_node_runs(run.id), evs)
    return out


def sum_usage(items: Iterable[Usage]) -> Usage:
    """필드별 합. 어느 항목에도 없는 필드는 `None`(0으로 지어내지 않는다).

    백엔드가 붙인 추가 숫자 키도 같은 규칙으로 더한다.
    """
    totals: dict[str, int | float] = {}
    for usage in items:
        for key, value in usage.model_dump(exclude_none=True).items():
            if isinstance(value, bool) or not isinstance(value, int | float):
                continue
            totals[key] = totals.get(key, 0) + value
    return Usage.model_validate(totals)


def _has_split(usage: Usage) -> bool:
    return any(getattr(usage, name) is not None for name in _SPLIT_FIELDS)


def _day(at: float | None, tz: tzinfo) -> str | None:
    return None if at is None else datetime.fromtimestamp(at, tz).date().isoformat()


def token_rollup(
    records: Iterable[UsageRecord],
    *,
    by: Sequence[RollupDimension] = ROLLUP_DIMENSIONS,
    tz: tzinfo = UTC,
    precision_text: Mapping[str, str] = DEFAULT_PRECISION_TEXT,
) -> list[TokenRollupRow]:
    """기록을 `by` 차원으로 묶어 합친다.

    Args:
        records: 사용량 기록.
        by: 묶을 차원(빈 목록 = 전체 하나). 빠진 차원은 행에서 `None`(그 차원으로 나누지 않음).
        tz: `day` 계산 시간대(서버 시간대를 넘긴다).
        precision_text: 정밀도 메모 문구(`total_only`·`mixed` 키).

    Returns:
        차원 값 순(`None`은 앞) 행 목록. `runs` = 서로 다른 Run 수.

    Raises:
        ValueError: 모르는 차원.
    """
    unknown = [d for d in by if d not in ROLLUP_DIMENSIONS]
    if unknown:
        raise ValueError(f"모르는 집계 차원: {unknown}")
    groups: dict[tuple[str | None, ...], list[UsageRecord]] = {}
    for rec in records:
        values: dict[str, Any] = {
            "agent_id": rec.agent_id,
            "graph_id": rec.graph_id,
            "model": rec.model,
            "day": _day(rec.at, tz),
        }
        groups.setdefault(tuple(values[d] for d in by), []).append(rec)

    rows: list[TokenRollupRow] = []
    for key in sorted(groups, key=lambda k: tuple((v is not None, v or "") for v in k)):
        recs = groups[key]
        split = [_has_split(r.usage) for r in recs]
        precision = None
        if not any(split) and any(r.usage.total_tokens is not None for r in recs):
            precision = precision_text.get("total_only")
        elif not all(split) and any(r.usage.total_tokens is not None for r in recs):
            precision = precision_text.get("mixed")
        rows.append(
            TokenRollupRow(
                **dict(zip(by, key, strict=True)),
                usage=sum_usage(r.usage for r in recs),
                runs=len({r.run_id for r in recs}),
                precision=precision,
            )
        )
    return rows
