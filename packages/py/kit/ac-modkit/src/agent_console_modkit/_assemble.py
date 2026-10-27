"""모듈 조립: 설정 적용 → 포트 충돌 판정 → 위상 정렬 → build → 보고(design §3R.1.2·§3R.1.8).

규칙
- 상태는 5종: ``active``·``disabled``(설정)·``unsatisfied``(필수 포트 없음)·
  ``failed``(설정 검증·build 예외, 메시지 가림)·``conflict``(같은 단일 포트를 여럿이 제공하고
  ``bindings``로 고르지 않음, 또는 같은 모듈 id가 둘 이상).
- 자동 보정은 하지 않는다. 충돌한 제공자는 **모두 꺼지고**(둘 다 그 포트를 제공하지 않음) 소비자는
  ``unsatisfied``가 된다. 사용자가 ``modules.bindings: {포트: 모듈 id}``로 고르면 고른 모듈만
  그 포트를 제공하고 나머지 제공자는 그 포트 없이 켜진다.
- ``PortKey(multi=True)`` 포트는 충돌이 아니다. 소비자는 제공 모듈 id 순 목록으로 받는다.
- 순서: 제공자 → 소비자(필수·선택 포트 모두). 선택 포트로 순환이 생기면 순환을 만드는 선택
  간선만 뺀다(단일 포트 간선을 먼저 지키고 여러 제공자 포트 간선을 먼저 뺀다 — 빠진 선택 포트는
  build 때 아직 없을 수 있다). 필수 포트끼리 순환이면 그 모듈들(과 그것에 기대는 모듈)은
  ``unsatisfied``(이유 ``cycle``)다.
"""

from __future__ import annotations

import asyncio
import contextlib
import heapq
import logging
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ._database import DatabaseHandle
from ._errors import ErrorMapping, FeatureUnavailableError
from ._events import EventBus, Handler
from ._hub import Hub
from ._module import Module, ModuleDescriptor, ModuleParts, WsTopicHandler
from ._options import OPTIONS_MASK, ModuleOptions, SecretPathFinder, read_module_options
from ._ports import PortKey, Topic
from ._services import BaseServices, Paths

_log = logging.getLogger("agent_console_modkit.assemble")


class ModuleState(StrEnum):
    """모듈 상태 5종."""

    ACTIVE = "active"
    DISABLED = "disabled"
    UNSATISFIED = "unsatisfied"
    FAILED = "failed"
    CONFLICT = "conflict"


class ModulesConfig(BaseModel):
    """설치자 설정 ``modules``(design §3R.1.8).

    Attributes:
        enabled: None이면 넘겨받은 모듈 전부. 목록이면 그것만.
        disabled: ``enabled`` 뒤에 끈다.
        bindings: 단일 포트를 여러 모듈이 줄 때 고른 모듈(``{포트 이름: 모듈 id}``).
        options: 모듈 id → 그 모듈 설정(각 모듈 ``settings_schema``로 검증).
    """

    model_config = ConfigDict(extra="forbid")

    enabled: list[str] | None = None
    disabled: list[str] = Field(default_factory=list)
    bindings: dict[str, str] = Field(default_factory=dict)
    options: dict[str, dict[str, Any]] = Field(default_factory=dict)

    def with_overrides(
        self, *, enable: Iterable[str] = (), disable: Iterable[str] = ()
    ) -> ModulesConfig:
        """명령행 ``--enable-module``·``--disable-module``을 적용한 사본(설정보다 우선).

        - ``enable``: ``disabled``에서 뺀다. ``enabled``가 목록이면 거기에 더한다
          (``None``이면 그대로 전부 켬).
        - ``disable``: ``disabled``에 더하고 ``enabled`` 목록에서 뺀다.
        - 같은 id가 둘 다에 있으면 ``disable``이 이긴다(안전한 쪽).
        """
        on = list(dict.fromkeys(enable))
        off = list(dict.fromkeys(disable))
        on = [mid for mid in on if mid not in off]
        enabled = self.enabled
        if enabled is not None:
            enabled = [mid for mid in dict.fromkeys([*enabled, *on]) if mid not in off]
        disabled = [mid for mid in dict.fromkeys([*self.disabled, *off]) if mid not in on]
        return self.model_copy(update={"enabled": enabled, "disabled": disabled})


