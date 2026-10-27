/**
 * 로그 화면의 순수 함수(UI·서버 호출 없음): 기간 → 요청 필터, 이벤트 → 레인·범주 칩, 화면 전용 필터, 대시보드 저장 병합.
 * 출처·범주·차원·지표 이름을 모른다(받은 데이터와 `logsConfig`/`logsData.json`의 이름 표만 쓴다).
 */
import type { LogQueryParams } from "@agent-console/api-client";
import type { LogDashboard, LogEvent, LogLane, LogSettings, LogSourceInfo, LogWidget, WorkspaceSettings } from "@agent-console/contracts";
import { preserveUnknownDashboards, type CategoryChipItem, type LaneEvent, type LogFilterValue, type LogTaxonomyView } from "@agent-console/log-view";
import { CUSTOM_RANGE_SEP, FILTER_KEYS, RANGE_OPTIONS } from "./logsConfig";

// ---------------------------------------------------------------- 기간

export type ParsedRange = { kind: "option"; id: string; seconds: number | null } | { kind: "custom"; since: string | undefined; until: string | undefined };

/** `range` URL 값 → 선택지 또는 사용자 지정. 모르는 값은 `fallbackId` 선택지. */
export function parseRange(value: string | undefined, fallbackId: string): ParsedRange {
  const raw = value ?? fallbackId;
  const option = RANGE_OPTIONS.find((p) => p.id === raw);
  if (option !== undefined) return { kind: "option", id: option.id, seconds: option.seconds };
  if (raw.includes(CUSTOM_RANGE_SEP)) {
    const [since, until] = raw.split(CUSTOM_RANGE_SEP);
    return { kind: "custom", since: since || undefined, until: until || undefined };
  }
  const fallback = RANGE_OPTIONS.find((p) => p.id === fallbackId);
  return { kind: "option", id: fallbackId, seconds: fallback?.seconds ?? null };
}

/** 사용자 지정 기간의 `range` 값. */
export function customRangeValue(since: string | undefined, until: string | undefined): string {
  return `${since ?? ""}${CUSTOM_RANGE_SEP}${until ?? ""}`;
}

/** 기간 → 서버 `since`/`until`(epoch 초 문자열). `anchorMs`는 "지금" 기준(요청 키가 매 렌더 바뀌지 않게 호출자가 고정한다). */
export function rangeToWindow(range: ParsedRange, anchorMs: number): { since?: string; until?: string } {
  if (range.kind === "custom") return { ...(range.since ? { since: range.since } : {}), ...(range.until ? { until: range.until } : {}) };
  if (range.seconds === null) return {};
  return { since: String(Math.floor(anchorMs / 1000) - range.seconds) };
}

// ---------------------------------------------------------------- 필터 → 요청

/** 필터 값(+ 기간 + 추가 항목)을 서버 쿼리로. 이미 `since`/`until` 칩이 있으면 기간 선택지보다 우선한다. 빈 값은 보내지 않는다. */
export function toRequestParams(filter: LogFilterValue, extra: LogQueryParams = {}, window: { since?: string; until?: string } = {}): LogQueryParams {
  const sinceKey = FILTER_KEYS.since;
  const untilKey = FILTER_KEYS.until;
  const out: Record<string, string | readonly string[]> = {};
  for (const [k, v] of Object.entries(filter)) {
    const list = Array.isArray(v) ? v.filter((x) => x !== "") : v === "" ? [] : [v];
    if (list.length > 0) out[k] = list.length === 1 ? (list[0] as string) : list;
  }
  if (out[sinceKey] === undefined && window.since !== undefined) out[sinceKey] = window.since;
  if (out[untilKey] === undefined && window.until !== undefined) out[untilKey] = window.until;
  for (const [k, v] of Object.entries(extra)) if (v !== undefined && v !== null) out[k] = typeof v === "object" ? (v as readonly string[]) : String(v);
  return out;
}

/** 요청 파라미터의 안정 직렬화(질의 키). 이름 순. */
export function paramsKey(params: LogQueryParams): string {
  return Object.keys(params)
    .sort()
    .map((k) => {
      const v = params[k];
      return `${k}=${Array.isArray(v) ? (v as readonly string[]).join("\u0001") : String(v)}`;
    })
    .join("&");
}

/** 필터에서 이름 하나의 값 목록. */
export function valuesOf(filter: LogFilterValue, name: string): string[] {
  const v = filter[name];
  return v === undefined ? [] : Array.isArray(v) ? v : v === "" ? [] : [v];
}

