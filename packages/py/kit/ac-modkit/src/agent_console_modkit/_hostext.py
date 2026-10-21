"""호스트 기본 서비스의 확장 지점(design §3R.1.2, 3R.16): 플러그인 레지스트리·DB 핸들·비밀 해석.

호스트(통합 서버·단독 실행·다른 앱)는 기능 이름을 모른 채 기본 서비스를 만든다. 무엇을 넣을지는
설치된 패키지가 entry point로 알린다.

- ``HOST_REGISTRIES_GROUP``: 인자 없는 함수 → 레지스트리 묶음(``BaseServices.registries``).
  이름 순 첫 번째를 쓴다. 없으면 ``ExtensionRegistries``.
- ``HOST_PLUGIN_LOADERS_GROUP``: ``PluginLoader`` — 묶음에 플러그인을 로드한다(이름 순).
- ``HOST_DATABASE_GROUP``: ``(Path) -> DatabaseHandle`` — ``BaseServices.database``.
  이름 순 첫 번째를 쓴다. 없으면 DB 없이 시작한다.

로더는 자기 확장 지점의 검사기를 붙이고(``registries.extension(이름, validator=)``) entry point를
읽는다. 로더를 모두 부른 뒤 설정 ``plugins.modules``의 ``register(registries)`` 플러그인을 같은
묶음에 로드한다(검사기가 이미 붙어 있으므로 같은 검사를 거친다).

비밀 해석: 환경변수(``env_secret_lookup``) 뒤에 묶음의 ``SECRET_PROVIDERS_REGISTRY`` 레지스트리
항목(``get_secret(name) -> str | None``)을 순서대로 묻는다(``secret_lookup``).
"""

from __future__ import annotations

import importlib
import importlib.metadata
import logging
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Protocol, runtime_checkable

from agent_console_registry import LoadReport, Registry, load_plugins

from ._database import DatabaseHandle
from ._services import Paths

_log = logging.getLogger("agent_console_modkit.hostext")

HOST_REGISTRIES_GROUP = "agent_console.host_registries"
"""레지스트리 묶음 공장 entry point 그룹(인자 없는 함수)."""

HOST_PLUGIN_LOADERS_GROUP = "agent_console.host_plugin_loaders"
"""플러그인 로더 entry point 그룹(``PluginLoader``)."""

HOST_DATABASE_GROUP = "agent_console.host_database"
"""DB 핸들 공장 entry point 그룹(``(Path) -> DatabaseHandle``)."""

PLUGIN_MODULES_REPORT_GROUP = "plugins.modules"
"""``register(registries)`` 플러그인 보고의 그룹 이름."""

HOST_EXTENSIONS_REPORT_GROUP = "host.extensions"
"""호스트 확장(공장·로더) 자체를 읽지 못했을 때 보고의 그룹 이름."""

SECRET_PROVIDERS_REGISTRY = "secret_providers"
"""비밀 공급자 레지스트리 이름. 묶음의 같은 이름 속성(``Registry``) 또는 ``extension(이름)``."""


@dataclass(frozen=True)
class PluginLoadContext:
    """플러그인 로더가 받는 것.

    Attributes:
        registries: 레지스트리 묶음(``extension(name, validator=)``이 있다).
        enabled: 설정 ``plugins.enabled``(None = 설치된 것 전부). entry point 이름 집합.
        paths: 호스트 경로(선언형 플러그인 폴더 등). 없으면 None.
        options: 설치자 모듈 설정 원본(``modules.options``, 모듈 id → 값). 로더가 자기 모듈
            설정(예: 확장 이름)을 읽을 때 쓴다. 검증은 로더가 한다.
    """

    registries: Any
    enabled: frozenset[str] | None = None
    paths: Paths | None = None
    options: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)


type PluginLoader = Callable[[PluginLoadContext], Iterable[tuple[str, LoadReport]]]
"""플러그인 로더: 묶음에 로드하고 ``(보고 그룹, 보고)``를 돌려준다. 실패는 예외 대신 보고."""


@runtime_checkable
class RegistryBundle(Protocol):
    """레지스트리 묶음이 갖출 최소 모양."""

    def extension(self, name: str, *, validator: Any = None) -> Registry[Any]:
        """이름 붙은 레지스트리(없으면 만든다)."""
        ...

    def all(self) -> list[Registry[Any]]:
        """묶음의 모든 레지스트리."""
        ...