@dataclass(frozen=True)
class ModuleReport:
    """모듈 하나의 조립 결과(웹·``/modules`` 보고용 원본, 계약 모델 변환은 호스트가 한다).

    Attributes:
        reason: 상태 이유(사람용). ``failed``는 예외 형식만 담고 메시지는 가린다.
        missing: ``unsatisfied``일 때 빠진 필수 포트 이름.
        conflicts: ``conflict``일 때 충돌한 포트 이름(같은 id 충돌이면 빈 튜플).
    """

    id: str
    version: str
    kind: str
    title: str
    state: ModuleState
    reason: str | None = None
    missing: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    provides: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()
    web_roles: tuple[str, ...] = ()
    contracts: Mapping[str, str] = field(default_factory=dict, hash=False)

    @property
    def active(self) -> bool:
        return self.state is ModuleState.ACTIVE

    def to_dict(self) -> dict[str, Any]:
        """JSON으로 보낼 수 있는 dict(호스트 기본 ``/modules`` 본문 항목)."""
        return {
            "id": self.id,
            "version": self.version,
            "kind": self.kind,
            "title": self.title,
            "state": self.state.value,
            "reason": self.reason,
            "missing": list(self.missing),
            "conflicts": list(self.conflicts),
            "provides": list(self.provides),
            "requires": list(self.requires),
            "optional": list(self.optional),
            "web_roles": list(self.web_roles),
            "contracts": dict(self.contracts),
        }


class UndeclaredPortError(LookupError):
    """서술자에 선언하지 않은 포트를 읽거나 제공하려 했다(조립 순서가 선언에 기대므로 막는다)."""


# ---------------------------------------------------------------- 포트 표


class _PortTable:
    """확정된 포트 구현. 이름 → [(제공 모듈 id, 구현)]."""

    def __init__(self) -> None:
        self._items: dict[str, list[tuple[str, Any]]] = {}

    def add(self, name: str, module_id: str, impl: Any) -> None:
        self._items.setdefault(name, []).append((module_id, impl))

    def has(self, name: str) -> bool:
        return bool(self._items.get(name))

    def single(self, name: str) -> Any | None:
        items = self._items.get(name)
        return items[0][1] if items else None

    def many(self, name: str) -> list[Any]:
        items = sorted(self._items.get(name, ()), key=lambda pair: pair[0])
        return [impl for _, impl in items]

    def providers(self, name: str) -> list[str]:
        return sorted({mid for mid, _ in self._items.get(name, ())})

    def names(self) -> list[str]:
        return sorted(n for n, items in self._items.items() if items)


# ---------------------------------------------------------------- 문맥


