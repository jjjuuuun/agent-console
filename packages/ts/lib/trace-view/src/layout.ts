import type { Trace, TraceLink, TraceSpan } from "@agent-console/contracts";

/** 사용자 대기 구간인지. 종류 문자열이 아니라 `interaction_id` 필드로 판정한다. */
export function isUserWait(span: TraceSpan): boolean {
  return span.interaction_id != null && span.interaction_id !== "";
}

/** 자식 Run 묶음 행에 실리는 요약(묶음 행은 `span`에 합성 span을 둔다). */
export interface TraceGroupInfo {
  /** 묶음 id = 자식 Run id(`span.run_id`). `expandedGroupIds`·`onGroupToggle`·`onOpenChildRun`이 쓰는 키. */
  runId: string;
  /** 묶음 안 실제 span(합성 행 제외, 후손 묶음의 span 제외). */
  spans: readonly TraceSpan[];
  /** 묶음의 맨 위 span들(묶음 안에서 부모가 없는 것). */
  rootSpans: readonly TraceSpan[];
}

export interface TraceRow {
  span: TraceSpan;
  depth: number;
  hasChildren: boolean;
  parentId: string | null;
  /** 자식 Run 묶음 행이면 요약. 이 행의 `span`은 합성이다(`kind` = `GROUP_SPAN_KIND`). */
  group?: TraceGroupInfo;
  /** 묶음 행이 펼쳐져 있는가(`group`이 있을 때만). */
  expanded?: boolean;
}

/** 합성 묶음 span의 `kind`. 화면 내부 표시용이며 계약 값이 아니다. */
export const GROUP_SPAN_KIND = "ac-trace-group";

/** 합성 묶음 span의 id. */
export function groupSpanId(runId: string): string {
  return `group:${runId}`;
}

function byStart(a: { span: TraceSpan; i: number }, b: { span: TraceSpan; i: number }): number {
  const as = a.span.started_at ?? Number.POSITIVE_INFINITY;
  const bs = b.span.started_at ?? Number.POSITIVE_INFINITY;
  return as !== bs ? (as < bs ? -1 : 1) : a.i - b.i;
}

/** span이 다른 Run(자식 Run)에 속하는가: `run_id`가 trace의 Run과 다를 때. */
export function isChildRunSpan(span: TraceSpan, runId: string | undefined): boolean {
  return runId !== undefined && span.run_id != null && span.run_id !== "" && span.run_id !== runId;
}

/** 호출 NodeRun(위임으로 불린 별도 세션 실행)인가. 판정은 계약 필드 `call`로(호출 span은 늘 채운다, 5R.14). */
export function isCallSpan(span: TraceSpan): boolean {
  return span.call != null;
}

export interface FlattenOptions {
  collapsed?: ReadonlySet<string>;
  showUserWait?: boolean;
  /** trace의 Run id. 있으면 `run_id`가 다른 span을 자식 Run 묶음으로 묶는다. */
  runId?: string;
  /** 펼친 자식 Run 묶음(묶음 id = 자식 Run id). 없으면 모두 접힘. */
  expandedGroups?: ReadonlySet<string>;
}

interface Entry {
  span: TraceSpan;
  i: number;
  group?: TraceGroupInfo;
}

function groupSpan(runId: string, spans: readonly TraceSpan[], parentId: string | null): TraceSpan {
  const starts = spans.map((s) => s.started_at).filter((v): v is number => v != null);
  const open = spans.some((s) => s.ended_at == null);
  const ends = spans.map((s) => s.ended_at).filter((v): v is number => v != null);
  const last = [...spans].sort((a, b) => (b.ended_at ?? Number.POSITIVE_INFINITY) - (a.ended_at ?? Number.POSITIVE_INFINITY))[0];
  return {
    id: groupSpanId(runId),
    kind: GROUP_SPAN_KIND,
    parent_id: parentId,
    run_id: runId,
    status: last?.status ?? null,
    started_at: starts.length ? Math.min(...starts) : null,
    ended_at: open || ends.length === 0 ? null : Math.max(...ends),
  };
}

