"""실행 백엔드 모델 목록 — 계정 조회 선택 능력(X54)과 합치기·캐시 서비스(design §1.1-MB).

백엔드는 선택 메서드 ``discover_models(ctx, timeout_s)``를 구현하고 디스크립터
``capabilities.model_discovery = true``로 알린다. 조회는 **모델을 부르지 않는다**(토큰 비용 없음).
``list_models()``의 뜻은 그대로 "설치자 설정 목록"이다.

- ``merge_models``: 설정 목록 + 조회 목록 → 한 목록(순수 함수, MD-3).
- ``BackendModelCatalogService``: 백엔드별 메모리 캐시(성공 ``ttl_s``, 실패 ``failure_ttl_s``),
  같은 백엔드 동시 조회 합치기, ``refresh``·``invalidate``, 직전 성공 목록 ``stale``,
  실패 → 경고 이슈 ``backend.model_discovery_failed``(오류 응답이 아니다), 길이 자르기,
  비밀 가림(주입 ``redact``), 로그 규칙(백엔드 id·state·reason·개수·소요 시간만).

이 모듈은 백엔드 id·모델 id·사유 이름을 모른다(사유는 백엔드가 정하는 열린 어휘).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from pydantic import ValidationError

from agent_console_contracts import (
    BackendDescriptor,
    BackendModelCatalog,
    Issue,
    KnownIssueCodes,
    ModelDiscoveryInfo,
    ModelInfo,
)

from ._interfaces import ExecutionBackend
from ._readiness import BackendCheckContext, UnknownBackendError

_log = logging.getLogger("agent_console_runtime.models")

DEFAULT_MODEL_TTL_S = 3600.0
"""성공한 조회를 다시 부르지 않고 쓰는 시간(초). 앱 설정으로 바꾼다."""

DEFAULT_MODEL_FAILURE_TTL_S = 60.0
"""실패한 조회를 다시 부르지 않는 시간(초)."""

DEFAULT_MODEL_DISCOVERY_TIMEOUT_S = 20.0
"""조회 한 번의 시간 상한(초)."""

SOURCE_CONFIG = "config"
"""``ModelInfo.sources`` 값: 설치자 설정 목록."""

SOURCE_DISCOVERED = "discovered"
"""``ModelInfo.sources`` 값: 백엔드 계정 조회."""


class ModelDiscoveryReasons:
    """조회 실패 사유(``ModelDiscoveryResult.reason``, 열린 어휘의 알려진 값).

    서비스가 직접 쓰는 값은 ``TIMEOUT``·``ERROR``·``INVALID_RESPONSE``다. 나머지는 백엔드가
    같은 뜻에 같은 이름을 쓰도록 둔 문서 상수다. 다른 값도 그대로 유효하다.
    """

    AUTH_MISSING = "auth_missing"
    """키·토큰·로그인이 없어 조회하지 않았다."""
    AUTH_FAILED = "auth_failed"
    """인증이 거부됐다."""
    SUBSCRIPTION_DISABLED = "subscription_disabled"
    """구독 방식이 설치자 설정으로 꺼져 있다."""
    NETWORK = "network"
    """연결하지 못했다."""
    TIMEOUT = "timeout"
    """시간 상한 안에 끝나지 않았다(서비스가 판단)."""
    INVALID_RESPONSE = "invalid_response"
    """응답 모양이 예상과 다르다."""
    CLI_MISSING = "cli_missing"
    """백엔드가 쓰는 실행 파일이 없다."""
    CLI_NO_MODELS = "cli_no_models"
    """실행 파일 응답에 모델 목록이 없다(``unsupported``로 알리는 것이 보통이다)."""
    ERROR = "error"
    """그 밖의 실패(백엔드 예외 등, ``details.error`` = 예외 형식 이름)."""


@dataclass(frozen=True)
class ModelDiscoveryResult:
    """Result of ``discover_models``: the models found, or a failure reason.

    Attributes:
        ok: 조회 성공.
        models: 계정이 쓸 수 있는 모델(백엔드가 준 순서). ``ModelInfo`` 또는 같은 모양의 사전.
        method: 쓴 방법(열린 어휘, 예: ``sdk_init``·``models_api``). 로그·``details``에만 쓴다.
        reason: 실패 사유(``ModelDiscoveryReasons``, 열린 문자열). 성공이면 None.
        unsupported: 참이면 이 인증·환경에서는 조회할 수 없다(실패가 아니다 → 상태
            ``unsupported``, 이슈 없음). ``ok``는 거짓으로 둔다.
        details: 확인 정보(예: ``skipped`` = 건너뛴 항목 수). 비밀 값을 넣지 않는다.
    """

    ok: bool
    models: Sequence[ModelInfo | Mapping[str, Any]] = field(default_factory=list)
    method: str | None = None
    reason: str | None = None
    unsupported: bool = False
    details: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class ModelDiscoveryCapableBackend(Protocol):
    """Optional capability: a backend that lists its account's models without a model call.

    선택 능력 X54: 계정 모델 조회(``capabilities.model_discovery=true``와 함께).
    """

    descriptor: BackendDescriptor

    async def discover_models(
        self, ctx: BackendCheckContext, timeout_s: float
    ) -> ModelDiscoveryResult:
        """모델 호출 없이 계정이 쓸 수 있는 모델을 묻는다.

        실패는 예외보다 ``ok=False`` + ``reason``으로 돌려준다. 서비스가 ``timeout_s``로 끊는다.
        """
        ...


def supports_model_discovery(backend: object) -> bool:
    """디스크립터가 ``model_discovery`` 능력을 선언하고 메서드도 있으면 참."""
    descriptor = getattr(backend, "descriptor", None)
    caps = getattr(descriptor, "capabilities", None)
    declared = bool(getattr(caps, "model_discovery", False))
    return declared and isinstance(backend, ModelDiscoveryCapableBackend)


def _filled(value: str | None) -> bool:
    return value is not None and value != ""


def merge_models(
    configured: Sequence[ModelInfo], discovered: Sequence[ModelInfo]
) -> list[ModelInfo]:
    """Merge the configured list and the discovered list into one list (pure function).

    입력을 바꾸지 않는다(design MD-3).

    - 설정 목록이 앞, 그 순서대로. 조회에만 있는 모델은 뒤에 조회 순서대로.
    - 같은 ``id``(문자열 완전 일치)는 한 항목이다. ``title``·``description``·``context_window``는
      설정 값이 비어 있지 않으면 설정이 이기고, ``attributes``는 키 단위로 설정이 이긴다.
    - ``sources``에 ``config``·``discovered`` 중 해당하는 것을 적는다. 같은 목록 안의 중복
      id는 처음 것만 쓴다. 별칭과 전체 id를 같은 것으로 보지 않는다.

    >>> merged = merge_models(
    ...     [ModelInfo(id="m-b", title="Mine")],
    ...     [ModelInfo(id="m-a"), ModelInfo(id="m-b", title="Theirs", context_window=9)],
    ... )
    >>> [(m.id, m.title, m.context_window, m.sources) for m in merged]
    [('m-b', 'Mine', 9, ['config', 'discovered']), ('m-a', None, None, ['discovered'])]
    """
    out: list[ModelInfo] = []
    index: dict[str, int] = {}
    for item in configured:
        if item.id in index:
            continue
        index[item.id] = len(out)
        out.append(item.model_copy(update={"sources": [SOURCE_CONFIG]}, deep=True))
    seen: set[str] = set()
    for item in discovered:
        if item.id in seen:
            continue
        seen.add(item.id)
        at = index.get(item.id)
        if at is None:
            index[item.id] = len(out)
            out.append(item.model_copy(update={"sources": [SOURCE_DISCOVERED]}, deep=True))
            continue
        mine = out[at]
        out[at] = mine.model_copy(
            update={
                "title": mine.title if _filled(mine.title) else item.title,
                "description": mine.description if _filled(mine.description) else item.description,
                "context_window": (
                    mine.context_window if mine.context_window is not None else item.context_window
                ),
                "attributes": {**item.attributes, **mine.attributes},
                "sources": [SOURCE_CONFIG, SOURCE_DISCOVERED],
            },
            deep=True,
        )
    return out


@dataclass(frozen=True)
class ModelListLimits:
    """조회한 모델 목록의 길이 상한(바깥 데이터라 자른다, MD-9). 앱이 바꿔 넣는다.

    Attributes:
        id_chars: id 최대 글자 수. 넘는 항목은 자르지 않고 뺀다(잘린 id는 다른 모델이 된다).
        title_chars: 이름 최대 글자 수(넘으면 자른다).
        description_chars: 설명 최대 글자 수(넘으면 자른다).
        max_items: 항목 수 상한(넘는 뒤 항목은 뺀다).
    """

    id_chars: int = 200
    title_chars: int = 200
    description_chars: int = 1000
    max_items: int = 500


@dataclass(frozen=True)
class ModelCatalogTexts:
    """서비스가 만드는 문구(데이터, 서버 원문). 화면은 이슈 코드로 번역한다.

    ``{backend_id}`` = 백엔드 id, ``{reason}`` = 사유 코드.
    """

    discovery_failed: str = (
        "실행 백엔드 '{backend_id}'의 모델 목록을 가져오지 못했습니다({reason}). "
        "설정한 목록과 직접 입력은 그대로 쓸 수 있습니다"
    )


def _identity(value: Any) -> Any:
    return value


@dataclass
class _Outcome:
    """조회 한 번의 정리된 결과(가림·자르기 끝)."""

    ok: bool
    unsupported: bool
    models: list[ModelInfo]
    reason: str | None
    fetched_at: float


@dataclass
class _Entry:
    """백엔드 하나의 캐시."""

    last_ok: list[ModelInfo] | None = None
    last_ok_at: float | None = None
    ok_until: float = 0.0
    """성공 목록을 다시 부르지 않고 쓰는 마지막 시각(monotonic)."""
    failure: _Outcome | None = None
    failure_until: float = 0.0
    """실패·unsupported를 다시 부르지 않는 마지막 시각(monotonic)."""


class BackendModelCatalogService:
    """Backend model lists (configured list plus account lookup) with caching and failure handling.

    서버·CLI·테스트에서 같은 로직이다. 첫 조회는 목록을 처음 요청할 때 한다(시작 때 부르지
    않는다). 캐시는 프로세스 안 메모리이고 저장하지 않는다. 조회 실패는 오류가 아니라
    ``state = failed`` + 경고 이슈다.

    Args:
        backends: 지금 등록된 ``id → 백엔드``를 돌려주는 함수(호출마다 다시 읽는다).
        enabled: 거짓이면 조회하지 않는다(상태 ``disabled``, 설정 목록만).
        disabled_backends: 조회하지 않을 백엔드 id.
        ttl_s: 성공한 조회를 다시 부르지 않는 시간(초).
        failure_ttl_s: 실패한 조회를 다시 부르지 않는 시간(초).
        timeout_s: 조회 한 번의 시간 상한(초).
        limits: 조회 목록 길이 상한.
        redact: JSON 값(dict)의 비밀을 가리는 함수. 조회 항목·이슈 문구에 건다.
        has_secret: 비밀 이름 존재 확인(``BackendCheckContext.has_secret``).
        clock: 현재 시각(epoch 초, ``fetched_at``·``expires_at``).
        monotonic: 캐시 시간 계산·소요 시간 측정용 시계(초).
        texts: 서비스가 만드는 문구.

    Raises:
        ValueError: 시간 값이 0 이하(``ttl_s``·``failure_ttl_s``는 0 허용 = 캐시 안 함).
    """

    def __init__(
        self,
        backends: Callable[[], Mapping[str, ExecutionBackend]],
        *,
        enabled: bool = True,
        disabled_backends: Collection[str] = (),
        ttl_s: float = DEFAULT_MODEL_TTL_S,
        failure_ttl_s: float = DEFAULT_MODEL_FAILURE_TTL_S,
        timeout_s: float = DEFAULT_MODEL_DISCOVERY_TIMEOUT_S,
        limits: ModelListLimits | None = None,
        redact: Callable[[Any], Any] = _identity,
        has_secret: Callable[[str], bool] = lambda _name: False,
        clock: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
        texts: ModelCatalogTexts | None = None,
    ) -> None:
        if timeout_s <= 0 or ttl_s < 0 or failure_ttl_s < 0:
            raise ValueError("timeout_s must be > 0 and ttl_s, failure_ttl_s must be >= 0")
        self._backends = backends
        self._enabled = enabled
        self._disabled = frozenset(disabled_backends)
        self._ttl = ttl_s
        self._failure_ttl = failure_ttl_s
        self._timeout = timeout_s
        self._limits = limits or ModelListLimits()
        self._redact = redact
        self._has_secret = has_secret
        self._clock = clock
        self._mono = monotonic
        self._texts = texts or ModelCatalogTexts()
        self._cache: dict[str, _Entry] = {}
        self._generation: dict[str, int] = {}
        self._inflight: dict[str, asyncio.Future[_Outcome]] = {}

    # ------------------------------------------------------------ 공개

    def discovery_enabled(self, backend_id: str) -> bool:
        """설치자 설정상 이 백엔드를 조회하는지(능력과 무관)."""
        return self._enabled and backend_id not in self._disabled

    async def catalog(self, backend_id: str, *, refresh: bool = False) -> BackendModelCatalog:
        """백엔드 하나의 합친 목록과 조회 상태.

        Args:
            backend_id: 백엔드 id.
            refresh: 참이면 캐시를 건너뛰고 다시 조회한다(진행 중인 조회가 있으면 그 결과를
                함께 받는다).

        Raises:
            UnknownBackendError: 등록되지 않은 id.
        """
        backend = self._backends().get(backend_id)
        if backend is None:
            raise UnknownBackendError(backend_id)
        configured = list(await backend.list_models())
        if not self.discovery_enabled(backend_id):
            return self._result(backend_id, configured, [], ModelDiscoveryInfo(state="disabled"))
        if not supports_model_discovery(backend):
            return self._result(backend_id, configured, [], ModelDiscoveryInfo(state="unsupported"))
        assert isinstance(backend, ModelDiscoveryCapableBackend)
        entry = self._cache.setdefault(backend_id, _Entry())
        now = self._mono()
        if not refresh:
            if entry.last_ok is not None and now < entry.ok_until:
                return self._from_ok(backend_id, configured, entry)
            if entry.failure is not None and now < entry.failure_until:
                return self._from_failure(backend_id, configured, entry, entry.failure)
            if entry.last_ok is not None and self._ttl > 0:
                # 낡은 목록: 다시 조회를 시작하고 기다리지 않는다(진행 중 = stale).
                # ttl_s = 0(요청마다 묻기)이면 기다려 새 결과를 준다.
                self._start(backend_id, backend)
                return self._stale(backend_id, configured, entry, None)
        outcome = await asyncio.shield(self._start(backend_id, backend))
        entry = self._cache.setdefault(backend_id, _Entry())
        if outcome.ok:
            return self._result(
                backend_id,
                configured,
                outcome.models,
                ModelDiscoveryInfo(
                    state="ok",
                    fetched_at=outcome.fetched_at,
                    expires_at=outcome.fetched_at + self._ttl,
                ),
            )
        return self._from_failure(backend_id, configured, entry, outcome)

    async def models(self, backend_id: str) -> list[ModelInfo]:
        """``catalog(backend_id).models``(``GET /backends/{id}/models``가 쓴다).

        Raises:
            UnknownBackendError: 등록되지 않은 id.
        """
        return (await self.catalog(backend_id)).models

    def invalidate(self, backend_id: str | None = None) -> None:
        """캐시를 비운다(None = 전부). 진행 중인 조회 결과는 캐시에 남지 않는다.

        같은 프로세스에서 로그인·로그아웃이 끝났을 때 앱이 부른다.
        """
        targets = list(self._cache) + list(self._inflight) if backend_id is None else [backend_id]
        for key in set(targets):
            self._cache.pop(key, None)
            self._inflight.pop(key, None)
            self._generation[key] = self._generation.get(key, 0) + 1

    async def aclose(self) -> None:
        """진행 중인 조회를 멈춘다(서버 종료 때)."""
        running = list(self._inflight.values())
        self._inflight.clear()
        for fut in running:
            fut.cancel()
        for fut in running:
            with contextlib.suppress(BaseException):
                await fut

    # ------------------------------------------------------------ 응답 만들기

    def _result(
        self,
        backend_id: str,
        configured: Sequence[ModelInfo],
        discovered: Sequence[ModelInfo],
        info: ModelDiscoveryInfo,
    ) -> BackendModelCatalog:
        return BackendModelCatalog(
            backend_id=backend_id, models=merge_models(configured, discovered), discovery=info
        )

    def _epoch(self, mono_deadline: float) -> float:
        return self._clock() + max(0.0, mono_deadline - self._mono())

    def _from_ok(
        self, backend_id: str, configured: Sequence[ModelInfo], entry: _Entry
    ) -> BackendModelCatalog:
        return self._result(
            backend_id,
            configured,
            entry.last_ok or [],
            ModelDiscoveryInfo(
                state="ok", fetched_at=entry.last_ok_at, expires_at=self._epoch(entry.ok_until)
            ),
        )

    def _stale(
        self,
        backend_id: str,
        configured: Sequence[ModelInfo],
        entry: _Entry,
        failure: _Outcome | None,
    ) -> BackendModelCatalog:
        issues = [self._issue(backend_id, failure.reason)] if failure is not None else []
        expires = self._epoch(entry.failure_until) if failure is not None else None
        if expires is None and entry.last_ok_at is not None:
            expires = entry.last_ok_at + self._ttl
        return self._result(
            backend_id,
            configured,
            entry.last_ok or [],
            ModelDiscoveryInfo(
                state="stale", fetched_at=entry.last_ok_at, expires_at=expires, issues=issues
            ),
        )

    def _from_failure(
        self,
        backend_id: str,
        configured: Sequence[ModelInfo],
        entry: _Entry,
        failure: _Outcome,
    ) -> BackendModelCatalog:
        if failure.unsupported:
            return self._result(
                backend_id,
                configured,
                [],
                ModelDiscoveryInfo(
                    state="unsupported", expires_at=self._epoch(entry.failure_until)
                ),
            )
        if entry.last_ok is not None:
            return self._stale(backend_id, configured, entry, failure)
        return self._result(
            backend_id,
            configured,
            [],
            ModelDiscoveryInfo(
                state="failed",
                expires_at=self._epoch(entry.failure_until),
                issues=[self._issue(backend_id, failure.reason)],
            ),
        )

    def _issue(self, backend_id: str, reason: str | None) -> Issue:
        code = reason or ModelDiscoveryReasons.ERROR
        message = self._texts.discovery_failed.format(backend_id=backend_id, reason=code)
        raw = Issue(
            severity="warning",
            code=KnownIssueCodes.BACKEND_MODEL_DISCOVERY_FAILED,
            message=message,
            details={"backend_id": backend_id, "reason": code},
        )
        try:
            return Issue.model_validate(self._redact(raw.model_dump(mode="json")))
        except ValidationError:
            return raw.model_copy(update={"message": ""})

    # ------------------------------------------------------------ 조회

    def _start(
        self, backend_id: str, backend: ModelDiscoveryCapableBackend
    ) -> asyncio.Future[_Outcome]:
        running = self._inflight.get(backend_id)
        if running is not None:
            return running
        generation = self._generation.get(backend_id, 0)
        fut = asyncio.ensure_future(self._fetch(backend_id, backend, generation))
        self._inflight[backend_id] = fut

        def _done(done: asyncio.Future[_Outcome], key: str = backend_id) -> None:
            if self._inflight.get(key) is done:
                del self._inflight[key]

        fut.add_done_callback(_done)
        return fut

    async def _fetch(
        self, backend_id: str, backend: ModelDiscoveryCapableBackend, generation: int
    ) -> _Outcome:
        started = self._mono()
        ctx = BackendCheckContext(backend_id, clock=self._clock, has_secret=self._has_secret)
        method: str | None = None
        try:
            # 플러그인이 형식을 어길 수 있어 결과를 object로 받아 확인한다
            result: object = await asyncio.wait_for(
                backend.discover_models(ctx, self._timeout), self._timeout
            )
        except TimeoutError:
            outcome = _Outcome(False, False, [], ModelDiscoveryReasons.TIMEOUT, self._clock())
        except Exception as exc:  # 문장 원문(비밀이 섞일 수 있음)은 버리고 형식 이름만 로그에
            _log.warning(
                "Backend model discovery raised: backend=%s error=%s",
                backend_id,
                type(exc).__name__,
            )
            outcome = _Outcome(False, False, [], ModelDiscoveryReasons.ERROR, self._clock())
        else:
            if isinstance(result, ModelDiscoveryResult):
                method = result.method
                outcome = self._clean(result)
            else:
                outcome = _Outcome(
                    False, False, [], ModelDiscoveryReasons.INVALID_RESPONSE, self._clock()
                )
        elapsed_ms = max(0, round((self._mono() - started) * 1000))
        if self._generation.get(backend_id, 0) == generation:
            self._store(backend_id, outcome)
        state = "ok" if outcome.ok else "unsupported" if outcome.unsupported else "failed"
        _log.info(
            "Backend model discovery: backend=%s state=%s reason=%s method=%s count=%d "
            "elapsed_ms=%d",
            backend_id,
            state,
            outcome.reason,
            method,
            len(outcome.models),
            elapsed_ms,
        )
        return outcome

    def _store(self, backend_id: str, outcome: _Outcome) -> None:
        entry = self._cache.setdefault(backend_id, _Entry())
        now = self._mono()
        if outcome.ok:
            entry.last_ok = list(outcome.models)
            entry.last_ok_at = outcome.fetched_at
            entry.ok_until = now + self._ttl
            entry.failure = None
            entry.failure_until = 0.0
        else:
            entry.ok_until = 0.0  # 직전 성공 목록은 이제 낡은 것(stale)으로만 준다
            if outcome.unsupported:  # 능력 없음은 직전 성공 목록을 남기지 않는다
                entry.last_ok = None
                entry.last_ok_at = None
            entry.failure = outcome
            entry.failure_until = now + self._failure_ttl

    def _clean(self, result: ModelDiscoveryResult) -> _Outcome:
        """백엔드 결과 → 가린·자른 결과."""
        fetched = self._clock()
        if not result.ok:
            reason = result.reason or (None if result.unsupported else ModelDiscoveryReasons.ERROR)
            return _Outcome(False, result.unsupported, [], reason, fetched)
        return _Outcome(True, False, self._trim(result.models), None, fetched)

    def _trim(self, items: Iterable[ModelInfo | Mapping[str, Any]]) -> list[ModelInfo]:
        limits = self._limits
        out: list[ModelInfo] = []
        for raw in items:
            if len(out) >= limits.max_items:
                break
            try:
                dumped = (
                    raw.model_dump(mode="json")
                    if isinstance(raw, ModelInfo)
                    else ModelInfo.model_validate(raw).model_dump(mode="json")
                )
                model = ModelInfo.model_validate(self._redact(dumped))
            except (ValidationError, TypeError, ValueError):
                continue
            if len(model.id) > limits.id_chars:
                continue
            update: dict[str, Any] = {"sources": []}
            if model.title is not None and len(model.title) > limits.title_chars:
                update["title"] = model.title[: limits.title_chars]
            if model.description is not None and len(model.description) > limits.description_chars:
                update["description"] = model.description[: limits.description_chars]
            out.append(model.model_copy(update=update))
        return out


__all__ = [
    "DEFAULT_MODEL_DISCOVERY_TIMEOUT_S",
    "DEFAULT_MODEL_FAILURE_TTL_S",
    "DEFAULT_MODEL_TTL_S",
    "SOURCE_CONFIG",
    "SOURCE_DISCOVERED",
    "BackendModelCatalogService",
    "ModelCatalogTexts",
    "ModelDiscoveryCapableBackend",
    "ModelDiscoveryReasons",
    "ModelDiscoveryResult",
    "ModelListLimits",
    "merge_models",
    "supports_model_discovery",
]