class ModuleContext:
    """``Module.build``가 받는 것(전역 없음). 조립기가 모듈마다 만든다.

    Attributes:
        module_id: 이 모듈 id.
        settings: ``settings_schema``로 검증한 자기 설정(스키마가 없으면 None).
        services: 호스트 기본 서비스. ``clock``·``environ``·``paths`` 등은 바로 꺼내 쓸 수 있다.
    """

    def __init__(
        self,
        descriptor: ModuleDescriptor,
        *,
        settings: BaseModel | None,
        services: BaseServices,
        table: _PortTable,
    ) -> None:
        self.descriptor = descriptor
        self.module_id = descriptor.id
        self.settings = settings
        self.services = services
        self._table = table
        self._provided: list[tuple[PortKey[Any], Any]] = []
        self._unsubscribers: list[Callable[[], None]] = []
        self._readable = {p.name: p for p in (*descriptor.requires, *descriptor.optional)}
        self._providable = {p.name: p for p in descriptor.provides}

    # ------------------------------------------------------------ 기본 서비스 바로 가기

    @property
    def clock(self) -> Callable[[], datetime]:
        return self.services.clock

    @property
    def environ(self) -> Mapping[str, str]:
        return self.services.environ

    @property
    def paths(self) -> Paths | None:
        return self.services.paths

    @property
    def database(self) -> DatabaseHandle | None:
        return self.services.database

    @property
    def registries(self) -> Any | None:
        return self.services.registries

    @property
    def ws_hub(self) -> Hub[Any]:
        return self.services.ws_hub

    @property
    def events(self) -> EventBus:
        return self.services.events

    @property
    def secret_resolver(self) -> Callable[[str], str | None] | None:
        return self.services.secret_resolver

    # ------------------------------------------------------------ 포트

    def _declared(self, key: PortKey[Any]) -> PortKey[Any]:
        declared = self._readable.get(key.name)
        if declared is None:
            raise UndeclaredPortError(
                f"{self.module_id}: requires·optional에 선언하지 않은 포트입니다: {key.name}"
            )
        return declared

    def port[T](self, key: PortKey[T]) -> T | None:
        """단일 포트 구현. 없으면 None(필수 포트는 조립기가 미리 확인하므로 항상 있다).

        Raises:
            UndeclaredPortError: 서술자에 선언하지 않은 포트.
            TypeError: ``multi`` 포트(``ports``를 쓴다).
        """
        self._declared(key)
        if key.multi:
            raise TypeError(f"multi 포트는 ports()로 읽습니다: {key.name}")
        impl: T | None = self._table.single(key.name)
        return impl

    def ports[T](self, key: PortKey[T]) -> list[T]:
        """포트 구현 목록(제공 모듈 id 순). 단일 포트면 0개 또는 1개.

        Raises:
            UndeclaredPortError: 서술자에 선언하지 않은 포트.
        """
        self._declared(key)
        impls: list[T] = self._table.many(key.name)
        return impls

    def unavailable(self, key: PortKey[Any], message: str | None = None) -> FeatureUnavailableError:
        """선택 포트 ``key``가 없어 꺼진 동작에서 던질 오류(호스트가 409 ``feature_unavailable``).

        예: ``launcher = ctx.port(LAUNCHER)``가 None이면 라우트에서
        ``raise ctx.unavailable(LAUNCHER)``.
        """
        return FeatureUnavailableError(self.module_id, key.name, message)

    def provide[T](self, key: PortKey[T], impl: T) -> None:
        """포트를 제공한다. build가 성공해야 확정된다(실패하면 버린다).

        Raises:
            UndeclaredPortError: ``provides``에 선언하지 않은 포트.
            ValueError: 단일 포트를 두 번 제공.
        """
        declared = self._providable.get(key.name)
        if declared is None:
            raise UndeclaredPortError(
                f"{self.module_id}: provides에 선언하지 않은 포트입니다: {key.name}"
            )
        if not declared.multi and any(k.name == key.name for k, _ in self._provided):
            raise ValueError(f"{self.module_id}: 단일 포트를 두 번 제공했습니다: {key.name}")
        self._provided.append((declared, impl))

    # ------------------------------------------------------------ 이벤트

    def publish[T](self, topic: Topic[T], item: T) -> None:
        """모듈 이벤트를 발행한다(막히지 않음, ``EventBus.publish``)."""
        self.services.events.publish(topic, item)

    def subscribe[T](self, topic: Topic[T], handler: Handler[T]) -> None:
        """모듈 이벤트를 구독한다. build가 실패하면 해제된다."""
        self._unsubscribers.append(self.services.events.subscribe(topic, handler))

    # ------------------------------------------------------------ 조립기 전용

    def _rollback(self) -> None:
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()
        self._provided.clear()


# ---------------------------------------------------------------- 결과