/** 필터에서 이름 하나를 바꾼다(빈 목록이면 지운다). 새 객체. */
export function withValues(filter: LogFilterValue, name: string, values: readonly string[]): LogFilterValue {
  const next = { ...filter };
  if (values.length === 0) delete next[name];
  else next[name] = values.length === 1 ? (values[0] as string) : [...values];
  return next;
}

// ---------------------------------------------------------------- 이벤트 → 화면

/** 이벤트가 속한 레인 id(없으면 빈 문자열). 레인 = 서버가 준 `thread`. */
export function laneOf(event: Pick<LogEvent, "thread" | "actor">): string {
  return event.thread ?? event.actor ?? "";
}

/** 레인 id → 표시 이름(`LogTimeline.lanes[].label`, 없으면 id 원문). */
export function laneLabels(lanes: readonly LogLane[]): Map<string, string> {
  return new Map(lanes.map((l) => [l.id, l.label?.trim() ? l.label : l.id] as const));
}

/**
 * 레인 띠용 틱. 짝 이벤트(서버가 완료 행에 `duration_ms`를 줌)는 `[time - duration, time]` 막대가 된다.
 * 시각이 없는 이벤트는 그리지 않는다.
 */
export function toLaneEvents(events: readonly LogEvent[], isError: (e: LogEvent) => boolean): LaneEvent[] {
  const out: LaneEvent[] = [];
  for (const e of events) {
    if (e.time == null) continue;
    const dur = e.duration_ms != null && e.duration_ms > 0 ? e.duration_ms / 1000 : null;
    out.push({ uid: e.uid, lane: laneOf(e), time: dur === null ? e.time : e.time - dur, endTime: dur === null ? null : e.time, category: e.category, error: isError(e) });
  }
  return out;
}

/** 세션에 실제로 나온 범주 전부(재생 위치까지의 개수 + 세션 전체 개수). 순서는 `orderCategories`가 정한다. */
export function categoryItems(all: readonly LogEvent[], visible: readonly LogEvent[]): CategoryChipItem[] {
  const total = new Map<string, number>();
  for (const e of all) total.set(e.category, (total.get(e.category) ?? 0) + 1);
  const current = new Map<string, number>();
  for (const e of visible) current.set(e.category, (current.get(e.category) ?? 0) + 1);
  return [...total.entries()].map(([id, n]) => ({ id, count: current.get(id) ?? 0, total: n }));
}

export interface EventViewFilter {
  /** URL 필터(서버 필터 이름 그대로). 세션 상세는 이미 불러온 타임라인을 이 값으로 클라이언트에서 좁힌다. */
  filter: LogFilterValue;
  /** 필터 이름 해석표(데이터 `logsData.json`에서): 검색어·범주·시각·출처 이름과 "필터 이름 → 이벤트 필드" */
  names: { search: string; category: string; since: string; until: string; source: string; suggestFrom: Readonly<Record<string, string>> };
  errorsOnly: boolean;
  lanes: readonly string[];
  includeHidden: boolean;
}

function toEpoch(v: string): number | null {
  const n = Number(v);
  if (Number.isFinite(n) && v.trim() !== "") return n;
  const d = Date.parse(v);
  return Number.isNaN(d) ? null : d / 1000;
}

/**
 * 세션 상세의 표시 필터(클라이언트): URL 필터(범주·검색어·시각·출처·그 밖의 이벤트 필드)·오류만·레인·숨긴 범주.
 * 판정(`isError`/`isHidden`)은 주입한다(한 곳). 이벤트에 대응하는 필드가 없는 필터 이름(예: 프로젝트)은 무시한다.
 */