/**
 * span 목록을 보이는 행으로 편다. 부모-자식은 `parent_id`가 가리키는 span이 있을 때만 잇는다
 * (시간상 이웃으로 추정하지 않는다). 부모를 찾을 수 없으면 최상위 행.
 * `runId`를 주면 `run_id`가 다른 span(자식 Run)을 Run별 묶음 행 하나 아래로 모은다. 묶음은 그 Run의 맨 위 span이
 * 가리키는 부모 span 아래(없으면 최상위)에 놓이고, 후손 Run 묶음은 부모 묶음 안에 중첩된다.
 */
export function flattenRows(spans: readonly TraceSpan[], opts: FlattenOptions = {}): TraceRow[] {
  const { collapsed, showUserWait = true, runId, expandedGroups } = opts;
  const visible = showUserWait ? spans : spans.filter((s) => !isUserWait(s));
  const ids = new Set(visible.map((s) => s.id));
  const owner = (s: TraceSpan): string | null => (isChildRunSpan(s, runId) ? (s.run_id as string) : null);
  const byId = new Map(visible.map((s) => [s.id, s]));
  const members = new Map<string, TraceSpan[]>();
  visible.forEach((s) => {
    const g = owner(s);
    if (g) members.set(g, [...(members.get(g) ?? []), s]);
  });
  const children = new Map<string | null, Entry[]>();
  const push = (parent: string | null, e: Entry) => {
    const list = children.get(parent) ?? [];
    list.push(e);
    children.set(parent, list);
  };
  const parentOf = (span: TraceSpan): string | null => (span.parent_id && ids.has(span.parent_id) && span.parent_id !== span.id ? span.parent_id : null);
  const groupInfo = new Map<string, TraceGroupInfo>();
  for (const [gid, list] of members) {
    const own = new Set(list.map((s) => s.id));
    const roots = list.filter((s) => !(s.parent_id && own.has(s.parent_id)));
    groupInfo.set(gid, { runId: gid, spans: list, rootSpans: roots });
  }
  visible.forEach((span, i) => {
    const g = owner(span);
    const parent = parentOf(span);
    if (g) {
      const inside = parent !== null && owner(byId.get(parent) as TraceSpan) === g;
      push(inside ? parent : groupSpanId(g), { span, i }); // 묶음의 맨 위 span은 묶음 행 아래
    } else {
      push(parent, { span, i });
    }
  });
  // 묶음 자신을 부모 span(또는 부모 묶음) 아래에 단다.
  let order = visible.length;
  for (const [gid, info] of groupInfo) {
    const root = [...info.rootSpans].sort((a, b) => (a.started_at ?? Number.POSITIVE_INFINITY) - (b.started_at ?? Number.POSITIVE_INFINITY))[0];
    const rawParent = root ? parentOf(root) : null;
    const own = new Set(info.spans.map((s) => s.id));
    // 부모가 자기 묶음 안이면(비정상) 최상위로 둔다.
    const attach = rawParent !== null && own.has(rawParent) ? null : rawParent;
    push(attach, { span: groupSpan(gid, info.spans, attach), i: order++, group: info });
  }
  const rows: TraceRow[] = [];
  const seen = new Set<string>();
  const walk = (parent: string | null, depth: number) => {
    for (const { span, group } of [...(children.get(parent) ?? [])].sort(byStart)) {
      if (seen.has(span.id)) continue; // 순환 방지
      seen.add(span.id);
      const kids = children.get(span.id) ?? [];
      const open = group ? (expandedGroups?.has(group.runId) ?? false) : !collapsed?.has(span.id);
      rows.push({ span, depth, hasChildren: kids.length > 0, parentId: parent, group, expanded: group ? open : undefined });
      if (open && kids.length > 0) walk(span.id, depth + 1);
    }
  };
  walk(null, 0);
  return rows;
}