@dataclass
class Assembly:
    """조립 결과. ``start``·``stop``으로 켜진 모듈의 시작·종료 훅을 돌린다(FastAPI 없이도 쓴다).

    Attributes:
        parts: 켜진(``active``) 모듈 id → 빌드 결과(조립 순서).
        report: 모든 모듈의 보고(id 순).
        order: 켜진 모듈의 조립 순서.
        warnings: 설정의 모르는 id·잘못된 bindings 등(조립은 계속).
        services: 모듈에 준 기본 서비스.
        descriptors: 넘겨받은 모든 모듈의 서술자(id → 첫 번째, 꺼진 모듈 포함).
        options: 설치자 설정 ``modules.options``(id → 원문, 읽기 전용 보기용).
    """

    parts: dict[str, ModuleParts]
    report: list[ModuleReport]
    order: list[str]
    warnings: list[str]
    services: BaseServices
    _table: _PortTable = field(repr=False)
    descriptors: dict[str, ModuleDescriptor] = field(default_factory=dict, repr=False)
    options: dict[str, dict[str, Any]] = field(default_factory=dict, repr=False)
    _background: list[asyncio.Task[None]] = field(default_factory=list, repr=False)
    _started: list[str] = field(default_factory=list, repr=False)
    _running: bool = field(default=False, repr=False)

    @property
    def running(self) -> bool:
        """``start``가 끝났고 ``stop``이 아직 시작되지 않았다(호스트 준비 신호, 3R.16)."""
        return self._running

    def status(self, module_id: str) -> ModuleReport | None:
        """id의 보고. 같은 id가 여럿이면 첫 번째."""
        return next((r for r in self.report if r.id == module_id), None)

    def module_options(
        self,
        module_id: str,
        *,
        secret_paths: SecretPathFinder | None = None,
        hide_paths: bool = False,
        mask: str = OPTIONS_MASK,
    ) -> ModuleOptions | None:
        """모듈 옵션 읽기 전용 보기(꺼진 모듈도). 모르는 id면 None.

        Args:
            module_id: 모듈 id.
            secret_paths: 평문 비밀 의심 위치 함수(주입). 스키마가 비밀로 표시한 필드는 늘 가린다.
            hide_paths: 참이면 경로 필드도 가린다.
            mask: 가린 자리 문자열(기본 ``OPTIONS_MASK``).
        """
        descriptor = self.descriptors.get(module_id)
        if descriptor is None:
            return None
        return read_module_options(
            descriptor,
            self.options.get(module_id),
            secret_paths=secret_paths,
            hide_paths=hide_paths,
            mask=mask,
        )

    def port[T](self, key: PortKey[T]) -> T | None:
        """확정된 단일 포트 구현(호스트·테스트용)."""
        impl: T | None = self._table.single(key.name)
        return impl

    def ports[T](self, key: PortKey[T]) -> list[T]:
        """확정된 포트 구현 목록(제공 모듈 id 순)."""
        impls: list[T] = self._table.many(key.name)
        return impls

    def provided_ports(self) -> dict[str, list[str]]:
        """포트 이름 → 제공 모듈 id 목록."""
        return {name: self._table.providers(name) for name in self._table.names()}

    def routers(self, *, first_kinds: Iterable[str] = ()) -> list[Any]:
        """켜진 모듈의 라우터(조립 순서). ``first_kinds``에 든 종류(``ModuleDescriptor.kind``)의
        모듈 라우터를 먼저 둔다(같은 경로 패턴이면 먼저 붙은 것이 맞는다 — 호스트는 연동 모듈의
        하위·고정 경로가 기능 모듈의 매개변수 경로에 가리지 않게 ``("link",)``을 준다)."""
        first = set(first_kinds)
        kinds = {r.id: r.kind for r in self.report}
        head = [mid for mid in self.order if kinds.get(mid) in first]
        tail = [mid for mid in self.order if kinds.get(mid) not in first]
        return [r for mid in [*head, *tail] for r in self.parts[mid].routers]

    def ws_topics(self) -> dict[str, WsTopicHandler]:
        return {k: h for mid in self.order for k, h in self.parts[mid].ws_topics.items()}

    def error_map(self) -> dict[type[Exception], ErrorMapping]:
        return {e: c for mid in self.order for e, c in self.parts[mid].error_map.items()}

    async def start(self, *, fail_fast: bool = False) -> None:
        """조립 순서대로 ``startup``을 부르고 ``background``를 띄운다.

        시작 훅이 실패한 모듈은 보고를 ``failed``로 바꾸고(메시지 가림) 그 모듈의 배경 작업은 띄우지
        않는다. 다른 모듈은 계속 시작한다.

        Args:
            fail_fast: 참이면 시작 훅 예외를 그대로 다시 던진다(뒤 모듈은 시작하지 않는다). 이미
                시작한 모듈의 정리는 호출자가 ``stop()``으로 한다. 시작 실패를 서버 기동 실패로
                보는 호스트가 쓴다.
        """
        for mid in self.order:
            parts = self.parts[mid]
            try:
                for hook in parts.startup:
                    await hook()
            except Exception as exc:
                self._mark_failed(mid, f"시작 실패({type(exc).__name__})")
                self._started.append(mid)  # 일부 시작했을 수 있으니 종료 훅은 부른다
                if fail_fast:
                    raise  # 호출자가 알린다(예외 메시지를 여기서 로그에 남기지 않는다)
                _log.exception("모듈 시작 실패: %s", mid)
                continue
            self._started.append(mid)
            for job in parts.background:
                self._background.append(asyncio.ensure_future(_guard_background(mid, job)))
        self._running = True

    async def stop(self) -> None:
        """배경 작업을 취소하고, 시작한 모듈의 ``shutdown``을 역순으로 부른 뒤 이벤트를 비운다."""
        self._running = False
        for task in self._background:
            task.cancel()
        for task in self._background:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._background.clear()
        for mid in reversed(self._started):
            for hook in reversed(self.parts[mid].shutdown):
                try:
                    await hook()
                except Exception:
                    _log.exception("모듈 종료 훅 실패: %s", mid)
        self._started.clear()
        await self.services.events.drain()

    def _mark_failed(self, module_id: str, reason: str) -> None:
        for i, r in enumerate(self.report):
            if r.id == module_id:
                self.report[i] = _replace_state(r, ModuleState.FAILED, reason)


