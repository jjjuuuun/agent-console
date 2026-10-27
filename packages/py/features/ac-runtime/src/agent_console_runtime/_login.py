"""실행 백엔드 계정 로그인·로그아웃 — 선택 능력과 세션 서비스(ux-overhaul §15.9, F14).

백엔드는 두 선택 메서드를 구현하고 디스크립터 ``capabilities.login``·``capabilities.logout``(와
``login_methods``)로 알린다. 이 모듈은 백엔드 id·로그인 방식(CLI·브라우저 등)을 모른다.

- ``start_login(ctx, method_id) -> LoginDriver``: 로그인 과정 하나를 시작한다. 진행은 드라이버가
  ``progress()``로 알리고, 사용자 입력(``send_text``·``send_key``)과 취소(``cancel``)를 받는다.
- ``logout(ctx, method_id) -> BackendLogoutResult``: 이 PC의 로그인을 지운다.

``BackendLoginService``(서버·CLI·테스트 공용)가 감싼다:

- **서버 전체에서 진행 중인 세션은 하나**(두 번째 시작은 ``LoginBusyError``).
- 시간 상한(요청 값 → 상한으로 자름) → ``expired``, 하트비트(조회가 ``heartbeat_s`` 넘게 끊김) →
  ``cancelled``(reason ``heartbeat``), 취소, 종료(``aclose``) 때 드라이버 ``cancel``.
- 응답 가림: 세션에 들어온 입력값(과 그 5자 이상 부분 문자열) + 드라이버 ``secrets_to_mask()`` +
  주입 ``redact``(비밀 해석기·의심 규칙).
- 서버 로그: 세션 id·백엔드 id·방법 id·phase·reason·소요 시간만(INFO).
  입력값·화면·URL은 남기지 않는다.
- 끝난 세션은 ``retain_s`` 동안만 조회된다. 이벤트·실행 기록에는 남기지 않는다.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Protocol, cast, runtime_checkable

from pydantic import ValidationError

from agent_console_contracts import (
    BackendDescriptor,
    BackendLoginPhase,
    BackendLoginSession,
    BackendLogoutResult,
    FixAction,
)

from ._interfaces import ExecutionBackend
from ._readiness import UnknownBackendError
from ._secrets import REDACTED

_log = logging.getLogger("agent_console_runtime.login")

DEFAULT_LOGIN_TIMEOUT_S = 300.0
"""로그인 세션 기본 시간 상한(초)."""
DEFAULT_LOGIN_TIMEOUT_MAX_S = 900.0
"""요청이 줄 수 있는 최대 시간(초)."""
DEFAULT_LOGIN_HEARTBEAT_S = 30.0
"""조회가 이만큼 끊기면 세션을 취소한다(초)."""
DEFAULT_LOGIN_RETAIN_S = 60.0
"""끝난 세션을 조회할 수 있는 시간(초)."""
DEFAULT_LOGIN_SCREEN_MAX_LINES = 40
"""응답 ``screen``의 최대 줄 수."""
DEFAULT_LOGOUT_TIMEOUT_S = 30.0
"""로그아웃 시간 상한(초)."""
DEFAULT_DRIVER_CANCEL_TIMEOUT_S = 10.0
"""드라이버 ``cancel``을 기다리는 최대 시간(초)."""
DEFAULT_DEFAULT_METHOD_ID = "default"
"""디스크립터에 ``login_methods``가 없을 때 쓰는 방법 id."""

DEFAULT_ACCEPTS_KEYS: Final = ("enter", "up", "down", "escape")
"""드라이버가 ``accepts_keys``를 비워 두면 서비스가 받는 키(설계 §15.9-6)."""

MASK_MIN_PART = 5
"""입력값의 이 길이 이상 부분 문자열도 가린다(잘린 화면 줄에 남은 일부)."""

TERMINAL_PHASES: Final = frozenset({"succeeded", "failed", "cancelled", "expired"})
"""끝난 단계(더 바뀌지 않는다)."""


class LoginReasons:
    """서비스가 직접 만드는 사유 코드(열린 어휘의 일부)."""

    TIMEOUT = "timeout"
    """시간 상한에 닿았다(``expired``)."""
    HEARTBEAT = "heartbeat"
    """조회가 끊겨 취소했다(``cancelled``)."""
    SHUTDOWN = "shutdown"
    """서버가 끝나며 취소했다(``cancelled``)."""
    START_FAILED = "start_failed"
    """``start_login``이 예외를 냈다(``failed``, ``details.error`` = 예외 형식 이름)."""
    ERROR = "error"
    """드라이버가 진행 중 예외를 냈다(``failed``)."""


@dataclass(frozen=True)
class LoginTexts:
    """서비스가 만드는 문구(데이터). 앱이 바꿔 넣을 수 있다."""

    starting: str = "로그인을 준비하고 있습니다."
    cancelled: str = "취소했습니다. 로그인 정보는 바뀌지 않았습니다."
    heartbeat: str = "화면과 연결이 끊겨 로그인을 취소했습니다. 로그인 정보는 바뀌지 않았습니다."
    shutdown: str = "서버가 종료되어 로그인을 취소했습니다."
    expired: str = "시간({minutes:g}분) 안에 끝나지 않아 로그인을 멈췄습니다. 다시 시도해 주세요."
    start_failed: str = "로그인을 시작하지 못했습니다."
    error: str = "로그인 중 오류가 났습니다."
    logout_timeout: str = "로그아웃이 {seconds:g}초 안에 끝나지 않았습니다."
    logout_error: str = "로그아웃 중 오류가 났습니다."


# ---------------------------------------------------------------- 확장 지점


@dataclass(frozen=True)
class BackendLoginContext:
    """``start_login``·``logout``에 넘기는 환경(주입).

    Attributes:
        backend_id: 등록된 백엔드 id.
        clock: 현재 시각(epoch 초).
        environ: 서버 환경변수(읽기 전용 사본). 하위 프로세스 환경은 백엔드가 자기 정책으로 만든다.
        has_secret: 비밀 이름이 공급자에 있는지만 묻는다(값을 돌려주지 않는다).
    """

    backend_id: str
    clock: Callable[[], float] = time.time
    environ: Mapping[str, str] = field(default_factory=dict)
    has_secret: Callable[[str], bool] = field(default=lambda _name: False)


@dataclass(frozen=True)
class LoginProgress:
    """드라이버가 알리는 지금 상태. 서비스가 ``BackendLoginSession``으로 바꾼다(가림 적용).

    Attributes:
        phase: ``starting``·``waiting_user``·``verifying``·``succeeded``·``failed``. 드라이버는
            ``cancelled``·``expired``를 쓰지 않는다(서비스 몫).
        message: 단계 안내 또는 결과 문장.
        open_url: 브라우저에서 열 주소(드라이버가 https·허용 호스트를 확인한 것만).
        needs_code: 코드 붙여 넣기를 기다린다.
        code_label: 코드 칸 라벨.
        accepts_keys: 받는 키 이름(비면 ``DEFAULT_ACCEPTS_KEYS``).
        screen: 하위 과정 화면 줄(서비스가 가리고 줄 수를 자른다).
        warnings: 주의 문장.
        reason: 실패 사유 코드.
        details: 접힌 상세(비밀 값 없음).
        fixes: 해결 버튼.
    """

    phase: str
    message: str = ""
    open_url: str | None = None
    needs_code: bool = False
    code_label: str = ""
    accepts_keys: Sequence[str] = ()
    screen: Sequence[str] = ()
    warnings: Sequence[str] = ()
    reason: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)
    fixes: Sequence[FixAction] = ()


@runtime_checkable
class LoginDriver(Protocol):
    """진행 중인 로그인 과정 하나(백엔드가 만든다)."""

    def progress(self) -> LoginProgress:
        """지금 상태(빨리 끝나야 한다, 막지 않는다)."""
        ...

    async def wait_changed(self, timeout: float) -> None:
        """상태가 바뀌거나 ``timeout``초가 지날 때까지 기다린다."""
        ...

    async def send_text(self, text: str) -> None:
        """사용자가 붙여 넣은 글자를 보낸다(앞뒤 공백은 서비스가 이미 잘랐다)."""
        ...

    async def send_key(self, key: str) -> None:
        """이름 붙은 키 하나를 보낸다(``accepts_keys`` 안의 값만 온다)."""
        ...

    async def cancel(self) -> None:
        """멈추고 하위 과정을 정리한다. 여러 번 불러도 된다. 로그인 정보는 바꾸지 않는다."""
        ...

    def secrets_to_mask(self) -> list[str]:
        """응답에서 가려야 할 값(드라이버가 받은 입력 등). 서비스는 자기가 받은 입력도 가린다."""
        ...


@runtime_checkable
class LoginCapableBackend(Protocol):
    """선택 능력: 앱 화면 로그인(``capabilities.login=true``와 함께)."""

    descriptor: BackendDescriptor

    async def start_login(self, ctx: BackendLoginContext, method_id: str) -> LoginDriver:
        """로그인 과정을 시작한다.

        Raises:
            LoginRefusedError: 설정 등으로 시작을 거절한다(사유 코드와 문장).
        """
        ...


@runtime_checkable
class LogoutCapableBackend(Protocol):
    """선택 능력: 앱 화면 로그아웃(``capabilities.logout=true``와 함께)."""

    descriptor: BackendDescriptor

    async def logout(self, ctx: BackendLoginContext, method_id: str | None) -> BackendLogoutResult:
        """이 PC의 로그인을 지운다. 실패는 예외보다 ``ok=false`` + ``reason``으로."""
        ...


def supports_login(backend: object) -> bool:
    """디스크립터가 ``login`` 능력을 선언하고 메서드도 있으면 참."""
    return _declares(backend, "login") and isinstance(backend, LoginCapableBackend)


def supports_logout(backend: object) -> bool:
    """디스크립터가 ``logout`` 능력을 선언하고 메서드도 있으면 참."""
    return _declares(backend, "logout") and isinstance(backend, LogoutCapableBackend)


def _declares(backend: object, name: str) -> bool:
    descriptor = getattr(backend, "descriptor", None)
    caps = getattr(descriptor, "capabilities", None)
    return bool(getattr(caps, name, False))


# ---------------------------------------------------------------- 오류


class LoginUnsupportedError(Exception):
    """백엔드가 로그인을 지원하지 않거나 그 방법이 없다."""

    def __init__(self, backend_id: str, method_id: str | None = None) -> None:
        super().__init__(f"백엔드 {backend_id}은(는) 이 로그인을 지원하지 않습니다")
        self.backend_id = backend_id
        self.method_id = method_id


class LogoutUnsupportedError(Exception):
    """백엔드가 로그아웃을 지원하지 않는다."""

    def __init__(self, backend_id: str) -> None:
        super().__init__(f"백엔드 {backend_id}은(는) 로그아웃을 지원하지 않습니다")
        self.backend_id = backend_id


class LoginBusyError(Exception):
    """다른 로그인 세션이 진행 중이다."""

    def __init__(self, session_id: str, backend_id: str) -> None:
        super().__init__("다른 로그인이 진행 중입니다")
        self.session_id = session_id
        self.backend_id = backend_id


class LoginRefusedError(Exception):
    """백엔드가 로그인 시작을 거절했다(예: 설치자 설정이 구독 인증을 껐다).

    Attributes:
        code: 오류 코드(열린 어휘, 예: ``backend.subscription_auth_disabled``).
        message: 사람에게 보일 문장(비밀 값 없음).
        details: 기계용 상세.
        fixes: 해결 버튼.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
        fixes: Sequence[FixAction] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})
        self.fixes = list(fixes)


