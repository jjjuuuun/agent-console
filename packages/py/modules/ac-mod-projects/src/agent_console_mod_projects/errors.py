"""모듈 예외 → 계약 오류 본문(``ModuleParts.error_map``). 통합 서버·단독 실행에서 같은 모양이다.

- ``ProjectError`` → 그 ``code``·``details``(이 모듈이 낸 409·404·403 등).
- ``StoreError`` → 그 ``code``(404·409·412 등, 412는 현재 버전과 ``ETag``). 비밀 거부
  (``SecretRejected``)는 422 + 위치(``details.paths``, 값 없음).
- ``SpaceError``(``ac-project-space``) → 그 ``code``(폴더 없음·쓰기 불가·매니페스트 깨짐 등).
- ``FolderError``(``ac-local-folders``) → ``folders.<code>``.
- pydantic ``ValidationError``(손으로 고친 파일이 계약에 맞지 않음) → ``validation_failed``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from agent_console_contracts import ErrorCodes
from agent_console_local_folders import FolderError
from agent_console_modkit import ErrorMapping, ErrorReply
from agent_console_project_space import ManifestInvalid, SecretRejected, SpaceError
from agent_console_store import StoreError, store_error_body


class ProjectError(Exception):
    """이 모듈이 내는 오류(코드 + 상세). 상세에 파일 내용·비밀을 넣지 않는다.

    Args:
        code: 계약 오류 코드(``ErrorCodes``).
        message: 사람용 메시지.
        details: 오류 본문 ``details``(계약 details 모델의 JSON 값).
    """

    def __init__(self, code: str, message: str, details: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


def project_error_reply(exc: Exception) -> ErrorReply:
    """``ProjectError`` → 그 코드·상세."""
    if not isinstance(exc, ProjectError):  # pragma: no cover - 표가 형식을 보장한다
        return ErrorReply(code=ErrorCodes.INTERNAL)
    return ErrorReply(code=exc.code, message=exc.message, details=exc.details)


def store_error_reply(exc: Exception) -> ErrorReply:
    """``StoreError`` → 그 ``code``(공용 매핑). 비밀 거부는 위치만 싣는다."""
    if isinstance(exc, SecretRejected):
        return ErrorReply(
            code=exc.code,
            message=(
                "비밀처럼 보이는 값은 저장하지 않습니다. 비밀 저장소에 넣고 secret:// 참조로 "
                "바꾸세요"
            ),
            # issues = 필드 위치 이슈(정의 경로와 같은 모양, 33x). 오류 처리기는 앱 전체에 걸린다.
            details={
                "paths": [f.path for f in exc.findings],
                **store_error_body(exc).details,
            },
        )
    if not isinstance(exc, StoreError):  # pragma: no cover - 표가 형식을 보장한다
        return ErrorReply(code=ErrorCodes.INTERNAL)
    body = store_error_body(exc)
    return ErrorReply(code=body.code, details=body.details, headers=body.headers)


def space_error_reply(exc: Exception) -> ErrorReply:
    """``SpaceError`` → 그 ``code``. 매니페스트 깨짐은 이유·위치(값 없음)를 싣는다."""
    code = getattr(exc, "code", ErrorCodes.INTERNAL)
    if isinstance(exc, ManifestInvalid):
        return ErrorReply(
            code=code,
            message="프로젝트 설정 파일을 읽을 수 없습니다",
            details={"reason": exc.reason, "issues": list(exc.issues)},
        )
    return ErrorReply(code=code)


def folder_error_reply(exc: Exception) -> ErrorReply:
    """``FolderError`` → ``folders.<code>``(입력 경로는 싣지 않는다)."""
    code = getattr(exc, "code", "io_error")
    message = getattr(exc, "message", None)
    return ErrorReply(code=f"folders.{code}", message=message)


def model_error_reply(exc: Exception) -> ErrorReply:
    """저장된 파일이 계약 형식에 맞지 않음(입력 값은 담지 않는다)."""
    count = len(exc.errors()) if isinstance(exc, ValidationError) else 0
    return ErrorReply(
        code=ErrorCodes.VALIDATION_FAILED,
        message="프로젝트 파일이 형식에 맞지 않습니다",
        details={"errors": count},
    )


ERROR_MAP: dict[type[Exception], ErrorMapping] = {
    ProjectError: project_error_reply,
    StoreError: store_error_reply,
    SecretRejected: store_error_reply,
    SpaceError: space_error_reply,
    FolderError: folder_error_reply,
    ValidationError: model_error_reply,
}
"""모듈 ``error_map``."""

__all__ = [
    "ERROR_MAP",
    "ProjectError",
    "folder_error_reply",
    "model_error_reply",
    "project_error_reply",
    "space_error_reply",
    "store_error_reply",
]