async def _guard_background(module_id: str, job: Callable[[], Awaitable[None]]) -> None:
    try:
        await job()
    except asyncio.CancelledError:
        raise
    except Exception:
        _log.exception("모듈 배경 작업 실패: %s", module_id)


def _replace_state(report: ModuleReport, state: ModuleState, reason: str | None) -> ModuleReport:
    return replace(report, state=state, reason=reason)


# ---------------------------------------------------------------- 조립


def _base_report(
    d: ModuleDescriptor, state: ModuleState, reason: str | None, **kw: Any
) -> ModuleReport:
    return ModuleReport(
        id=d.id,
        version=d.version,
        kind=d.kind,
        title=d.title,
        state=state,
        reason=reason,
        provides=tuple(p.name for p in d.provides),
        requires=tuple(p.name for p in d.requires),
        optional=tuple(p.name for p in d.optional),
        web_roles=d.web_roles,
        contracts=dict(d.contracts),
        **kw,
    )


def _topo_order(ids: Iterable[str], deps: Mapping[str, set[str]]) -> tuple[list[str], list[str]]:
    """Kahn 정렬(같은 단계는 id 순). 돌려준 값: (순서, 순환에 걸린 id)."""
    remaining = {i: set(deps.get(i, ())) for i in ids}
    users: dict[str, set[str]] = {i: set() for i in remaining}
    for i, ds in remaining.items():
        for d in ds:
            users.setdefault(d, set()).add(i)
    ready = [i for i, ds in remaining.items() if not ds]
    heapq.heapify(ready)
    order: list[str] = []
    while ready:
        current = heapq.heappop(ready)
        order.append(current)
        for user in sorted(users.get(current, ())):
            pending = remaining[user]
            pending.discard(current)
            if not pending and user not in order and user not in ready:
                heapq.heappush(ready, user)
    cyclic = sorted(i for i in remaining if i not in order)
    return order, cyclic


