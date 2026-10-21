"""모듈 예외 → 계약 오류 본문(``ModuleParts.error_map``). 통합 서버·단독 실행에서 같은 모양이다.

- ``ChatError``(대화 서비스 오류) → 그 ``code``·``message``·``details``(``not_found``·
  ``conversation_busy``·``run_not_resumable``·``bad_request``).
- ``ChatFeatureUnavailableError``(실행 연결이 없음) → ``feature_unavailable``,
  ``details = {module, port}``(``FeatureUnavailableDetails`` — 빠진 의존을 이 모듈의 포트 이름으로).
"""

from __future__ import annotations

from collections.abc import Mapping

from agent_console_chat import (
    LAUNCHER_DEPENDENCY,
    RUNS_DEPENDENCY,
    ChatError,
    ChatFeatureUnavailableError,
)
from agent_console_contracts import ErrorCodes, FeatureUnavailableDetails
from agent_console_modkit import ErrorMapping, ErrorReply

from .ports import CHAT_RUNS, CHAT_TURN_LAUNCHER

DEPENDENCY_PORTS: Mapping[str, str] = {
    LAUNCHER_DEPENDENCY: CHAT_TURN_LAUNCHER.name,
    RUNS_DEPENDENCY: CHAT_RUNS.name,
}
"""``ChatFeatureUnavailableError.dependency`` → 이 모듈의 선택 포트 이름."""


def _chat(exc: Exception) -> ErrorReply:
    if not isinstance(exc, ChatError):  # pragma: no cover - 표가 형식을 보장한다
        return ErrorReply(code=ErrorCodes.BAD_REQUEST)
    return ErrorReply(code=exc.code, message=exc.message, details=dict(exc.details))


def error_map(module_id: str) -> dict[type[Exception], ErrorMapping]:
    """이 모듈의 ``error_map``(``feature_unavailable``의 ``module``에 ``module_id``를 넣는다)."""

    def unavailable(exc: Exception) -> ErrorReply:
        dependency = exc.dependency if isinstance(exc, ChatFeatureUnavailableError) else ""
        details = FeatureUnavailableDetails(
            module=module_id, port=DEPENDENCY_PORTS.get(dependency, dependency or "unknown")
        )
        return ErrorReply(
            code=ErrorCodes.FEATURE_UNAVAILABLE,
            message=str(exc),
            details=details.model_dump(mode="json"),
        )

    return {ChatError: _chat, ChatFeatureUnavailableError: unavailable}


__all__ = ["DEPENDENCY_PORTS", "error_map"]
