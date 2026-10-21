"""실행 백엔드 준비 상태(정적 점검)·연결 테스트(probe) — 선택 능력과 조회 서비스(ux-overhaul §15.8).

백엔드는 두 선택 메서드를 구현하고 디스크립터 ``capabilities.status``·``capabilities.probe``로
알린다. 이 모듈은 백엔드 id·상태 이름을 모른다. 능력이 없으면 상태는 ``unknown``, 연결 테스트는
``ProbeUnsupportedError``다.

- ``status(ctx)``: 모델·네트워크 호출 금지(환경·설정·파일 존재 확인만). 빨리 끝나야 한다.
- ``probe(ctx, timeout_s)``: 가능한 가장 짧고 싼 실제 호출 한 번.

``BackendReadinessService``가 둘을 감싼다: 시간 상한, 같은 백엔드 동시 probe 합치기, 응답 글자의
비밀 가림(주입 ``redact``), 서버 로그 규칙(백엔드 id·ok·reason·소요 시간만, 문장 원문 없음).
probe 결과는 기억하지 않고 실행 기록·이벤트에도 남기지 않는다.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel, ValidationError

from agent_console_contracts import BackendDescriptor, BackendProbeResult, BackendReadiness

from ._interfaces import ExecutionBackend

_log = logging.getLogger("agent_console_runtime.readiness")

DEFAULT_PROBE_TIMEOUT_MAX_S = 20.0
"""연결 테스트 기본 시간 상한(초). 앱 설정으로 바꾼다."""

DEFAULT_STATUS_TIMEOUT_S = 2.0
"""정적 점검 시간 상한(초). 넘으면 ``unknown``(점검은 빨라야 한다)."""

UNKNOWN_STATE = "unknown"
"""점검을 지원하지 않거나 점검이 실패했을 때의 상태 이름."""


class ProbeReasons:
    """서비스가 직접 만드는 연결 테스트 실패 사유(열린 어휘의 일부)."""

    TIMEOUT = "timeout"
    """시간 상한 안에 끝나지 않았다."""
    ERROR = "error"
    """백엔드 ``probe``가 예외를 냈다(``details.error`` = 예외 형식 이름)."""


@dataclass(frozen=True)
class ReadinessTexts:
    """서비스가 만드는 기본 문구(데이터). 앱이 바꿔 넣을 수 있다."""

    unknown_summary: str = "확인할 수 없음"
    unknown_short: str = "확인 불가"
    unsupported_detail: str = "이 백엔드는 상태 점검을 지원하지 않습니다."
    failed_detail: str = "상태 점검이 실패했거나 시간 안에 끝나지 않았습니다."
    probe_timeout: str = "{seconds:g}초 안에 응답이 없었습니다."
    probe_error: str = "연결 테스트 중 오류가 났습니다."


@dataclass(frozen=True)
class BackendCheckContext:
    """``status``·``probe``에 넘기는 환경(주입).

    Attributes:
        backend_id: 등록된 백엔드 id(같은 구현을 여러 이름으로 등록할 수 있다).
        clock: 현재 시각(epoch 초). ``checked_at``·``finished_at``에 쓴다.
        has_secret: 비밀 이름이 공급자에 있는지만 묻는다(값을 돌려주지 않는다).
    """

    backend_id: str
    clock: Callable[[], float] = time.time
    has_secret: Callable[[str], bool] = field(default=lambda _name: False)


@runtime_checkable
class StatusCapableBackend(Protocol):
    """선택 능력: 정적 점검(``capabilities.status=true``와 함께)."""

    descriptor: BackendDescriptor

    async def status(self, ctx: BackendCheckContext) -> BackendReadiness:
        """모델·네트워크를 부르지 않고 지금 쓸 수 있는지 점검한다. 비밀 값을 담지 않는다."""
        ...


@runtime_checkable
class ProbeCapableBackend(Protocol):
    """선택 능력: 연결 테스트(``capabilities.probe=true``와 함께)."""

    descriptor: BackendDescriptor

    async def probe(self, ctx: BackendCheckContext, timeout_s: float) -> BackendProbeResult:
        """가장 짧은 실제 호출 한 번. 실패는 예외보다 ``ok=false`` + ``reason``으로 돌려준다."""
        ...


def supports_status(backend: object) -> bool:
    """디스크립터가 ``status`` 능력을 선언하고 메서드도 있으면 참."""
    return _declares(backend, "status") and isinstance(backend, StatusCapableBackend)


def supports_probe(backend: object) -> bool:
    """디스크립터가 ``probe`` 능력을 선언하고 메서드도 있으면 참."""
    return _declares(backend, "probe") and isinstance(backend, ProbeCapableBackend)


def _declares(backend: object, name: str) -> bool:
    descriptor = getattr(backend, "descriptor", None)
    caps = getattr(descriptor, "capabilities", None)
    return bool(getattr(caps, name, False))


class UnknownBackendError(LookupError):
    """등록되지 않은 백엔드 id."""

    def __init__(self, backend_id: str) -> None:
        super().__init__(f"백엔드 {backend_id}이(가) 없습니다")
        self.backend_id = backend_id


class ProbeUnsupportedError(Exception):
    """백엔드가 연결 테스트를 지원하지 않는다(``capabilities.probe=false`` 또는 메서드 없음)."""

    def __init__(self, backend_id: str) -> None:
        super().__init__(f"백엔드 {backend_id}은(는) 연결 테스트를 지원하지 않습니다")
        self.backend_id = backend_id


M = TypeVar("M", bound=BaseModel)


def _identity(value: Any) -> Any:
    return value


class BackendReadinessService:
    """백엔드 정적 점검·연결 테스트 조회(서버·CLI·테스트에서 같은 로직).

    Args:
        backends: 지금 등록된 ``id → 백엔드``를 돌려주는 함수(호출마다 다시 읽는다).
        redact: 응답 JSON 값(dict)의 비밀을 가리는 함수. 글자 필드 전부에 건다.
        has_secret: 비밀 이름 존재 확인(``BackendCheckContext.has_secret``).
        clock: 현재 시각(epoch 초).
        monotonic: 소요 시간 측정용 시계(초).
        probe_timeout_max_s: 연결 테스트 시간 상한. 요청 값은 이 값으로 잘린다.
        probe_timeout_default_s: 요청이 값을 주지 않았을 때. None이면 상한.
        status_timeout_s: 정적 점검 시간 상한.
        texts: 서비스가 만드는 문구.
    """

    def __init__(
        self,
        backends: Callable[[], Mapping[str, ExecutionBackend]],
        *,
        redact: Callable[[Any], Any] = _identity,
        has_secret: Callable[[str], bool] = lambda _name: False,
        clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
        probe_timeout_max_s: float = DEFAULT_PROBE_TIMEOUT_MAX_S,
        probe_timeout_default_s: float | None = None,
        status_timeout_s: float = DEFAULT_STATUS_TIMEOUT_S,
        texts: ReadinessTexts | None = None,
    ) -> None:
        if probe_timeout_max_s <= 0 or status_timeout_s <= 0:
            raise ValueError("시간 상한은 0보다 커야 합니다")
        self._backends = backends
        self._redact = redact
        self._has_secret = has_secret
        self._clock = clock
        self._monotonic = monotonic
        self._probe_max = probe_timeout_max_s
        self._probe_default = probe_timeout_default_s
        self._status_timeout = status_timeout_s
        self._texts = texts or ReadinessTexts()
        self._inflight: dict[str, asyncio.Future[BackendProbeResult]] = {}

    # ------------------------------------------------------------ 공용

    def _get(self, backend_id: str) -> ExecutionBackend:
        found = self._backends().get(backend_id)
        if found is None:
            raise UnknownBackendError(backend_id)
        return found

    def _context(self, backend_id: str) -> BackendCheckContext:
        return BackendCheckContext(backend_id, clock=self._clock, has_secret=self._has_secret)

    def _masked(self, model: M) -> M:
        """글자 필드에 비밀 가림을 건 사본.

        Raises:
            ValidationError: 가린 결과가 계약 형식에 맞지 않을 때(호출자가 대체 응답을 만든다).
        """
        dumped = model.model_dump(mode="json")
        return type(model).model_validate(self._redact(dumped))

    def clamp_timeout(self, requested: float | None) -> float:
        """요청한 시간(없으면 기본) → 상한으로 자른 값."""
        wanted = requested if requested is not None else self._probe_default
        if wanted is None or wanted <= 0:
            return self._probe_max
        return min(wanted, self._probe_max)

    # ------------------------------------------------------------ 정적 점검

    def _unknown(self, backend_id: str, detail: str) -> BackendReadiness:
        return BackendReadiness(
            backend_id=backend_id,
            state=UNKNOWN_STATE,
            tone="unknown",
            summary=self._texts.unknown_summary,
            short_summary=self._texts.unknown_short,
            detail=detail,
            checked_at=self._clock(),
        )

    async def status(self, backend_id: str) -> BackendReadiness:
        """한 백엔드의 정적 점검.

        능력이 없으면 ``unknown``(오류 아님). 점검이 예외를 내거나 시간을 넘기면 ``unknown``.

        Raises:
            UnknownBackendError: 등록되지 않은 id.
        """
        backend = self._get(backend_id)
        return await self._status_of(backend_id, backend)

    async def status_all(self) -> list[BackendReadiness]:
        """등록된 모든 백엔드의 정적 점검(등록 순)."""
        items = list(self._backends().items())
        return list(
            await asyncio.gather(*(self._status_of(bid, backend) for bid, backend in items))
        )

    async def _status_of(self, backend_id: str, backend: ExecutionBackend) -> BackendReadiness:
        if not supports_status(backend):
            return self._unknown(backend_id, self._texts.unsupported_detail)
        assert isinstance(backend, StatusCapableBackend)
        try:
            result = await asyncio.wait_for(
                backend.status(self._context(backend_id)), self._status_timeout
            )
        except TimeoutError:
            _log.warning("백엔드 상태 점검 시간 초과: backend=%s", backend_id)
            return self._unknown(backend_id, self._texts.failed_detail)
        except Exception as exc:  # 백엔드 오류는 상태 unknown으로(문장 원문은 남기지 않는다)
            _log.warning(
                "백엔드 상태 점검 실패: backend=%s error=%s", backend_id, type(exc).__name__
            )
            return self._unknown(backend_id, self._texts.failed_detail)
        try:
            return self._masked(result.model_copy(update={"backend_id": backend_id}))
        except ValidationError:
            _log.warning("백엔드 상태 점검 결과 형식 오류: backend=%s", backend_id)
            return self._unknown(backend_id, self._texts.failed_detail)

    # ------------------------------------------------------------ 연결 테스트

    def probe_supported(self, backend_id: str) -> bool:
        """연결 테스트 지원 여부.

        Raises:
            UnknownBackendError: 등록되지 않은 id.
        """
        return supports_probe(self._get(backend_id))

    async def probe(self, backend_id: str, timeout_s: float | None = None) -> BackendProbeResult:
        """연결 테스트 한 번. 같은 백엔드에 진행 중인 테스트가 있으면 그 결과를 같이 받는다.

        Args:
            backend_id: 백엔드 id.
            timeout_s: 기다릴 최대 초(None = 기본). 상한으로 잘린다. 합쳐진 요청은 먼저 시작한
                테스트의 시간을 따른다.

        Raises:
            UnknownBackendError: 등록되지 않은 id.
            ProbeUnsupportedError: 능력이 없다.
        """
        backend = self._get(backend_id)
        if not supports_probe(backend):
            raise ProbeUnsupportedError(backend_id)
        assert isinstance(backend, ProbeCapableBackend)
        running = self._inflight.get(backend_id)
        if running is None:
            running = asyncio.ensure_future(
                self._run_probe(backend_id, backend, self.clamp_timeout(timeout_s))
            )
            self._inflight[backend_id] = running

            def _done(fut: asyncio.Future[BackendProbeResult], key: str = backend_id) -> None:
                if self._inflight.get(key) is fut:
                    del self._inflight[key]

            running.add_done_callback(_done)
        # 요청 하나가 끊겨도(클라이언트 종료) 함께 기다리는 요청의 테스트는 계속된다
        return await asyncio.shield(running)

    async def _run_probe(
        self, backend_id: str, backend: ProbeCapableBackend, timeout_s: float
    ) -> BackendProbeResult:
        started = self._monotonic()
        try:
            result = await asyncio.wait_for(
                backend.probe(self._context(backend_id), timeout_s), timeout_s
            )
        except TimeoutError:
            result = BackendProbeResult(
                backend_id=backend_id,
                ok=False,
                reason=ProbeReasons.TIMEOUT,
                message=self._texts.probe_timeout.format(seconds=timeout_s),
                details={"timeout_s": timeout_s},
                finished_at=self._clock(),
            )
        except Exception as exc:  # 문장 원문(비밀이 섞일 수 있음)은 버리고 형식 이름만
            result = BackendProbeResult(
                backend_id=backend_id,
                ok=False,
                reason=ProbeReasons.ERROR,
                message=self._texts.probe_error,
                details={"error": type(exc).__name__},
                finished_at=self._clock(),
            )
        elapsed_ms = max(0, round((self._monotonic() - started) * 1000))
        update: dict[str, Any] = {"backend_id": backend_id}
        if result.latency_ms is None:
            update["latency_ms"] = elapsed_ms
        try:
            result = self._masked(result.model_copy(update=update))
        except ValidationError:  # 가리지 못한 결과는 내보내지 않는다
            result = BackendProbeResult(
                backend_id=backend_id,
                ok=False,
                reason=ProbeReasons.ERROR,
                message=self._texts.probe_error,
                details={"error": "invalid_result"},
                latency_ms=elapsed_ms,
                finished_at=self._clock(),
            )
        _log.info(
            "백엔드 연결 테스트: backend=%s ok=%s reason=%s latency_ms=%s",
            backend_id,
            result.ok,
            result.reason,
            result.latency_ms,
        )
        return result


__all__ = [
    "DEFAULT_PROBE_TIMEOUT_MAX_S",
    "DEFAULT_STATUS_TIMEOUT_S",
    "UNKNOWN_STATE",
    "BackendCheckContext",
    "BackendReadinessService",
    "ProbeCapableBackend",
    "ProbeReasons",
    "ProbeUnsupportedError",
    "ReadinessTexts",
    "StatusCapableBackend",
    "UnknownBackendError",
    "supports_probe",
    "supports_status",
]