def _reaches(start: str, goal: str, deps: Mapping[str, set[str]]) -> bool:
    """``start``에서 ``deps`` 간선을 따라 ``goal``에 닿는지."""
    stack, seen = [start], {start}
    while stack:
        current = stack.pop()
        if current == goal:
            return True
        for nxt in deps.get(current, ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return False


def _settings_of(module: Module, raw: Mapping[str, Any] | None) -> BaseModel | None:
    schema = module.descriptor.settings_schema
    if schema is None:
        return None
    return schema.model_validate(dict(raw or {}))


def _validation_locations(exc: ValidationError) -> str:
    locs = sorted({".".join(str(p) for p in e.get("loc", ())) or "(root)" for e in exc.errors()})
    return ", ".join(locs)


def assemble(
    modules: Iterable[Module],
    config: ModulesConfig | None = None,
    *,
    base: BaseServices | None = None,
) -> Assembly:
    """모듈들을 조립한다.

    Args:
        modules: 조립할 모듈(설치된 entry point·직접 만든 것).
        config: 설치자 설정 ``modules``. None이면 기본(전부 켬).
        base: 호스트 기본 서비스. None이면 기본값(빈 환경, 경로·DB 없음).

    Returns:
        ``Assembly``. 모듈 하나가 실패해도 예외를 던지지 않고 보고에 담는다.
    """
    cfg = config or ModulesConfig()
    services = base or BaseServices()
    items = list(modules)
    warnings: list[str] = []
    reports: dict[int, ModuleReport] = {}  # 입력 위치 → 보고(같은 id가 여럿일 수 있어 위치로)
    table = _PortTable()

    # 1) 같은 id
    by_id: dict[str, list[int]] = {}
    for idx, m in enumerate(items):
        by_id.setdefault(m.descriptor.id, []).append(idx)
    for mid, idxs in by_id.items():
        if len(idxs) > 1:
            for idx in idxs:
                reports[idx] = _base_report(
                    items[idx].descriptor,
                    ModuleState.CONFLICT,
                    f"같은 모듈 id가 {len(idxs)}개입니다: {mid}",
                )

    # 2) 켜고 끄기
    known = set(by_id)
    for name in [*(cfg.enabled or ()), *cfg.disabled, *cfg.options]:
        if name not in known:
            warnings.append(f"모르는 모듈 id: {name}")
    enabled = None if cfg.enabled is None else set(cfg.enabled)
    disabled = set(cfg.disabled)
    candidates: dict[str, Module] = {}
    for idx, m in enumerate(items):
        if idx in reports:
            continue
        mid = m.descriptor.id
        if enabled is not None and mid not in enabled:
            reports[idx] = _base_report(
                m.descriptor, ModuleState.DISABLED, "modules.enabled에 없음"
            )
        elif mid in disabled:
            reports[idx] = _base_report(m.descriptor, ModuleState.DISABLED, "modules.disabled")
        else:
            candidates[mid] = m
    index_of = {items[idx].descriptor.id: idx for idx in range(len(items)) if idx not in reports}

    # 3) 단일 포트 충돌·bindings
    declared_providers: dict[str, list[tuple[str, PortKey[Any]]]] = {}
    for mid, m in candidates.items():
        for key in m.descriptor.provides:
            declared_providers.setdefault(key.name, []).append((mid, key))
    chosen: dict[str, str] = {}  # 단일 포트 → 고른 제공자
    conflicted: dict[str, set[str]] = {}  # 모듈 id → 충돌 포트
    for port, binding in cfg.bindings.items():
        if binding not in {mid for mid, _ in declared_providers.get(port, ())}:
            warnings.append(f"modules.bindings.{port}: {binding}은(는) 켜진 제공자가 아닙니다")
    for port, provs in declared_providers.items():
        ids = sorted({mid for mid, _ in provs})
        is_multi = all(key.multi for _, key in provs)
        if len(ids) < 2 or is_multi:
            continue
        picked = cfg.bindings.get(port)
        if picked is not None and picked in ids:
            chosen[port] = picked
            continue
        for mid in ids:
            conflicted.setdefault(mid, set()).add(port)
    for mid, ports in conflicted.items():
        d = candidates[mid].descriptor
        names = ", ".join(sorted(ports))
        reports[index_of[mid]] = _base_report(
            d,
            ModuleState.CONFLICT,
            f"같은 포트를 여러 모듈이 제공합니다: {names} (modules.bindings로 고르세요)",
            conflicts=tuple(sorted(ports)),
        )
    live = {mid: m for mid, m in candidates.items() if mid not in conflicted}

    def providers_of(port: str) -> set[str]:
        if port in chosen:
            return {chosen[port]} & set(live)
        return {mid for mid, _ in declared_providers.get(port, ()) if mid in live}

    required: dict[str, set[str]] = {}
    for mid, m in live.items():
        required[mid] = {p for k in m.descriptor.requires for p in providers_of(k.name)} - {mid}

    # 4) 순서: 필수 간선은 모두, 선택 간선은 순환을 만들지 않는 것만 넣고 정렬한다.
    #    선택 간선은 단일 포트(설정·저장소처럼 build 때 읽는 값)를 먼저, 여러 제공자 포트(등록
    #    목록 — 보통 부를 때 읽는다)를 나중에 넣는다. 순환을 만드는 선택 간선만 빠지므로 순환과
    #    상관없는 모듈은 선택 포트 순서(제공자 먼저)를 잃지 않는다. 필수 간선끼리 순환이면
    #    그 모듈들은 정렬되지 않는다(아래에서 ``cycle``).
    edges: dict[str, set[str]] = {mid: set(required[mid]) for mid in live}
    optional_edges: list[tuple[bool, str, str]] = sorted(
        (bool(k.multi), consumer, provider)
        for consumer, m in live.items()
        for k in m.descriptor.optional
        for provider in providers_of(k.name)
        if provider != consumer
    )
    for _multi, consumer, provider in optional_edges:
        if provider in edges[consumer]:
            continue
        if not _reaches(provider, consumer, edges):  # 이미 소비자에 기대면 순환을 만든다
            edges[consumer].add(provider)
    order, stuck = _topo_order(live, edges)
    cyclic = stuck
    for mid in cyclic:
        reports[index_of[mid]] = _base_report(
            live[mid].descriptor,
            ModuleState.UNSATISFIED,
            f"필수 포트 순환에 걸렸습니다(cycle): {', '.join(cyclic)}",
        )

    # 5) build
    parts: dict[str, ModuleParts] = {}
    ws_owner: dict[str, str] = {}
    for mid in order:
        module = live[mid]
        d = module.descriptor
        idx = index_of[mid]
        missing = tuple(k.name for k in d.requires if not table.has(k.name))
        if missing:
            reports[idx] = _base_report(
                d,
                ModuleState.UNSATISFIED,
                f"필수 포트 없음: {', '.join(missing)}",
                missing=missing,
            )
            continue
        raw = cfg.options.get(mid)
        if raw and d.settings_schema is None:
            warnings.append(f"modules.options.{mid}: 이 모듈은 설정을 받지 않습니다(무시)")
        try:
            settings = _settings_of(module, raw)
        except ValidationError as exc:
            reports[idx] = _base_report(
                d, ModuleState.FAILED, f"설정 검증 실패: {_validation_locations(exc)}"
            )
            continue
        if d.migrations and services.database is not None:
            try:
                services.database.upgrade(d.migrations)
            except Exception as exc:
                _log.exception("모듈 마이그레이션 실패: %s", mid)
                reports[idx] = _base_report(
                    d, ModuleState.FAILED, f"마이그레이션 실패({type(exc).__name__})"
                )
                continue
        ctx = ModuleContext(d, settings=settings, services=services, table=table)
        try:
            built = module.build(ctx)
            if not isinstance(built, ModuleParts):
                raise TypeError(f"build가 ModuleParts가 아닌 값을 돌려줬습니다: {type(built)!r}")
        except Exception as exc:
            _log.exception("모듈 build 실패: %s", mid)
            ctx._rollback()
            reports[idx] = _base_report(d, ModuleState.FAILED, f"build 실패({type(exc).__name__})")
            continue
        clash = sorted(k for k in built.ws_topics if k in ws_owner)
        if clash:
            ctx._rollback()
            owners = ", ".join(f"{k}({ws_owner[k]})" for k in clash)
            reports[idx] = _base_report(d, ModuleState.FAILED, f"WS 토픽 키 중복: {owners}")
            continue
        for key, impl in ctx._provided:
            if key.name in chosen and chosen[key.name] != mid:
                continue  # 사용자가 다른 제공자를 골랐다
            table.add(key.name, mid, impl)
        for k in built.ws_topics:
            ws_owner[k] = mid
        parts[mid] = built
        reports[idx] = _base_report(d, ModuleState.ACTIVE, None)

    report = sorted(reports.values(), key=lambda r: r.id)
    return Assembly(
        parts=parts,
        report=report,
        order=list(parts),
        warnings=warnings,
        services=services,
        _table=table,
        descriptors={mid: items[idxs[0]].descriptor for mid, idxs in sorted(by_id.items())},
        options={mid: dict(raw) for mid, raw in cfg.options.items()},
    )


def default_paths(base_dir: Path, *, workspace: str | Path, state: str | Path) -> Paths:
    """``base_dir`` 기준으로 상대 경로를 푼 ``Paths``."""

    def resolve(p: str | Path) -> Path:
        path = Path(p)
        return path if path.is_absolute() else base_dir / path

    return Paths(base_dir=base_dir, workspace=resolve(workspace), state=resolve(state))


__all__ = [
    "Assembly",
    "ModuleContext",
    "ModuleReport",
    "ModuleState",
    "ModulesConfig",
    "UndeclaredPortError",
    "assemble",
    "default_paths",
]
