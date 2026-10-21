"""사용량 관측값 인메모리 저장소(테스트·저장소 없는 사용). SQLite 구현과 같은 규칙."""

from __future__ import annotations

import threading

from agent_console_contracts import UsageWindowSnapshot


class InMemoryUsageObservationRepository:
    """`UsageObservationRepository`의 인메모리 구현."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._rows: dict[tuple[str, str, float], UsageWindowSnapshot] = {}

    def record(self, snapshot: UsageWindowSnapshot) -> None:
        key = (snapshot.source, snapshot.window, snapshot.observed_at)
        with self._lock:
            self._rows[key] = snapshot.model_copy(deep=True)

    def latest(self, *, source: str | None = None) -> list[UsageWindowSnapshot]:
        best: dict[tuple[str, str], UsageWindowSnapshot] = {}
        with self._lock:
            for (src, win, _), snap in self._rows.items():
                if source is not None and src != source:
                    continue
                kept = best.get((src, win))
                if kept is None or snap.observed_at > kept.observed_at:
                    best[(src, win)] = snap
        return [best[k].model_copy(deep=True) for k in sorted(best)]

    def history(
        self,
        source: str,
        window: str,
        *,
        since: float | None = None,
        limit: int | None = None,
    ) -> list[UsageWindowSnapshot]:
        with self._lock:
            rows = [
                snap
                for (src, win, at), snap in self._rows.items()
                if src == source and win == window and (since is None or at >= since)
            ]
        rows.sort(key=lambda r: r.observed_at, reverse=True)
        return [r.model_copy(deep=True) for r in rows[:limit]]

    def prune(self, before: float) -> int:
        with self._lock:
            stale = [k for k in self._rows if k[2] < before]
            for k in stale:
                del self._rows[k]
        return len(stale)


__all__ = ["InMemoryUsageObservationRepository"]
