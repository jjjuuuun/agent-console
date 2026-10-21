"""모듈이 던지는 공용 오류(design §3R.1.8).

켜진 모듈 안에서 **선택 포트가 없어** 그 동작만 꺼졌을 때 ``FeatureUnavailableError``를 던진다.
호스트가 오류 코드 ``feature_unavailable``(HTTP 409)와 상세 ``{module, port}``로 바꾼다.
꺼진 모듈의 경로는 아예 등록되지 않으므로(404) 이 오류를 쓰지 않는다.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

FEATURE_UNAVAILABLE = "feature_unavailable"
"""``FeatureUnavailableError``의 오류 코드(계약 ``ErrorCodes.FEATURE_UNAVAILABLE``과 같은 값)."""

NOT_READY = "not_ready"
"""호스트가 아직 준비되지 않았다(모듈 시작 전·종료 중, ``GET /health`` 503 — 계약
``ErrorCodes.NOT_READY``와 같은 값)."""


class FeatureUnavailableError(Exception):
    """선택 포트가 없어 이 동작을 할 수 없다.

    Args:
        module: 요청을 받은 모듈 id.
        port: 빠진 포트 이름.
        message: 사람용 메시지(없으면 기본 문구). 비밀을 넣지 않는다.

    Attributes:
        code: 항상 ``FEATURE_UNAVAILABLE``.
    """

    code = FEATURE_UNAVAILABLE

    def __init__(self, module: str, port: str, message: str | None = None) -> None:
        super().__init__(message or f"{module}: 이 기능에 필요한 포트가 없습니다({port})")
        self.module = module
        self.port = port

    @property
    def details(self) -> dict[str, str]:
        """오류 본문 ``details``(``{"module", "port"}``)."""
        return {"module": self.module, "port": self.port}


@dataclass(frozen=True)
class ErrorReply:
    """모듈 예외 하나를 오류 본문으로 바꾼 결과(``ErrorMapper``가 돌려준다).

    Attributes:
        code: 오류 코드(호스트가 HTTP 상태로 바꾼다).
        message: 사람용 메시지. None이면 ``str(exc)``. 호스트가 가림 함수를 거친다.
        details: 오류 본문 ``details``(JSON 값). 비밀을 넣지 않는다.
        headers: 응답에 더할 헤더(예: ``ETag``).
        fix: 오류 본문 ``fix``(해결 버튼, 계약 ``Fix``의 JSON 값). None이면 본문에 키를 넣지 않는다.
    """

    code: str
    message: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)
    headers: Mapping[str, str] = field(default_factory=dict)
    fix: Mapping[str, Any] | None = None


type ErrorMapper = Callable[[Exception], ErrorReply]
"""예외 → ``ErrorReply``(상세·헤더가 필요한 오류용)."""

type ErrorMapping = str | ErrorMapper
"""``ModuleParts.error_map``의 값: 오류 코드 문자열(본문 ``details`` 비움) 또는 ``ErrorMapper``."""


def error_reply(mapping: ErrorMapping, exc: Exception) -> ErrorReply:
    """``error_map`` 값 하나를 예외에 적용한다(문자열이면 코드만 정한 ``ErrorReply``)."""
    if isinstance(mapping, str):
        return ErrorReply(code=mapping)
    return mapping(exc)


__all__ = [
    "FEATURE_UNAVAILABLE",
    "ErrorMapper",
    "ErrorMapping",
    "ErrorReply",
    "FeatureUnavailableError",
    "error_reply",
]
