"""로그 이벤트 + 프로필 → 구조도(`ArchitectureView`, 순수 함수, design §5.5R.2.3).

지표 계산 규칙 5개(`count`·`errors`·`duration`·`tokens`·`inferred_duration`)는 코드다(K-7). 어느 칸·
연결이 어떤 지표를 보일지, 무엇을 셀지, 어떤 출처가 어떤 칸을 채우는지는 전부 프로필 데이터다.
값이 없으면 0이 아니라 `not_collected`(null)다(R8.8). 계산은 누적 집계 `ArchitectureTally`
(`_tally.py`) 한 벌이고, 이 함수는 목록을 한 번에 더해 그린다.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from typing import Any

from agent_console_conditions import ConditionOperator
from agent_console_contracts.architecture import (
    ArchitectureNote,
    ArchitectureProfile,
    ArchitectureView,
)
from agent_console_contracts.logs import LogEvent, TokenSample

from ._match import EventMatch, ProfileMatcher
from ._tally import DEFAULT_CELL_SIZE, DEFAULT_METRICS, KNOWN_METRICS, ArchitectureTally

__all__ = [
    "DEFAULT_CELL_SIZE",
    "DEFAULT_METRICS",
    "KNOWN_METRICS",
    "project_architecture",
]


def project_architecture(
    events: Iterable[LogEvent | Mapping[str, Any]],
    profile: ArchitectureProfile,
    *,
    profile_id: str,
    operators: Mapping[str, ConditionOperator],
    source_kinds: Mapping[str, str] | None = None,
    tokens: Iterable[TokenSample] = (),
    error_categories: Collection[str] = frozenset(),
    max_seq: int | None = None,
    notes: Iterable[ArchitectureNote] = (),
    cell_size: tuple[float, float] = DEFAULT_CELL_SIZE,
    matches: Sequence[EventMatch] | None = None,
) -> ArchitectureView:
    """이벤트 목록을 프로필로 투영한다(순수 함수: 서버·색인·시계 없음).

    - 칸·연결: 프로필 조건에 맞는 이벤트를 센다. 한 이벤트가 여러 칸·연결에 맞을 수 있다.
      어느 칸에도 맞지 않으면 분류 안 됨(`profile.unassigned`일 때). 관측 연결은 그 전달을 기록한
      이벤트 하나를 세고, 시간상 이웃을 잇지 않는다(R8.6). 구조 연결은 지표가 없다.
    - 출처 우선순위(`source_priority`): 칸·연결마다 맞은 이벤트의 출처 종류 중 목록 앞의 것만 센다.
      쓴 출처 id는 `selector.arch_sources`에 실린다(클릭 필터가 같은 이벤트를 고른다).
    - 수집 범위(`coverage`): 이 범위의 출처 종류 중 칸을 채우는 것이 없으면 `not_collected`.
    - `max_seq`: 주면 순번이 그 이하인 이벤트만 센다(수집이 이어져도 클릭 필터와 수가 같다).

    수집이 이어지는 범위를 반복해 그리면 `ArchitectureTally`로 새 이벤트만 더한다(증분 투영).

    Args:
        events: 범위의 로그 이벤트(계약 `LogEvent`) 또는 그 JSON 행(`LogEvent`를 계약 별칭으로
            `model_dump(mode="json")`한 dict — 예: `ac-logs` `iter_event_rows`). 섞어도 된다.
        profile: 프로필.
        profile_id: 프로필 id(선택 필터 `arch`에 쓴다).
        operators: 조건 연산자(X22).
        source_kinds: 로그 출처 id → 출처 종류. 없는 출처는 종류를 모른다(우선순위 맨 뒤).
        tokens: 토큰 표본(응답 (thread, message_id)마다 한 번 센다).
        error_categories: 오류로 볼 범주 id(분류 체계에서 오류로 표시한 범주).
        max_seq: 셀 이벤트 순번 상한.
        notes: 결과에 그대로 실을 안내(예: `ProfileCatalog.pick`의 대체 안내).
        cell_size: 칸 크기를 비운 칸의 기본 (폭, 높이).
        matches: 이미 판정한 결과(`events`와 같은 순서·길이). 같은 프로필·연산자·`error_categories`
            로 만든 `ProfileMatcher`의 결과여야 한다. 반복 투영에서 판정을 다시 하지 않으려고
            쓴다(연동 모듈의 결과 캐시·증분 읽기). 없으면 여기서 판정한다.

    Returns:
        그리기 완결형 `ArchitectureView`. 이벤트·칸이 없어도 예외 없이 빈 결과다.

    Raises:
        ValueError: `matches`의 길이가 `events`와 다를 때.
    """
    given = list(events)
    if matches is not None and len(given) != len(matches):
        raise ValueError(f"판정 결과 수({len(matches)})가 이벤트 수({len(given)})와 다릅니다")
    known = matches
    matcher = (
        ProfileMatcher(profile, operators, error_categories=error_categories)
        if known is None
        else None
    )

    def judge(i: int, item: LogEvent | Mapping[str, Any]) -> EventMatch:
        if known is not None:
            return known[i]
        assert matcher is not None  # known이 없으면 만든다
        if isinstance(item, LogEvent):
            return matcher.match(item)
        return matcher.match_subject(item)

    tally = ArchitectureTally(profile, profile_id=profile_id)
    for i, item in enumerate(given):
        if isinstance(item, LogEvent):
            if max_seq is None or item.seq <= max_seq:
                tally.add_event(item, judge(i, item))
        elif max_seq is None or item["seq"] <= max_seq:
            tally.add_row(item, judge(i, item))
    return tally.view(source_kinds=source_kinds, tokens=tokens, notes=notes, cell_size=cell_size)
