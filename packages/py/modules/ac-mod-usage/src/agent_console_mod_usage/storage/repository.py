"""사용량 관측값 저장소: 프로토콜과 SQLite 구현(엔진은 호스트의 `DatabaseHandle.engine`)."""

from __future__ import annotations

from typing import Protocol

import sqlalchemy as sa
from sqlalchemy import Engine
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from agent_console_contracts import UsageWindowSnapshot

from .schema import usage_observations


class UsageObservationRepository(Protocol):
    """사용량 창 관측값(design §R4.3). 값을 지어내지 않고 관측한 것만 쌓는다."""

    def record(self, snapshot: UsageWindowSnapshot) -> None:
        """저장한다. (source, window, observed_at)이 같으면 교체(멱등)."""
        ...

    def latest(self, *, source: str | None = None) -> list[UsageWindowSnapshot]:
        """(source, window)마다 가장 최근 관측값. source, window 순."""
        ...

    def history(
        self,
        source: str,
        window: str,
        *,
        since: float | None = None,
        limit: int | None = None,
    ) -> list[UsageWindowSnapshot]:
        """한 창의 관측 이력(observed_at 내림차순)."""
        ...

    def prune(self, before: float) -> int:
        """`observed_at < before`인 관측값을 지우고 개수를 돌려준다(보존 기간 정리)."""
        ...


class SqliteUsageObservationRepository:
    """`UsageObservationRepository`의 SQLite 구현(엔진은 호스트가 준다)."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def record(self, snapshot: UsageWindowSnapshot) -> None:
        values = {
            "source": snapshot.source,
            "window_id": snapshot.window,
            "observed_at": snapshot.observed_at,
            "used_ratio": snapshot.used_ratio,
            "used_tokens": snapshot.used_tokens,
            "status": snapshot.status,
            "resets_at": snapshot.resets_at,
            "doc": snapshot.model_dump_json(),
        }
        key = ["source", "window_id", "observed_at"]
        stmt = sqlite_insert(usage_observations).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=key, set_={k: v for k, v in values.items() if k not in key}
        )
        with self._engine.begin() as conn:
            conn.execute(stmt)

    def latest(self, *, source: str | None = None) -> list[UsageWindowSnapshot]:
        c = usage_observations.c
        newest = (
            sa.select(c.source, c.window_id, sa.func.max(c.observed_at).label("at"))
            .group_by(c.source, c.window_id)
            .subquery()
        )
        stmt = (
            sa.select(c.doc)
            .join(
                newest,
                sa.and_(
                    c.source == newest.c.source,
                    c.window_id == newest.c.window_id,
                    c.observed_at == newest.c.at,
                ),
            )
            .order_by(c.source, c.window_id)
        )
        if source is not None:
            stmt = stmt.where(c.source == source)
        with self._engine.connect() as conn:
            return [
                UsageWindowSnapshot.model_validate_json(d) for d in conn.execute(stmt).scalars()
            ]

    def history(
        self,
        source: str,
        window: str,
        *,
        since: float | None = None,
        limit: int | None = None,
    ) -> list[UsageWindowSnapshot]:
        c = usage_observations.c
        stmt = (
            sa.select(c.doc)
            .where(c.source == source, c.window_id == window)
            .order_by(c.observed_at.desc())
        )
        if since is not None:
            stmt = stmt.where(c.observed_at >= since)
        if limit is not None:
            stmt = stmt.limit(limit)
        with self._engine.connect() as conn:
            return [
                UsageWindowSnapshot.model_validate_json(d) for d in conn.execute(stmt).scalars()
            ]

    def prune(self, before: float) -> int:
        with self._engine.begin() as conn:
            result = conn.execute(
                sa.delete(usage_observations).where(usage_observations.c.observed_at < before)
            )
        return int(result.rowcount)


__all__ = ["SqliteUsageObservationRepository", "UsageObservationRepository"]
