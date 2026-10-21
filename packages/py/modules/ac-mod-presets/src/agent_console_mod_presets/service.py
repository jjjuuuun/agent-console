"""프리셋 목록·적용(ac-presets 공개 API를 설정 값으로 부른다). HTTP 없이도 쓴다."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_console_contracts import AppliedItemInfo, ApplyPresetResult, PresetSummary
from agent_console_presets import (
    MANIFEST_FILE,
    ApplyReport,
    ConflictPolicy,
    ItemDependencies,
    ItemValidator,
    Preset,
    PresetError,
    Stamp,
    apply_preset,
    collect_values,
    discover_presets,
    load_items,
)
from agent_console_store import (
    DEFAULT_KINDS,
    GRAPH_KIND,
    SCOPE_FIELD,
    DefinitionKind,
    DefinitionStore,
)

from .ports import DefinitionCheck, DocumentDependencies

_log = logging.getLogger("agent_console_mod_presets")


class PresetNotFoundError(LookupError):
    """요청한 프리셋 id가 프리셋 폴더 목록에 없다."""


def discover(search_paths: Iterable[Path]) -> list[Preset]:
    """프리셋 폴더의 프리셋(앞 경로 우선 아님 — 발견 순서). 문제 있는 폴더는 경고 로그."""
    found = discover_presets(list(search_paths))
    for problem in found.problems:
        _log.warning("프리셋 폴더 문제: %s", problem)
    return found.presets


BackendBadge = Callable[[str], str | None]
"""실행 백엔드 이름 → 카드 배지 글자(디스크립터 ``ui_hints.badge``, 없으면 ``None``)."""

BACKEND_KEY = "backend"
"""프리셋 항목 문서에서 실행 백엔드 이름을 담는 키의 기본값(에이전트 ``backend``·팀 구성
``settings.backend``·노드 설정 층 모두 같은 이름이다)."""


def _no_badge(_backend: str) -> str | None:
    return None


def registry_backend_badge(registries: Callable[[], Any]) -> BackendBadge:
    """레지스트리 묶음의 ``backends``(예: ``agent_console_runtime.Registries``) → ``BackendBadge``.

    부를 때마다 묶음을 다시 읽는다(플러그인 로드 뒤 값). 묶음·``backends``가 없거나 모양이 다르면
    배지가 없다(실행 기능이 꺼져도 프리셋 목록은 동작한다). 의존 없이 이름으로만 읽는다.
    """

    def badge(backend: str) -> str | None:
        registry = getattr(registries(), "backends", None)
        listing = getattr(registry, "list", None)
        if not callable(listing):
            return None
        for entry in listing(all_versions=False):
            if getattr(entry, "key", None) != backend:
                continue
            descriptor = getattr(getattr(entry, "item", None), "descriptor", None)
            hints = getattr(descriptor, "ui_hints", None)
            value = getattr(hints, "badge", None)
            return value if isinstance(value, str) and value else None
        return None

    return badge


@dataclass(frozen=True, slots=True)
class PresetScan:
    """프리셋 항목을 훑은 결과(쓰지 않는다). ``ok``가 거짓이면 항목을 읽지 못했다."""

    backends: tuple[str, ...] = ()
    graph_ids: frozenset[str] = frozenset()
    ok: bool = True


def scan_preset(
    preset: Preset,
    *,
    kinds: Iterable[DefinitionKind] = DEFAULT_KINDS,
    backend_key: str = BACKEND_KEY,
) -> PresetScan:
    """항목 파일을 읽어 쓰는 실행 백엔드 이름과 팀 구성 id를 모은다.

    항목을 읽지 못하면(형식 오류) 경고 로그를 남기고 ``PresetScan(ok=False)``.
    """
    try:
        items = load_items(preset, kinds=kinds)
    except PresetError as exc:
        _log.warning("프리셋 %s 항목을 읽지 못해 배지·시작 팀 구성을 비웁니다: %s", preset.id, exc)
        return PresetScan(ok=False)
    return PresetScan(
        backends=tuple(collect_values(items, backend_key)),
        graph_ids=frozenset(i.id for i in items if i.kind == GRAPH_KIND.name),
    )


def _fingerprint(preset: Preset) -> tuple[tuple[str, int, int], ...]:
    """매니페스트·항목 파일의 (경로, 수정 시각, 크기). 없는 파일은 (-1, -1)."""
    files = [preset.directory / MANIFEST_FILE]
    for ref in preset.manifest.item_refs():
        try:
            files.append(preset.resolve(ref.file))
        except PresetError:
            continue
    out: list[tuple[str, int, int]] = []
    for path in files:
        try:
            st = path.stat()
            out.append((str(path), st.st_mtime_ns, st.st_size))
        except OSError:
            out.append((str(path), -1, -1))
    return tuple(out)


class ScanCache:
    """``scan_preset`` 결과를 파일 수정 시각·크기로 기억한다(요청마다 YAML을 다시 읽지 않게).

    파일이 바뀌면 다시 읽는다. 배지 글자는 매번 ``backend_badge``로 다시 계산한다.
    """

    def __init__(self) -> None:
        self._entries: dict[str, tuple[tuple[tuple[str, int, int], ...], PresetScan]] = {}

    def scan(
        self,
        preset: Preset,
        *,
        kinds: Iterable[DefinitionKind] = DEFAULT_KINDS,
        backend_key: str = BACKEND_KEY,
    ) -> PresetScan:
        key = str(preset.directory.resolve())
        stamp = _fingerprint(preset)
        hit = self._entries.get(key)
        if hit is not None and hit[0] == stamp:
            return hit[1]
        result = scan_preset(preset, kinds=kinds, backend_key=backend_key)
        self._entries[key] = (stamp, result)
        return result


def summarize(
    preset: Preset,
    *,
    backend_badge: BackendBadge = _no_badge,
    kinds: Iterable[DefinitionKind] = DEFAULT_KINDS,
    backend_key: str = BACKEND_KEY,
    scan: PresetScan | None = None,
) -> PresetSummary:
    """프리셋 하나 → 계약 ``PresetSummary``.

    - ``badges`` = 매니페스트 ``badges`` + 항목이 쓰는 실행 백엔드의 배지(``backend_badge``),
      중복 없음.
    - ``featured`` = 매니페스트 값 그대로.
    - ``start_graph`` = 매니페스트 ``start_graph``(생략하면 ``default_entry``). 프리셋 항목에
      그 id의 팀 구성이 없으면 ``None``(웹이 없는 팀 구성을 열지 않게).

    ``scan``을 주지 않으면 ``scan_preset``으로 항목을 읽는다. 항목을 읽지 못하면 백엔드 배지와
    ``start_graph``를 비운다.
    """
    m = preset.manifest
    refs = m.item_refs()
    found = scan if scan is not None else scan_preset(preset, kinds=kinds, backend_key=backend_key)
    badges: dict[str, None] = dict.fromkeys(b for b in m.badges if b)
    for backend in found.backends:
        badge = backend_badge(backend)
        if badge:
            badges.setdefault(badge, None)
    start_graph = m.start_graph_id()
    if start_graph is not None and start_graph not in found.graph_ids:
        if found.ok:
            _log.warning("프리셋 %s: start_graph %r 팀 구성이 항목에 없습니다", m.id, start_graph)
        start_graph = None
    return PresetSummary(
        id=m.id,
        name=m.name,
        description=m.description,
        labels=list(m.labels),
        item_count=len(refs),
        items=[r.model_dump(exclude_none=True) for r in refs],
        badges=list(badges),
        featured=m.featured,
        start_graph=start_graph,
    )


def list_presets(
    search_paths: Iterable[Path],
    *,
    backend_badge: BackendBadge = _no_badge,
    kinds: Iterable[DefinitionKind] = DEFAULT_KINDS,
    cache: ScanCache | None = None,
) -> list[PresetSummary]:
    """프리셋 폴더의 프리셋 요약(문제 있는 폴더는 건너뜀). 프리셋이 없어도 빈 목록.

    순서는 발견 순서다. "바로 시작" 순서는 각 요약의 ``featured``(데이터)로 화면이 정한다.
    ``cache``를 주면 바뀌지 않은 프리셋의 항목을 다시 읽지 않는다.
    """
    kind_list = list(kinds)
    out: list[PresetSummary] = []
    for preset in discover(search_paths):
        scan = (
            cache.scan(preset, kinds=kind_list)
            if cache is not None
            else scan_preset(preset, kinds=kind_list)
        )
        out.append(summarize(preset, backend_badge=backend_badge, scan=scan))
    return out


def to_result(report: ApplyReport) -> ApplyPresetResult:
    """``ApplyReport`` → 계약 ``ApplyPresetResult``."""
    return ApplyPresetResult(
        preset_id=report.preset_id,
        items=[
            AppliedItemInfo(
                source=i.source,
                kind=i.kind,
                id=i.id,
                target_id=i.target_id,
                action=i.action,
                error=i.error,
            )
            for i in report.items
        ],
        warnings=list(report.warnings),
    )


def item_validator(checks: Callable[[], Sequence[DefinitionCheck]]) -> ItemValidator:
    """``definitions.checks`` → ac-presets ``validate_item``.

    error 이슈를 ``코드(path)`` 문자열로 바꾼다(값은 담지 않는다).
    """

    def check(kind: str, document: Mapping[str, Any]) -> list[str]:
        return [
            f"{i.code}({i.path or ''})"
            for c in checks()
            for i in c.issues(kind, document)
            if i.severity == "error"
        ]

    return check


def item_dependencies(
    source: Callable[[], DocumentDependencies | None],
) -> ItemDependencies:
    """``definitions.dependencies`` → ac-presets ``dependencies``(없으면 의존 없음)."""

    def uses(kind: str, document: Mapping[str, Any]) -> list[tuple[str, str]]:
        provider = source()
        if provider is None:
            return []
        return [(d.kind, d.id) for d in provider.dependencies_of(kind, document)]

    return uses


def store_kinds(store: DefinitionStore, kinds: Iterable[DefinitionKind]) -> list[DefinitionKind]:
    """``kinds`` 중 저장소에 등록된 종류(항목 경로 → 종류 해석용)."""
    names = set(store.kinds())
    return [k for k in kinds if k.name in names]


class PresetService:
    """프리셋 폴더에서 찾아 정의 저장소로 적용한다.

    Args:
        store: 대상 정의 저장소(``definitions.store``).
        search_paths: 프리셋 폴더(앞쪽 우선).
        checks: 저장 전 검사 목록을 돌려주는 함수(``definitions.checks``, 없으면 빈 목록).
        on_conflict: 기본 충돌 정책.
        dependencies: 문서가 쓰는 정의를 돌려주는 함수(``definitions.dependencies``). 있으면 쓰는
            정의부터 적용한다. 없거나 None을 돌려주면 매니페스트 순서.
        kinds: 항목 경로 → 종류 해석 후보(저장소에 등록된 것만 쓴다). 기본 ``DEFAULT_KINDS``.
        backend_badge: 실행 백엔드 이름 → 배지 글자(요약 ``badges``). 없으면 백엔드 배지를
            싣지 않는다.
    """

    def __init__(
        self,
        store: DefinitionStore,
        search_paths: Sequence[Path],
        *,
        checks: Callable[[], Sequence[DefinitionCheck]] = lambda: (),
        on_conflict: ConflictPolicy = "skip",
        dependencies: Callable[[], DocumentDependencies | None] = lambda: None,
        kinds: Iterable[DefinitionKind] = DEFAULT_KINDS,
        backend_badge: BackendBadge = _no_badge,
    ) -> None:
        self._store = store
        self._paths = list(search_paths)
        self._checks = checks
        self._on_conflict: ConflictPolicy = on_conflict
        self._dependencies = dependencies
        self._kinds = list(kinds)
        self._backend_badge = backend_badge
        self._scan_cache = ScanCache()

    @property
    def search_paths(self) -> list[Path]:
        return list(self._paths)

    def presets(self) -> list[PresetSummary]:
        """프리셋 요약 목록."""
        return list_presets(
            self._paths,
            backend_badge=self._backend_badge,
            kinds=store_kinds(self._store, self._kinds),
            cache=self._scan_cache,
        )

    def apply(
        self,
        preset_ids: Sequence[str],
        *,
        on_conflict: ConflictPolicy | None = None,
        stamp: Stamp | None = None,
    ) -> list[ApplyReport]:
        """``preset_ids`` 순서대로 적용한다(모두 찾은 뒤 쓰기 시작한다).

        ``stamp``는 쓰는 항목마다 찍을 최상위 필드다(``ac-presets`` ``apply_preset(stamp=)``,
        예: ``scope_stamp(project)``).

        Raises:
            PresetNotFoundError: 어떤 id가 없을 때(아무것도 적용하지 않는다).
            agent_console_presets.PresetError: 프리셋 항목 형식 오류.
        """
        by_id = {p.id: p for p in reversed(discover(self._paths))}  # 앞 경로 우선
        presets: list[Preset] = []
        for preset_id in preset_ids:
            preset = by_id.get(preset_id)
            if preset is None:
                raise PresetNotFoundError(f"프리셋을 찾을 수 없습니다: {preset_id}")
            presets.append(preset)
        kinds = store_kinds(self._store, self._kinds)
        validate = item_validator(self._checks)
        uses = item_dependencies(self._dependencies)
        reports: list[ApplyReport] = []
        for preset in presets:
            report = apply_preset(
                preset,
                self._store,
                kinds=kinds,
                on_conflict=on_conflict or self._on_conflict,
                validate_item=validate,
                dependencies=uses,
                stamp=stamp,
            )
            _log_report(preset.id, report)
            reports.append(report)
        return reports


def scope_stamp(project: str | None) -> Stamp | None:
    """요청 ``project`` → 만든 정의에 찍을 범위 필드(``None`` = 찍지 않음 = 공용, 지금과 같음)."""
    return {SCOPE_FIELD: project} if project else None


def _log_report(preset_id: str, report: ApplyReport) -> None:
    for item in report.items:
        _log.info(
            "프리셋 %s: %s/%s → %s (%s)", preset_id, item.kind, item.id, item.target_id, item.action
        )
        if item.action == "failed":
            _log.warning("프리셋 %s: %s/%s 실패 (%s)", preset_id, item.kind, item.id, item.error)
    for warning in report.warnings:
        _log.warning("프리셋 %s: %s", preset_id, warning)


__all__ = [
    "BACKEND_KEY",
    "BackendBadge",
    "PresetNotFoundError",
    "PresetScan",
    "PresetService",
    "ScanCache",
    "discover",
    "item_dependencies",
    "item_validator",
    "list_presets",
    "registry_backend_badge",
    "scan_preset",
    "scope_stamp",
    "store_kinds",
    "summarize",
    "to_result",
]