/**
 * 묶음의 기본 펼침: 아직 끝나지 않은 span이 있으면(실행 중이거나 응답 대기) 펼침, 끝났으면 접힘.
 * 사용자가 바꾼 상태는 화면이 따로 쥐고 이 값 위에 덮는다.
 */
export function defaultExpandedGroups(spans: readonly TraceSpan[], runId: string | undefined): Set<string> {
  const out = new Set<string>();
  for (const s of spans) {
    if (isChildRunSpan(s, runId) && s.ended_at == null) out.add(s.run_id as string);
  }
  return out;
}

/** 같은 노드의 회차·호출 표기. 값은 서버(0부터), 화면 번호는 `+ 1`은 messages 쪽에서 한다. */
export interface SpanOrdinal {
  /** 이 span의 회차(0부터). 같은 노드에 회차가 둘 이상(또는 1 이상)일 때만 있다. */
  iteration?: number;
  /** 이 span의 호출 번호(0부터). 같은 노드에 호출 span이 둘 이상일 때만 있다. */
  call?: number;
}

/** span마다 이름 뒤에 붙일 회차·호출 번호를 계산한다. 하나뿐인 노드에는 붙이지 않는다. */
export function spanOrdinals(spans: readonly TraceSpan[]): Map<string, SpanOrdinal> {
  const byNode = new Map<string, TraceSpan[]>();
  for (const s of spans) {
    if (s.node_id) byNode.set(`${s.run_id ?? ""}\u0000${s.node_id}`, [...(byNode.get(`${s.run_id ?? ""}\u0000${s.node_id}`) ?? []), s]);
  }
  const out = new Map<string, SpanOrdinal>();
  for (const list of byNode.values()) {
    const iters = new Set(list.map((s) => s.iteration).filter((v): v is number => v != null));
    const calls = new Set(list.filter((s) => s.call != null).map((s) => `${s.iteration ?? 0}:${s.call}`));
    for (const s of list) {
      const o: SpanOrdinal = {};
      if (s.iteration != null && (iters.size > 1 || s.iteration > 0)) o.iteration = s.iteration;
      if (s.call != null && calls.size > 1) o.call = s.call;
      if (o.iteration !== undefined || o.call !== undefined) out.set(s.id, o);
    }
  }
  return out;
}

/** 같은 세션 안 위임인지: 부모가 있고, 양쪽 세션 id가 모두 있으면 같을 때만 같은 세션. */
export function isSameSession(span: TraceSpan, parent: TraceSpan | undefined): boolean {
  if (!parent) return false;
  if (span.session_id && parent.session_id) return span.session_id === parent.session_id;
  return true;
}

export interface TimeScale {
  /** 시작 시각(초). */
  t0: number;
  /** 압축된 전체 길이(초). */
  total: number;
  /** 시각 → 0..1 위치(사용자 대기를 접었으면 그 구간을 뺀다). */
  at: (t: number) => number;
}

function spanEnd(span: TraceSpan, now: number | undefined, running: boolean): number | undefined {
  if (span.ended_at != null) return span.ended_at;
  if (span.started_at == null) return undefined;
  return running && now != null ? Math.max(now, span.started_at) : span.started_at;
}

/**
 * 시간 축 계산. `showUserWait=false`이면 사용자 대기 구간의 길이를 시간 축에서 뺀다(작업 시간만 보기).
 */
