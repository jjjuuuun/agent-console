"""X13 사용량 출처 인터페이스와 주입 프로토콜(design §R4.3)."""

from __future__ import annotations

import builtins
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from agent_console_contracts import RunEvent, UsageSourceDescriptor, UsageWindowSnapshot

__all__ = [
    "UsageEventQuery",
    "UsageObservationSink",
    "UsageSource",
    "UsageSourceContext",
]


@runtime_checkable
class UsageEventQuery(Protocol):
    """실행 이벤트 조회(저장소 `EventRepository`가 구조적으로 만족한다)."""

    def latest_by_type(
        self,
        type: str,
        *,
        run_id: str | None = None,
        actor: str | None = None,
        limit: int = 1,
    ) -> builtins.list[RunEvent]:
        """그 `type`의 최근 이벤트 `limit`개(ts 내림차순). `run_id` 생략 = 모든 Run."""
        ...


@runtime_checkable
class UsageObservationSink(Protocol):
    """관측값 기록·정리(저장소 `UsageObservationRepository`가 구조적으로 만족한다)."""

    def record(self, snapshot: UsageWindowSnapshot) -> None:
        """저장한다. (source, window, observed_at)이 같으면 교체(멱등)."""
        ...

    def prune(self, before: float) -> int:
        """`observed_at < before`인 관측값을 지우고 개수를 돌려준다."""
        ...


@dataclass(frozen=True, slots=True)
class UsageSourceContext:
    """`UsageSource.snapshot`에 넘기는 맥락(읽기 전용).

    - `source_id`: 레지스트리 key. 스냅샷의 `source`는 이 값이어야 한다(서비스가 맞춰 넣는다).
    - `config`: 출처 설정(`config_schema`로 검증된 값).
    - `now`: 관측 기준 시각(Unix epoch 초, 주입된 시계).
    - `events`: 플랫폼 실행 이벤트 조회. 없으면 `None`(이벤트를 쓰는 출처는 빈 목록).
    - `state_dir`: workspace 시스템 기록 폴더(예: `<workspace>/.state`). 없으면 `None`.
    """

    source_id: str
    config: Mapping[str, Any] = field(default_factory=dict)
    now: float = 0.0
    events: UsageEventQuery | None = None
    state_dir: Path | None = None


@runtime_checkable
class UsageSource(Protocol):
    """사용량 출처(X13). entry point `agent_console.usage_sources`로 등록한다.

    규칙: **값을 지어내지 않는다.** 출처가 주지 않은 값(사용률·초기화 시각·상태)은 `None`으로 둔다.
    창 id는 출처가 주는 문자열 그대로이며 코드에 창 목록을 두지 않는다. 관측할 것이 없으면 빈 목록,
    읽기 실패는 예외로 알린다(서비스가 출처 오류로 보고한다).
    """

    descriptor: UsageSourceDescriptor

    async def snapshot(self, ctx: UsageSourceContext) -> list[UsageWindowSnapshot]:
        """현재 알 수 있는 창별 최신 관측값."""
        ...
