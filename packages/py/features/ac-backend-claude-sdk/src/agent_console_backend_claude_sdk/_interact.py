"""SDK `can_use_tool` ↔ 실행 중 상호작용(design §R14.8). 되묻기(`AskUserQuestion`)·도구 승인.

엔진은 상호작용 종류 이름을 모른다. 이 어댑터가 여는 종류 이름은 연결표 데이터
(`InteractionKindMap`, 설치자 설정으로 바꿀 수 있음)다.

- `AskUserQuestion`(질문 도구) → `question` 상호작용
  `{questions[{question, header?, options, multi_select}]}`. 응답 `answers`(+`response`)를
  `PermissionResultAllow(updated_input={…입력, answers, response?})`로 돌려준다.
- 그 밖의 도구 → `tool_permission` 상호작용 `{tool_name, input_preview, title?, display_name?,
  description?, blocked_path?, decision_reason?, tool_use_id?, agent_id?}`. 응답 `decision`이
  `allow`(+`updated_input`)·`allow_for_run`(이번 실행 메모리)·`deny`(+`message`).

- 순서: 실행 범위(ToolGuard) → 이번 실행 허용 메모리 → 상호작용 → 응답 경로가 없으면
  `unmatched_permission`.
- 상호작용이 Run 취소로 닫히면 `PermissionResultDeny(interrupt=True)`.
  만료면 종류의 `expire_response`를
  응답으로 쓰고, 해석할 수 없으면 거부한다.
- `updated_permissions`는 쓰지 않는다
  (사용자 프로젝트 `.claude/settings.local.json` 쓰기 방지, §R13a).
- 도구 입력은 `scrub` 후 잘라 낸 미리보기만 payload에 싣는다. 원본 입력은 SDK로만 돌아간다.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import (
    PermissionResult,
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)
from pydantic import BaseModel, ConfigDict, Field

from agent_console_contracts import KnownInteractionKinds
from agent_console_runtime import (
    InteractionCloseReasons,
    InteractionOutcome,
    InteractionRequest,
    InteractivePort,
    preview,
)

from ._guard import ToolGuard

DEFAULT_QUESTION_TOOL = "AskUserQuestion"
"""SDK의 되묻기 도구 이름."""

DEFAULT_PROMPTING_PERMISSION_MODES: tuple[str, ...] = ("default", "acceptEdits", "plan")
"""권한 흐름이 "묻기"로 끝날 수 있는 모드(콜백이 불린다, §R14.8).

`auto`는 콜백이 불리는지 미확인이라 넣지 않았다."""

DEFAULT_INPUT_PREVIEW_CHARS = 2000
"""`tool_permission` payload의 `input_preview` 최대 길이."""

DEFAULT_DENY_MESSAGE = "사용자가 거부했습니다"
"""사용자가 사유 없이 거부했을 때 모델에 돌려줄 메시지."""

DEFAULT_NO_ANSWER_MESSAGE = "사용자 응답이 없습니다"

UPDATED_INPUT_BLOCKED_MESSAGE = "실행 범위 제한: 사용자가 바꾼 입력이 허용된 실행 범위를 벗어납니다"
"""사용자가 바꾼 입력을 실행 범위 검사가 막았을 때의 메시지(입력 값은 싣지 않는다)."""
"""만료·해석할 수 없는 응답일 때 모델에 돌려줄 메시지."""

_CONTEXT_FIELDS = (
    "title",
    "display_name",
    "description",
    "blocked_path",
    "decision_reason",
    "tool_use_id",
    "agent_id",
)


class InteractionKindMap(BaseModel):
    """이 어댑터가 여는 상호작용 종류 id(연결표 데이터). 기본은 기본 플러그인 종류 이름."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(default=KnownInteractionKinds.QUESTION, min_length=1)
    tool_permission: str = Field(default=KnownInteractionKinds.TOOL_PERMISSION, min_length=1)

    def kinds(self) -> list[str]:
        """`capabilities.interactions`로 선언할 목록."""
        return [self.question, self.tool_permission]


type AttributionLookup = Callable[[str | None], str | None]
"""`ToolPermissionContext.agent_id` → 서브에이전트 이름(모르면 None = 위임자)."""


