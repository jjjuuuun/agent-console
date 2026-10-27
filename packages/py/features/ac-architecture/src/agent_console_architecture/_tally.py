"""구조도 누적 집계(증분 투영, design §5.5R.10 `[5.5R.36]`).

`project_architecture`는 이벤트 목록 전체를 한 번에 센다. 수집이 이어지는 범위를 다시 그릴 때는
이미 센 것을 다시 셀 필요가 없다. `ArchitectureTally`는 칸·연결·분류 안 됨·묶음마다 **출처 id별**
누적 값(수·오류·소요 값·응답 키)을 들고 있다가, 새 이벤트만 더하고(`add_event`·`add_row`) 부를 때
`view`로 그리기 완결형 `ArchitectureView`를 만든다.

- 출처 우선순위·수집 범위(`coverage`)는 출처 종류에 달렸고 출처 종류는 `view`의 인자다. 누적은
  출처 id별로 나눠 두므로 출처 종류가 바뀌어도 다시 셀 필요가 없다.
- 프로필·연산자·오류 범주가 바뀌면 판정 결과(`EventMatch`)가 달라진다 — 새 누적을 만든다.
- `inferred_duration` 지표(`options.inferred_llm_duration`)는 같은 thread의 앞 이벤트까지 간격이라
  이벤트마다 (thread, 시각, 순번, 응답 키)를 따로 기억하고 `view`에서 간격을 계산한다.
- 소요 합은 `math.fsum`(더하는 순서와 상관없이 같은 값)이다.

`project_architecture`도 이 누적을 한 번 채워 `view`를 부른다(같은 계산 한 벌).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

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

from ._match import EventMatch, is_observed_kind
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

PLAN_LIMIT: Final = 4096
"""(판정 결과, 출처)별로 기억할 "더할 누적 목록" 수. 넘으면 새 것은 매번 찾는다."""

_GROUP_PLACEHOLDER: Final = "{group}"

_OBSERVED: Final = "observed"
_PARTIAL: Final = "partial"
_NOT_COLLECTED: Final = "not_collected"
_INFERRED: Final = "inferred"

type _Light = tuple[str, float | None, int, str]
"""inferred_duration용 이벤트 요약: (thread, 시각, 순번, 응답 키)."""


@dataclass(slots=True)
class _Bucket:
    """대상 하나(칸·연결·분류 안 됨·묶음)와 출처 id 하나의 누적."""

    count: int = 0
    errors: int = 0
    durations: list[float] = field(default_factory=list)
    responses: set[tuple[str, str]] = field(default_factory=set)
    members: list[int] | None = None


@dataclass(slots=True)
class _Merged:
    """출처 우선순위로 남긴 출처들의 누적을 합친 것(지표 계산 입력)."""

    count: int = 0
    errors: int = 0
    durations: list[float] = field(default_factory=list)
    responses: set[tuple[str, str]] = field(default_factory=set)
    members: list[int] = field(default_factory=list)

    def take(self, bucket: _Bucket) -> None:
        self.count += bucket.count
        self.errors += bucket.errors
        self.durations.extend(bucket.durations)
        self.responses |= bucket.responses
        if bucket.members:
            self.members.extend(bucket.members)


type _BySource = dict[str, _Bucket]


def _not_collected() -> ArchitectureMetric:
    return ArchitectureMetric(status=_NOT_COLLECTED, value=None)


def _detail(values: Sequence[float]) -> ArchitectureMetricDetail:
    total = math.fsum(values)
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


def _gaps(light: Sequence[_Light]) -> dict[int, float]:
    """응답 첫 행 → 같은 thread의 바로 앞 이벤트까지 간격(ms). 시각이 없는 이벤트는 빠진다."""
    by_thread: dict[str, list[int]] = {}
    for i, (thread, when, _seq, _key) in enumerate(light):
        if when is not None:
            by_thread.setdefault(thread, []).append(i)
    gaps: dict[int, float] = {}
    for order in by_thread.values():
        order.sort(key=lambda i: (light[i][1] or 0.0, light[i][2]))
        for pos, i in enumerate(order):
            if pos > 0 and light[order[pos - 1]][3] == light[i][3]:
                continue  # 응답 첫 행이 아니다
            prev = pos - 1
            if prev < 0:
                continue
            gap = ((light[i][1] or 0.0) - (light[order[prev]][1] or 0.0)) * 1000
            if gap >= 0:
                gaps[i] = gap
    return gaps


@dataclass(slots=True)
class _ViewInputs:
    """`view` 한 번의 공유 재료(출처 순위·토큰·간격)."""

    source_kinds: Mapping[str, str]
    priority: Mapping[str, int]
    tokens: Mapping[tuple[str, str], TokenSample]
    inferred: bool
    light: Sequence[_Light]
    _gaps: dict[int, float] | None = None

    def rank(self, source: str) -> int:
        kind = self.source_kinds.get(source)
        last = len(self.priority)
        return last if kind is None else self.priority.get(kind, last)

    def gaps(self) -> dict[int, float]:
        if self._gaps is None:
            self._gaps = _gaps(self.light)
        return self._gaps

    def prioritize(self, by_source: Mapping[str, _Bucket]) -> tuple[list[str], list[str] | None]:
        """출처 우선순위: 맞은 이벤트의 출처 종류 중 목록 앞의 것만 남긴다.

        Returns:
            (남긴 출처 id, 선택 필터에 실을 출처 id). 하나도 빼지 않았으면 둘째는 None(거르지 않음).
        """
        matched = [s for s, b in by_source.items() if b.count]
        if not matched:
            return [], None
        ranks = {s: self.rank(s) for s in matched}
        best = min(ranks.values())
        kept = [s for s in matched if ranks[s] == best]
        if len(kept) == len(matched):
            return kept, None
        return kept, sorted(kept)


def _merge(by_source: Mapping[str, _Bucket], kept: Iterable[str]) -> _Merged:
    out = _Merged()
    for source in kept:
        bucket = by_source.get(source)
        if bucket is not None:
            out.take(bucket)
    return out


def _metric(name: str, merged: _Merged, inputs: _ViewInputs) -> ArchitectureMetric:
    if name == KnownArchitectureMetrics.COUNT:
        return ArchitectureMetric(status=_OBSERVED, value=merged.count)
    if name == KnownArchitectureMetrics.ERRORS:
        return ArchitectureMetric(status=_OBSERVED, value=merged.errors)
    if name == KnownArchitectureMetrics.DURATION:
        if not merged.durations:
            return _not_collected()
        detail = _detail(merged.durations)
        return ArchitectureMetric(status=_OBSERVED, value=detail.avg_ms, detail=detail)
    if name == KnownArchitectureMetrics.TOKENS:
        totals = [
            t
            for t in (
                _token_total(inputs.tokens[k]) for k in merged.responses if k in inputs.tokens
            )
            if t is not None
        ]
        if not totals:
            return _not_collected()
        return ArchitectureMetric(status=_OBSERVED, value=sum(totals))
    # inferred_duration: 응답(thread, 응답 키)마다 첫 행 하나의 간격만 쓴다.
    gaps = inputs.gaps()
    light = inputs.light
    firsts: dict[tuple[str, str], int] = {}
    for i in merged.members:
        if i not in gaps:
            continue
        thread, when, seq, key = light[i]
        response = (thread, key)
        old = firsts.get(response)
        if old is None or (when or 0.0, seq) < (light[old][1] or 0.0, light[old][2]):
            firsts[response] = i
    values = [gaps[i] for i in firsts.values()]
    if not values:
        return _not_collected()
    detail = _detail(values)
    return ArchitectureMetric(status=_INFERRED, value=detail.avg_ms, detail=detail)


def _metrics(
    names: Sequence[str] | None,
    merged: _Merged,
    inputs: _ViewInputs,
    status: ArchitectureItemStatus,
) -> dict[str, ArchitectureMetric]:
    out: dict[str, ArchitectureMetric] = {}
    for name in names if names is not None else DEFAULT_METRICS:
        if name not in KNOWN_METRICS or name in out:
            continue
        if name == KnownArchitectureMetrics.INFERRED_DURATION and not inputs.inferred:
            continue
        out[name] = _not_collected() if status == _NOT_COLLECTED else _metric(name, merged, inputs)
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


def _total(by_source: Mapping[str, _Bucket]) -> int:
    return sum(b.count for b in by_source.values())


def _groups(
    cell: ArchitectureCell,
    by_group: Mapping[str | None, _BySource],
    kept: Sequence[str],
    inputs: _ViewInputs,
    status: ArchitectureItemStatus,
    arch: str,
    sources: list[str] | None,
    limit: int,
) -> tuple[list[ArchitectureGroupView], ArchitectureGroupRest | None]:
    if status == _NOT_COLLECTED:
        return [], None
    merged = [(key, _merge(per, kept)) for key, per in by_group.items()]
    merged = [(key, m) for key, m in merged if m.count]
    order = sorted(merged, key=lambda kv: (-kv[1].count, kv[0] is None, kv[0] or ""))
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
                metrics=_metrics(cell.metrics, members, inputs, status),
                selector=ArchitectureSelector(
                    arch=arch, arch_group=key if key is not None else "", arch_sources=sources
                ),
                drill=drill,
            )
        )
    rest_view = None
    if rest:
        together = _Merged()
        for _key, part in rest:
            together.count += part.count
            together.errors += part.errors
            together.durations.extend(part.durations)
            together.responses |= part.responses
            together.members.extend(part.members)
        rest_view = ArchitectureGroupRest(
            groups=len(rest), metrics=_metrics(cell.metrics, together, inputs, status)
        )
    return views, rest_view


class ArchitectureTally:
    """구조도 누적 집계: 판정한 이벤트를 하나씩 더하고, 부를 때 구조도를 만든다(증분 투영).

    같은 이벤트 목록을 순서대로 더한 뒤의 `view(...)`는 같은 인자의
    `project_architecture(events, ..., matches=)` 결과와 같다(그 함수도 이것을 쓴다). 순번(`seq`)
    오름차순으로 더하지 않아도 되지만, 같은 이벤트를 두 번 더하면 두 번 센다(호출자가 막는다).
    스레드 안전하지 않다 — 호출자가 잠근다.

    Args:
        profile: 프로필(판정 결과 `EventMatch`를 만든 것과 같은 프로필).
        profile_id: 프로필 id(선택 필터 `arch`에 쓴다).
    """

    def __init__(self, profile: ArchitectureProfile, *, profile_id: str) -> None:
        self.profile = profile
        self.profile_id = profile_id
        self._inferred = bool(profile.options and profile.options.inferred_llm_duration)
        self._grouped = frozenset(c for c, cell in profile.cells.items() if cell.group_by)
        self._cells: dict[str, _BySource] = {}
        self._groups: dict[str, dict[str | None, _BySource]] = {}
        self._edges: dict[str, _BySource] = {}
        self._lonely: _BySource = {}
        self._sources: dict[str, int] = {}
        self._light: list[_Light] = []
        self._plans: dict[tuple[int, str], tuple[EventMatch, tuple[_Bucket, ...]]] = {}
        self._count = 0
        self._max_seq: int | None = None

    @property
    def events(self) -> int:
        """더한 이벤트 수."""
        return self._count

    @property
    def max_seq(self) -> int | None:
        """더한 이벤트의 가장 큰 순번(없으면 None)."""
        return self._max_seq

    def add_event(self, event: LogEvent, match: EventMatch) -> None:
        """이벤트 하나와 그 판정 결과를 더한다."""
        self._add(
            event.seq,
            event.source,
            event.uid,
            event.thread,
            event.message_id,
            event.time,
            event.duration_ms,
            match,
        )

    def add_row(self, row: Mapping[str, Any], match: EventMatch) -> None:
        """이벤트 JSON 행(`LogEvent`를 계약 별칭으로 JSON 덤프한 모양)과 판정 결과를 더한다.

        쓰는 키: `seq`·`source`·`uid`·`thread`·`message_id`·`time`·`duration_ms`(없으면 기본값).
        """
        self._add(
            row["seq"],
            row["source"],
            row["uid"],
            row.get("thread", ""),
            row.get("message_id", ""),
            row.get("time"),
            row.get("duration_ms"),
            match,
        )

    def _add(
        self,
        seq: int,
        source: str,
        uid: str,
        thread: str,
        message_id: str,
        when: float | None,
        duration: float | None,
        match: EventMatch,
    ) -> None:
        position: int | None = None
        if self._inferred:
            position = len(self._light)
            self._light.append((thread, when, seq, message_id or f"#{uid}"))
        self._count += 1
        if self._max_seq is None or seq > self._max_seq:
            self._max_seq = seq
        self._sources[source] = self._sources.get(source, 0) + 1
        # 같은 판정 결과(판정기가 나눠 쓰는 객체)·출처면 더할 누적들이 같다 — 한 번 찾아 기억한다
        slot = (id(match), source)
        plan = self._plans.get(slot)
        if plan is None or plan[0] is not match:
            plan = (match, self._targets(match, source))
            if len(self._plans) < PLAN_LIMIT:
                self._plans[slot] = plan
        error = match.error
        response = (thread, message_id) if message_id else None
        for bucket in plan[1]:
            bucket.count += 1
            if error:
                bucket.errors += 1
            if duration is not None:
                bucket.durations.append(duration)
            if response is not None:
                bucket.responses.add(response)
            if position is not None:
                if bucket.members is None:
                    bucket.members = []
                bucket.members.append(position)

    def _targets(self, match: EventMatch, source: str) -> tuple[_Bucket, ...]:
        """판정 결과 하나·출처 하나가 더해질 누적들(칸·묶음·연결·분류 안 됨)."""
        found: list[_Bucket] = []
        for cid in match.cells:
            found.append(_bucket(self._cells, cid, source))
            if cid in self._grouped:
                per = self._groups.setdefault(cid, {})
                key = match.groups.get(cid)
                by_source = per.get(key)
                if by_source is None:
                    by_source = per[key] = {}
                bucket = by_source.get(source)
                if bucket is None:
                    bucket = by_source[source] = _Bucket()
                found.append(bucket)
        for eid in match.edges:
            found.append(_bucket(self._edges, eid, source))
        if not match.cells:
            bucket = self._lonely.get(source)
            if bucket is None:
                bucket = self._lonely[source] = _Bucket()
            found.append(bucket)
        return tuple(found)

    def view(
        self,
        *,
        source_kinds: Mapping[str, str] | None = None,
        tokens: Iterable[TokenSample] = (),
        notes: Iterable[ArchitectureNote] = (),
        cell_size: tuple[float, float] = DEFAULT_CELL_SIZE,
    ) -> ArchitectureView:
        """지금까지 더한 이벤트의 구조도(누적은 그대로 — 더 더하고 다시 부를 수 있다).

        Args:
            source_kinds: 로그 출처 id → 출처 종류. 없는 출처는 종류를 모른다(우선순위 맨 뒤).
            tokens: 토큰 표본(응답 (thread, message_id)마다 한 번 센다).
            notes: 결과에 그대로 실을 안내.
            cell_size: 칸 크기를 비운 칸의 기본 (폭, 높이).
        """
        profile, profile_id = self.profile, self.profile_id
        kinds = dict(source_kinds or {})
        priority: dict[str, int] = {}
        for kind in profile.source_priority:
            priority.setdefault(kind, len(priority))
        inputs = _ViewInputs(
            source_kinds=kinds,
            priority=priority,
            tokens=_token_index(tokens),
            inferred=self._inferred,
            light=self._light,
        )
        present = sorted(
            {kinds[s] for s in self._sources if s in kinds},
            key=lambda k: (priority.get(k, len(priority)), k),
        )
        present = [k for k in present if k in profile.coverage]

        cell_views: list[ArchitectureCellView] = []
        unavailable: list[ArchitectureUnavailableView] = []
        statuses: dict[str, tuple[ArchitectureItemStatus, str | None]] = {}
        empty: _BySource = {}
        for cid, cell in profile.cells.items():
            by_source = self._cells.get(cid, empty)
            kept, sources = inputs.prioritize(by_source)
            status, reason = _cell_status(profile, cid, present, _total(by_source))
            statuses[cid] = (status, reason)
            arch = format_arch(profile_id, KnownArchitectureTargets.CELL, cid)
            groups: list[ArchitectureGroupView] | None = None
            rest: ArchitectureGroupRest | None = None
            if cell.group_by is not None:
                groups, rest = _groups(
                    cell,
                    self._groups.get(cid, {}),
                    kept,
                    inputs,
                    status,
                    arch,
                    sources,
                    profile.group_limit,
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
                    metrics=_metrics(cell.metrics, _merge(by_source, kept), inputs, status),
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
            by_source = self._edges.get(edge.id, empty) if observed else empty
            kept, sources = inputs.prioritize(by_source)
            status, reason = _edge_status(edge, _total(by_source), statuses)
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
                        "metrics": (
                            _metrics(edge.metrics, _merge(by_source, kept), inputs, status)
                            if observed
                            else {}
                        ),
                        "selector": (
                            ArchitectureSelector(
                                arch=format_arch(
                                    profile_id, KnownArchitectureTargets.EDGE, edge.id
                                ),
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
            kept, sources = inputs.prioritize(self._lonely)
            unassigned_view = ArchitectureUnassignedView(
                metrics=_metrics(None, _merge(self._lonely, kept), inputs, _OBSERVED),
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
                for sid, n in sorted(self._sources.items())
            ],
            event_total=self._count,
            max_seq=self._max_seq,
            notes=all_notes,
        )


def _bucket(table: dict[str, _BySource], target: str, source: str) -> _Bucket:
    by_source = table.get(target)
    if by_source is None:
        by_source = table[target] = {}
    found = by_source.get(source)
    if found is None:
        found = by_source[source] = _Bucket()
    return found
