"""모듈 예외 → 계약 오류 본문(``ModuleParts.error_map``). 통합 서버·단독 실행에서 같은 모양이다.

| 예외 | 코드(HTTP) | details |
| --- | --- | --- |
| ``agent_console_sdd.SddError`` 하위 | 그 ``code`` | 그 ``details`` |
| ``TaskPatchError``(``TaskChangedError`` 포함) | 그 ``code`` | 그 ``details`` |
| ``StoreError`` | 그 ``code``(``store_error_body``) | 412는 현재 버전·``ETag`` |
| ``SecretRejectedError``(본문 reject·YAML) | ``sdd.secret_rejected``(422) | ``issues`` |
| ``SddRequestError``(틀린 질의·본문, 상한) | 그 ``code`` | 그 ``details`` |
| ``SpaceError``(공간 없음·제공자 없음) | 그 ``code`` | ``project_id`` |
| ``ValidationError``(손으로 고친 파일) | ``validation_failed``(422) | ``issues`` |
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from agent_console_contracts import ErrorCodes, Issue
from agent_console_modkit import ErrorMapping, ErrorReply
from agent_console_sdd import SddError, TaskPatchError
from agent_console_store import StoreError, store_error_body

from .secrets import SecretRejectedError


class SddRequestError(Exception):
    """요청이 틀렸거나 쓸 수 없는 동작이다(``code``·``details``를 그대로 싣는다).

    Attributes:
        code: 계약 오류 코드(기본 ``bad_request``).
        details: 화면에 줄 세부(입력 값 원문은 넣지 않는다).
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = ErrorCodes.BAD_REQUEST,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details: dict[str, Any] = dict(details or {})


class SpaceError(Exception):
    """공간을 고를 수 없다.

    - 공간 이름이 왔는데 ``sdd.spaces`` 제공자가 없다 → ``sdd.spaces_unavailable``(409).
    - 제공자가 모르는 이름 → ``project.not_found``(404).
    - 제공자가 열 수 없다 → 제공자 예외의 ``code``(없으면 ``internal``).

    Attributes:
        code: 계약 오류 코드. space: 요청한 공간 이름.
    """

    def __init__(self, code: str, space: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.space = space


def _issues_body(issues: list[Issue]) -> dict[str, Any]:
    return {"issues": [i.model_dump(mode="json", exclude_none=True) for i in issues]}


def _sdd(exc: Exception) -> ErrorReply:
    code = getattr(exc, "code", ErrorCodes.BAD_REQUEST)
    details = getattr(exc, "details", {})
    return ErrorReply(code=str(code), message=str(exc), details=dict(details or {}))


def _store(exc: Exception) -> ErrorReply:
    if not isinstance(exc, StoreError):  # pragma: no cover - 표가 형식을 보장한다
        return ErrorReply(code=ErrorCodes.INTERNAL)
    body = store_error_body(exc)
    return ErrorReply(code=body.code, details=body.details, headers=body.headers)


def _secret(exc: Exception) -> ErrorReply:
    issues = exc.issues if isinstance(exc, SecretRejectedError) else []
    return ErrorReply(
        code=ErrorCodes.SDD_SECRET_REJECTED, message=str(exc), details=_issues_body(list(issues))
    )


def _space(exc: Exception) -> ErrorReply:
    if not isinstance(exc, SpaceError):  # pragma: no cover - 표가 형식을 보장한다
        return ErrorReply(code=ErrorCodes.INTERNAL)
    return ErrorReply(code=exc.code, message=str(exc), details={"project_id": exc.space})


def _validation(exc: Exception) -> ErrorReply:
    issues: list[Issue] = []
    if isinstance(exc, ValidationError):
        for e in exc.errors():
            loc = "".join(
                "/" + str(p).replace("~", "~0").replace("/", "~1") for p in e.get("loc", ())
            )
            issues.append(
                Issue(
                    severity="error",
                    code="request." + str(e.get("type", "invalid")),
                    message=str(e.get("msg", "")),
                    path=loc,
                )
            )
    return ErrorReply(
        code=ErrorCodes.VALIDATION_FAILED,
        message="저장된 정의가 형식에 맞지 않습니다",
        details=_issues_body(issues),
    )


ERROR_MAP: dict[type[Exception], ErrorMapping] = {
    SddError: _sdd,
    TaskPatchError: _sdd,
    SddRequestError: _sdd,
    StoreError: _store,
    SecretRejectedError: _secret,
    SpaceError: _space,
    ValidationError: _validation,
}
"""``ModuleParts.error_map``에 넣는 표."""

__all__ = ["ERROR_MAP", "SddRequestError", "SpaceError"]
