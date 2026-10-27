"""로그 이벤트 + 프로필 → 구조도(`ArchitectureView`, 순수 함수, design §5.5R.2.3).

지표 계산 규칙 5개(`count`·`errors`·`duration`·`tokens`·`inferred_duration`)는 코드다(K-7). 어느 칸·
연결이 어떤 지표를 보일지, 무엇을 셀지, 어떤 출처가 어떤 칸을 채우는지는 전부 프로필 데이터다.
값이 없으면 0이 아니라 `not_collected`(null)다(R8.8).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from agent_console_conditions import ConditionOperator
from agent_console_contracts.architecture import (
    ArchitectureCell,
    ArchitectureCellView,
    ArchitectureDrillTarget,
    ArchitectureEdge,
    ArchitectureEdgeView,
    ArchitectureGroupRest,
    ArchitectureGroupView,
    ArchitectureItemStatus,
    ArchitectureMetric,
    ArchitectureMetricDetail,
    ArchitectureNote,
    ArchitectureProfile,
    ArchitectureSelector,
    ArchitectureSourceCount,
    ArchitectureUnassignedView,
    ArchitectureUnavailableView,
    ArchitectureView,
    KnownArchitectureEdgeKinds,
    KnownArchitectureMetrics,
    KnownArchitectureNoteCodes,
    KnownArchitectureTargets,
)
from agent_console_contracts.logs import LogEvent, TokenSample

from ._match import EventMatch, ProfileMatcher, event_subject, is_observed_kind
from ._selector import format_arch

DEFAULT_CELL_SIZE: Final = (180.0, 68.0)
"""칸 크기를 프로필에서 비웠을 때 쓰는 기본 폭·높이(px, agent_bench 카드 크기)."""

DEFAULT_METRICS: Final = (KnownArchitectureMetrics.COUNT, KnownArchitectureMetrics.ERRORS)
"""보일 지표를 비웠을 때(칸·연결·분류 안 됨)."""

KNOWN_METRICS: Final = frozenset(
    {
        KnownArchitectureMetrics.COUNT,
        KnownArchitectureMetrics.ERRORS,
        KnownArchitectureMetrics.DURATION,
        KnownArchitectureMetrics.TOKENS,
        KnownArchitectureMetrics.INFERRED_DURATION,
    }
)
"""계산 규칙이 있는 지표 이름. 모르는 이름은 투영에서 빠지고 프로필 검사가 알린다."""

_GROUP_PLACEHOLDER: Final = "{group}"

_OBSERVED: Final = "observed"
_PARTIAL: Final = "partial"
_NOT_COLLECTED: Final = "not_collected"
_INFERRED: Final = "inferred"


def _not_collected() -> ArchitectureMetric:
    return ArchitectureMetric(status=_NOT_COLLECTED, value=None)


def _detail(values: Sequence[float]) -> ArchitectureMetricDetail:
    total = float(sum(values))
    return ArchitectureMetricDetail(
        samples=len(values), total_ms=total, avg_ms=total / len(values), max_ms=float(max(values))
    )


def _token_total(sample: TokenSample) -> int | None:
    parts = [
        v
        for v in (
            sample.input_tokens,
            sample.output_tokens,
            sample.cache_read_input_tokens,
            sample.cache_creation_input_tokens,
        )
        if v is not None
    ]
    return sum(parts) if parts else None


def _token_index(tokens: Iterable[TokenSample]) -> dict[tuple[str, str], TokenSample]:
    # 같은 응답(thread, message_id)의 표본이 여럿이면 출력 토큰이 큰 것 하나만 쓴다(F-8, 색인과 같은
    # 규칙: 스트리밍 중간 행보다 마지막 행이 크다).
    found: dict[tuple[str, str], TokenSample] = {}
    for sample in tokens:
        if not sample.message_id:
            continue
        key = (sample.thread, sample.message_id)
        old = found.get(key)
        if old is None or (sample.output_tokens or -1) > (old.output_tokens or -1):
            found[key] = sample
    return found


@dataclass(slots=True)
class _Scope:
    """투영 한 번의 공유 재료(이벤트·판정·출처 순위·토큰·추정 소요)."""

    events: list[LogEvent]
    matches: list[EventMatch]
    source_kinds: Mapping[str, str]
    priority: Mapping[str, int]
    tokens: Mapping[tuple[str, str], TokenSample]
    inferred: bool
    _gaps: dict[int, float] | None = field(default=None)

    def rank(self, index: int) -> int:
        kind = self.source_kinds.get(self.events[index].source)
        last = len(self.priority)
        return last if kind is None else self.priority.get(kind, last)

    def prioritize(self, indices: Sequence[int]) -> tuple[list[int], list[str] | None]:
        """출처 우선순위: 맞은 이벤트의 출처 종류 중 목록 앞의 것만 남긴다.

        Returns:
            (남긴 이벤트, 선택 필터에 실을 출처 id). 하나도 빼지 않았으면 출처는 None(거르지 않음).
        """
        if not indices:
            return [], None
        ranks = [self.rank(i) for i in indices]
        best = min(ranks)
        kept = [i for i, r in zip(indices, ranks, strict=True) if r == best]
        if len(kept) == len(indices):
            return kept, None
        return kept, sorted({self.events[i].source for i in kept})

    def gaps(self) -> dict[int, float]:
        """응답 첫 행 → 같은 thread의 바로 앞 이벤트까지 간격(ms). 시각이 없는 이벤트는 빠진다."""
        if self._gaps is not None:
            return self._gaps
        by_thread: dict[str, list[int]] = {}
        for i, event in enumerate(self.events):
            if event.time is not None:
                by_thread.setdefault(event.thread, []).append(i)
        gaps: dict[int, float] = {}
        for order in by_thread.values():
            order.sort(key=lambda i: (self.events[i].time or 0.0, self.events[i].seq))
            for pos, i in enumerate(order):
                key = self._message_key(i)
                if pos > 0 and self._message_key(order[pos - 1]) == key:
                    continue  # 응답 첫 행이 아니다
                prev = pos - 1
                if prev < 0:
                    continue
                gap = ((self.events[i].time or 0.0) - (self.events[order[prev]].time or 0.0)) * 1000
                if gap >= 0:
                    gaps[i] = gap
        self._gaps = gaps
        return gaps

    def _message_key(self, index: int) -> str:
        event = self.events[index]
        return event.message_id or f"#{event.uid}"


def _metric(name: str, indices: Sequence[int], scope: _Scope) -> ArchitectureMetric:
    events = [scope.events[i] for i in indices]
    if name == KnownArchitectureMetrics.COUNT:
        return ArchitectureMetric(status=_OBSERVED, value=len(indices))
    if name == KnownArchitectureMetrics.ERRORS:
        return ArchitectureMetric(
            status=_OBSERVED, value=sum(1 for i in indices if scope.matches[i].error)
        )
    if name == KnownArchitectureMetrics.DURATION:
        values = [e.duration_ms for e in events if e.duration_ms is not None]
        if not values:
            return _not_collected()
        detail = _detail(values)
        return ArchitectureMetric(status=_OBSERVED, value=detail.avg_ms, detail=detail)
    if name == KnownArchitectureMetrics.TOKENS:
        keys = {(e.thread, e.message_id) for e in events if e.message_id}
        totals = [
            t
            for t in (_token_total(scope.tokens[k]) for k in keys if k in scope.tokens)
            if t is not None
        ]
        if not totals:
            return _not_collected()
        return ArchitectureMetric(status=_OBSERVED, value=sum(totals))
    # inferred_duration: 응답(thread, message_id)마다 첫 행 하나의 간격만 쓴다.
    gaps = scope.gaps()
    firsts: dict[tuple[str, str], int] = {}
    for i in indices:
        if i not in gaps:
            continue
        event = scope.events[i]
        key = (event.thread, event.message_id or f"#{event.uid}")
        old = firsts.get(key)
        if old is None or (event.time or 0.0, event.seq) < (
            scope.events[old].time or 0.0,
            scope.events[old].seq,
        ):
            firsts[key] = i
    values = [gaps[i] for i in firsts.values()]
    if not values:
        return _not_collected()
    detail = _detail(values)
    return ArchitectureMetric(status=_INFERRED, value=detail.avg_ms, detail=detail)


def _metrics(
    names: Sequence[str] | None,
    indices: Sequence[int],
    scope: _Scope,
    status: ArchitectureItemStatus,
) -> dict[str, ArchitectureMetric]:
    out: dict[str, ArchitectureMetric] = {}
    for name in names if names is not None else DEFAULT_METRICS:
        if name not in KNOWN_METRICS or name in out:
            continue
        if name == KnownArchitectureMetrics.INFERRED_DURATION and not scope.inferred:
            continue
        out[name] = _not_collected() if status == _NOT_COLLECTED else _metric(name, indices, scope)
    return out


def _cell_status(
    profile: ArchitectureProfile, cell_id: str, present: Sequence[str], matched: int
) -> tuple[ArchitectureItemStatus, str | None]:
    """칸 수집 상태. 수집 범위가 없는 프로필은 모든 칸이 관측이다.

    이 범위의 출처 종류 중 그 칸을 채우는 것이 없고 맞은 이벤트도 없으면 `not_collected`.
    채우는 종류가 모두 그 칸을 부분으로 적었으면 `partial`(이유는 우선순위가 가장 앞인 종류의 것).
    """
    if not profile.coverage:
        return _OBSERVED, None
    covering = [k for k in present if cell_id in profile.coverage[k].cells]
    if not covering:
        return (_OBSERVED, None) if matched else (_NOT_COLLECTED, None)
    reasons = [profile.coverage[k].partial.get(cell_id) for k in covering]
    if all(r is not None for r in reasons):
        return _PARTIAL, reasons[0]
    return _OBSERVED, None


def _edge_status(
    edge: ArchitectureEdge,
    matched: int,
    cell_status: Mapping[str, tuple[ArchitectureItemStatus, str | None]],
) -> tuple[ArchitectureItemStatus, str | None]:
    """연결 수집 상태: 맞은 이벤트가 있으면 관측, 없으면 양 끝 칸 상태를 따른다."""
    if matched:
        return _OBSERVED, None
    ends = [cell_status[edge.from_], cell_status[edge.to]]
    for status in (_NOT_COLLECTED, _PARTIAL):
        for found, reason in ends:
            if found == status:
                return found, reason
    return _OBSERVED, None


def _groups(
    cell_id: str,
    cell: ArchitectureCell,
    kept: Sequence[int],
    scope: _Scope,
    status: ArchitectureItemStatus,
    arch: str,
    sources: list[str] | None,
    limit: int,
) -> tuple[list[ArchitectureGroupView], ArchitectureGroupRest | None]:
    if status == _NOT_COLLECTED:
        return [], None
    by_key: dict[str | None, list[int]] = {}
    for i in kept:
        by_key.setdefault(scope.matches[i].groups.get(cell_id), []).append(i)
    order = sorted(by_key.items(), key=lambda kv: (-len(kv[1]), kv[0] is None, kv[0] or ""))
    shown, rest = order[:limit], order[limit:]
    views: list[ArchitectureGroupView] = []
    for key, members in shown:
        drill = None
        if cell.drill is not None and key is not None:
            drill = ArchitectureDrillTarget(
                filter=cell.drill.filter, value=cell.drill.value.replace(_GROUP_PLACEHOLDER, key)
            )
        views.append(
            ArchitectureGroupView(
                key=key,
                status=status,
                metrics=_metrics(cell.metrics, members, scope, status),
                selector=ArchitectureSelector(
                    arch=arch, arch_group=key if key is not None else "", arch_sources=sources
                ),
                drill=drill,
            )
        )
    rest_view = None
    if rest:
        members = [i for _key, items in rest for i in items]
        rest_view = ArchitectureGroupRest(
            groups=len(rest), metrics=_metrics(cell.metrics, members, scope, status)
        )
    return views, rest_view


def project_architecture(
    events: Iterable[LogEvent],
    profile: ArchitectureProfile,
    *,
    profile_id: str,
    operators: Mapping[str, ConditionOperator],
    source_kinds: Mapping[str, str] | None = None,
    tokens: Iterable[TokenSample] = (),
    error_categories: Collection[str] = frozenset(),
    max_seq: int | None = None,
    notes: Iterable[ArchitectureNote] = (),
    cell_size: tuple[float, float] = DEFAULT_CELL_SIZE,
) -> ArchitectureView:
    """이벤트 목록을 프로필로 투영한다(순수 함수: 서버·색인·시계 없음).

    - 칸·연결: 프로필 조건에 맞는 이벤트를 센다. 한 이벤트가 여러 칸·연결에 맞을 수 있다.
      어느 칸에도 맞지 않으면 분류 안 됨(`profile.unassigned`일 때). 관측 연결은 그 전달을 기록한
      이벤트 하나를 세고, 시간상 이웃을 잇지 않는다(R8.6). 구조 연결은 지표가 없다.
    - 출처 우선순위(`source_priority`): 칸·연결마다 맞은 이벤트의 출처 종류 중 목록 앞의 것만 센다.
      쓴 출처 id는 `selector.arch_sources`에 실린다(클릭 필터가 같은 이벤트를 고른다).
    - 수집 범위(`coverage`): 이 범위의 출처 종류 중 칸을 채우는 것이 없으면 `not_collected`.
    - `max_seq`: 주면 순번이 그 이하인 이벤트만 센다(수집이 이어져도 클릭 필터와 수가 같다).

    Args:
        events: 범위의 로그 이벤트(계약 `LogEvent`).
        profile: 프로필.
        profile_id: 프로필 id(선택 필터 `arch`에 쓴다).
        operators: 조건 연산자(X22).
        source_kinds: 로그 출처 id → 출처 종류. 없는 출처는 종류를 모른다(우선순위 맨 뒤).
        tokens: 토큰 표본(응답 (thread, message_id)마다 한 번 센다).
        error_categories: 오류로 볼 범주 id(분류 체계에서 오류로 표시한 범주).
        max_seq: 셀 이벤트 순번 상한.
        notes: 결과에 그대로 실을 안내(예: `ProfileCatalog.pick`의 대체 안내).
        cell_size: 칸 크기를 비운 칸의 기본 (폭, 높이).

    Returns:
        그리기 완결형 `ArchitectureView`. 이벤트·칸이 없어도 예외 없이 빈 결과다.
    """
    kinds = dict(source_kinds or {})
    scoped = [e for e in events if max_seq is None or e.seq <= max_seq]
    matcher = ProfileMatcher(profile, operators, error_categories=error_categories)
    matches = [matcher.match_subject(event_subject(e)) for e in scoped]
    priority: dict[str, int] = {}
    for kind in profile.source_priority:
        priority.setdefault(kind, len(priority))
    scope = _Scope(
        events=scoped,
        matches=matches,
        source_kinds=kinds,
        priority=priority,
        tokens=_token_index(tokens),
        inferred=bool(profile.options and profile.options.inferred_llm_duration),
    )
    counts = Counter(e.source for e in scoped)
    present = sorted(
        {kinds[s] for s in counts if s in kinds},
        key=lambda k: (priority.get(k, len(priority)), k),
    )
    present = [k for k in present if k in profile.coverage]

    cell_views: list[ArchitectureCellView] = []
    unavailable: list[ArchitectureUnavailableView] = []
    statuses: dict[str, tuple[ArchitectureItemStatus, str | None]] = {}
    for cid, cell in profile.cells.items():
        matched = [i for i, m in enumerate(matches) if cid in m.cells]
        kept, sources = scope.prioritize(matched)
        status, reason = _cell_status(profile, cid, present, len(matched))
        statuses[cid] = (status, reason)
        arch = format_arch(profile_id, KnownArchitectureTargets.CELL, cid)
        groups: list[ArchitectureGroupView] | None = None
        rest: ArchitectureGroupRest | None = None
        if cell.group_by is not None:
            groups, rest = _groups(
                cid, cell, kept, scope, status, arch, sources, profile.group_limit
            )
        items = [
            ArchitectureUnavailableView(cell=cid, item=u.item, reason=u.reason)
            for u in cell.unavailable
        ]
        unavailable.extend(items)
        cell_views.append(
            ArchitectureCellView(
                id=cid,
                label=cell.label or cid,
                description=cell.description,
                x=cell.x,
                y=cell.y,
                w=cell.w or cell_size[0],
                h=cell.h or cell_size[1],
                zone=cell.zone,
                tone=cell.tone,
                view=cell.view,
                status=status,
                partial_reason=reason,
                metrics=_metrics(cell.metrics, kept, scope, status),
                selector=ArchitectureSelector(arch=arch, arch_sources=sources),
                groups=groups,
                groups_rest=rest,
                drillable=cell.drill is not None and cell.group_by is not None,
                unavailable=items,
            )
        )

    edge_views: list[ArchitectureEdgeView] = []
    seen: set[str] = set()
    skipped = 0
    for edge in profile.edges:
        if edge.id in seen or edge.from_ not in profile.cells or edge.to not in profile.cells:
            skipped += 1
            continue
        seen.add(edge.id)
        observed = is_observed_kind(edge.kind)
        matched = [i for i, m in enumerate(matches) if edge.id in m.edges] if observed else []
        kept, sources = scope.prioritize(matched)
        status, reason = _edge_status(edge, len(matched), statuses)
        edge_views.append(
            ArchitectureEdgeView.model_validate(
                {
                    "id": edge.id,
                    "from": edge.from_,
                    "to": edge.to,
                    "label": edge.label,
                    "kind": (
                        KnownArchitectureEdgeKinds.OBSERVED
                        if observed
                        else KnownArchitectureEdgeKinds.STRUCTURAL
                    ),
                    "style": edge.style,
                    "points": edge.points,
                    "label_at": edge.label_at,
                    "label_max_w": edge.label_max_w,
                    "status": status,
                    "partial_reason": reason,
                    "metrics": _metrics(edge.metrics, kept, scope, status) if observed else {},
                    "selector": (
                        ArchitectureSelector(
                            arch=format_arch(profile_id, KnownArchitectureTargets.EDGE, edge.id),
                            arch_sources=sources,
                        )
                        if observed
                        else None
                    ),
                }
            )
        )

    unassigned_view = None
    if profile.unassigned:
        kept, sources = scope.prioritize([i for i, m in enumerate(matches) if m.unassigned])
        unassigned_view = ArchitectureUnassignedView(
            metrics=_metrics(None, kept, scope, _OBSERVED),
            selector=ArchitectureSelector(
                arch=format_arch(profile_id, KnownArchitectureTargets.UNASSIGNED),
                arch_sources=sources,
            ),
        )

    all_notes = list(notes)
    if skipped:
        all_notes.append(
            ArchitectureNote(
                code=KnownArchitectureNoteCodes.PROFILE_ISSUES,
                message=(
                    f"프로필에 문제 {skipped}개가 있어 일부 연결이 빠졌습니다"
                    "(없는 칸을 가리키거나 id가 겹침)"
                ),
                details={"issues": skipped},
            )
        )
    return ArchitectureView(
        profile=profile_id,
        title=profile.title or profile_id,
        canvas=profile.canvas,
        zones=list(profile.zones),
        cells=cell_views,
        edges=edge_views,
        unassigned=unassigned_view,
        unavailable=unavailable,
        sources=[
            ArchitectureSourceCount(id=sid, kind=kinds.get(sid), events=n)
            for sid, n in sorted(counts.items())
        ],
        event_total=len(scoped),
        max_seq=max((e.seq for e in scoped), default=None),
        notes=all_notes,
    )
