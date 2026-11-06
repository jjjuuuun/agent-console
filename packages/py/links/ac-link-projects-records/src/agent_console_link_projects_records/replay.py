"""대기 파일 줄을 기록 DB에 다시 쓰는 기본 적용 함수(종류 → 함수, 주입 가능)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from sqlalchemy import Engine

from agent_console_contracts import Interaction, NodeRun, Run, RunEvent
from agent_console_store import SqliteStorage

type Applier = Callable[[SqliteStorage, Mapping[str, Any]], bool]
"""``(저장소, 모델 JSON) -> 새로 썼나``. 이미 있어 무시했으면 False."""

SPOOL_KIND_RUN = "run"
SPOOL_KIND_NODE_RUN = "node_run"
SPOOL_KIND_EVENT = "event"
SPOOL_KIND_INTERACTION = "interaction"
"""``mod-runs``가 쓰는 대기 줄 종류(기본 적용 함수의 키). 다른 종류는 적용 함수를 더해 쓴다."""


def _run(storage: SqliteStorage, data: Mapping[str, Any]) -> bool:
    storage.runs.save(Run.model_validate(data))
    return True


def _node_run(storage: SqliteStorage, data: Mapping[str, Any]) -> bool:
    storage.runs.save_node_run(NodeRun.model_validate(data))
    return True


def _event(storage: SqliteStorage, data: Mapping[str, Any]) -> bool:
    return storage.events.append(RunEvent.model_validate(data))  # (run_id, seq) 중복은 False


def _interaction(storage: SqliteStorage, data: Mapping[str, Any]) -> bool:
    return storage.interactions.save(Interaction.model_validate(data))


def default_appliers() -> dict[str, Applier]:
    """기본 적용 함수: ``run``·``node_run``·``event``·``interaction``(저장소가 같은 키로 멱등)."""
    return {
        SPOOL_KIND_RUN: _run,
        SPOOL_KIND_NODE_RUN: _node_run,
        SPOOL_KIND_EVENT: _event,
        SPOOL_KIND_INTERACTION: _interaction,
    }


def storage_apply(
    engine: Engine, appliers: Mapping[str, Applier]
) -> Callable[[str, Mapping[str, Any]], bool]:
    """``RecordsSpool.drain``에 줄 ``apply``로 넘길 함수(엔진 위 저장소 + 종류별 적용 함수).

    Raises:
        KeyError: (호출 시) 적용 함수가 없는 종류 - 그 줄은 남는다.
    """
    storage = SqliteStorage(engine)

    def apply(kind: str, data: Mapping[str, Any]) -> bool:
        return appliers[kind](storage, data)

    return apply


__all__ = [
    "SPOOL_KIND_EVENT",
    "SPOOL_KIND_INTERACTION",
    "SPOOL_KIND_NODE_RUN",
    "SPOOL_KIND_RUN",
    "Applier",
    "default_appliers",
    "storage_apply",
]
