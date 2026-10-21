"""명시 id 상관(agent_bench `log_view.correlation`·`link_events`)과 짝 이벤트 소요 시간.

시간상 이웃 이벤트는 잇지 않는다(R8.6). 같은 id를 명시적으로 공유한 이벤트만 잇는다.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Iterable, Sequence

from agent_console_contracts.logs import LogEvent, LogEvidenceLink

__all__ = [
    "CALL_ID_BASIS",
    "MAX_GROUP_LINKS",
    "correlation_keys",
    "link_events",
    "pair_durations",
]

CALL_ID_BASIS = "call_id"
"""`correlation`이 비었을 때 `call_id`로 잇는 근거 이름."""

MAX_GROUP_LINKS = 100
"""근거 묶음 하나에서 이벤트마다 붙일 연결 상한(agent_bench 그대로)."""


def correlation_keys(event: LogEvent) -> list[tuple[str, str]]:
    """이벤트의 명시 상관 (근거, 값) 목록. `correlation`이 비면 `call_id`."""
    values: dict[str, str | list[str]] = dict(event.correlation)
    if not values and event.call_id:
        values = {CALL_ID_BASIS: event.call_id}
    out: list[tuple[str, str]] = []
    for basis, items in values.items():
        for value in items if isinstance(items, list) else [items]:
            if value:
                out.append((basis, str(value)))
    return out


def link_events(
    events: Iterable[LogEvent],
    *,
    visible: Callable[[LogEvent], bool] | None = None,
    max_links: int = MAX_GROUP_LINKS,
) -> dict[str, list[LogEvidenceLink]]:
    """같은 명시 id를 공유한 이벤트끼리 근거 연결을 만든다.

    Args:
        events: 후보 이벤트.
        visible: 주면 참인 이벤트만 연결한다(분류 체계 숨김 등).
        max_links: 근거 묶음 하나에서 볼 이벤트 상한.

    Returns:
        uid → 연결 목록(자기 자신 제외, uid 중복 없음).
    """
    groups: dict[tuple[str, str], list[LogEvent]] = {}
    for event in events:
        if visible is not None and not visible(event):
            continue
        for key in correlation_keys(event):
            groups.setdefault(key, []).append(event)
    result: dict[str, list[LogEvidenceLink]] = {}
    seen: dict[str, set[str]] = {}
    for (basis, value), members in groups.items():
        for event in members:
            links = result.setdefault(event.uid, [])
            have = seen.setdefault(event.uid, set())
            for other in members[:max_links]:
                if other.uid != event.uid and other.uid not in have:
                    have.add(other.uid)
                    links.append(
                        LogEvidenceLink(uid=other.uid, title=other.title, basis=basis, value=value)
                    )
    return result


def _when(event: LogEvent) -> float | None:
    return event.time


def pair_durations(
    events: Sequence[LogEvent],
    *,
    start_stages: Collection[str] = frozenset({"start"}),
    end_stages: Collection[str] = frozenset({"complete"}),
) -> dict[str, float]:
    """같은 (thread, call_id)의 시작·끝 단계 짝으로 소요 시간(ms)을 계산한다.

    명시 id 짝만 계산한다. 시작·끝이 여럿이면 가장 이른 시작과 가장 늦은 끝을 쓴다.
    시각이 없거나 음수면 계산하지 않는다(값을 지어내지 않는다).

    Returns:
        uid → 소요 시간(ms). 짝의 시작·끝 이벤트 모두에 같은 값을 준다.
    """
    starts: dict[tuple[str, str], list[LogEvent]] = {}
    ends: dict[tuple[str, str], list[LogEvent]] = {}
    for event in events:
        if not event.call_id:
            continue
        key = (event.thread, event.call_id)
        if event.stage in start_stages:
            starts.setdefault(key, []).append(event)
        elif event.stage in end_stages:
            ends.setdefault(key, []).append(event)
    out: dict[str, float] = {}
    for key, start_events in starts.items():
        end_events = ends.get(key)
        if not end_events:
            continue
        t0s = [t for e in start_events if (t := _when(e)) is not None]
        t1s = [t for e in end_events if (t := _when(e)) is not None]
        if not t0s or not t1s:
            continue
        duration = (max(t1s) - min(t0s)) * 1000.0
        if duration < 0:
            continue
        for e in (*start_events, *end_events):
            out[e.uid] = duration
    return out