@dataclass
class ExtensionRegistries:
    """기본 레지스트리 묶음(공장 entry point가 없을 때). 이름 붙은 레지스트리만 있다."""

    extensions: dict[str, Registry[Any]] = field(default_factory=dict)

    def extension(self, name: str, *, validator: Any = None) -> Registry[Any]:
        """이름 붙은 레지스트리(없으면 만든다, ``validator``는 처음 또는 다시 붙인다)."""
        registry = self.extensions.get(name)
        if registry is None:
            registry = self.extensions[name] = Registry(name, validator=validator)
        elif validator is not None:
            registry.set_validator(validator)
        return registry

    def all(self) -> list[Registry[Any]]:
        return list(self.extensions.values())


@dataclass
class HostPlugins:
    """``load_host_plugins`` 결과.

    Attributes:
        registries: 레지스트리 묶음(``BaseServices.registries``).
        reports: ``(그룹, 보고)`` 목록(서버 정보의 플러그인 목록).
    """

    registries: Any
    reports: list[tuple[str, LoadReport]] = field(default_factory=list)

    @property
    def secret_providers(self) -> list[Any]:
        """묶음의 비밀 공급자(등록 순)."""
        return secret_providers_of(self.registries)


def _entry_points(
    group: str, entry_points: Iterable[importlib.metadata.EntryPoint] | None
) -> list[importlib.metadata.EntryPoint]:
    found = (
        [ep for ep in entry_points if ep.group == group]
        if entry_points is not None
        else list(importlib.metadata.entry_points(group=group))
    )
    return sorted(found, key=lambda e: (e.name, e.value))


def _source(ep: importlib.metadata.EntryPoint) -> str:
    return f"entry_point {ep.group}:{ep.name} ({ep.value})"


def _failed(source: str, key: str | None, exc: BaseException) -> LoadReport:
    return LoadReport(source=source, status="failed", key=key, error=f"{type(exc).__name__}: {exc}")


def _first_factory(
    group: str,
    entry_points: Iterable[importlib.metadata.EntryPoint] | None,
    reports: list[tuple[str, LoadReport]],
) -> Callable[..., Any] | None:
    """그룹의 이름 순 첫 번째로 읽히는 공장. 나머지는 ``skipped``(여럿이면 경고)."""
    chosen: Callable[..., Any] | None = None
    for ep in _entry_points(group, entry_points):
        if chosen is not None:
            _log.warning("%s: 공장이 여럿입니다. 앞의 것을 쓰고 %s는 건너뜁니다", group, ep.name)
            reports.append(
                (HOST_EXTENSIONS_REPORT_GROUP, LoadReport(_source(ep), "skipped", key=ep.name))
            )
            continue
        try:
            factory = ep.load()
            if not callable(factory):
                raise TypeError("호출 가능한 공장이 아닙니다")
        except (Exception, SystemExit) as exc:
            reports.append((HOST_EXTENSIONS_REPORT_GROUP, _failed(_source(ep), ep.name, exc)))
            continue
        chosen = factory
    return chosen


def load_host_plugins(
    *,
    enabled: Iterable[str] | None = None,
    paths: Paths | None = None,
    modules: Sequence[str] = (),
    options: Mapping[str, Mapping[str, Any]] | None = None,
    entry_points: Iterable[importlib.metadata.EntryPoint] | None = None,
    import_module: Callable[[str], ModuleType] = importlib.import_module,
) -> HostPlugins:
    """레지스트리 묶음을 만들고 설치된 플러그인 로더와 ``register(registries)`` 플러그인을 로드한다.

    Args:
        enabled: 로드할 entry point 이름(모든 그룹 공통, 설정 ``plugins.enabled``). None = 전부.
        paths: 호스트 경로(로더에 넘긴다).
        modules: ``register(registries)`` 플러그인 경로(설정 ``plugins.modules``).
        options: 모듈 설정 원본(``modules.options``, 로더에 넘긴다).
        entry_points: 테스트용 주입(그룹이 맞는 것만 쓴다). None이면 설치된 것.
        import_module: ``modules`` import 함수 주입.

    Returns:
        ``HostPlugins``. 실패는 예외 대신 보고에 담는다(경고 로그도 남긴다).
    """
    reports: list[tuple[str, LoadReport]] = []
    factory = _first_factory(HOST_REGISTRIES_GROUP, entry_points, reports)
    registries: Any = None
    if factory is not None:
        try:
            registries = factory()
            if not isinstance(registries, RegistryBundle):
                raise TypeError("extension()·all()이 있는 묶음이 아닙니다")
        except Exception as exc:
            reports.append(
                (HOST_EXTENSIONS_REPORT_GROUP, _failed(HOST_REGISTRIES_GROUP, None, exc))
            )
            registries = None
    if registries is None:
        registries = ExtensionRegistries()
    allowed = frozenset(enabled) if enabled is not None else None
    context = PluginLoadContext(
        registries=registries, enabled=allowed, paths=paths, options=dict(options or {})
    )
    for ep in _entry_points(HOST_PLUGIN_LOADERS_GROUP, entry_points):
        try:
            loader = ep.load()
            reports.extend(loader(context))
        except (Exception, SystemExit) as exc:
            reports.append((HOST_EXTENSIONS_REPORT_GROUP, _failed(_source(ep), ep.name, exc)))
    reports.extend(
        (PLUGIN_MODULES_REPORT_GROUP, r)
        for r in load_plugins(
            modules,
            registries,
            enabled=set(allowed) if allowed is not None else None,
            watch=registries.all,
            import_module=import_module,
        )
    )
    for _, report in reports:
        if not report.ok:
            _log.warning("플러그인 로드 실패: %s (%s)", report.source, report.error)
    return HostPlugins(registries=registries, reports=reports)


