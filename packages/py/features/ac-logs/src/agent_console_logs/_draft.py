"""분류기가 내는 이벤트 초안(design §4R.3)과 코어가 아는 약속 태그."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from agent_console_contracts.logs import LogDocumentRef, LogLane, TokenSample

from ._values import JsonValue

__all__ = [
    "TAG_DIAGNOSTIC",
    "TAG_SESSION_TITLE",
    "TAG_TOOL",
    "AgentInfo",
    "LogEventDraft",
]

TAG_TOOL = "tool"
"""도구 이벤트 표시 태그. 이 태그와 `call_id`가 있으면 identity가
`tool:{source}:{thread}:{call_id}:{stage}`가 되어 같은 호출을 두 위치에서 읽어도
하나로 색인된다(agent_bench `_insert` 규칙).
`tool_calls` 지표도 이 태그로 센다. 범주 id가 아니라 분류기와 코어 사이의 약속이다."""

TAG_SESSION_TITLE = "session_title"
"""세션 제목 후보 태그. 세션 목록의 `title`은 이 태그가 붙은 첫 이벤트(시간순)의 제목이다.
붙은 이벤트가 없으면 제목은 빈 문자열이다(범주 이름으로 추측하지 않는다)."""

TAG_DIAGNOSTIC = "diagnostic"
"""코어가 만든 진단 이벤트(해석·분류 실패 줄)에 붙는 태그."""

AgentInfo = LogLane
"""thread의 표시 이름·부모(색인 `log_agents`). 계약 `LogLane`과 같은 모양이다."""


@dataclass(frozen=True, slots=True)
class LogEventDraft:
    """분류기가 원본 행 하나에서 만든 이벤트 초안. `LogEvent`에서 uid·seq·observed_at을 뺀 것.

    범주·단계·태그는 열린 문자열이다. 코어는 `TAG_TOOL`·`TAG_SESSION_TITLE`만 약속으로 읽는다.

    Attributes:
        identity: 중복 판정 키. None이면 코어가 정한다(기본 `{source}:{ref}:{offset}[:{index}]`,
            도구 이벤트는 `tool:{source}:{thread}:{call_id}:{stage}`).
        usage: 이 이벤트가 실은 토큰 표본. 색인은 (출처, thread, message_id)마다 output이 가장 큰
            값 하나만 센다(F-8). message_id가 비면 코어가 `~{uid}`를 채운다.
        agent: thread 표시 이름·부모(서브에이전트).
        summary: 목록용 짧은 본문(사람이 읽는 평문). None이면 코어가 `detail`(없으면 `raw`)을
            문자열로 만든다. 저장 전 가리기·길이 제한은 코어가 한다.
    """

    category: str
    title: str = ""
    stage: str = "info"
    status: str = ""
    thread: str = ""
    role: str = ""
    actor: str = ""
    from_: tuple[str, ...] = ()
    to: tuple[str, ...] = ()
    via: str = ""
    tool: str = ""
    call_id: str = ""
    turn_id: str = ""
    message_id: str = ""
    session: str = ""
    cwd: str = ""
    model: str = ""
    run_id: str = ""
    node_path: tuple[str, ...] = ()
    time: float | None = None
    evidence: str = "observed"
    tags: tuple[str, ...] = ()
    documents: tuple[LogDocumentRef, ...] = ()
    correlation: Mapping[str, str | list[str]] = field(default_factory=dict)
    detail: JsonValue = None
    raw: JsonValue = None
    identity: str | None = None
    usage: TokenSample | None = None
    agent: AgentInfo | None = None
    summary: str | None = None