class LoginSessionNotFoundError(LookupError):
    """로그인 세션이 없거나 보관 시간이 지났다."""

    def __init__(self, session_id: str) -> None:
        super().__init__("로그인 세션이 없습니다")
        self.session_id = session_id


class LoginInputError(ValueError):
    """입력을 받을 수 없다. 메시지·속성에 입력값은 없다.

    Attributes:
        reason: ``key_not_accepted``·``text_invalid``·``session_finished``.
    """

    KEY_NOT_ACCEPTED = "key_not_accepted"
    TEXT_INVALID = "text_invalid"
    SESSION_FINISHED = "session_finished"

    def __init__(self, reason: str) -> None:
        super().__init__(f"입력을 받을 수 없습니다: {reason}")
        self.reason = reason


# ---------------------------------------------------------------- 가림


def mask_values(text: str, secrets: Sequence[str], *, min_part: int = MASK_MIN_PART) -> str:
    """``secrets``의 값과 그 ``min_part``자 이상 부분 문자열을 ``[REDACTED]``로 바꾼다.

    ``min_part``보다 짧은 값은 값 전체가 나올 때만 가린다.

    Example:
        >>> mask_values("code=ABCDEFGH tail=FGH12", ["ABCDEFGH"])
        'code=[REDACTED] tail=FGH12'
        >>> mask_values("partial=CDEFG!", ["ABCDEFGH"])
        'partial=[REDACTED]!'
    """
    if not text or not secrets:
        return text
    covered = [False] * len(text)
    for secret in secrets:
        if not secret:
            continue
        if len(secret) < min_part:
            start = text.find(secret)
            while start >= 0:
                for i in range(start, start + len(secret)):
                    covered[i] = True
                start = text.find(secret, start + 1)
            continue
        parts = {secret[i : i + min_part] for i in range(len(secret) - min_part + 1)}
        for i in range(len(text) - min_part + 1):
            if text[i : i + min_part] in parts:
                for j in range(i, i + min_part):
                    covered[j] = True
    if not any(covered):
        return text
    out: list[str] = []
    i = 0
    while i < len(text):
        if covered[i]:
            while i < len(text) and covered[i]:
                i += 1
            out.append(REDACTED)
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def _mask_json(value: Any, secrets: Sequence[str]) -> Any:
    if isinstance(value, str):
        return mask_values(value, secrets)
    if isinstance(value, Mapping):
        return {k: _mask_json(v, secrets) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_mask_json(v, secrets) for v in value]
    return value