export function computeTimeScale(spans: readonly TraceSpan[], opts: { now?: number; running?: boolean; showUserWait?: boolean } = {}): TimeScale {
  const { now, running = false, showUserWait = true } = opts;
  const starts = spans.map((s) => s.started_at).filter((v): v is number => v != null);
  const ends = spans.map((s) => spanEnd(s, now, running)).filter((v): v is number => v != null);
  if (starts.length === 0) return { t0: 0, total: 0, at: () => 0 };
  const t0 = Math.min(...starts);
  const t1 = Math.max(...ends, t0);
  // 사용자 대기 구간 병합
  const waits: [number, number][] = [];
  if (!showUserWait) {
    const raw = spans
      .filter(isUserWait)
      .map((s): [number, number] | undefined => {
        const e = spanEnd(s, now, running);
        return s.started_at != null && e != null ? [s.started_at, e] : undefined;
      })
      .filter((v): v is [number, number] => !!v)
      .sort((a, b) => a[0] - b[0]);
    for (const iv of raw) {
      const last = waits[waits.length - 1];
      if (last && iv[0] <= last[1]) last[1] = Math.max(last[1], iv[1]);
      else waits.push([iv[0], iv[1]]);
    }
  }
  const removedBefore = (t: number) => waits.reduce((acc, [s, e]) => acc + Math.max(0, Math.min(t, e) - s), 0);
  const compress = (t: number) => t - t0 - removedBefore(t);
  const total = compress(t1);
  return { t0, total, at: (t) => (total > 0 ? Math.min(1, Math.max(0, compress(t) / total)) : 0) };
}

/** 눈금: 전체 길이(초)에 맞춰 5~8칸이 되는 "보기 좋은" 간격의 위치(초). */
export function niceTicks(totalSeconds: number): number[] {
  if (!(totalSeconds > 0)) return [0];
  const steps = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200];
  let step = steps[steps.length - 1] ?? 3600;
  for (const s of steps) {
    if (totalSeconds / s <= 8) {
      step = s;
      break;
    }
  }
  const out: number[] = [];
  for (let t = 0; t <= totalSeconds + 1e-9; t += step) out.push(t);
  return out;
}

/** 초 → "12초" / "2분 5초". */
export function formatDuration(seconds: number, units: { s: string; m: string; h: string }): string {
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s}${units.s}`;
  const m = Math.floor(s / 60);
  if (m < 60) return s % 60 ? `${m}${units.m} ${s % 60}${units.s}` : `${m}${units.m}`;
  const h = Math.floor(m / 60);
  return m % 60 ? `${h}${units.h} ${m % 60}${units.m}` : `${h}${units.h}`;
}

/**
 * 수치 열용 짧은 소요 표기(최대 8자). 시간 단위 없이 분·초로 쓰고, 100분 이상은 `99분+`.
 * 전체 값은 `formatDuration`으로 툴팁·aria에 남는다.
 */
export function formatTailDuration(seconds: number, units: { s: string; m: string; h: string }): string {
  const s = Math.max(0, Math.round(seconds));
  if (s >= 6000) return `99${units.m}+`;
  if (s < 60) return `${s}${units.s}`;
  const m = Math.floor(s / 60);
  return s % 60 ? `${m}${units.m} ${s % 60}${units.s}` : `${m}${units.m}`;
}

/** 큰 수 줄임: 1234 -> `1.2k`, 34000 -> `34k`, 1_200_000 -> `1.2M`. */
export function compactCount(n: number): string {
  const trim = (v: number) => (v >= 10 ? String(Math.round(v)) : String(Math.round(v * 10) / 10));
  if (n < 1000) return String(Math.round(n));
  if (n < 1_000_000) return `${trim(n / 1000)}k`;
  return `${trim(n / 1_000_000)}M`;
}

export interface Handoff {
  link: TraceLink;
  sourceRow: number;
  targetRow: number;
  order?: number;
}

/**
 * 넘기기 화살표 후보: 링크 중 도착 span이 출발 span의 자식이 아닌 것(자식은 트리 가이드로 표현)이고
 * 두 행이 모두 보이는 것.
 */
export function visibleHandoffs(trace: Pick<Trace, "links">, rows: readonly TraceRow[]): Handoff[] {
  const index = new Map(rows.map((r, i) => [r.span.id, i]));
  const out: Handoff[] = [];
  for (const link of trace.links ?? []) {
    const s = index.get(link.source);
    const t = index.get(link.target);
    if (s === undefined || t === undefined) continue;
    const target = rows[t]?.span;
    if (!target || target.parent_id === link.source) continue;
    out.push({ link, sourceRow: s, targetRow: t, order: target.order ?? undefined });
  }
  return out;
}
