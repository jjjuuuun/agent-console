"""플러그인 로딩: entry point, 명시 모듈 경로, ``register(target)`` 플러그인.

어떤 로더도 로딩 실패를 예외로 전파하지 않는다. 결과는 항목별 ``LoadReport`` 로 돌려준다.
entry point 그룹 이름·확장 지점 이름은 이 패키지에 없다 — 모두 호출자가 넘긴다.
"""

from __future__ import annotations

import importlib
import importlib.metadata
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Literal

from agent_console_registry._registry import Registry, RegistryEntry

LoadStatus = Literal["loaded", "failed", "skipped", "disabled"]

ImportModule = Callable[[str], ModuleType]


@dataclass(frozen=True, slots=True)
class LoadReport:
    """로딩 시도 한 건의 결과. 화면·로그에 그대로 노출할 수 있는 값만 담는다.

    Attributes:
        source: 사람이 읽는 출처(예: ``"entry_point <group>:<name> (<value>)"``,
            ``"module <pkg.mod:attr>"``).
        status: ``loaded`` | ``failed`` | ``skipped`` (``enabled`` 에서 제외되어 로드하지 않음) |
            ``disabled`` (``register(target)`` 플러그인이 등록했지만 ``enabled`` 에 없어 해제함).
        key: 등록(시도)한 key. 경로를 해석하지 못하면 None.
        version: 등록된 버전(``loaded`` 일 때).
        error: 실패 사유 ``"<예외 타입>: <메시지>"`` (``failed`` 일 때).
    """

    source: str
    status: LoadStatus
    key: str | None = None
    version: int | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        """``failed`` 가 아니면 True(``skipped``·``disabled`` 포함)."""
        return self.status != "failed"


