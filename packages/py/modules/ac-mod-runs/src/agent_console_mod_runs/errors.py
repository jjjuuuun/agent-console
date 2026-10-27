"""모듈 예외 → 계약 오류 본문(``ModuleParts.error_map``). 통합 서버·단독 실행에서 같은 모양이다.

- ``GraphValidationError``(엔진·준비자 차단 이슈) → ``validation_failed``(``details.issues``,
  문구 = 머리 + 첫 오류 이슈 문구, ``fix`` = 해결 버튼이 있는 첫 이슈의 버튼).
- ``ResponseValidationError``(응답이 요청 형식에 맞지 않음) → ``validation_failed``.
- ``UnknownInteractionError`` → ``not_found``. ``InteractionClosedError`` → ``interaction_closed``
  (``details.interaction``).
- ``ResumeError`` → 그 ``code``(``not_found``·``run_not_resumable`` 등)와 ``details``. 자식 Run
  거절(``details.root_run_id``)이면 ``fix`` = [맨 위 실행 열기](역할 ``runs``, id = 루트 Run).
- ``RunNotFoundError``·``NodeTypeNotFoundError``·``BackendNotFoundError``·``UnknownBackendError`` →
  ``not_found``.
- ``ProbeUnsupportedError``(백엔드가 연결 테스트 능력이 없음) → 409 ``backend.probe_unsupported``
  (``details.backend``).
- 로그인(F14, ux-overhaul §15.9): ``LoginUnsupportedError`` → 409 ``backend.login_unsupported``,
  ``LogoutUnsupportedError`` → 409 ``backend.logout_unsupported``, ``LoginBusyError`` → 409
  ``backend.login_busy``(``details.session_id``·``details.backend``), ``LoginRefusedError`` → 그
  ``code``(HTTP 상태는 호스트 표, 표에 없는 코드는 호스트 기본 400)·``details``·``fix``,
  ``LoginSessionNotFoundError`` → 404 ``backend.login_session_not_found``, ``LoginInputError`` →
  422 ``validation_failed``(``details.reason``, 입력값 없음), ``LoginPayloadTooLargeError`` → 413.
- ``PortConfigError``(노드 config로 포트를 계산할 수 없음) → ``validation_failed``.
- ``RunPreflightError``(준비자 사전 점검이 실행을 만들기 전에 막음, 예: ``backend.unresolved``) →
  그 ``ErrorInfo``의 ``code``·``message``·``details``·``fix`` 그대로.
- ``DefinitionReadError``(팀 구성을 읽지 못함 — 저장소 오류·계약에 맞지 않는 파일) → 그 ``code``.
  저장소 예외 형식(``StoreError``)은 정의 모듈의 오류 맵이 맡으므로 여기서는 다시 걸지 않는다.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from agent_console_contracts import ErrorCodes, ErrorInfo, Fix, FixAction, FixTarget, Issue
from agent_console_modkit import ErrorMapping, ErrorReply
from agent_console_runtime import (
    GraphValidationError,
    InteractionClosedError,
    LoginBusyError,
    LoginInputError,
    LoginRefusedError,
    LoginSessionNotFoundError,
    LoginUnsupportedError,
    LogoutUnsupportedError,
    ProbeUnsupportedError,
    ResponseValidationError,
    ResumeError,
    UnknownBackendError,
    UnknownInteractionError,
)

ISSUE_CODE_PREFIX = "request."
"""pydantic 오류를 ``Issue``로 바꿀 때 code 접두어(뒤는 pydantic 오류 type)."""


class RunNotFoundError(LookupError):
    """Run이 없다(404)."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"Run {run_id}이(가) 없습니다")
        self.run_id = run_id


class NodeTypeNotFoundError(LookupError):
    """등록되지 않은 노드 타입(404)."""

    def __init__(self, type_id: str) -> None:
        super().__init__(f"노드 타입 {type_id}이(가) 없습니다")


class BackendNotFoundError(LookupError):
    """등록되지 않은 실행 백엔드(404)."""

    def __init__(self, backend_id: str) -> None:
        super().__init__(f"백엔드 {backend_id}이(가) 없습니다")


class PortConfigError(ValueError):
    """노드 config가 잘못되어 포트를 계산할 수 없다(422).

    Args:
        issues: 위치별 이슈(pydantic 검증이면 채운다).
        error: 그 밖의 예외 형식 이름(값은 담지 않는다).
    """

    def __init__(self, issues: Iterable[Issue] = (), *, error: str | None = None) -> None:
        super().__init__("노드 config가 잘못되어 포트를 계산할 수 없습니다")
        self.issues = list(issues)
        self.error = error


class DefinitionReadError(Exception):
    """실행할 팀 구성을 읽지 못했다(없음 404, 손상·계약 위반 422 등 — 저장소 ``code`` 그대로).

    Args:
        code: 계약 오류 코드.
        message: 사람이 읽는 문장(값 없음).
        issues: 계약 위반이면 위치별 이슈.
    """

    def __init__(self, code: str, message: str, issues: Iterable[Issue] = ()) -> None:
        super().__init__(message)
        self.code = code
        self.issues = list(issues)