def open_host_database(
    path: Path, *, entry_points: Iterable[importlib.metadata.EntryPoint] | None = None
) -> DatabaseHandle | None:
    """설치된 DB 공장(``HOST_DATABASE_GROUP`` 이름 순 첫 번째)으로 ``path``의 DB 핸들을 연다.

    공장이 없으면 None(모듈은 저장소 없이 켜진다 — 메모리로 떨어지는 부분은 각 모듈이 알린다).

    Raises:
        Exception: 공장이 DB를 열지 못하면 그 예외(서버 기동 실패로 본다).
    """
    reports: list[tuple[str, LoadReport]] = []
    factory = _first_factory(HOST_DATABASE_GROUP, entry_points, reports)
    for _, report in reports:
        if not report.ok:
            _log.warning("DB 공장 로드 실패: %s (%s)", report.source, report.error)
    if factory is None:
        _log.warning("DB 공장(%s)이 설치되어 있지 않아 DB 없이 시작합니다", HOST_DATABASE_GROUP)
        return None
    handle = factory(path)
    if not isinstance(handle, DatabaseHandle):
        raise TypeError("DB 공장이 DatabaseHandle(engine·upgrade·close)을 돌려주지 않았습니다")
    return handle


def secret_providers_of(registries: Any) -> list[Any]:
    """묶음의 비밀 공급자 항목(``get_secret``이 있는 것만, 등록 순)."""
    registry = getattr(registries, SECRET_PROVIDERS_REGISTRY, None)
    if not isinstance(registry, Registry):
        extension = getattr(registries, "extension", None)
        registry = extension(SECRET_PROVIDERS_REGISTRY) if callable(extension) else None
    if not isinstance(registry, Registry):
        return []
    return [e.item for e in registry.list() if callable(getattr(e.item, "get_secret", None))]


def env_secret_lookup(
    environ: Mapping[str, str], *, prefix: str = ""
) -> Callable[[str], str | None]:
    """환경변수 비밀 조회: ``prefix + name``, 없으면 그 대문자 키. 없으면 None."""

    def lookup(name: str) -> str | None:
        for key in (prefix + name, (prefix + name).upper()):
            if key in environ:
                return environ[key]
        return None

    return lookup


def secret_lookup(
    first: Callable[[str], str | None] | None = None, providers: Iterable[Any] = ()
) -> Callable[[str], str | None]:
    """조회 함수 ``first`` 뒤에 공급자(``get_secret``)를 순서대로 묻는 ``이름 → 값`` 함수."""
    chain = list(providers)

    def lookup(name: str) -> str | None:
        if first is not None and (value := first(name)) is not None:
            return value
        for provider in chain:
            found = provider.get_secret(name)
            if found is not None:
                return str(found)
        return None

    return lookup


__all__ = [
    "HOST_DATABASE_GROUP",
    "HOST_EXTENSIONS_REPORT_GROUP",
    "HOST_PLUGIN_LOADERS_GROUP",
    "HOST_REGISTRIES_GROUP",
    "PLUGIN_MODULES_REPORT_GROUP",
    "SECRET_PROVIDERS_REGISTRY",
    "ExtensionRegistries",
    "HostPlugins",
    "PluginLoadContext",
    "PluginLoader",
    "RegistryBundle",
    "env_secret_lookup",
    "load_host_plugins",
    "open_host_database",
    "secret_lookup",
    "secret_providers_of",
]
