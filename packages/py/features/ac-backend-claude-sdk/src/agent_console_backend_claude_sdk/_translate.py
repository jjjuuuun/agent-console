"""SDK 메시지 → 공급자 독립 이벤트(design §5.6 `agent.*`) 변환.

`MessageTranslator`는 한 번의 실행 동안 상태(세션 id, 메시지별 사용량, 위임)를 가지며
I/O가 없다. 백엔드가 결과를 sink로 내보낸다. 관측 이벤트(`hook.*`·`mcp.*`)는 여기서 내지 않는다 —
관측 수집기(X7, `collectors` 하위 모듈)가 같은 메시지를 받아 낸다(4R.8).

| SDK 메시지 | 이벤트 |
| --- | --- |
| `SystemMessage(subtype="init")` | `agent.session_started` |
| `StreamEvent` text_delta (최상위) | `agent.text_delta` (raw 없음) |
| `AssistantMessage` 텍스트 (최상위) | `agent.message` |
| `ToolUseBlock`·`ServerToolUseBlock` | `agent.tool_call` |
| `ToolResultBlock`·`ServerToolResultBlock` | `agent.tool_result` |
| `AssistantMessage.usage` (최상위, message_id별 최신값 합) | `agent.usage` (누적) |
| `AssistantMessage.error` | `log.warning` |
| `TaskStartedMessage` | `agent.subagent_started` (대상 귀속) |
| `TaskNotificationMessage`·끝난 `TaskUpdatedMessage` | `agent.subagent_stopped` (총 토큰) |
| `RateLimitEvent` | `usage.rate_limit` |
| `ResultMessage` | `agent.usage` (최종 누적값) |

서브에이전트 귀속(design §R3.1d·§R3.4): 최상위 위임 도구 호출(`Agent`/`Task`)의 입력
`subagent_type`이 등록한 서브에이전트 이름이면 그 호출 id를 대상에 묶는다. `parent_tool_use_id`가
그 id인 메시지에서 나온 이벤트는 `Emission.target`=대상 이름을 가진다(백엔드가 actor·하위
node_path로 바꾼다). 대상의 결과는 위임 도구 결과(전체 텍스트)로 `take_subagent_results()`에
쌓인다. 등록하지 않은 이름은 위임자에게 귀속한다.
서브에이전트 메시지의 사용량은 세지 않는다(세션 합계는 `ResultMessage`, 대상별은 `TaskUsage`).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    RateLimitEvent,
    ResultMessage,
    ServerToolResultBlock,
    ServerToolUseBlock,
    StreamEvent,
    SystemMessage,
    TaskNotificationMessage,
    TaskStartedMessage,
    TaskUpdatedMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from pydantic import BaseModel

from agent_console_contracts import (
    AgentMessagePayload,
    AgentSessionStartedPayload,
    AgentSubagentPayload,
    AgentTextDeltaPayload,
    AgentToolCallPayload,
    AgentToolResultPayload,
    AgentUsagePayload,
    LogWarningPayload,
    Usage,
    UsageRateLimitPayload,
)
from agent_console_runtime import preview, sum_usage

MCP_TOOL_PREFIX = "mcp__"
"""Claude Code의 MCP 도구 이름 형식 `mcp__<server>__<tool>`."""

_USAGE_KEYS = {
    "input_tokens": "input_tokens",
    "output_tokens": "output_tokens",
    "cache_read_input_tokens": "cache_read_tokens",
    "cache_creation_input_tokens": "cache_creation_tokens",
}


_AGENT_ID_LINE = re.compile(r"^\s*agentId:\s*\S+.*$", re.MULTILINE)
"""위임 도구 결과 끝에 CLI가 붙이는 `agentId: <id>` 줄(SDK 문서 "Resume subagents")."""

_TERMINAL_TASK = {"completed": "completed", "failed": "failed", "killed": "stopped"}
"""`TaskUpdatedMessage.status` 중 끝난 상태 → `subagent_stopped.status`."""


@dataclass(frozen=True)
class Emission:
    """내보낼 이벤트 하나.

    - `raw`가 True면 백엔드가 원본 메시지를 정제해 `raw`로 붙인다.
    - `target`이 있으면 서브에이전트(그 이름) 이벤트다. 백엔드가 actor·하위 node_path로 바꾼다.
    """

    type: str
    payload: BaseModel | Mapping[str, Any]
    raw: bool = True
    target: str | None = None


@dataclass(frozen=True)
class SubagentOutcome:
    """서브에이전트 호출 하나의 결과(위임 도구 결과). 위임 방식이 답변 발행에 쓴다.

    `status`는 `succeeded`/`failed`(위임 도구 결과의 is_error).
    """

    name: str
    text: str
    status: str
    tool_use_id: str
    task_id: str | None = None


@dataclass
class _Delegation:
    """위임 도구 호출 하나의 상태."""

    tool_use_id: str
    name: str | None
    preview: str | None
    task_id: str | None = None
    started: bool = False
    stopped: bool = False
    result_status: str | None = None
    result_text: str | None = None


def usage_from_sdk(data: Mapping[str, Any] | None, cost_usd: float | None = None) -> Usage:
    """SDK/API 사용량 dict → `Usage`(모르는 키는 버린다)."""
    values: dict[str, Any] = {}
    for src, dst in _USAGE_KEYS.items():
        value = (data or {}).get(src)
        if isinstance(value, int) and not isinstance(value, bool):
            values[dst] = value
    if cost_usd is not None:
        values["cost_usd"] = cost_usd
    return Usage.model_validate(values)


def split_mcp_name(name: str) -> tuple[str, str] | None:
    """`mcp__server__tool` → (server, tool). 형식이 아니면 None."""
    if not name.startswith(MCP_TOOL_PREFIX):
        return None
    server, sep, tool = name[len(MCP_TOOL_PREFIX) :].partition("__")
    if not sep or not server or not tool:
        return None
    return server, tool


@dataclass
class MessageTranslator:
    """한 실행의 SDK 메시지를 이벤트로 바꾼다.

    Args:
        backend_id: `agent.session_started.backend` 값.
        model: 요청한 모델(init 메시지에 모델이 있으면 그것으로 바뀐다).
        scrub: 페이로드에 실리는 도구 입력·결과를 정제하는 함수.
        preview_chars: `output_preview`·위임 미리보기 최대 길이.
        subagent_names: 등록한 서브에이전트 이름(위임 도구 입력 `subagent_type`과 맞춘다).
        delegation_tools: 위임 도구 호출로 알아볼 도구 이름.
    """

    backend_id: str
    model: str | None = None
    scrub: Callable[[Any], Any] = lambda v: v
    preview_chars: int = 500
    subagent_names: frozenset[str] = frozenset()
    delegation_tools: frozenset[str] = frozenset({"Agent", "Task"})

    session_id: str | None = None
    texts: list[str] = field(default_factory=list)
    result: ResultMessage | None = None
    usage: Usage | None = None
    _message_usage: dict[str, Usage] = field(default_factory=dict)
    _stream_message_id: str | None = None
    _delegations: dict[str, _Delegation] = field(default_factory=dict)
    _tasks: dict[str, _Delegation] = field(default_factory=dict)
    _outcomes: list[SubagentOutcome] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.subagent_names = frozenset(self.subagent_names)
        self.delegation_tools = frozenset(self.delegation_tools)

    def translate(self, msg: Any) -> list[Emission]:
        """메시지 하나 → 이벤트 목록(모르는 메시지는 빈 목록)."""
        if isinstance(msg, StreamEvent):
            return self._stream(msg)
        if isinstance(msg, AssistantMessage):
            return self._assistant(msg)
        if isinstance(msg, UserMessage):
            return self._user(msg)
        if isinstance(msg, ResultMessage):
            return self._result(msg)
        if isinstance(msg, TaskStartedMessage):
            return self._task_started(msg)
        if isinstance(msg, TaskNotificationMessage):
            return self._task_notification(msg)
        if isinstance(msg, TaskUpdatedMessage):
            return self._task_updated(msg)
        if isinstance(msg, RateLimitEvent):
            return self._rate_limit(msg)
        if isinstance(msg, SystemMessage) and msg.subtype == "init":
            return self._init(msg)
        return []

    # ------------------------------------------------------------ 메시지별

    def _init(self, msg: SystemMessage) -> list[Emission]:
        data = msg.data
        session_id = data.get("session_id")
        if isinstance(session_id, str) and session_id:
            self.session_id = session_id
        model = data.get("model")
        if isinstance(model, str) and model:
            self.model = model
        out: list[Emission] = []
        if self.session_id:
            out.append(
                Emission(
                    "agent.session_started",
                    AgentSessionStartedPayload(
                        session_id=self.session_id, backend=self.backend_id, model=self.model
                    ),
                )
            )
        return out

    def _stream(self, msg: StreamEvent) -> list[Emission]:
        if msg.parent_tool_use_id is not None:
            return []
        event = msg.event
        kind = event.get("type")
        if kind == "message_start":
            message = event.get("message")
            if isinstance(message, Mapping) and isinstance(message.get("id"), str):
                self._stream_message_id = message["id"]
            return []
        if kind == "content_block_delta":
            delta = event.get("delta")
            if isinstance(delta, Mapping) and delta.get("type") == "text_delta":
                text = delta.get("text")
                if isinstance(text, str) and text:
                    return [
                        Emission(
                            "agent.text_delta",
                            AgentTextDeltaPayload(text=text, message_id=self._stream_message_id),
                            raw=False,
                        )
                    ]
        return []

    def _assistant(self, msg: AssistantMessage) -> list[Emission]:
        top = msg.parent_tool_use_id is None
        target = self._target_of(msg.parent_tool_use_id)
        out: list[Emission] = []
        texts = [b.text for b in msg.content if isinstance(b, TextBlock) and b.text]
        # 서브에이전트 텍스트(forward_subagent_text)는 대상을 알 때만 낸다
        # (모르면 위임자 텍스트로 오인된다).
        if texts and (top or target is not None):
            text = "".join(texts)
            if top:
                self.texts.append(text)
            out.append(
                Emission(
                    "agent.message",
                    AgentMessagePayload(role="assistant", text=text, message_id=msg.message_id),
                    target=target,
                )
            )
        for block in msg.content:
            if isinstance(block, ToolUseBlock | ServerToolUseBlock):
                self._note_delegation(block.id, block.name, block.input, msg.parent_tool_use_id)
                out.extend(self._tool_call(block.id, block.name, block.input, target))
            elif isinstance(block, ToolResultBlock | ServerToolResultBlock):
                out.extend(self._tool_result(block, target))
        if msg.error:
            out.append(
                Emission(
                    "log.warning",
                    LogWarningPayload(
                        message=f"assistant error: {msg.error}", details={"error": msg.error}
                    ),
                    target=target,
                )
            )
        if top and msg.usage and msg.message_id:
            usage = usage_from_sdk(msg.usage)
            if self._message_usage.get(msg.message_id) != usage:
                self._message_usage[msg.message_id] = usage
                self.usage = sum_usage(self._message_usage.values())
                if self.usage is not None:
                    out.append(
                        Emission(
                            "agent.usage", AgentUsagePayload(usage=self.usage, model=self.model)
                        )
                    )
        return out

    def _user(self, msg: UserMessage) -> list[Emission]:
        if isinstance(msg.content, str):
            return []
        target = self._target_of(msg.parent_tool_use_id)
        out: list[Emission] = []
        for block in msg.content:
            if isinstance(block, ToolResultBlock | ServerToolResultBlock):
                out.extend(self._tool_result(block, target))
        return out

    def _result(self, msg: ResultMessage) -> list[Emission]:
        self.result = msg
        if msg.session_id:
            self.session_id = msg.session_id
        if msg.usage is None and msg.total_cost_usd is None:
            return []
        self.usage = usage_from_sdk(msg.usage, msg.total_cost_usd)
        return [Emission("agent.usage", AgentUsagePayload(usage=self.usage, model=self.model))]

    # ------------------------------------------------------------ 도구

    def _tool_call(
        self, tool_use_id: str, name: str, tool_input: Any, target: str | None = None
    ) -> list[Emission]:
        return [
            Emission(
                "agent.tool_call",
                AgentToolCallPayload(
                    tool_use_id=tool_use_id, name=name, input=self.scrub(tool_input)
                ),
                target=target,
            )
        ]

    def _tool_result(
        self, block: ToolResultBlock | ServerToolResultBlock, target: str | None = None
    ) -> list[Emission]:
        is_error = bool(getattr(block, "is_error", False))
        text = preview(self.scrub(block.content), self.preview_chars) or ""
        out = [
            Emission(
                "agent.tool_result",
                AgentToolResultPayload(
                    tool_use_id=block.tool_use_id, is_error=is_error, output_preview=text
                ),
                target=target,
            )
        ]
        delegation = self._delegations.get(block.tool_use_id)
        if delegation is not None and delegation.result_status is None:
            self._delegation_result(delegation, block.content, is_error)
        return out

    # ------------------------------------------------------------ 서브에이전트

    def target_of(self, parent_tool_use_id: str | None) -> str | None:
        """SDK 메시지의 `parent_tool_use_id` → 귀속할 서브에이전트 이름(없으면 None = 위임자).

        관측 수집기 이벤트를 번역 이벤트와 같은 규칙으로 귀속할 때 쓴다.
        """
        return self._target_of(parent_tool_use_id)

    def _target_of(self, parent_tool_use_id: str | None) -> str | None:
        if parent_tool_use_id is None:
            return None
        delegation = self._delegations.get(parent_tool_use_id)
        return delegation.name if delegation is not None else None

    def _note_delegation(
        self, tool_use_id: str, name: str, tool_input: Any, parent: str | None
    ) -> None:
        if name not in self.delegation_tools:
            return
        data = tool_input if isinstance(tool_input, Mapping) else {}
        if parent is not None:
            # 서브에이전트 안의 위임(깊이 제한을 바꾼 경우): 바깥 대상에 귀속한다.
            target = self._target_of(parent)
        else:
            requested = data.get("subagent_type")
            target = requested if requested in self.subagent_names else None
        hint = data.get("description") or data.get("prompt")
        self._delegations[tool_use_id] = _Delegation(
            tool_use_id=tool_use_id,
            name=target,
            preview=self._clip(hint) if isinstance(hint, str) else None,
        )

    def _delegation_result(self, delegation: _Delegation, content: Any, is_error: bool) -> None:
        # 결과 텍스트는 이벤트(result_preview)와 위임 방식 알림(답변)으로 나가므로 먼저 가린다.
        scrubbed = self.scrub(delegation_result_text(content))
        text = scrubbed if isinstance(scrubbed, str) else str(scrubbed)
        delegation.result_status = "failed" if is_error else "succeeded"
        delegation.result_text = text
        if delegation.name is not None:
            self._outcomes.append(
                SubagentOutcome(
                    name=delegation.name,
                    text=text,
                    status=delegation.result_status,
                    tool_use_id=delegation.tool_use_id,
                    task_id=delegation.task_id,
                )
            )

    def _task_started(self, msg: TaskStartedMessage) -> list[Emission]:
        delegation = self._delegations.get(msg.tool_use_id) if msg.tool_use_id else None
        if delegation is None:
            delegation = _Delegation(
                tool_use_id=msg.tool_use_id or msg.task_id, name=None, preview=None
            )
        delegation.task_id = msg.task_id
        delegation.started = True
        self._tasks[msg.task_id] = delegation
        return [
            Emission(
                "agent.subagent_started",
                AgentSubagentPayload(
                    subagent_id=msg.task_id,
                    name=delegation.name,
                    tool_use_id=msg.tool_use_id,
                    task_type=msg.task_type,
                    task_preview=delegation.preview or self._clip(msg.description or None),
                ),
                target=delegation.name,
            )
        ]

    def _task_notification(self, msg: TaskNotificationMessage) -> list[Emission]:
        delegation = self._tasks.get(msg.task_id)
        if delegation is not None:
            if delegation.stopped:
                return []
            delegation.stopped = True
        usage = None
        tool_uses: int | None = None
        duration_ms: int | None = None
        if msg.usage:
            total = msg.usage.get("total_tokens")
            if isinstance(total, int):
                usage = Usage(total_tokens=total)
            tool_uses = _int_or_none(msg.usage.get("tool_uses"))
            duration_ms = _int_or_none(msg.usage.get("duration_ms"))
        result = delegation.result_text if delegation is not None else None
        return [
            Emission(
                "agent.subagent_stopped",
                AgentSubagentPayload(
                    subagent_id=msg.task_id,
                    name=delegation.name if delegation is not None else None,
                    tool_use_id=msg.tool_use_id,
                    status=msg.status,
                    usage=usage,
                    tool_uses=tool_uses,
                    duration_ms=duration_ms,
                    result_preview=self._clip(result if result is not None else msg.summary),
                ),
                target=delegation.name if delegation is not None else None,
            )
        ]

    def _task_updated(self, msg: TaskUpdatedMessage) -> list[Emission]:
        status = msg.status or msg.patch.get("status")
        mapped = _TERMINAL_TASK.get(status) if isinstance(status, str) else None
        delegation = self._tasks.get(msg.task_id)
        if mapped is None or delegation is None or delegation.stopped:
            return []
        delegation.stopped = True
        return [self._stopped(delegation, mapped, raw=True)]

    def _stopped(self, delegation: _Delegation, status: str | None, *, raw: bool) -> Emission:
        return Emission(
            "agent.subagent_stopped",
            AgentSubagentPayload(
                subagent_id=delegation.task_id or delegation.tool_use_id,
                name=delegation.name,
                tool_use_id=delegation.tool_use_id,
                status=status,
                result_preview=self._clip(delegation.result_text),
            ),
            raw=raw,
            target=delegation.name,
        )

    def _rate_limit(self, msg: RateLimitEvent) -> list[Emission]:
        info = msg.rate_limit_info
        window = info.rate_limit_type or info.raw.get("rateLimitType")
        utilization = info.utilization
        return [
            Emission(
                "usage.rate_limit",
                UsageRateLimitPayload(
                    window=window if isinstance(window, str) and window else "unspecified",
                    status=info.status,
                    utilization=(
                        utilization
                        if isinstance(utilization, int | float) and utilization >= 0
                        else None
                    ),
                    resets_at=float(info.resets_at) if info.resets_at is not None else None,
                    overage_status=info.overage_status,
                ),
            )
        ]

    def target_for_agent(self, agent_id: str | None) -> str | None:
        """권한 요청의 `agent_id` → 서브에이전트 이름(task_id나 위임 도구 호출 id로 맞춘다).

        맞추지 못하면 None(위임자에게 귀속).
        """
        if not agent_id:
            return None
        delegation = self._tasks.get(agent_id) or self._delegations.get(agent_id)
        return delegation.name if delegation is not None else None

    def take_subagent_results(self) -> list[SubagentOutcome]:
        """지금까지 쌓인 서브에이전트 결과를 꺼낸다(꺼낸 것은 비운다)."""
        out, self._outcomes = self._outcomes, []
        return out

    def finish(self, *, cancelled: bool = False) -> list[Emission]:
        """실행이 끝날 때 닫히지 않은 위임을 닫는다.

        - 시작 이벤트(TaskStarted)를 받지 못한 위임: 위임 도구 호출 id로 시작·종료 쌍을 만든다.
        - 시작했지만 종료를 받지 못한 위임: 위임 도구 결과의 상태로 종료(결과도 없으면 상태 없음,
          취소면 `stopped`).
        """
        out: list[Emission] = []
        for delegation in self._delegations.values():
            if delegation.stopped:
                continue
            status = _status_of(delegation.result_status) or ("stopped" if cancelled else None)
            if not delegation.started:
                if delegation.result_status is None and not cancelled:
                    continue  # 호출만 있고 아무 결과도 없음(도구 거부 등): 위임이 아니었다
                delegation.started = True
                out.append(
                    Emission(
                        "agent.subagent_started",
                        AgentSubagentPayload(
                            subagent_id=delegation.tool_use_id,
                            name=delegation.name,
                            tool_use_id=delegation.tool_use_id,
                            task_preview=delegation.preview,
                        ),
                        raw=False,
                        target=delegation.name,
                    )
                )
            delegation.stopped = True
            out.append(self._stopped(delegation, status, raw=False))
        return out

    def _clip(self, text: Any) -> str | None:
        """미리보기: 비밀을 가린(scrub) 뒤 자른다. 모든 미리보기 필드는 이 함수를 거친다."""
        if not isinstance(text, str) or not text:
            return None
        cleaned = self.scrub(text)
        return preview(cleaned if isinstance(cleaned, str) else str(cleaned), self.preview_chars)

    @property
    def final_text(self) -> str:
        """최종 텍스트: ResultMessage.result가 있으면 그것, 없으면 최상위 assistant 텍스트 이음."""
        if self.result is not None and self.result.result is not None:
            return self.result.result
        return "\n".join(self.texts)


def delegation_result_text(content: Any) -> str:
    """위임 도구 결과 내용 → 서브에이전트 결과 텍스트(끝의 `agentId: …` 줄 제거)."""
    parts: list[str] = []
    if isinstance(content, str):
        parts.append(content)
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, Mapping) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            elif isinstance(item, str):
                parts.append(item)
    kept = [p for p in parts if not _AGENT_ID_LINE.fullmatch(p.strip())]
    text = "\n".join(kept)
    lines = text.rstrip().splitlines()
    while lines and _AGENT_ID_LINE.fullmatch(lines[-1]):
        lines.pop()
    return "\n".join(lines).rstrip()


def _status_of(result_status: str | None) -> str | None:
    if result_status == "succeeded":
        return "completed"
    if result_status == "failed":
        return "failed"
    return None


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