@dataclass
class PermissionBridge:
    """`can_use_tool` 콜백 하나(실행 단위 상태: 이번 실행 허용 메모리).

    Args:
        guard: 실행 범위 검사(사용자 허용보다 먼저).
        unmatched: 응답 경로가 없을 때 답(`allow`/`deny`).
        port: 상호작용을 열 곳(sink가 `InteractivePort`일 때). None이면 열지 않는다.
        kinds: 종류 이름 표.
        granted: 이 세션 grant의 종류 id.
        question_tool: 되묻기 도구 이름.
        scrub: 도구 입력을 가리는 함수(`RawSanitizer.scrub`).
        attribute: `agent_id` → 서브에이전트 이름.
        child_path: 서브에이전트 이름 → `node_path`.
        actors: 서브에이전트 이름 → actor.
        preview_chars: `input_preview` 최대 길이.
    """

    guard: ToolGuard
    unmatched: str = "deny"
    port: InteractivePort | None = None
    kinds: InteractionKindMap = field(default_factory=InteractionKindMap)
    granted: frozenset[str] = frozenset()
    question_tool: str = DEFAULT_QUESTION_TOOL
    scrub: Callable[[Any], Any] = lambda v: v
    attribute: AttributionLookup = lambda _agent_id: None
    child_path: Callable[[str], Sequence[str]] | None = None
    actors: Mapping[str, str | None] = field(default_factory=dict)
    preview_chars: int = DEFAULT_INPUT_PREVIEW_CHARS
    _allowed_for_run: set[tuple[str, str]] = field(default_factory=set)

    @property
    def asks_questions(self) -> bool:
        """되묻기를 열 수 있으면 참(grant + 열 곳)."""
        return self.port is not None and self.kinds.question in self.granted

    @property
    def asks_permissions(self) -> bool:
        """도구 승인을 열 수 있으면 참(grant + 열 곳)."""
        return self.port is not None and self.kinds.tool_permission in self.granted

    async def __call__(
        self, tool_name: str, tool_input: dict[str, Any], context: ToolPermissionContext | None
    ) -> PermissionResult:
        reason = self.guard.check(tool_name, tool_input)
        if reason is not None:
            return PermissionResultDeny(message=f"실행 범위 제한: {reason}")
        key = (tool_name, _input_key(tool_input))
        if key in self._allowed_for_run:
            return PermissionResultAllow(updated_input=tool_input)
        target = self.attribute(getattr(context, "agent_id", None))
        if tool_name == self.question_tool:
            # 서브에이전트는 되묻기를 쓸 수 없다(SDK 문서). 대상 귀속이 된 질문은 열지 않는다.
            if self.asks_questions and target is None:
                return await self._question(tool_input, context)
        elif self.asks_permissions:
            return await self._permission(tool_name, tool_input, context, target)
        return self._unmatched()

    # ------------------------------------------------------------ 종류별

    async def _question(
        self, tool_input: dict[str, Any], context: ToolPermissionContext | None
    ) -> PermissionResult:
        questions = [_question_to_payload(q) for q in tool_input.get("questions") or []]
        payload: dict[str, Any] = {"questions": questions}
        texts = [q.get("question") for q in questions if isinstance(q.get("question"), str)]
        request = InteractionRequest(
            kind=self.kinds.question,
            title=self._text(
                _first_str(getattr(context, "title", None), *(q.get("header") for q in questions))
            ),
            message=self._text("\n".join(t for t in texts if t)),
            payload=self.scrub(payload),
        )
        outcome = await self._open(request)
        if _interrupted(outcome):
            return PermissionResultDeny(message=DEFAULT_NO_ANSWER_MESSAGE, interrupt=True)
        response = outcome.response or {}
        answers = response.get("answers")
        if not isinstance(answers, Mapping):
            return PermissionResultDeny(message=DEFAULT_NO_ANSWER_MESSAGE)
        updated = {**tool_input, "answers": dict(answers)}
        if isinstance(response.get("response"), str):
            updated["response"] = response["response"]
        return self._allow(self.question_tool, updated)

    async def _permission(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        context: ToolPermissionContext | None,
        target: str | None,
    ) -> PermissionResult:
        payload: dict[str, Any] = {
            "tool_name": tool_name,
            "input_preview": preview(self.scrub(tool_input), self.preview_chars) or "",
        }
        for name in _CONTEXT_FIELDS:
            value = getattr(context, name, None)
            if value is not None:
                payload[name] = value
        request = InteractionRequest(
            kind=self.kinds.tool_permission,
            title=self._text(_first_str(payload.get("display_name"), tool_name)),
            message=self._text(_first_str(payload.get("title"), payload.get("description"))),
            payload=self.scrub(payload),
            actor=self.actors.get(target) if target is not None else None,
            node_path=(
                list(self.child_path(target))
                if target is not None and self.child_path is not None
                else None
            ),
        )
        outcome = await self._open(request)
        if _interrupted(outcome):
            return PermissionResultDeny(message=DEFAULT_NO_ANSWER_MESSAGE, interrupt=True)
        response = outcome.response or {}
        decision = response.get("decision")
        if decision in ("allow", "allow_for_run"):
            updated = response.get("updated_input")
            final = dict(updated) if isinstance(updated, Mapping) else tool_input
            return self._allow(tool_name, final, remember=decision == "allow_for_run")
        message = response.get("message")
        if isinstance(message, str) and message:
            return PermissionResultDeny(message=message)
        return PermissionResultDeny(
            message=DEFAULT_DENY_MESSAGE
            if outcome.status == "answered"
            else DEFAULT_NO_ANSWER_MESSAGE
        )

    def _allow(
        self, tool_name: str, final_input: dict[str, Any], *, remember: bool = False
    ) -> PermissionResult:
        """최종 입력(사용자가 바꾼 입력 포함)을 실행 범위로 다시 검사한 뒤 허용한다.

        `remember`면 실제로 허용한 최종 입력을 "이번 실행 동안 허용" 메모리 키로 남긴다.
        """
        if self.guard.check(tool_name, final_input) is not None:
            return PermissionResultDeny(message=UPDATED_INPUT_BLOCKED_MESSAGE)
        if remember:
            self._allowed_for_run.add((tool_name, _input_key(final_input)))
        return PermissionResultAllow(updated_input=final_input)

    def _text(self, text: str) -> str:
        """요청 제목·메시지에 넣을 문자열(비밀 가림)."""
        cleaned = self.scrub(text)
        return cleaned if isinstance(cleaned, str) else str(cleaned)

    async def _open(self, request: InteractionRequest) -> InteractionOutcome:
        assert self.port is not None  # asks_* 가 확인했다
        return await self.port.request_input(request)

    def _unmatched(self) -> PermissionResult:
        if self.unmatched == "allow":
            return PermissionResultAllow()
        return PermissionResultDeny(
            message="사전 승인되지 않은 도구입니다(unmatched_permission=deny)"
        )


def _question_to_payload(question: Any) -> dict[str, Any]:
    """SDK `AskUserQuestion` 질문 하나 → `question` 종류 payload 항목.

    `multiSelect`를 `multi_select`로 바꾼다.
    """
    if not isinstance(question, Mapping):
        return {"question": str(question), "options": [], "multi_select": False}
    out: dict[str, Any] = {
        "question": question.get("question", ""),
        "options": [
            {k: v for k, v in o.items() if k in ("label", "description")}
            for o in question.get("options") or []
            if isinstance(o, Mapping)
        ],
        "multi_select": bool(question.get("multiSelect", question.get("multi_select", False))),
    }
    if isinstance(question.get("header"), str):
        out["header"] = question["header"]
    return out


def _interrupted(outcome: InteractionOutcome) -> bool:
    return outcome.status == "cancelled" and outcome.reason == InteractionCloseReasons.CANCELLED


def _input_key(tool_input: Mapping[str, Any]) -> str:
    """ "이번 실행 동안 허용" 키: 입력을 정렬한 JSON."""
    return json.dumps(tool_input, sort_keys=True, ensure_ascii=False, default=str)


def _first_str(*values: Any) -> str:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return ""