class RunPreflightError(Exception):
    """준비자 사전 점검(``RunPreparer.preflight``)이 실행을 막았다. Run을 만들지 않았다.

    Args:
        error: 오류 본문 그대로(코드·사용자 문구·상세·해결 버튼). HTTP 상태는 코드로 정한다.
    """

    def __init__(self, error: ErrorInfo) -> None:
        super().__init__(error.message)
        self.error = error


def _pointer(loc: Iterable[Any]) -> str:
    parts = [str(p).replace("~", "~0").replace("/", "~1") for p in loc]
    return "".join("/" + p for p in parts)


def issues_from_errors(errors: Iterable[Mapping[str, Any]]) -> list[Issue]:
    """pydantic 오류 목록 → ``Issue[]``(입력 값은 담지 않는다)."""
    return [
        Issue(
            severity="error",
            code=ISSUE_CODE_PREFIX + str(e.get("type", "invalid")),
            message=str(e.get("msg", "")),
            path=_pointer(e.get("loc", ())),
        )
        for e in errors
    ]


def issues_body(issues: Iterable[Issue]) -> dict[str, Any]:
    return {"issues": [i.model_dump(mode="json", exclude_none=True) for i in issues]}


GRAPH_INVALID_MESSAGE = "팀 구성에 실행을 막는 문제가 있습니다"
"""차단 이슈 응답 문구의 머리(뒤에 첫 이슈 문구가 붙는다)."""

CHILD_RESUME_ACTION_LABEL = "맨 위 실행 열기"
CHILD_RESUME_ROLE = "runs"
"""자식 Run 이어 가기 거절(409)의 해결 버튼: 문구와 웹 라우트 역할(실행 화면, ``FixTarget.id`` =
루트 Run id)."""


def _first_fix(issues: Iterable[Issue]) -> dict[str, Any] | None:
    for issue in issues:
        if issue.fix is not None and issue.fix.actions:
            return issue.fix.model_dump(mode="json", exclude_none=True)
    return None


def _graph_reply(exc: Exception) -> ErrorReply:
    issues = list(exc.issues) if isinstance(exc, GraphValidationError) else []
    first = next((i for i in issues if i.severity == "error"), issues[0] if issues else None)
    message = (
        f"{GRAPH_INVALID_MESSAGE}: {first.message}" if first is not None else GRAPH_INVALID_MESSAGE
    )
    return ErrorReply(
        code=ErrorCodes.VALIDATION_FAILED,
        message=message,
        details=issues_body(issues),
        fix=_first_fix(issues),
    )


def _response_reply(exc: Exception) -> ErrorReply:
    issues = exc.issues if isinstance(exc, ResponseValidationError) else []
    return ErrorReply(
        code=ErrorCodes.VALIDATION_FAILED,
        message="응답이 요청의 형식에 맞지 않습니다",
        details=issues_body(issues),
    )


def _unknown_interaction(_: Exception) -> ErrorReply:
    return ErrorReply(code=ErrorCodes.NOT_FOUND, message="상호작용이 없습니다")


def _closed(exc: Exception) -> ErrorReply:
    details = (
        {"interaction": exc.interaction.model_dump(mode="json")}
        if isinstance(exc, InteractionClosedError)
        else {}
    )
    return ErrorReply(
        code=ErrorCodes.INTERACTION_CLOSED, message="이미 닫힌 상호작용입니다", details=details
    )


def _resume(exc: Exception) -> ErrorReply:
    if not isinstance(exc, ResumeError):  # pragma: no cover - 표가 형식을 보장한다
        return ErrorReply(code=ErrorCodes.BAD_REQUEST)
    details = dict(exc.details)
    root = details.get("root_run_id")
    fix = (
        Fix(
            actions=[
                FixAction(
                    label=CHILD_RESUME_ACTION_LABEL,
                    target=FixTarget(role=CHILD_RESUME_ROLE, id=str(root)),
                )
            ]
        ).model_dump(mode="json", exclude_none=True)
        if isinstance(root, str) and root
        else None
    )
    return ErrorReply(code=exc.code, message=exc.message, details=details, fix=fix)


def _ports(exc: Exception) -> ErrorReply:
    if not isinstance(exc, PortConfigError):  # pragma: no cover
        return ErrorReply(code=ErrorCodes.VALIDATION_FAILED)
    details = issues_body(exc.issues)
    if exc.error is not None:
        details["error"] = exc.error
    return ErrorReply(code=ErrorCodes.VALIDATION_FAILED, details=details)


def _definition(exc: Exception) -> ErrorReply:
    if not isinstance(exc, DefinitionReadError):  # pragma: no cover
        return ErrorReply(code=ErrorCodes.INTERNAL)
    details = issues_body(exc.issues) if exc.code == ErrorCodes.VALIDATION_FAILED else {}
    return ErrorReply(code=exc.code, details=details)