def _identity(value: Any) -> Any:
    return value


_PLAIN_FIELDS: Final = (
    "session_id",
    "backend_id",
    "method_id",
    "phase",
    "started_at",
    "expires_at",
    "finished_at",
)


# ---------------------------------------------------------------- 서비스


@dataclass
class _Session:
    session_id: str
    backend_id: str
    method_id: str
    started_at: float
    expires_at: float
    started_mono: float
    deadline_mono: float
    timeout_s: float
    last_seen: float
    driver: LoginDriver | None = None
    secrets: list[str] = field(default_factory=list)
    final: BackendLoginSession | None = None
    finished_mono: float | None = None
    watch: asyncio.Task[None] | None = None

    @property
    def finished(self) -> bool:
        return self.final is not None


class BackendLoginService:
    """백엔드 로그인 세션(서버 전체 하나)·로그아웃(서버·CLI·테스트에서 같은 로직).

    Args:
        backends: 지금 등록된 ``id → 백엔드``를 돌려주는 함수(호출마다 다시 읽는다).
        redact: 응답 JSON 값(dict)의 비밀을 가리는 함수(비밀 해석기·의심 규칙).
        has_secret: 비밀 이름 존재 확인.
        environ: 서버 환경변수를 돌려주는 함수(``BackendLoginContext.environ``).
        clock: 현재 시각(epoch 초).
        monotonic: 시간 상한·하트비트 계산용 시계(초).
        timeout_default_s: 요청이 시간을 주지 않을 때.
        timeout_max_s: 요청 시간 상한(넘으면 잘린다).
        heartbeat_s: 조회가 이만큼 끊기면 취소한다.
        retain_s: 끝난 세션을 조회할 수 있는 시간.
        screen_max_lines: 응답 ``screen`` 최대 줄 수.
        logout_timeout_s: 로그아웃 시간 상한.
        tick_s: 감시 간격(테스트에서 줄인다).
        id_factory: 세션 id 생성.
        texts: 서비스 문구.
    """

    def __init__(
        self,
        backends: Callable[[], Mapping[str, ExecutionBackend]],
        *,
        redact: Callable[[Any], Any] = _identity,
        has_secret: Callable[[str], bool] = lambda _name: False,
        environ: Callable[[], Mapping[str, str]] = dict,
        clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
        timeout_default_s: float = DEFAULT_LOGIN_TIMEOUT_S,
        timeout_max_s: float = DEFAULT_LOGIN_TIMEOUT_MAX_S,
        heartbeat_s: float = DEFAULT_LOGIN_HEARTBEAT_S,
        retain_s: float = DEFAULT_LOGIN_RETAIN_S,
        screen_max_lines: int = DEFAULT_LOGIN_SCREEN_MAX_LINES,
        logout_timeout_s: float = DEFAULT_LOGOUT_TIMEOUT_S,
        tick_s: float = 0.5,
        id_factory: Callable[[], str] = lambda: uuid.uuid4().hex,
        texts: LoginTexts | None = None,
    ) -> None:
        if min(timeout_default_s, timeout_max_s, heartbeat_s, logout_timeout_s, tick_s) <= 0:
            raise ValueError("시간 값은 0보다 커야 합니다")
        if retain_s < 0 or screen_max_lines < 0:
            raise ValueError("retain_s·screen_max_lines는 0 이상이어야 합니다")
        self._backends = backends
        self._redact = redact
        self._has_secret = has_secret
        self._environ = environ
        self._clock = clock
        self._mono = monotonic
        self._timeout_default = timeout_default_s
        self._timeout_max = timeout_max_s
        self._heartbeat = heartbeat_s
        self._retain = retain_s
        self._screen_max = screen_max_lines
        self._logout_timeout = logout_timeout_s
        self._tick = tick_s
        self._new_id = id_factory
        self._texts = texts or LoginTexts()
        self._sessions: dict[str, _Session] = {}
        self._active: _Session | None = None
        self._lock = asyncio.Lock()
        self._closed = False

    # ------------------------------------------------------------ 공용

    def _get_backend(self, backend_id: str) -> ExecutionBackend:
        found = self._backends().get(backend_id)
        if found is None:
            raise UnknownBackendError(backend_id)
        return found

    def _context(self, backend_id: str) -> BackendLoginContext:
        return BackendLoginContext(
            backend_id,
            clock=self._clock,
            environ=dict(self._environ()),
            has_secret=self._has_secret,
        )

    def clamp_timeout(self, requested: float | None) -> float:
        """요청한 시간(없으면 기본) → 상한으로 자른 값."""
        wanted = requested if requested is not None and requested > 0 else self._timeout_default
        return min(wanted, self._timeout_max)

    def _prune(self) -> None:
        now = self._mono()
        for sid, rec in list(self._sessions.items()):
            if rec.finished_mono is not None and now - rec.finished_mono > self._retain:
                del self._sessions[sid]

    def _find(self, session_id: str) -> _Session:
        self._prune()
        rec = self._sessions.get(session_id)
        if rec is None:
            raise LoginSessionNotFoundError(session_id)
        return rec

    # ------------------------------------------------------------ 응답 만들기

    def _snapshot(self, rec: _Session, progress: LoginProgress) -> BackendLoginSession:
        keys = list(progress.accepts_keys) or list(DEFAULT_ACCEPTS_KEYS)
        screen = list(progress.screen)
        screen = screen[-self._screen_max :] if self._screen_max > 0 else []
        raw = BackendLoginSession(
            session_id=rec.session_id,
            backend_id=rec.backend_id,
            method_id=rec.method_id,
            phase=cast(
                "BackendLoginPhase", progress.phase if progress.phase in _ALL_PHASES else "failed"
            ),
            message=progress.message,
            open_url=progress.open_url,
            needs_code=progress.needs_code and progress.phase == "waiting_user",
            code_label=progress.code_label,
            accepts_keys=keys if progress.phase not in TERMINAL_PHASES else [],
            screen=screen,
            warnings=list(progress.warnings),
            reason=progress.reason,
            details=dict(progress.details),
            fixes=list(progress.fixes),
            started_at=rec.started_at,
            expires_at=rec.expires_at,
            finished_at=self._clock() if progress.phase in TERMINAL_PHASES else None,
        )
        return self._masked(rec, raw)

    def _masked(self, rec: _Session, session: BackendLoginSession) -> BackendLoginSession:
        dumped = session.model_dump(mode="json")
        plain = {k: dumped.pop(k) for k in _PLAIN_FIELDS}
        secrets = self._secrets_of(rec)
        masked = _mask_json(self._redact(_mask_json(dumped, secrets)), secrets)
        try:
            return BackendLoginSession.model_validate({**masked, **plain})
        except ValidationError:  # 가린 결과가 형식에 맞지 않으면 글자 없이
            return BackendLoginSession(
                session_id=rec.session_id,
                backend_id=rec.backend_id,
                method_id=rec.method_id,
                phase=session.phase,
                message=self._texts.error,
                reason=session.reason if session.reason else None,
                started_at=rec.started_at,
                expires_at=rec.expires_at,
                finished_at=session.finished_at,
            )

    def _secrets_of(self, rec: _Session) -> list[str]:
        values = list(rec.secrets)
        if rec.driver is not None:
            with contextlib.suppress(Exception):
                values.extend(v for v in rec.driver.secrets_to_mask() if v)
        return sorted(set(values), key=len, reverse=True)

    def _view(self, rec: _Session) -> BackendLoginSession:
        if rec.final is not None:
            return rec.final
        assert rec.driver is not None
        try:
            progress = rec.driver.progress()
        except Exception as exc:  # 드라이버 오류 → 실패로 끝낸다(문장 원문은 버림)
            progress = LoginProgress(
                phase="failed",
                message=self._texts.error,
                reason=LoginReasons.ERROR,
                details={"error": type(exc).__name__},
            )
        if progress.phase in TERMINAL_PHASES:
            return self._finish(rec, progress)
        return self._snapshot(rec, progress)

    def _finish(self, rec: _Session, progress: LoginProgress) -> BackendLoginSession:
        if rec.final is not None:
            return rec.final
        rec.final = self._snapshot(rec, progress)
        rec.finished_mono = self._mono()
        if self._active is rec:
            self._active = None
        _log.info(
            "백엔드 로그인 끝: session=%s backend=%s method=%s phase=%s reason=%s elapsed_ms=%s",
            rec.session_id,
            rec.backend_id,
            rec.method_id,
            rec.final.phase,
            rec.final.reason,
            max(0, round((rec.finished_mono - rec.started_mono) * 1000)),
        )
        return rec.final

    # ------------------------------------------------------------ 로그인

    def login_supported(self, backend_id: str) -> bool:
        """로그인 지원 여부.

        Raises:
            UnknownBackendError: 등록되지 않은 id.
        """
        return supports_login(self._get_backend(backend_id))

    def _method(self, backend_id: str, backend: ExecutionBackend, wanted: str | None) -> str:
        methods = [m.id for m in getattr(backend.descriptor, "login_methods", [])]
        if wanted is None:
            return methods[0] if methods else DEFAULT_DEFAULT_METHOD_ID
        if methods and wanted not in methods:
            raise LoginUnsupportedError(backend_id, wanted)
        return wanted

    async def start(
        self, backend_id: str, method_id: str | None = None, timeout_s: float | None = None
    ) -> BackendLoginSession:
        """로그인 세션을 시작한다.

        Args:
            backend_id: 백엔드 id.
            method_id: 로그인 방법 id(None = 디스크립터의 첫 방법).
            timeout_s: 최대 진행 시간(None = 기본, 상한으로 잘림).

        Returns:
            시작한 세션. 백엔드가 시작 중 예외를 내면 ``failed``(``reason=start_failed``) 세션.

        Raises:
            UnknownBackendError: 등록되지 않은 id.
            LoginUnsupportedError: 능력이 없거나 모르는 방법.
            LoginBusyError: 다른 세션이 진행 중.
            LoginRefusedError: 백엔드가 시작을 거절.
        """
        backend = self._get_backend(backend_id)
        if not supports_login(backend):
            raise LoginUnsupportedError(backend_id, method_id)
        assert isinstance(backend, LoginCapableBackend)
        method = self._method(backend_id, backend, method_id)
        async with self._lock:
            if self._closed:
                raise LoginRefusedError("not_ready", "서버가 종료 중입니다")
            active = self._active
            if active is not None and not active.finished:
                self._view(active)  # 끝났는데 아직 감시가 못 본 경우를 정리
                if not active.finished:
                    raise LoginBusyError(active.session_id, active.backend_id)
            timeout = self.clamp_timeout(timeout_s)
            now, mono = self._clock(), self._mono()
            rec = _Session(
                session_id=self._new_id(),
                backend_id=backend_id,
                method_id=method,
                started_at=now,
                expires_at=now + timeout,
                started_mono=mono,
                deadline_mono=mono + timeout,
                timeout_s=timeout,
                last_seen=mono,
            )
            self._prune()
            self._sessions[rec.session_id] = rec
            self._active = rec
            _log.info(
                "백엔드 로그인 시작: session=%s backend=%s method=%s timeout_s=%s",
                rec.session_id,
                backend_id,
                method,
                timeout,
            )
            try:
                rec.driver = await backend.start_login(self._context(backend_id), method)
            except LoginRefusedError as exc:
                del self._sessions[rec.session_id]
                self._active = None
                _log.info(
                    "백엔드 로그인 거절: session=%s backend=%s code=%s",
                    rec.session_id,
                    backend_id,
                    exc.code,
                )
                raise
            except Exception as exc:  # 문장 원문(비밀이 섞일 수 있음)은 버리고 형식 이름만
                return self._finish(
                    rec,
                    LoginProgress(
                        phase="failed",
                        message=self._texts.start_failed,
                        reason=LoginReasons.START_FAILED,
                        details={"error": type(exc).__name__},
                    ),
                )
            rec.watch = asyncio.ensure_future(self._watch(rec))
            return self._view(rec)

    async def _watch(self, rec: _Session) -> None:
        driver = rec.driver
        assert driver is not None
        while not rec.finished:
            try:
                await driver.wait_changed(self._tick)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self._stop(
                    rec,
                    "failed",
                    self._texts.error,
                    LoginReasons.ERROR,
                    details={"error": type(exc).__name__},
                )
                return
            view = self._view(rec)  # 이미 끝났으면 끝난 세션(끝 단계)을 돌려준다
            if view.phase in TERMINAL_PHASES:
                return
            now = self._mono()
            if now >= rec.deadline_mono:
                await self._stop(
                    rec,
                    "expired",
                    self._texts.expired.format(minutes=rec.timeout_s / 60),
                    LoginReasons.TIMEOUT,
                    details={"timeout_s": rec.timeout_s},
                )
                return
            if now - rec.last_seen >= self._heartbeat:
                await self._stop(rec, "cancelled", self._texts.heartbeat, LoginReasons.HEARTBEAT)
                return

    async def _stop(
        self,
        rec: _Session,
        phase: str,
        message: str,
        reason: str | None,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> BackendLoginSession:
        """드라이버를 멈추고 서비스 단계로 끝낸다(화면 줄은 마지막 상태에서 가져온다)."""
        if rec.final is not None:
            return rec.final
        last = LoginProgress(phase=phase)
        driver = rec.driver
        if driver is not None:
            with contextlib.suppress(Exception):
                last = driver.progress()
            if last.phase == "succeeded":  # 멈추기 전에 이미 성공했다
                return self._finish(rec, last)
            try:
                await asyncio.wait_for(driver.cancel(), DEFAULT_DRIVER_CANCEL_TIMEOUT_S)
            except Exception as exc:
                _log.warning(
                    "백엔드 로그인 드라이버 취소 실패: session=%s error=%s",
                    rec.session_id,
                    type(exc).__name__,
                )
        return self._finish(
            rec,
            LoginProgress(
                phase=phase,
                message=message,
                open_url=None,
                screen=last.screen,
                warnings=last.warnings,
                reason=reason,
                details=dict(details or {}),
            ),
        )

    def current(self) -> BackendLoginSession | None:
        """진행 중인 세션(없으면 None). 하트비트로 친다."""
        active = self._active
        if active is None or active.finished:
            return None
        active.last_seen = self._mono()
        return self._view(active)

    def get(self, session_id: str) -> BackendLoginSession:
        """세션 하나(폴링). 하트비트로 친다.

        Raises:
            LoginSessionNotFoundError: 없거나 보관 시간이 지났다.
        """
        rec = self._find(session_id)
        rec.last_seen = self._mono()
        return self._view(rec)

    async def send_input(
        self, session_id: str, *, text: str | None = None, key: str | None = None
    ) -> None:
        """글자 또는 키 하나를 보낸다. 값은 세션 가림 목록에 들어가고 로그·오류에 남지 않는다.

        Raises:
            LoginSessionNotFoundError: 세션이 없다.
            LoginInputError: 끝난 세션, 받지 않는 키, 빈 글자·인쇄할 수 없는 글자.
        """
        rec = self._find(session_id)
        rec.last_seen = self._mono()
        view = self._view(rec)
        if rec.finished or rec.driver is None:
            raise LoginInputError(LoginInputError.SESSION_FINISHED)
        if (text is None) == (key is None):
            raise LoginInputError(LoginInputError.TEXT_INVALID)
        if key is not None:
            if key not in view.accepts_keys:
                raise LoginInputError(LoginInputError.KEY_NOT_ACCEPTED)
            await rec.driver.send_key(key)
            return
        assert text is not None
        value = text.strip()
        if not value or not value.isprintable():
            raise LoginInputError(LoginInputError.TEXT_INVALID)
        rec.secrets.append(value)
        try:
            await rec.driver.send_text(value)
        except Exception as exc:  # 예외 문장에 값이 섞일 수 있다 → 형식 이름만
            _log.warning(
                "백엔드 로그인 입력 실패: session=%s error=%s", rec.session_id, type(exc).__name__
            )
            raise LoginInputError(LoginInputError.SESSION_FINISHED) from None

    async def cancel(self, session_id: str) -> BackendLoginSession:
        """세션을 취소한다(끝난 세션은 그대로 돌려준다).

        Raises:
            LoginSessionNotFoundError: 세션이 없다.
        """
        rec = self._find(session_id)
        rec.last_seen = self._mono()
        if rec.finished:
            assert rec.final is not None
            return rec.final
        return await self._stop(rec, "cancelled", self._texts.cancelled, None)

    async def aclose(self) -> None:
        """진행 중인 세션을 취소하고 감시를 멈춘다(서버 종료 훅). 여러 번 불러도 된다."""
        self._closed = True
        active = self._active
        if active is not None and not active.finished:
            await self._stop(active, "cancelled", self._texts.shutdown, LoginReasons.SHUTDOWN)
        for rec in list(self._sessions.values()):
            task = rec.watch
            if task is not None and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task

    # ------------------------------------------------------------ 로그아웃

    def logout_supported(self, backend_id: str) -> bool:
        """로그아웃 지원 여부.

        Raises:
            UnknownBackendError: 등록되지 않은 id.
        """
        return supports_logout(self._get_backend(backend_id))

    async def logout(self, backend_id: str, method_id: str | None = None) -> BackendLogoutResult:
        """이 PC의 로그인을 지운다(확인은 화면 몫).

        Raises:
            UnknownBackendError: 등록되지 않은 id.
            LogoutUnsupportedError: 능력이 없다.
            LoginBusyError: 같은 백엔드의 로그인 세션이 진행 중.
        """
        backend = self._get_backend(backend_id)
        if not supports_logout(backend):
            raise LogoutUnsupportedError(backend_id)
        assert isinstance(backend, LogoutCapableBackend)
        active = self._active
        if active is not None and not active.finished:
            self._view(active)
            if not active.finished and active.backend_id == backend_id:
                raise LoginBusyError(active.session_id, active.backend_id)
        started = self._mono()
        try:
            result = await asyncio.wait_for(
                backend.logout(self._context(backend_id), method_id), self._logout_timeout
            )
        except TimeoutError:
            result = BackendLogoutResult(
                backend_id=backend_id,
                ok=False,
                reason=LoginReasons.TIMEOUT,
                message=self._texts.logout_timeout.format(seconds=self._logout_timeout),
                finished_at=self._clock(),
            )
        except Exception as exc:
            result = BackendLogoutResult(
                backend_id=backend_id,
                ok=False,
                reason=LoginReasons.ERROR,
                message=self._texts.logout_error,
                finished_at=self._clock(),
            )
            _log.warning(
                "백엔드 로그아웃 실패: backend=%s error=%s", backend_id, type(exc).__name__
            )
        try:
            dumped = result.model_copy(update={"backend_id": backend_id}).model_dump(mode="json")
            result = BackendLogoutResult.model_validate(
                {**self._redact(dumped), "backend_id": backend_id}
            )
        except ValidationError:
            result = BackendLogoutResult(
                backend_id=backend_id,
                ok=False,
                reason=LoginReasons.ERROR,
                message=self._texts.logout_error,
                finished_at=self._clock(),
            )
        _log.info(
            "백엔드 로그아웃: backend=%s ok=%s reason=%s elapsed_ms=%s",
            backend_id,
            result.ok,
            result.reason,
            max(0, round((self._mono() - started) * 1000)),
        )
        return result


_ALL_PHASES: Final = frozenset(
    {"starting", "waiting_user", "verifying", "succeeded", "failed", "cancelled", "expired"}
)


__all__ = [
    "DEFAULT_ACCEPTS_KEYS",
    "DEFAULT_LOGIN_HEARTBEAT_S",
    "DEFAULT_LOGIN_RETAIN_S",
    "DEFAULT_LOGIN_SCREEN_MAX_LINES",
    "DEFAULT_LOGIN_TIMEOUT_MAX_S",
    "DEFAULT_LOGIN_TIMEOUT_S",
    "DEFAULT_LOGOUT_TIMEOUT_S",
    "MASK_MIN_PART",
    "TERMINAL_PHASES",
    "BackendLoginContext",
    "BackendLoginService",
    "LoginBusyError",
    "LoginCapableBackend",
    "LoginDriver",
    "LoginInputError",
    "LoginProgress",
    "LoginReasons",
    "LoginRefusedError",
    "LoginSessionNotFoundError",
    "LoginTexts",
    "LoginUnsupportedError",
    "LogoutCapableBackend",
    "LogoutUnsupportedError",
    "mask_values",
    "supports_login",
    "supports_logout",
]