export function filterSessionEvents(events: readonly LogEvent[], f: EventViewFilter, isError: (e: LogEvent) => boolean, isHidden: (e: LogEvent) => boolean): LogEvent[] {
  const lanes = new Set(f.lanes);
  const checks: ((e: LogEvent) => boolean)[] = [];
  for (const [name, raw] of Object.entries(f.filter)) {
    const values = (Array.isArray(raw) ? raw : [raw]).filter((x) => x !== "");
    if (values.length === 0) continue;
    if (name === f.names.search) {
      const q = (values[0] as string).trim().toLowerCase();
      checks.push((e) => `${e.title ?? ""} ${e.summary ?? ""} ${e.tool ?? ""}`.toLowerCase().includes(q));
    } else if (name === f.names.category) {
      checks.push((e) => values.includes(e.category) || (e.tags ?? []).some((t) => values.includes(t)));
    } else if (name === f.names.since) {
      const at = toEpoch(values[0] as string);
      if (at !== null) checks.push((e) => e.time == null || e.time >= at);
    } else if (name === f.names.until) {
      const at = toEpoch(values[0] as string);
      if (at !== null) checks.push((e) => e.time == null || e.time < at);
    } else if (name === f.names.source) {
      checks.push((e) => values.includes(e.source));
    } else {
      const field = f.names.suggestFrom[name];
      if (field !== undefined) checks.push((e) => eventFieldValues(e, field).some((v) => values.includes(v)));
    }
  }
  return events.filter((e) => {
    if (!f.includeHidden && isHidden(e)) return false;
    if (f.errorsOnly && !isError(e)) return false;
    if (lanes.size > 0 && !lanes.has(laneOf(e))) return false;
    return checks.every((c) => c(e));
  });
}

/** 현재 불러온 항목에서 필드의 고유값(제안용, 최대 `max`). */
export function suggestionsFor(events: readonly LogEvent[], pick: (e: LogEvent) => string | readonly string[] | undefined, max = 20): string[] {
  const seen = new Set<string>();
  for (const e of events) {
    const v = pick(e);
    for (const item of v === undefined ? [] : typeof v === "string" ? [v] : v) {
      if (item !== "") seen.add(item);
      if (seen.size >= max) return [...seen];
    }
  }
  return [...seen];
}

/** 이벤트 필드 하나의 값 목록(문자열 또는 문자열 배열 필드). 제안(autocomplete)이 쓴다. */
export function eventFieldValues(e: LogEvent, field: string): string[] {
  const v = (e as unknown as Record<string, unknown>)[field];
  if (typeof v === "string") return [v];
  if (Array.isArray(v)) return v.filter((x): x is string => typeof x === "string");
  return [];
}

/** 정렬된 이벤트에서 상대 시각 기준(첫 시각). */
export function originOf(events: readonly { time?: number | null }[]): number | null {
  for (const e of events) if (e.time != null) return e.time;
  return null;
}

// ---------------------------------------------------------------- 첫 사용 안내 판정

export type EmptyKind = "A" | "B" | "C";

/** 켜진 출처 수. */
export function enabledCount(sources: readonly LogSourceInfo[] | undefined): number {
  return (sources ?? []).filter((s) => s.enabled).length;
}

/**
 * 빈 상태 판정(§1.8). `list0`은 목록 응답이 비었는지, `anyEvents`는 필터 없는 `limit=1` 조회에서 이벤트가 있는지
 * (조회 실패는 `undefined`: B로 단정하지 않고 C).
 */
export function classifyEmpty(sources: readonly LogSourceInfo[] | undefined, anyEvents: boolean | undefined): EmptyKind {
  if (sources !== undefined && enabledCount(sources) === 0) return "A";
  if (anyEvents === false) return "B";
  return "C";
}

/** 켤 수 있는 출처 카드 순서: 꺼진 출처만, `reads_paths && !default_enabled`를 먼저(디스크립터 속성만 본다). */
export function firstUseSources(sources: readonly LogSourceInfo[]): LogSourceInfo[] {
  const off = sources.filter((s) => !s.enabled);
  const rank = (s: LogSourceInfo) => (s.descriptor.reads_paths === true && s.descriptor.default_enabled !== true ? 0 : 1);
  return off
    .map((s, i) => ({ s, i }))
    .sort((a, b) => rank(a.s) - rank(b.s) || a.i - b.i)
    .map((x) => x.s);
}

/** 배너 D 대상: 외부 파일을 읽는 출처가 꺼져 있는지. */
export function offReadingSources(sources: readonly LogSourceInfo[] | undefined): LogSourceInfo[] {
  return (sources ?? []).filter((s) => !s.enabled && s.descriptor.reads_paths === true);
}

// ---------------------------------------------------------------- 대시보드 저장

/** 설정의 `logs.dashboards`(없으면 빈 목록). */
export function dashboardsOf(settings: WorkspaceSettings | undefined): readonly LogDashboard[] {
  return settings?.logs?.dashboards ?? [];
}

