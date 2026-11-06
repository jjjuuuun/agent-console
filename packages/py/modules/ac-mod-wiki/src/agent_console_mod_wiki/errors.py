"""모듈 예외 → 계약 오류 본문(``ModuleParts.error_map``). 통합 서버·단독 실행에서 같은 모양이다.

| 예외 | 코드(HTTP) | details |
| --- | --- | --- |
| ``agent_console_wiki.WikiError`` 하위 | 그 ``code`` | 그 ``details``(예: ``has_history``) |
| ``WikiPathError`` | ``folders.invalid_path``(422, design §7R.7 재사용) | ``path``·``reason`` |
| ``WikiTemplateNotFoundError`` | ``not_found``(404) | ``id`` |
| ``WikiConflictError`` | ``version_conflict``(412) + ``ETag`` | ``expected``·``actual`` |
| ``WikiNotFound`` | ``wiki.not_found``(404) | ``id`` |
| ``WikiRequestError``(틀린 질의·본문, 읽기 전용) | 그 ``code`` | 그 ``details`` |
| ``SpaceError``(공간 없음·제공자 없음) | 그 ``code`` | ``project_id`` |
| ``StoreError`` | 그 ``code``(``store_error_body``) | 412는 현재 버전·``ETag`` |
| ``ValidationError``(손으로 고친 파일) | ``validation_failed``(422) | ``issues`` |
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from agent_console_contracts import ErrorCodes, Issue
from agent_console_modkit import ErrorMapping, ErrorReply
from agent_console_store import StoreError, store_error_body
from agent_console_wiki import (
    WikiConflictError,
    WikiError,
    WikiPathError,
    WikiTemplateNotFoundError,
)


class WikiRequestError(Exception):
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


class WikiNotFound(LookupError):  # noqa: N818 - 계약 코드 이름(`wiki.not_found`)과 맞춘다
    """그 공간에 위키 정의가 없다(``wiki.not_found``, 404).

    Attributes:
        wiki_id: 찾은 위키 id.
    """

    code = ErrorCodes.WIKI_NOT_FOUND

    def __init__(self, wiki_id: str) -> None:
        super().__init__(f"위키가 없습니다: {wiki_id!r}")
        self.wiki_id = wiki_id


class SpaceError(Exception):
    """공간을 고를 수 없다.

    - 공간 이름이 왔는데 ``wiki.spaces`` 제공자가 없다 → ``wiki.spaces_unavailable``(409).
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


def _wiki(exc: Exception) -> ErrorReply:
    details = dict(getattr(exc, "details", {}) or {})
    if isinstance(exc, WikiPathError):
        return ErrorReply(code=ErrorCodes.FOLDERS_INVALID_PATH, message=str(exc), details=details)
    if isinstance(exc, WikiTemplateNotFoundError):
        return ErrorReply(code=ErrorCodes.NOT_FOUND, message=str(exc), details=details)
    headers: dict[str, str] = {}
    if isinstance(exc, WikiConflictError) and exc.actual:
        headers["ETag"] = f'"{exc.actual}"'
    code = str(getattr(exc, "code", "") or ErrorCodes.BAD_REQUEST)
    return ErrorReply(code=code, message=str(exc), details=details, headers=headers)


def _request(exc: Exception) -> ErrorReply:
    code = getattr(exc, "code", ErrorCodes.BAD_REQUEST)
    details = getattr(exc, "details", {})
    return ErrorReply(code=str(code), message=str(exc), details=dict(details or {}))


def _not_found(exc: Exception) -> ErrorReply:
    wiki_id = getattr(exc, "wiki_id", "")
    return ErrorReply(code=ErrorCodes.WIKI_NOT_FOUND, message=str(exc), details={"id": wiki_id})


def _store(exc: Exception) -> ErrorReply:
    if not isinstance(exc, StoreError):  # pragma: no cover - 표가 형식을 보장한다
        return ErrorReply(code=ErrorCodes.INTERNAL)
    body = store_error_body(exc)
    return ErrorReply(code=body.code, details=body.details, headers=body.headers)


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
    WikiError: _wiki,
    WikiRequestError: _request,
    WikiNotFound: _not_found,
    StoreError: _store,
    SpaceError: _space,
    ValidationError: _validation,
}
"""``ModuleParts.error_map``에 넣는 표."""

__all__ = ["ERROR_MAP", "SpaceError", "WikiNotFound", "WikiRequestError"]
