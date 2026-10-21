"""세션 로그 이벤트(``LogEvent``) → 위임 흐름(``Trace``). 서버·색인·도구 형식을 모른다.

연결 원칙은 ``ac-trace``와 같다: **명시 id만** 잇는다. 시간상 가까운 이벤트를 인과로 잇지 않는다.

| 관계 | 연결 키 |
| --- | --- |
| span | 이벤트의 ``thread``(에이전트 줄) 하나 = span 하나 |
| 부모 | 줄 S의 이벤트 ``correlation[<연결 키>]`` = C이고, C가 **다른** 줄 T의 이벤트 ``call_id``면
  T가 S의 부모다(위임 호출 id ↔ 서브에이전트 메타 ``toolUseId``). 후보 부모가 둘 이상이거나
  없으면 부모 없이 남긴다. |
| 링크 | ``from``·``to``가 있는 이벤트: 보낸 줄 span → 받는 줄 span(양쪽 다 span이 있을 때만) |

같은 위임(호출 id)을 여러 이벤트가 같은 방향으로 말하면(위임 호출·수신) 링크 하나로 합친다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

from agent_console_contracts import Trace, TraceLink, TraceSpan
from agent_console_contracts.logs import LogEvent
from agent_console_trace import SPAN_KIND_DELEGATED

SPAN_KIND_THREAD = "thread"
"""부모가 없는 줄(메인 세션, 연결 키가 없는 줄)의 span 종류."""

DEFAULT_LINK_KEYS: tuple[str, ...] = ("tool_use_id",)
"""기본 연결 키(``correlation`` 이름). Claude Code 분류기가 서브에이전트 수신 이벤트에 메타
``toolUseId``를 이 이름으로 싣는다. 다른 형식은 모듈 설정 ``link_keys``로 바꾼다."""

_PREVIEW_CHARS = 200


def thread_span_id(thread: str) -> str:
    """줄 id → span id(``thread:<줄 id>``)."""
    return f"thread:{thread}"


def _when(event: LogEvent) -> float:
    return event.time if event.time is not None else event.observed_at


def _preview(event: LogEvent) -> str | None:
    text = (event.summary or event.title).strip()
    if not text:
        return None
    return text if len(text) <= _PREVIEW_CHARS else text[: _PREVIEW_CHARS - 1] + "…"


def _values(value: str | list[str]) -> list[str]:
    return [value] if isinstance(value, str) else list(value)


@dataclass
class _Thread:
    id: str
    session: str
    times: list[float] = field(default_factory=list)
    label: str = ""


def build_log_trace(
    events: Iterable[LogEvent],
    *,
    session: str | None = None,
    link_keys: Sequence[str] = DEFAULT_LINK_KEYS,
) -> Trace:
    """한 세션의 로그 이벤트로 위임 흐름을 만든다.

    Args:
        events: 세션 이벤트(순서 무관 — 시각 → ``seq`` 순으로 다시 정렬한다). 목록용 이벤트
            (``summary``만 있고 ``detail`` 없음)로 충분하다.
        session: ``Trace.run_id``에 넣을 세션 id. 없으면 첫 이벤트의 ``session``.
        link_keys: 부모를 찾을 ``correlation`` 이름(앞쪽부터 모두 본다).

    Returns:
        ``Trace``(``run_id`` = 세션 id). span = 줄, ``parent_id`` = 위임한 줄,
        링크 = ``from``→``to``.

    Raises:
        ValueError: ``session``이 없고 이벤트에서도 세션 id를 알 수 없다.
    """
    ordered = sorted(events, key=lambda e: (_when(e), e.seq))
    found_session = session or next((e.session for e in ordered if e.session), "")
    if not found_session:
        raise ValueError("세션 id를 알 수 없습니다(session 인자나 이벤트의 session이 필요합니다)")

    threads: dict[str, _Thread] = {}
    owners: dict[str, list[str]] = {}  # 호출 id → 그 id를 call_id로 가진 줄(나온 순)
    for event in ordered:
        if not event.thread:
            continue
        info = threads.get(event.thread)
        if info is None:
            info = threads[event.thread] = _Thread(
                id=event.thread, session=event.session or found_session
            )
        if event.time is not None:
            info.times.append(event.time)
        if not info.label and event.role:
            info.label = event.role
        if event.call_id:
            seen = owners.setdefault(event.call_id, [])
            if event.thread not in seen:
                seen.append(event.thread)

    # 부모 후보: 다른 줄이 가진 호출 id를 자기 correlation에 실은 이벤트
    candidates: dict[str, dict[str, str]] = {}  # 줄 → {부모 줄: 호출 id}
    received: dict[tuple[str, str], LogEvent] = {}  # (줄, 호출 id) → 첫 수신 이벤트
    for event in ordered:
        if not event.thread:
            continue
        for basis in link_keys:
            raw = event.correlation.get(basis)
            if raw is None:
                continue
            for call in _values(raw):
                for owner in owners.get(call, ()):
                    if owner == event.thread:
                        continue
                    candidates.setdefault(event.thread, {}).setdefault(owner, call)
                    received.setdefault((event.thread, call), event)

    parents: dict[str, tuple[str, str]] = {}  # 줄 → (부모 줄, 호출 id)
    for thread in threads:
        options = candidates.get(thread, {})
        if len(options) == 1:  # 없음 또는 모호함 → 부모 없이 남긴다
            [(parent, call)] = options.items()
            if parent in threads:
                parents[thread] = (parent, call)
    for thread in [t for t in parents if _on_cycle(t, parents)]:
        del parents[thread]  # 서로를 부모로 가리키면 어느 쪽도 고르지 않는다

    # 위임 결과: 부모 줄에서 같은 호출 id로 끝난 이벤트(complete 단계 우선)
    results: dict[tuple[str, str], LogEvent] = {}
    for event in ordered:
        if event.thread and event.call_id:
            key = (event.thread, event.call_id)
            prev = results.get(key)
            if prev is None or (prev.stage != "complete" and event.stage == "complete"):
                results[key] = event

    spans: list[TraceSpan] = []
    for info in threads.values():
        link = parents.get(info.id)
        start = min(info.times) if info.times else None
        end = max(info.times) if info.times else None
        task = result = status = None
        if link is not None:
            parent, call = link
            got = received.get((info.id, call))
            task = _preview(got) if got is not None else None
            done = results.get((parent, call))
            if done is not None and done.stage == "complete":
                result = _preview(done)
                status = done.status or None
        spans.append(
            TraceSpan(
                id=thread_span_id(info.id),
                kind=SPAN_KIND_DELEGATED if link is not None else SPAN_KIND_THREAD,
                parent_id=thread_span_id(link[0]) if link is not None else None,
                actor=info.label or info.id,
                status=status,
                started_at=start,
                ended_at=end,
                session_id=info.session,
                tool_use_id=link[1] if link is not None else None,
                task_preview=task,
                result_preview=result,
            )
        )

    links: list[TraceLink] = []
    seen_links: set[tuple[str, str, str]] = set()
    for event in ordered:
        if not event.from_ or not event.to:
            continue
        call = event.call_id or _first_key(event.correlation, link_keys)
        for sender in event.from_:
            for receiver in event.to:
                if sender == receiver or sender not in threads or receiver not in threads:
                    continue
                link_key = (sender, receiver, call or event.uid)
                if link_key in seen_links:
                    continue
                seen_links.add(link_key)
                links.append(
                    TraceLink(
                        source=thread_span_id(sender),
                        target=thread_span_id(receiver),
                        edge_id=call or None,
                        kind=event.via or None,
                    )
                )
    return Trace(run_id=found_session, spans=spans, links=links)


def _on_cycle(start: str, parents: Mapping[str, tuple[str, str]]) -> bool:
    seen = {start}
    cursor = parents.get(start)
    while cursor is not None:
        if cursor[0] in seen:
            return cursor[0] == start
        seen.add(cursor[0])
        cursor = parents.get(cursor[0])
    return False


def _first_key(correlation: Mapping[str, str | list[str]], keys: Sequence[str]) -> str:
    for key in keys:
        raw = correlation.get(key)
        if raw is not None:
            values = _values(raw)
            if values:
                return values[0]
    return ""


__all__ = ["DEFAULT_LINK_KEYS", "SPAN_KIND_THREAD", "build_log_trace", "thread_span_id"]