/**
 * 대시보드 목록만 바꾼 **전체 설정 문서**. 다른 설정 키·`logs`의 다른 키는 그대로이고, 대시보드·위젯·질의·옵션의 알 수 없는 키는
 * 서버에서 읽은 `current`에서 이어받는다(`preserveUnknownDashboards`).
 */
export function withDashboards(current: WorkspaceSettings, next: readonly LogDashboard[], opts: { prev?: readonly LogDashboard[]; ownedOptionKeys?: (kind: string) => readonly string[] } = {}): WorkspaceSettings {
  const prev = opts.prev ?? current.logs?.dashboards ?? [];
  const logs: LogSettings = { ...(current.logs ?? {}), dashboards: preserveUnknownDashboards(prev, next, opts.ownedOptionKeys === undefined ? {} : { ownedOptionKeys: opts.ownedOptionKeys }) };
  return { ...current, logs };
}

/** 새 대시보드 id: 제목과 상관없는 접두 + 겹치지 않는 번호. */
export function newDashboardId(existing: readonly LogDashboard[], make: () => string): string {
  const ids = new Set(existing.map((d) => d.id));
  for (let i = 0; i < 20; i++) {
    const id = make();
    if (!ids.has(id)) return id;
  }
  return `${make()}-${ids.size}`;
}

/** 제목이 겹치면 ` (2)`, ` (3)`… 을 붙인다. */
export function uniqueTitle(title: string, existing: readonly string[], numbered: (name: string, n: number) => string): string {
  if (!existing.includes(title)) return title;
  for (let n = 2; n < 1000; n++) {
    const t = numbered(title, n);
    if (!existing.includes(t)) return t;
  }
  return title;
}

/** 템플릿을 복사한다: 위젯 id는 새로 만든다(알 수 없는 키 포함 깊은 복사). */
export function cloneWidgets(widgets: readonly LogWidget[], newId: () => string): LogWidget[] {
  return widgets.map((w) => ({ ...(structuredClone(w) as LogWidget), id: newId() }));
}

/** 레지스트리가 모르는 위젯 종류 수(템플릿 경고 칩). */
export function unknownKindCount(d: LogDashboard, known: (kind: string) => boolean): number {
  return (d.widgets ?? []).filter((w) => !known(w.kind)).length;
}

/** 집계 요청의 질의 키(같은 질의는 한 번만 요청). */
export function aggregateKey(w: Pick<LogWidget, "query">, filter: Record<string, unknown>, tz: string): string {
  return JSON.stringify([w.query.group_by ?? [], w.query.metric, filter, tz]);
}

/** 위젯 질의 필터에 도구 줄 기간 덮어쓰기를 얹는다(저장하지 않는 조회용). */
export function overrideWindow(filter: Record<string, unknown> | undefined, window: { since?: string; until?: string } | null): Record<string, unknown> {
  const base = { ...(filter ?? {}) };
  if (window === null) return base;
  delete base[FILTER_KEYS.since];
  delete base[FILTER_KEYS.until];
  return { ...base, ...window };
}

/** 대시보드 위젯에 쓰지 않는 입력(IME·단축키 제외)에서 키 이벤트를 무시할지. */
export function isTypingTarget(target: EventTarget | null): boolean {
  return typeof Element !== "undefined" && target instanceof Element && target.closest("input, textarea, select, [contenteditable]:not([contenteditable='false']), [data-ac-editable]") !== null;
}

/** 분류 체계 순서 기반으로 칩 id 목록 정렬 도우미(테스트용 노출). */
export function categoryOrder(taxonomy: LogTaxonomyView): readonly string[] {
  return taxonomy.order;
}

/**
 * 이벤트 표 세로 공간이 최소 행 수보다 작으면 흐름 패널을 자동으로 접어야 하는지.
 * 사용자가 직접 펴 둔 상태(`userOpened`)이거나 이미 접혀 있으면 false.
 */
export function shouldAutoFoldFlow(o: { tableHeight: number; minRows: number; rowHeight: number; collapsed: boolean; userOpened: boolean }): boolean {
  return !o.collapsed && !o.userOpened && o.tableHeight < o.minRows * o.rowHeight;
}

/** 저장된 값을 범위 안으로 맞춘다(숫자가 아니면 기본값). */
export function clampOr(value: number, min: number, max: number, fallback: number): number {
  return Number.isFinite(value) ? Math.min(max, Math.max(min, value)) : fallback;
}