def _describe(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def _register_loaded[T](
    registry: Registry[T],
    key: str,
    obj: Any,
    source: str,
    validate: Callable[[Any], T] | None,
    version_of: Callable[[T], int] | None,
) -> LoadReport:
    """로드한 객체를 검증·등록하고 보고서를 만든다. 예외는 보고서로 바꾼다."""
    try:
        item: T = validate(obj) if validate is not None else obj
        version = version_of(item) if version_of is not None else 1
        registry.register(key, item, version=version, source=source)
    except (Exception, SystemExit) as exc:
        return LoadReport(source=source, status="failed", key=key, error=_describe(exc))
    return LoadReport(source=source, status="loaded", key=key, version=version)


def load_entry_points[T](
    group: str,
    registry: Registry[T],
    *,
    enabled: set[str] | None = None,
    validate: Callable[[Any], T] | None = None,
    version_of: Callable[[T], int] | None = None,
    entry_points: Iterable[importlib.metadata.EntryPoint] | None = None,
) -> list[LoadReport]:
    """entry point 그룹의 각 항목을 로드해 ``entry point 이름 → 로드한 객체`` 로 등록한다.

    Args:
        group: entry point 그룹 이름. 호출자가 정한다.
        registry: 등록 대상 레지스트리.
        enabled: 주어지면 이 이름들만 로드하고 나머지는 ``skipped`` 로 보고한다.
        validate: 로드한 객체를 검사·변환해 ``T`` 를 돌려주는 함수. 예외를 던지면 ``failed``.
        version_of: 항목의 버전을 구하는 함수. 없으면 1.
        entry_points: 테스트·특수 환경용 주입. None이면
            ``importlib.metadata.entry_points(group=group)`` 로 설치된 패키지에서 찾는다.

    Returns:
        entry point별 ``LoadReport`` (이름 오름차순). import 실패(``SystemExit`` 포함)·속성 없음·
        검증 실패·중복 key는 예외 대신 ``failed`` 로 담긴다. ``KeyboardInterrupt`` 는 전파한다.
    """
    eps = (
        list(entry_points)
        if entry_points is not None
        else list(importlib.metadata.entry_points(group=group))
    )
    reports: list[LoadReport] = []
    for ep in sorted(eps, key=lambda e: (e.name, e.value)):
        dist = getattr(ep, "dist", None)
        dist_part = f" [{dist.name} {dist.version}]" if dist is not None else ""
        source = f"entry_point {group}:{ep.name} ({ep.value}){dist_part}"
        if enabled is not None and ep.name not in enabled:
            reports.append(LoadReport(source=source, status="skipped", key=ep.name))
            continue
        try:
            obj = ep.load()
        except (Exception, SystemExit) as exc:
            reports.append(
                LoadReport(source=source, status="failed", key=ep.name, error=_describe(exc))
            )
            continue
        reports.append(_register_loaded(registry, ep.name, obj, source, validate, version_of))
    return reports


def _parse_path(path: str) -> tuple[str, str, str]:
    """``"[key=]pkg.mod:attr[.sub]"`` → ``(key, module, attr)``.

    형식 오류(콜론 없음, 빈 모듈·속성, ``=`` 뒤에 빈 key)면 ValueError.
    """
    key, sep, target = path.partition("=")
    if not sep:
        key, target = "", path
    module, colon, attr = target.strip().partition(":")
    module, attr, key = module.strip(), attr.strip(), key.strip()
    if not colon or not module or not attr or (sep and not key):
        raise ValueError(f"경로 형식은 '[key=]pkg.module:attr' 이어야 한다: {path!r}")
    return key or attr.rsplit(".", 1)[-1], module, attr


def _import_target(module: str, attr: str, import_module: ImportModule) -> Any:
    obj: Any = import_module(module)
    for part in attr.split("."):
        obj = getattr(obj, part)
    return obj


def load_modules[T](
    paths: Iterable[str],
    registry: Registry[T],
    *,
    validate: Callable[[Any], T] | None = None,
    version_of: Callable[[T], int] | None = None,
    import_module: ImportModule = importlib.import_module,
) -> list[LoadReport]:
    """명시한 모듈 경로의 객체를 로드해 등록한다(설치하지 않은 로컬 모듈용).

    경로 형식은 ``"pkg.module:attr"`` 또는 ``"key=pkg.module:attr"``. key를 생략하면
    ``attr`` 의 마지막 이름이 key가 된다. ``attr`` 은 ``obj.sub`` 처럼 점으로 이어도 된다.

    Args:
        paths: 모듈 경로 목록(설정 파일에서 읽은 값 등).
        registry: 등록 대상 레지스트리.
        validate: ``load_entry_points`` 와 같음.
        version_of: ``load_entry_points`` 와 같음.
        import_module: 모듈 import 함수 주입(기본 ``importlib.import_module``).

    Returns:
        경로별 ``LoadReport`` (입력 순서). 형식 오류(빈 ``key=`` 포함)·import 실패
        (``SystemExit`` 포함)·검증 실패·중복 key는 예외 대신 ``failed`` 로 담긴다.
        ``KeyboardInterrupt`` 는 전파한다.
    """
    reports: list[LoadReport] = []
    for path in paths:
        source = f"module {path}"
        try:
            key, module, attr = _parse_path(path)
        except ValueError as exc:
            reports.append(LoadReport(source=source, status="failed", error=_describe(exc)))
            continue
        try:
            obj = _import_target(module, attr, import_module)
        except (Exception, SystemExit) as exc:
            reports.append(
                LoadReport(source=source, status="failed", key=key, error=_describe(exc))
            )
            continue
        reports.append(_register_loaded(registry, key, obj, source, validate, version_of))
    return reports


type Snapshot = dict[tuple[int, str, int], RegistryEntry[Any]]


def _snapshot(registries: Iterable[Registry[Any]]) -> tuple[dict[int, Registry[Any]], Snapshot]:
    regs = {id(r): r for r in registries}
    entries: Snapshot = {
        (rid, e.key, e.version): e for rid, r in regs.items() for e in r.list(all_versions=True)
    }
    return regs, entries


def _disable_new(
    before: Snapshot,
    watch: Callable[[], Iterable[Registry[Any]]],
    enabled: set[str],
    source: str,
) -> list[LoadReport]:
    """플러그인이 새로 등록·교체한 항목 중 ``enabled`` 에 없는 key를 되돌리고 보고서를 만든다."""
    regs, after = _snapshot(watch())
    reports: list[LoadReport] = []
    for (rid, key, version), entry in after.items():
        if key in enabled or before.get((rid, key, version)) is entry:
            continue
        registry = regs[rid]
        previous = before.get((rid, key, version))
        registry.unregister(key, version)
        if previous is not None:  # 덮어쓴 것이면 원래 항목을 되살린다
            registry.register(key, previous.item, version=version, source=previous.source)
        reports.append(
            LoadReport(
                source=f"{source} -> {registry.name}:{key}",
                status="disabled",
                key=key,
                version=version,
            )
        )
    return reports


def load_plugins(
    paths: Iterable[str],
    target: object,
    *,
    enabled: set[str] | None = None,
    watch: Callable[[], Iterable[Registry[Any]]] | None = None,
    import_module: ImportModule = importlib.import_module,
) -> list[LoadReport]:
    """``"pkg.module:attr"`` 플러그인 객체를 로드해 ``target`` 을 넘겨 호출한다.

    여러 레지스트리에 한꺼번에 등록하는 플러그인용이다. ``target`` 은 호출자가 정한
    아무 객체(예: 앱이 만든 레지스트리 묶음)이며 이 패키지는 그 모양을 모른다.
    로드한 객체에 호출 가능한 ``register`` 속성이 있으면 ``obj.register(target)`` 을,
    없고 객체 자체가 호출 가능하면 ``obj(target)`` 을 호출한다.

    등록 검사는 각 ``Registry`` 의 검사기가 한다(검사기가 거부하면 플러그인 예외 → ``failed``).

    Args:
        paths: 플러그인 경로 목록(``key=`` 접두어는 보고서의 key로만 쓴다).
        target: 플러그인에 넘길 객체.
        enabled: 주어지면 플러그인이 등록한 항목 중 key가 이 집합에 없는 것을 등록 직후
            해제하고(덮어쓴 경우 원래 항목 복원) ``disabled`` 보고서를 더한다.
            entry point 로더의 ``enabled`` 와 같은 이름 집합이다. ``watch`` 가 필요하다.
        watch: ``enabled`` 를 적용할 레지스트리 목록을 돌려주는 함수(플러그인 호출 전후에
            부른다 — 플러그인이 새로 만든 레지스트리도 잡도록).
        import_module: 모듈 import 함수 주입.

    Returns:
        경로별 ``LoadReport`` (+ 해제한 항목별 ``disabled``). 플러그인 내부 예외(중복 등록·검사
        거부·``SystemExit`` 포함)도 ``failed`` 로 담긴다. ``KeyboardInterrupt`` 는 전파한다.
        한 플러그인이 중간에 실패하면 그 전까지 등록한 항목은 남는다(``enabled`` 는 적용).

    Raises:
        ValueError: ``enabled`` 를 주고 ``watch`` 를 주지 않았을 때.
    """
    if enabled is not None and watch is None:
        raise ValueError("enabled를 적용하려면 watch(레지스트리 목록)가 필요하다")
    reports: list[LoadReport] = []
    for path in paths:
        source = f"plugin {path}"
        try:
            key, module, attr = _parse_path(path)
        except ValueError as exc:
            reports.append(LoadReport(source=source, status="failed", error=_describe(exc)))
            continue
        before = _snapshot(watch())[1] if watch is not None and enabled is not None else {}
        try:
            obj = _import_target(module, attr, import_module)
            register = getattr(obj, "register", None)
            if callable(register):
                register(target)
            elif callable(obj):
                obj(target)
            else:
                raise TypeError(f"{path!r} 는 register(target) 또는 호출 가능 객체가 아니다")
        except (Exception, SystemExit) as exc:
            reports.append(
                LoadReport(source=source, status="failed", key=key, error=_describe(exc))
            )
        else:
            reports.append(LoadReport(source=source, status="loaded", key=key))
        if watch is not None and enabled is not None:
            reports.extend(_disable_new(before, watch, enabled, source))
    return reports
