"""hook 결과(종료 코드·stdout JSON)에서 결정을 파생한다(표준 라이브러리만).

Claude Code hook 규칙(2026-10 문서 기준):
- 종료 코드 2 = 차단(JSON이 있어도 뒤집지 못함). 0 = 성공(stdout 전체가 JSON 객체 하나면 해석).
  그 밖 = 막지 않는 오류.
- JSON: `continue: false`(+`stopReason`) = 멈춤, `hookSpecificOutput.permissionDecision`
  (allow·deny·ask·defer, PreToolUse), `hookSpecificOutput.decision.behavior`(allow·deny,
  PermissionRequest), 최상위 `decision`(`block`, PreToolUse의 옛 값 `approve`·`block`은 allow·deny),
  `updatedInput`(수정 입력), `updatedToolOutput`(수정 결과).
결정 값은 열린 문자열이다. 모르는 값은 그대로 남긴다.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

__all__ = [
    "BLOCKING_EXIT_CODE",
    "derive_decision",
    "parse_hook_output",
]

BLOCKING_EXIT_CODE = 2
"""Claude Code가 차단으로 보는 종료 코드."""

_LEGACY_PRE_TOOL = {"approve": "allow", "block": "deny"}


def parse_hook_output(stdout: bytes) -> dict[str, Any] | None:
    """stdout 전체가 JSON 객체 하나면 그 객체, 아니면 None."""
    text = stdout.strip()
    if not text.startswith(b"{"):
        return None
    try:
        value = json.loads(text)
    except (ValueError, UnicodeDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def derive_decision(
    output: Mapping[str, Any] | None, exit_code: int | None, *, event: str = ""
) -> dict[str, Any]:
    """결정 요약.

    Args:
        output: `parse_hook_output` 결과(종료 코드 0·2일 때만 읽는다).
        exit_code: 원래 명령의 종료 코드(None = 실행하지 못함·신호로 끝남).
        event: hook 이벤트 이름(PreToolUse의 옛 `decision` 값 해석용).

    Returns:
        `{"value", "source", "reason", "updated_input", "updated_output", "additional_context"}`.
        value: `block`(종료 코드 2) · `stop`(continue false) · JSON 결정 값 · `modify`(수정 입력만)
        · `none`(결정 없음, 종료 0) · `error`(그 밖 종료 코드·실행 실패).
    """
    readable = output if exit_code in (0, BLOCKING_EXIT_CODE) and output is not None else {}
    specific = readable.get("hookSpecificOutput")
    specific = specific if isinstance(specific, Mapping) else {}
    permission = specific.get("decision")
    permission = permission if isinstance(permission, Mapping) else {}
    updated_input = "updatedInput" in specific or "updatedInput" in permission
    summary: dict[str, Any] = {
        "value": "none",
        "source": "none",
        "reason": None,
        "updated_input": updated_input,
        "updated_output": "updatedToolOutput" in specific,
        "additional_context": "additionalContext" in specific,
    }
    if exit_code == BLOCKING_EXIT_CODE:
        summary.update(value="block", source="exit_code")
        return summary
    if exit_code != 0:
        summary.update(value="error", source="exit_code")
        return summary
    if readable.get("continue") is False:
        summary.update(value="stop", source="json", reason=_text(readable.get("stopReason")))
    elif isinstance(specific.get("permissionDecision"), str):
        summary.update(
            value=specific["permissionDecision"],
            source="json",
            reason=_text(specific.get("permissionDecisionReason")),
        )
    elif isinstance(permission.get("behavior"), str):
        summary.update(
            value=permission["behavior"], source="json", reason=_text(permission.get("message"))
        )
    elif isinstance(readable.get("decision"), str):
        value = str(readable["decision"])
        if event == "PreToolUse":
            value = _LEGACY_PRE_TOOL.get(value, value)
        summary.update(value=value, source="json", reason=_text(readable.get("reason")))
    elif updated_input:
        summary.update(value="modify", source="json")
    return summary
