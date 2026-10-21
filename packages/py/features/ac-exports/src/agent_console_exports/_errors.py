"""내보내기 오류. `code`는 계약 오류 코드(`ErrorCodes`)다 — 앱이 HTTP 상태로 바꾼다."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from agent_console_contracts import ErrorCodes, Issue

__all__ = [
    "ExportConflictError",
    "ExportError",
    "ExportItemNotFoundError",
    "ExportValidationError",
    "UnknownExportRootError",
    "UnknownExporterError",
]


class ExportError(Exception):
    """내보내기 오류의 베이스.

    Attributes:
        code: 계약 오류 코드.
        issues: 위치가 붙은 이슈(요청 문서 기준 JSON Pointer, 값 없음).
        details: 추가 정보(값 없음).
    """

    code: str = ErrorCodes.BAD_REQUEST

    def __init__(
        self,
        message: str,
        *,
        issues: Sequence[Issue] = (),
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.issues = list(issues)
        self.details = dict(details or {})


class UnknownExporterError(ExportError):
    """등록되지 않은 형식."""

    code = ErrorCodes.NOT_FOUND


class UnknownExportRootError(ExportError):
    """허용 목록에 없는(또는 보호 위치라 쓸 수 없는) 폴더 루트."""

    code = ErrorCodes.NOT_FOUND


class ExportItemNotFoundError(ExportError):
    """고른 정의가 없다."""

    code = ErrorCodes.NOT_FOUND


class ExportValidationError(ExportError):
    """요청·옵션·경로가 잘못됐거나 형식이 내보낼 수 없다고 했다(`issues`)."""

    code = ErrorCodes.VALIDATION_FAILED


class ExportConflictError(ExportError):
    """`on_conflict=fail`인데 이미 있는 다른 파일이 있다(아무것도 쓰지 않았다, `details.paths`)."""

    code = ErrorCodes.ALREADY_EXISTS
