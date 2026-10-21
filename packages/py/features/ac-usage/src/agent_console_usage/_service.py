"""사용량 수집 서비스: 켜진 출처를 돌려 창 스냅샷을 모으고 관측값을 기록한다."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from agent_console_contracts import (
    ErrorCodes,
    ErrorInfo,
    Issue,
    IssueSeverity,
    JsonObject,
    TokenRollupRow,
    UsageReport,
    UsageSettings,
    UsageSourceDescriptor,
    UsageSourceInfo,
    UsageSourceSetting,
    UsageWindowSnapshot,
)
from agent_console_registry import Registry

from ._config_check import SOURCE_SCHEMA_INVALID, config_error, source_config_issues
from ._interfaces import UsageEventQuery, UsageObservationSink, UsageSource, UsageSourceContext
from ._setup import fill_setup_snippets

__all__ = [
    "SOURCE_FAILED",
    "SOURCE_TIMEOUT",
    "ExtraUsageSources",
    "SetupValues",
    "UsageService",
    "auto_enabled",
]

_log = logging.getLogger("agent_console_usage")

type ExtraUsageSources = Mapping[str, UsageSource] | Callable[[], Mapping[str, UsageSource]]
"""레지스트리 밖 출처(런타임 출처, 예: 다른 모듈이 포트로 준 것): id → 출처, 또는 그것을 돌려주는
함수(부를 때마다 다시 읽는다 — 서버 조립 뒤에 채워지는 포트 목록용)."""

type SetupValues = Mapping[str, str] | Callable[[], Mapping[str, str]]
"""연결 조각 자리표시자 값(예: `agent_console_cmd`), 또는 그것을 돌려주는 함수."""

SOURCE_FAILED = "usage_source_failed"
"""출처가 예외를 냈을 때 `UsageSourceInfo.error.code`."""

_CONFIG_CODES = frozenset({ErrorCodes.VALIDATION_FAILED, SOURCE_SCHEMA_INVALID})
"""설정 검증에서 나는 출처 오류 코드(설정을 고치면 수집 전이라도 지운다)."""

SOURCE_TIMEOUT = "usage_source_timeout"
"""출처가 시간 안에 답하지 않았을 때 `UsageSourceInfo.error.code`."""


def auto_enabled(descriptor: UsageSourceDescriptor) -> bool:
    """설정 `usage.sources`에 적지 않은 출처를 켤지: `auto_enable`이고 `test_only`가 아니면 켠다.

    >>> auto_enabled(UsageSourceDescriptor(id="a", title="a", trust="x", auto_enable=True))
    True
    >>> auto_enabled(
    ...     UsageSourceDescriptor(id="f", title="f", trust="x", auto_enable=True, test_only=True)
    ... )
    False
    """
    return descriptor.auto_enable and not descriptor.test_only


@dataclass(slots=True)
class _Status:
    last_observed_at: float | None = None
    error: ErrorInfo | None = None


@dataclass(frozen=True, slots=True)
class _Plan:
    key: str
    source: UsageSource
    enabled: bool
    config: JsonObject


class UsageService:
    """X13 출처 조립. 출처 이름·창 이름을 모르고 레지스트리와 설정 데이터로만 동작한다.

    - 설정 `usage.sources`에 적은 출처는 그 `enabled`를 따른다(사용자 값이 항상 우선).
    - 적지 않은 출처는 디스크립터가 정한다: `auto_enable`이고 `test_only`가 아니면 켜짐 + 빈 설정,
      아니면 꺼짐(`auto_enabled`). 그래서 설정이 비어 있어도 값이 나오는 출처는 켜지고, 시험용
      출처(`fake`)는 적어야 켜진다.
    - 디스크립터의 연결 조각(`setup_snippets`)은 자리표시자를 채워 내보낸다. 값은 서비스의
      `setup_values`에 출처의 `setup_values(ctx)`(선택 메서드)를 덮어 만든다.
    - `last_received_at`: 출처의 `received_at(ctx)`(선택 메서드)가 있으면 그 값, 없으면 지금까지
      받은 스냅샷의 가장 늦은 관측 시각.
    - 출처 설정은 디스크립터 `config_schema`로 검증한다(틀리면 그 출처만 오류).
    - 한 출처의 실패·시간 초과는 다른 출처를 막지 않는다(`sources()`의 `error`로 보인다).
    - 모은 스냅샷은 `observations`가 있으면 그대로 기록한다(이력). 현재 값(`collect`·`report`)에서는
      초기화 시각이 지난 창을 뺀다 — 초기화 뒤 사용률은 알 수 없으므로 이전 값을 보이지 않는다.
    """

    def __init__(
        self,
        sources: Registry[UsageSource],
        *,
        clock: Callable[[], float],
        events: UsageEventQuery | None = None,
        state_dir: Path | None = None,
        observations: UsageObservationSink | None = None,
        timeout_seconds: float | None = 10.0,
        extra_sources: ExtraUsageSources | None = None,
        setup_values: SetupValues | None = None,
    ) -> None:
        """
        Args:
            sources: 출처 레지스트리(`load_usage_sources`로 채운 것).
            clock: 현재 시각(Unix epoch 초).
            events: 실행 이벤트 조회(출처 맥락으로 전달).
            state_dir: workspace 시스템 기록 폴더(출처 맥락으로 전달).
            observations: 관측값 기록·정리. 없으면 기록하지 않는다.
            timeout_seconds: 출처 하나의 응답 한도. `None`이면 무기한.
            extra_sources: 레지스트리 밖 출처(id → 출처, 또는 그것을 돌려주는 함수). 레지스트리
                출처와 id가 겹치면 **레지스트리가 이기고** 겹친 id는 `conflicts()`·경고 로그로
                알린다. 레지스트리 출처 뒤에 id 순으로 붙는다.
            setup_values: 연결 조각 자리표시자 값(예: `{"agent_console_cmd": "/…/agent-console"}`)
                또는 그것을 돌려주는 함수. 출처가 주는 값(`output_path` 등)이 이긴다.
        """
        self._sources = sources
        self._clock = clock
        self._events = events
        self._state_dir = state_dir
        self._observations = observations
        self._timeout = timeout_seconds
        self._extra = extra_sources
        self._setup_values = setup_values
        self._status: dict[str, _Status] = {}
        self._warned: set[str] = set()

    # ------------------------------------------------------------ 조회

    def descriptors(self) -> list[UsageSourceDescriptor]:
        """등록된 출처 디스크립터(레지스트리 key 순, 그 뒤 추가 출처 id 순. id = key).

        연결 조각은 빈 설정 기준으로 채운다(설정별 값은 `sources(settings)`).
        """
        now = self._clock()
        return [self._describe(k, s, self._context(k, {}, now)) for k, s in self._entries()]

    def conflicts(self) -> list[str]:
        """추가 출처 중 레지스트리 출처와 id가 겹쳐 빠진 것(id 순)."""
        registry = {e.key for e in self._sources.list()}
        return sorted(k for k in self._extras() if k in registry)

    def config_issues(
        self,
        settings: UsageSettings | None,
        *,
        base_path: str = "/usage/sources",
        severity: IssueSeverity = "error",
    ) -> list[Issue]:
        """설정의 출처별 `config`를 지금 쓸 수 있는 출처의 `config_schema`로 검증한 이슈.

        지금 없는 출처 id(등록되지 않음·연동 꺼짐)는 건너뛴다. 규칙은 `source_config_issues`.

        Args:
            settings: 사용량 설정(`None`이면 빈 목록).
            base_path: 이슈 `path` 접두(JSON Pointer, 기본은 워크스페이스 설정 문서 기준).
            severity: 이슈 심각도.
        """
        if settings is None:
            return []
        descriptors = {key: source.descriptor for key, source in self._entries()}
        return source_config_issues(settings, descriptors, base_path=base_path, severity=severity)

    def sources(self, settings: UsageSettings | None = None) -> list[UsageSourceInfo]:
        """`GET /usage/sources` 항목: 디스크립터 + 사용 여부·설정 + 마지막 수집 상태."""
        out: list[UsageSourceInfo] = []
        now = self._clock()
        for plan in self._plans(settings):
            ctx = self._context(plan.key, plan.config, now)
            status = self._status.get(plan.key, _Status())
            error = status.error
            if plan.enabled:
                # 지금 설정으로 다시 본다: 수집 전이어도 틀린 설정이 바로 보이고(저장 뒤 출처가
                # 나타난 경우 등), 고친 설정의 지난 검증 오류는 남기지 않는다.
                invalid = config_error(plan.config, plan.source.descriptor.config_schema)
                if invalid is not None or (error is not None and error.code in _CONFIG_CODES):
                    error = invalid
            out.append(
                UsageSourceInfo(
                    descriptor=self._describe(plan.key, plan.source, ctx),
                    enabled=plan.enabled,
                    config=dict(plan.config),
                    last_observed_at=status.last_observed_at,
                    last_received_at=self._received_at(plan, ctx, status),
                    error=error,
                )
            )
        return out

    # ------------------------------------------------------------ 수집

    async def collect(self, settings: UsageSettings | None = None) -> list[UsageWindowSnapshot]:
        """켜진 출처를 함께 돌려 현재 창 스냅샷을 모은다((source, window) 순).

        출처가 주지 않은 값은 `None` 그대로다(서비스는 값을 채우지 않는다).
        """
        now = self._clock()
        plans = [p for p in self._plans(settings) if p.enabled]
        results = await asyncio.gather(*(self._run(p, now) for p in plans))
        current: list[UsageWindowSnapshot] = []
        for snaps in results:
            for snap in snaps:
                if self._observations is not None:
                    self._observations.record(snap)
                if snap.resets_at is None or snap.resets_at > now:
                    current.append(snap)
        current.sort(key=lambda s: (s.source, s.window))
        return current

    async def report(
        self,
        settings: UsageSettings | None = None,
        *,
        rollups: Sequence[TokenRollupRow] = (),
    ) -> UsageReport:
        """`GET /usage` 응답: 현재 창 스냅샷 + 주어진 토큰 집계."""
        windows = await self.collect(settings)
        return UsageReport(windows=windows, rollups=list(rollups), generated_at=self._clock())

    def prune(self, *, keep_seconds: float) -> int:
        """`keep_seconds`보다 오래된 관측값을 지운다(기록소가 없으면 0)."""
        if self._observations is None:
            return 0
        return self._observations.prune(self._clock() - keep_seconds)

    # ------------------------------------------------------------ 내부

    def _extras(self) -> Mapping[str, UsageSource]:
        extra = self._extra
        if extra is None:
            return {}
        return extra() if callable(extra) else extra

    def _entries(self) -> list[tuple[str, UsageSource]]:
        """(id, 출처): 레지스트리(key 순) + 겹치지 않는 추가 출처(id 순)."""
        out = [(e.key, e.item) for e in self._sources.list()]
        taken = {k for k, _ in out}
        extras = self._extras()
        for key in sorted(extras):
            if key in taken:
                if key not in self._warned:
                    self._warned.add(key)
                    _log.warning("사용량 출처 id가 겹쳐 레지스트리 출처를 씁니다: %s", key)
                continue
            out.append((key, extras[key]))
        return out

    def _context(self, key: str, config: JsonObject, now: float) -> UsageSourceContext:
        return UsageSourceContext(
            source_id=key,
            config=config,
            now=now,
            events=self._events,
            state_dir=self._state_dir,
        )

    def _describe(
        self, key: str, source: UsageSource, ctx: UsageSourceContext
    ) -> UsageSourceDescriptor:
        descriptor = source.descriptor
        update: dict[str, object] = {"id": key}
        if descriptor.setup_snippets:
            base = self._setup_values
            values = dict((base() if callable(base) else base) or {})
            own = getattr(source, "setup_values", None)
            if callable(own):
                try:
                    values.update(own(ctx))
                except Exception:  # 안내 값이 없어도 목록은 답한다(자리표시자 그대로)
                    _log.warning("사용량 출처 %s의 연결 안내 값을 만들지 못했습니다", key)
            update["setup_snippets"] = fill_setup_snippets(descriptor.setup_snippets, values)
        return descriptor.model_copy(update=update)

    @staticmethod
    def _received_at(plan: _Plan, ctx: UsageSourceContext, status: _Status) -> float | None:
        hook = getattr(plan.source, "received_at", None)
        if callable(hook):
            try:
                value = hook(ctx)
            except Exception:  # 읽기 실패는 수집 오류로 따로 보인다
                return None
            return float(value) if isinstance(value, int | float) else None
        return status.last_observed_at

    def _plans(self, settings: UsageSettings | None) -> list[_Plan]:
        configured: dict[str, UsageSourceSetting] = {}
        for item in settings.sources if settings is not None else []:
            configured.setdefault(item.id, item)
        plans: list[_Plan] = []
        for key, source in self._entries():
            setting = configured.get(key)
            plans.append(
                _Plan(
                    key=key,
                    source=source,
                    enabled=auto_enabled(source.descriptor) if setting is None else setting.enabled,
                    config={} if setting is None else dict(setting.config),
                )
            )
        return plans

    async def _run(self, plan: _Plan, now: float) -> list[UsageWindowSnapshot]:
        status = self._status.setdefault(plan.key, _Status())
        invalid = config_error(plan.config, plan.source.descriptor.config_schema)
        if invalid is not None:
            # 위치(설정 키 경로)와 어긴 스키마 키워드 이름만 알린다(값은 담지 않는다).
            status.error = invalid
            return []
        ctx = self._context(plan.key, plan.config, now)
        try:
            snaps = await asyncio.wait_for(plan.source.snapshot(ctx), self._timeout)
        except TimeoutError:
            status.error = ErrorInfo(
                code=SOURCE_TIMEOUT, message="출처가 시간 안에 답하지 않았습니다"
            )
            return []
        except Exception as exc:
            # 예외 문장은 내보내지 않는다(출처가 경로·자격 정보를 담을 수 있다). 형식 이름만.
            status.error = ErrorInfo(
                code=SOURCE_FAILED, message=f"출처를 읽지 못했습니다: {type(exc).__name__}"
            )
            return []
        status.error = None
        fixed = [
            s if s.source == plan.key else s.model_copy(update={"source": plan.key}) for s in snaps
        ]
        if fixed:
            newest = max(s.observed_at for s in fixed)
            if status.last_observed_at is None or newest > status.last_observed_at:
                status.last_observed_at = newest
        return fixed