def _preflight(exc: Exception) -> ErrorReply:
    if not isinstance(exc, RunPreflightError):  # pragma: no cover
        return ErrorReply(code=ErrorCodes.BAD_REQUEST)
    error = exc.error
    fix = error.fix.model_dump(mode="json", exclude_none=True) if error.fix is not None else None
    return ErrorReply(code=error.code, message=error.message, details=dict(error.details), fix=fix)


def _probe_unsupported(exc: Exception) -> ErrorReply:
    backend = exc.backend_id if isinstance(exc, ProbeUnsupportedError) else None
    return ErrorReply(
        code=ErrorCodes.BACKEND_PROBE_UNSUPPORTED,
        message="이 실행 백엔드는 연결 테스트를 지원하지 않습니다",
        details={"backend": backend} if backend else {},
    )


class LoginPayloadTooLargeError(ValueError):
    """로그인 입력 본문이 한도를 넘었다(413). 값은 담지 않는다."""

    def __init__(self, limit: int) -> None:
        super().__init__(f"입력이 너무 깁니다({limit}바이트 한도)")
        self.limit = limit


def _login_unsupported(exc: Exception) -> ErrorReply:
    backend = exc.backend_id if isinstance(exc, LoginUnsupportedError) else None
    method = exc.method_id if isinstance(exc, LoginUnsupportedError) else None
    details: dict[str, Any] = {"backend": backend} if backend else {}
    if method:
        details["method"] = method
    return ErrorReply(
        code=ErrorCodes.BACKEND_LOGIN_UNSUPPORTED,
        message="이 실행 백엔드는 앱 화면 로그인을 지원하지 않습니다",
        details=details,
    )


def _logout_unsupported(exc: Exception) -> ErrorReply:
    backend = exc.backend_id if isinstance(exc, LogoutUnsupportedError) else None
    return ErrorReply(
        code=ErrorCodes.BACKEND_LOGOUT_UNSUPPORTED,
        message="이 실행 백엔드는 앱 화면 로그아웃을 지원하지 않습니다",
        details={"backend": backend} if backend else {},
    )


def _login_busy(exc: Exception) -> ErrorReply:
    if not isinstance(exc, LoginBusyError):  # pragma: no cover
        return ErrorReply(code=ErrorCodes.BACKEND_LOGIN_BUSY)
    return ErrorReply(
        code=ErrorCodes.BACKEND_LOGIN_BUSY,
        message="다른 창에서 로그인이 진행 중입니다",
        details={"session_id": exc.session_id, "backend": exc.backend_id},
    )


def _login_refused(exc: Exception) -> ErrorReply:
    if not isinstance(exc, LoginRefusedError):  # pragma: no cover
        return ErrorReply(code=ErrorCodes.BAD_REQUEST)
    fix = (
        Fix(actions=list(exc.fixes)).model_dump(mode="json", exclude_none=True)
        if exc.fixes
        else None
    )
    return ErrorReply(code=exc.code, message=exc.message, details=dict(exc.details), fix=fix)


def _login_input(exc: Exception) -> ErrorReply:
    reason = exc.reason if isinstance(exc, LoginInputError) else "invalid"
    return ErrorReply(
        code=ErrorCodes.VALIDATION_FAILED,
        message="이 입력을 받을 수 없습니다",
        details={"reason": reason},
    )


def _login_too_large(exc: Exception) -> ErrorReply:
    limit = exc.limit if isinstance(exc, LoginPayloadTooLargeError) else None
    return ErrorReply(
        code=ErrorCodes.PAYLOAD_TOO_LARGE,
        message="입력이 너무 깁니다",
        details={"limit_bytes": limit} if limit else {},
    )


ERROR_MAP: dict[type[Exception], ErrorMapping] = {
    GraphValidationError: _graph_reply,
    ResponseValidationError: _response_reply,
    UnknownInteractionError: _unknown_interaction,
    InteractionClosedError: _closed,
    ResumeError: _resume,
    RunNotFoundError: ErrorCodes.NOT_FOUND,
    NodeTypeNotFoundError: ErrorCodes.NOT_FOUND,
    BackendNotFoundError: ErrorCodes.NOT_FOUND,
    UnknownBackendError: ErrorCodes.NOT_FOUND,
    ProbeUnsupportedError: _probe_unsupported,
    LoginUnsupportedError: _login_unsupported,
    LogoutUnsupportedError: _logout_unsupported,
    LoginBusyError: _login_busy,
    LoginRefusedError: _login_refused,
    LoginSessionNotFoundError: ErrorCodes.BACKEND_LOGIN_SESSION_NOT_FOUND,
    LoginInputError: _login_input,
    LoginPayloadTooLargeError: _login_too_large,
    PortConfigError: _ports,
    DefinitionReadError: _definition,
    RunPreflightError: _preflight,
}
"""모듈 ``error_map``."""

__all__ = [
    "ERROR_MAP",
    "BackendNotFoundError",
    "DefinitionReadError",
    "LoginPayloadTooLargeError",
    "NodeTypeNotFoundError",
    "PortConfigError",
    "RunNotFoundError",
    "RunPreflightError",
    "issues_body",
    "issues_from_errors",
]
