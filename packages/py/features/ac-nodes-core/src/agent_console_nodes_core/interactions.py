"""기본 상호작용 종류(X15, design §R14.3): `question`·`tool_permission`·`review`.

entry point(`agent_console.interaction_kinds`)는 아래 디스크립터 객체를 바로 가리킨다(엔진의
`as_interaction_kind`가 감싼다). 엔진·서버·웹은 이 id를 모르고 디스크립터(스키마·화면 힌트)만 본다.
특정 종류를 여는 코드(claude-sdk 어댑터, 사용자 검토 노드)만 id를 쓴다.

모양은 claude-sdk 어댑터(1R.30)가 여는 payload·응답과 같다:
    - `question`: SDK AskUserQuestion과 같은 모양(`multiSelect` ↔ `multi_select`). 선택지 없는 자유
      질문은 `text`. 채팅 입력창 답은 `/response`로 들어간다.
      만료 응답은 없다(어댑터가 거부로 처리).
    - `tool_permission`: 정제한 입력 미리보기 + 권한 문맥. 응답 `decision`. 만료 = 거부.
    - `review`: 사용자 중간 검토. 결정 목록이 요청마다 다르므로 노드가 요청마다 `response_schema`를
      `review_response_schema(결정 id들)`로 바꾼다.
      만료 응답은 없다(노드가 `review.expired`로 실패).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final

from agent_console_contracts import InteractionKindDescriptor, KnownInteractionKinds, UiHints

__all__ = [
    "QUESTION",
    "REVIEW",
    "TOOL_PERMISSION",
    "TOOL_PERMISSION_DECISIONS",
    "review_response_schema",
]

_STR: Final[dict[str, Any]] = {"type": "string"}

QUESTION = InteractionKindDescriptor(
    id=KnownInteractionKinds.QUESTION,
    version=1,
    title="되묻기",
    description="에이전트가 실행 중 사용자에게 묻는다(선택지 또는 자유 답).",
    request_schema={
        "type": "object",
        "properties": {
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "question": _STR,
                        "header": _STR,
                        "options": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {"label": _STR, "description": _STR},
                                "required": ["label"],
                            },
                        },
                        "multi_select": {"type": "boolean", "default": False},
                    },
                    "required": ["question"],
                },
            },
            "text": {**_STR, "description": "선택지 없는 자유 질문."},
        },
    },
    response_schema={
        "type": "object",
        "properties": {
            "answers": {
                "type": "object",
                "description": "질문 → 고른 라벨(여럿 고르기면 목록) 또는 직접 입력.",
                "additionalProperties": {
                    "anyOf": [_STR, {"type": "array", "items": _STR}],
                },
            },
            "response": {**_STR, "description": "자유 답(채팅 입력창 답이 여기 들어간다)."},
        },
        "anyOf": [{"required": ["answers"]}, {"required": ["response"]}],
        "additionalProperties": False,
    },
    free_text_path="/response",
    expire_response=None,
    ui_hints=UiHints(renderer="choices", icon="?"),
)
"""`question`: 되묻기."""

TOOL_PERMISSION_DECISIONS: Final = ("allow", "allow_for_run", "deny")
"""`tool_permission` 응답 `decision` 값."""

TOOL_PERMISSION = InteractionKindDescriptor(
    id=KnownInteractionKinds.TOOL_PERMISSION,
    version=1,
    title="도구 승인",
    description="에이전트가 도구를 쓰기 전에 사용자 승인을 받는다.",
    request_schema={
        "type": "object",
        "properties": {
            "tool_name": _STR,
            "input_preview": {**_STR, "description": "비밀을 가린 입력 미리보기."},
            "title": _STR,
            "display_name": _STR,
            "description": _STR,
            "blocked_path": _STR,
            "decision_reason": _STR,
            "tool_use_id": _STR,
            "agent_id": _STR,
        },
        "required": ["tool_name"],
    },
    response_schema={
        "type": "object",
        "properties": {
            "decision": {"enum": list(TOOL_PERMISSION_DECISIONS)},
            "message": {**_STR, "description": "거부 사유 등 에이전트에게 전할 말."},
            "updated_input": {"type": "object", "description": "고친 도구 입력(허용일 때)."},
        },
        "required": ["decision"],
        "additionalProperties": False,
    },
    free_text_path=None,
    expire_response={"decision": "deny", "message": "사용자 응답 없음"},
    ui_hints=UiHints(renderer="permission", icon="!"),
)
"""`tool_permission`: 도구 승인."""


def review_response_schema(decision_ids: Sequence[str]) -> dict[str, Any]:
    """검토 응답 스키마. `decision`은 이 요청의 결정 id 중 하나(요청마다 다르다)."""
    decision: dict[str, Any] = {"type": "string"}
    if decision_ids:
        decision = {"enum": list(decision_ids)}
    return {
        "type": "object",
        "properties": {
            "decision": decision,
            "edited": {**_STR, "description": "고친 내용(결정이 edit을 허용할 때)."},
            "feedback": {**_STR, "description": "의견(결정이 feedback을 허용할 때)."},
        },
        "required": ["decision"],
        "additionalProperties": False,
    }


REVIEW = InteractionKindDescriptor(
    id=KnownInteractionKinds.REVIEW,
    version=1,
    title="검토",
    description="흐름 중간에 사용자가 내용을 보고 결정(승인·반려 등)한다.",
    request_schema={
        "type": "object",
        "properties": {
            "content": {**_STR, "description": "검토할 내용."},
            "source_node": _STR,
            "title": _STR,
            "decisions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": _STR,
                        "label": _STR,
                        "edit": {"type": "boolean"},
                        "feedback": {"type": "boolean"},
                        "ui_hints": {"type": "object"},
                    },
                    "required": ["id"],
                },
            },
        },
        "required": ["content", "decisions"],
    },
    response_schema=review_response_schema(()),
    free_text_path=None,
    expire_response=None,
    ui_hints=UiHints(renderer="review", icon="✓"),
)
"""`review`: 사용자 중간 검토."""
