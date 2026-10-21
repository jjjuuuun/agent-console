import type { EdgeTypeDescriptor, Graph, Interaction, NodeRun, Run, RunEvent, Trace, TraceSpan, Usage } from "@agent-console/contracts";
import payloadKeys from "./eventPayloadKeys.json";
import { formatDuration as formatDurationLib } from "../../lib/format";
import { conditionPayloadOf, parseDelegationEvent } from "../delegation";
import { compareNodeRuns, type VisibleRun } from "./nodeRuns";
import {
  ACTIVE_RUN_STATUSES,
  EDGE_SKIPPED_EVENT,
  EDGE_TRAVERSED_EVENT,
  NO_ORDER_SCHEDULING,
  SUBAGENT_RUNNING_STATUS,
  SUBAGENT_START_EVENT,
  SUBAGENT_STOP_EVENT,
  SUBAGENT_STOP_STATUS,
  TEXT_DELTA_EVENT,
  type PeriodOption,
} from "./runsConfig";

/** 실행 화면의 순수 로직(UI·네트워크 없음). 시각은 모두 epoch 초. */

// ---------------------------------------------------------------- 목록 필터

export interface RunFilterState {
  /** 비어 있으면 전체. 목록은 Run 상태 어휘 그대로 */
  statuses: readonly string[];
  /** `PERIOD_OPTIONS`의 id */
  period: string;
  /** run id·대화 제목·팀 구성 이름 부분 일치(대소문자 무시) */
  query: string;
}

/** 클라이언트 쪽 필터(서버는 팀 구성·에이전트·대화만 거른다). `titleOf`는 검색 대상 문자열을 더 주는 훅. */
export function filterRuns(
  runs: readonly Run[],
  filter: RunFilterState,
  nowSec: number,
  periods: readonly PeriodOption[],
  searchTextOf: (run: Run) => string = () => "",
): Run[] {
  const seconds = periods.find((p) => p.id === filter.period)?.seconds ?? null;
  const since = seconds === null ? null : nowSec - seconds;
  const q = filter.query.trim().toLowerCase();
  return runs.filter((run) => {
    if (filter.statuses.length > 0 && !filter.statuses.includes(run.status)) return false;
    if (since !== null && run.created_at < since) return false;
    if (q === "") return true;
    const haystack = [run.id, inputSummary(run.input), searchTextOf(run)].join("\n").toLowerCase();
    return haystack.includes(q);
  });
}

/** 입력 객체에서 사람이 읽을 한 줄(첫 문자열 값). */
export function inputSummary(input: Readonly<Record<string, unknown>> | undefined, max = 120): string {
  if (input === undefined) return "";
  for (const value of Object.values(input)) {
    if (typeof value === "string" && value.trim() !== "") return truncate(value.trim().replace(/\s+/g, " "), max);
  }
  return "";
}

export function truncate(text: string, max: number): string {
  return text.length <= max ? text : `${text.slice(0, Math.max(0, max - 1))}…`;
}

export function isActiveRun(status: string): boolean {
  return ACTIVE_RUN_STATUSES.includes(status);
}

export interface ActiveCounts {
  running: number;
  waiting: number;
}

/** 헤더 요약용: 실행 중/응답 대기 수. `waitingStatus`는 응답 대기 상태 문자열. */
export function activeCounts(runs: readonly Run[], waitingStatus: string): ActiveCounts {
  let running = 0;
  let waiting = 0;
  for (const run of runs) {
    if (run.status === waitingStatus) waiting += 1;
    else if (isActiveRun(run.status)) running += 1;
  }
  return { running, waiting };
}

/** 소요(ms). 끝났으면 ended-started, 아니면 now-started. 시작 전이면 undefined. */
export function runDurationMs(run: Run, nowSec: number): number | undefined {
  const start = run.started_at ?? undefined;
  if (start === undefined) return undefined;
  const end = run.ended_at ?? (isActiveRun(run.status) ? nowSec : start);
  return Math.max(0, (end - start) * 1000);
}

/** 약식 토큰 수 `4.1k`, `1.2M`. 값이 없으면 "–". */
export function formatTokensShort(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return "–";
  if (n < 1000) return String(Math.round(n));
  if (n < 1_000_000) return `${trimZero((n / 1000).toFixed(n < 10_000 ? 1 : 0))}k`;
  return `${trimZero((n / 1_000_000).toFixed(1))}M`;
}
function trimZero(s: string): string {
  return s.includes(".") ? s.replace(/\.?0+$/, "") : s;
}

/** 입력+출력, 둘 다 없으면 `total_tokens`. 서버가 준 값만 쓴다. */
export function totalTokens(usage: Usage | null | undefined): number | undefined {
  if (usage === null || usage === undefined) return undefined;
  if (typeof usage.total_tokens === "number") return usage.total_tokens;
  const parts = [usage.input_tokens, usage.output_tokens].filter((v): v is number => typeof v === "number");
  return parts.length === 0 ? undefined : parts.reduce((a, b) => a + b, 0);
}

// ---------------------------------------------------------------- 이벤트 누적

export interface MergeResult {
  events: RunEvent[];
  /** 받은 이벤트 중 seq가 이어지지 않는 곳이 있으면 true(스냅샷/이벤트 재요청 신호) */
  gap: boolean;
  /** 새로 반영된 개수 */
  added: number;
}

/** seq 기준으로 중복 없이 합친다. 같은 seq는 한 번만 적용. */
export function mergeEvents(current: readonly RunEvent[], incoming: readonly RunEvent[]): MergeResult {
  const seen = new Set(current.map((e) => e.seq));
  const fresh: RunEvent[] = [];
  for (const e of incoming) {
    if (seen.has(e.seq)) continue;
    seen.add(e.seq);
    fresh.push(e);
  }
  fresh.sort((a, b) => a.seq - b.seq);
  if (fresh.length === 0) return { events: current as RunEvent[], gap: false, added: 0 };
  const lastSeq = current.length === 0 ? 0 : current[current.length - 1]!.seq;
  const events = [...current, ...fresh].sort((a, b) => a.seq - b.seq);
  // 시작이 1이 아닌 첫 로딩도 "처음"이므로 current가 비어 있을 때는 틈으로 보지 않는다.
  const gap = current.length > 0 && fresh[0]!.seq > lastSeq + 1;
  return { events, gap, added: fresh.length };
}

export function lastSeqOf(events: readonly RunEvent[]): number {
  return events.length === 0 ? 0 : events[events.length - 1]!.seq;
}

// ---------------------------------------------------------------- 그래프 오버레이

export interface NodeStateOverlay {
  status: string;
  attempt?: number;
  iteration?: number;
  summary?: string;
  errorSummary?: string;
}

export interface RunOverlay {
  nodeStates: Record<string, NodeStateOverlay>;
  edgeStates: Record<string, string>;
  edgeOrder: Record<string, number>;
  edgeCounts: Record<string, number>;
  waitingNodes: Record<string, { since: string }>;
  /** 서브에이전트가 한 번 이상 불린 노드 id → 호출 횟수 */
  subagentCalls: Record<string, number>;
  /** 연결 id → 이 Run에서 지나간 횟수(`edge.traversed`) */
  edgeTraversals: Record<string, number>;
  /** 반복 한도에 닿은 연결 id → 적용된 한도(반복 한도 도달 이벤트; 서버가 안 주면 undefined) */
  exhausted: Record<string, number | undefined>;
  /** 조건이 맞지 않아 지나가지 않은 연결(조건 판정 근거가 붙은 건너뜀; 상류 건너뜀과 구분) */
  conditionSkipped: Record<string, true>;
  /** 실패했지만 실패 처리 연결이 지나가 처리된 노드 */
  handledNodes: Record<string, true>;
}

export interface OverlayInput {
  graph: Graph | undefined;
  edgeTypes: readonly EdgeTypeDescriptor[];
  nodeRuns: readonly NodeRun[];
  events: readonly RunEvent[];
  pending: readonly Interaction[];
  /** 노드 상태 한 줄 요약(앱이 포맷해 주입) */
  summarize?: (nodeRun: NodeRun) => string | undefined;
  /** 노드별 보이는 실행(사용자가 고른 실행 또는 최신). 없으면 최신 실행의 상태를 그린다 */
  visible?: ReadonlyMap<string, VisibleRun>;
}

/** 노드별 가장 최근 NodeRun(시작이 가장 늦은 쪽, 같으면 회차·호출·시도가 큰 쪽). */
export function latestNodeRuns(nodeRuns: readonly NodeRun[]): Map<string, NodeRun> {
  const map = new Map<string, NodeRun>();
  for (const n of nodeRuns) {
    const prev = map.get(n.node_id);
    if (prev === undefined || compareNodeRuns(n, prev) >= 0) map.set(n.node_id, n);
  }
  return map;
}

function str(value: unknown): string | undefined {
  return typeof value === "string" && value !== "" ? value : undefined;
}

/**
 * 그래프 위에 얹을 실행 상태를 이벤트·NodeRun·대기 요청에서 계산한다.
 * 서브에이전트(NodeRun 없음)의 상태는 `agent.subagent_started|stopped`로, 지나간 연결은 `edge.traversed`로 그린다.
 * 어떤 엣지가 어떤 방식인지는 이벤트 종류와 연결 종류 디스크립터(`invocation`·`scheduling`)로만 판단한다.
 */
export function deriveRunOverlay(input: OverlayInput): RunOverlay {
  const { graph, edgeTypes, nodeRuns, events, pending } = input;
  const kinds = new Map(edgeTypes.map((t) => [t.id, t]));
  const edges = graph?.edges ?? [];
  const edgeById = new Map(edges.map((e) => [e.id, e]));

  const nodeStates: Record<string, NodeStateOverlay> = {};
  const latest = latestNodeRuns(nodeRuns);
  for (const [nodeId, latestRun] of latest) {
    const nr = input.visible?.get(nodeId)?.run ?? latestRun;
    const summary = input.summarize?.(nr);
    nodeStates[nodeId] = {
      status: nr.status,
      ...(nr.attempt !== undefined ? { attempt: nr.attempt } : {}),
      ...(nr.iteration !== undefined ? { iteration: nr.iteration } : {}),
      ...(summary !== undefined ? { summary } : {}),
      ...(nr.error?.message ? { errorSummary: nr.error.message } : {}),
    };
  }

  const edgeStates: Record<string, string> = {};
  const edgeOrder: Record<string, number> = {};
  const edgeCounts: Record<string, number> = {};
  const subagentCalls: Record<string, number> = {};
  const edgeTraversals: Record<string, number> = {};
  const exhausted: Record<string, number | undefined> = {};
  const conditionSkipped: Record<string, true> = {};
  let order = 0;
  for (const event of events) {
    const loop = parseDelegationEvent(event);
    if (loop?.kind === "loop-exhausted") {
      exhausted[loop.edgeId] = loop.maxIterations;
      edgeStates[loop.edgeId] = "dead";
      continue;
    }
    if (event.type === EDGE_SKIPPED_EVENT) {
      const edgeId = str(event.payload?.["edge_id"]);
      if (edgeId === undefined) continue;
      // 반복 연결은 회차마다 다시 평가되므로 한 번이라도 지나갔으면 지나간 연결로 둔다
      if (edgeStates[edgeId] !== "traversed") edgeStates[edgeId] = "dead";
      if (conditionPayloadOf(event) !== undefined) conditionSkipped[edgeId] = true;
      continue;
    }
    if (event.type === EDGE_TRAVERSED_EVENT) {
      const edgeId = str(event.payload?.["edge_id"]);
      if (edgeId === undefined) continue;
      if (exhausted[edgeId] === undefined && !(edgeId in exhausted)) edgeStates[edgeId] = "traversed";
      edgeTraversals[edgeId] = (edgeTraversals[edgeId] ?? 0) + 1;
      delete conditionSkipped[edgeId];
      const edge = edgeById.get(edgeId);
      const kind = edge ? kinds.get(edge.kind) : undefined;
      // 반복 연결은 순번 배지(①②…)를 쓰지 않는다(통과 횟수 배지 `↻×k`가 대신한다)
      if (kind?.cycle != null) continue;
      const scheduling = kind?.scheduling;
      if (scheduling !== undefined && NO_ORDER_SCHEDULING.includes(scheduling)) continue;
      if (edgeOrder[edgeId] === undefined) {
        order += 1;
        edgeOrder[edgeId] = order;
      }
    } else if (event.type === SUBAGENT_START_EVENT || event.type === SUBAGENT_STOP_EVENT) {
      const target = str(event.payload?.["name"]);
      if (target === undefined) continue;
      if (event.type === SUBAGENT_START_EVENT) {
        subagentCalls[target] = (subagentCalls[target] ?? 0) + 1;
        nodeStates[target] = { status: SUBAGENT_RUNNING_STATUS };
        const edge = delegationEdgeFor(edges, kinds, target, event.node_path[0]);
        if (edge !== undefined) edgeCounts[edge.id] = (edgeCounts[edge.id] ?? 0) + 1;
      } else {
        const raw = str(event.payload?.["status"]) ?? "";
        const mapped = SUBAGENT_STOP_STATUS[raw] ?? (raw === "" ? "succeeded" : raw);
        nodeStates[target] = { status: mapped };
      }
    }
  }
  // 위임 엣지는 호출이 있었으면 지나간 연결로 강조한다(순번 배지는 독립 넘기기에만).
  for (const id of Object.keys(edgeCounts)) edgeStates[id] ??= "traversed";

  // 건너뛴 노드에서 나가는 엣지는 죽은 연결.
  for (const edge of edges) {
    if (edgeStates[edge.id] === undefined && nodeStates[edge.source.node]?.status === "skipped") edgeStates[edge.id] = "dead";
  }

  const waitingNodes: Record<string, { since: string }> = {};
  for (const i of pending) {
    if (i.status !== "pending") continue;
    const since = new Date(i.created_at * 1000).toISOString();
    const prev = waitingNodes[i.node_id];
    if (prev === undefined || since < prev.since) waitingNodes[i.node_id] = { since };
  }
  // 실패했지만 그 노드에서 나가는 실패 처리 연결이 지나갔으면 처리된 실패다(디스크립터 `handles_failure`로만 판정)
  const handledNodes: Record<string, true> = {};
  for (const edge of edges) {
    if (kinds.get(edge.kind)?.handles_failure === true && (edgeTraversals[edge.id] ?? 0) > 0 && nodeStates[edge.source.node]?.status === "failed") handledNodes[edge.source.node] = true;
  }
  return { nodeStates, edgeStates, edgeOrder, edgeCounts, waitingNodes, subagentCalls, edgeTraversals, exhausted, conditionSkipped, handledNodes };
}

/** 위임 방식 연결(디스크립터 `invocation`이 있는 종류) 중 도착 노드가 `target`인 엣지. 출발이 `preferSource`면 우선. */
export function delegationEdgeFor(
  edges: readonly { id: string; kind: string; source: { node: string }; target: { node: string } }[],
  kinds: ReadonlyMap<string, EdgeTypeDescriptor>,
  target: string,
  preferSource?: string,
) {
  const candidates = edges.filter((e) => e.target.node === target && kinds.get(e.kind)?.invocation != null);
  return candidates.find((e) => e.source.node === preferSource) ?? candidates[0];
}

// ---------------------------------------------------------------- 이벤트 표시

export interface EventRow {
  /** 합쳐진 행의 첫 이벤트 */
  event: RunEvent;
  /** 같은 행에 합쳐진 이벤트 수(텍스트 조각) */
  count: number;
  /** 합친 텍스트(조각이 아니면 undefined) */
  text?: string;
  key: string;
}

/** 연속된 같은 actor의 텍스트 조각을 한 행으로 합친다. */
export function buildEventRows(events: readonly RunEvent[]): EventRow[] {
  const rows: EventRow[] = [];
  for (const event of events) {
    const prev = rows[rows.length - 1];
    if (event.type === TEXT_DELTA_EVENT && prev && prev.event.type === TEXT_DELTA_EVENT && (prev.event.actor ?? null) === (event.actor ?? null) && prev.text !== undefined) {
      prev.text += str(event.payload?.["text"]) ?? "";
      prev.count += 1;
      continue;
    }
    rows.push({ event, count: 1, key: `${event.seq}`, ...(event.type === TEXT_DELTA_EVENT ? { text: str(event.payload?.["text"]) ?? "" } : {}) });
  }
  return rows;
}


/** 이벤트 한 줄 요약. 모르는 type은 payload의 눈에 띄는 값을 이어 붙인다. */
export function summarizeEvent(event: RunEvent, max = 160): string {
  const payload = event.payload ?? {};
  if (event.type.endsWith("tool_call")) {
    const name = str(payload["name"]) ?? "";
    const input = payload[payloadKeys.toolCallArgsKey];
    const args = input === undefined ? "" : truncate(compact(input), 80);
    return truncate(`${name}${args ? `(${args})` : ""}`, max);
  }
  const parts: string[] = [];
  for (const key of payloadKeys.summaryKeys) {
    const value = payload[key];
    if (typeof value === "string" && value !== "") parts.push(parts.length === 0 && payloadKeys.primaryTextKeys.includes(key) ? value : `${key}=${value}`);
    if (parts.length >= 3) break;
  }
  if (parts.length === 0) {
    const rest = Object.keys(payload);
    if (rest.length > 0) parts.push(compact(payload));
  }
  return truncate(parts.join(" · ").replace(/\s+/g, " "), max);
}

function compact(value: unknown): string {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value) ?? String(value);
  } catch {
    return String(value);
  }
}

/** 이벤트 type의 접두(첫 점까지, 점 포함). 점이 없으면 type 전체. 데이터에서 목록을 만든다. */
export function typePrefixOf(type: string): string {
  const dot = type.indexOf(".");
  return dot < 0 ? type : type.slice(0, dot + 1);
}

export function collectPrefixes(events: readonly RunEvent[]): string[] {
  return [...new Set(events.map((e) => typePrefixOf(e.type)))].sort();
}

export interface ActorSummary {
  actor: string;
  count: number;
  /** 마지막으로 본 이 actor의 이벤트 type (상태 아이콘 판단은 앱이) */
  lastType: string;
}

export function summarizeActors(events: readonly RunEvent[]): ActorSummary[] {
  const map = new Map<string, ActorSummary>();
  for (const e of events) {
    const actor = e.actor ?? "";
    if (actor === "") continue;
    const prev = map.get(actor);
    map.set(actor, { actor, count: (prev?.count ?? 0) + 1, lastType: e.type });
  }
  return [...map.values()];
}

export function isErrorEvent(event: RunEvent): boolean {
  const p = event.payload ?? {};
  if (p["is_error"] === true) return true;
  if (typeof p["exit_code"] === "number" && p["exit_code"] !== 0) return true;
  if (p["error"] !== undefined && p["error"] !== null && p["error"] !== false) return true;
  return event.type.endsWith("failed") || event.type === "log.warning";
}

export interface ObserveRow {
  event: RunEvent;
  prefix: string;
  /** 종류 열: hook이면 이벤트 이름·매처, mcp이면 서버·도구 */
  kind: string;
  durationMs?: number;
  error: boolean;
  summary: string;
}

/** 관측 이벤트(`prefixes`로 시작하는 type) → 표 행. payload 키 어휘는 `eventPayloadKeys.json`(데이터)이고 `duration_ms`는 계약 필드다. */
export function buildObserveRows(events: readonly RunEvent[], prefixes: readonly string[]): ObserveRow[] {
  return events
    .filter((e) => prefixes.some((p) => e.type.startsWith(p)))
    .map((event) => {
      const p = event.payload ?? {};
      const bits = payloadKeys.observeKindKeys.map((k) => str(p[k])).filter((x): x is string => x !== undefined);
      const duration = typeof p["duration_ms"] === "number" ? (p["duration_ms"] as number) : undefined;
      return {
        event,
        prefix: typePrefixOf(event.type),
        kind: bits.join(" · "),
        ...(duration !== undefined ? { durationMs: duration } : {}),
        error: isErrorEvent(event),
        summary: summarizeEvent(event),
      };
    });
}

export interface ObserveStats {
  /** 접두별 이벤트 수 */
  byPrefix: Record<string, number>;
  errors: number;
  avgMs: number | undefined;
}

export function observeStats(rows: readonly ObserveRow[]): ObserveStats {
  const byPrefix: Record<string, number> = {};
  let errors = 0;
  let sum = 0;
  let n = 0;
  for (const r of rows) {
    byPrefix[r.prefix] = (byPrefix[r.prefix] ?? 0) + 1;
    if (r.error) errors += 1;
    if (r.durationMs !== undefined) {
      sum += r.durationMs;
      n += 1;
    }
  }
  return { byPrefix, errors, avgMs: n === 0 ? undefined : Math.round(sum / n) };
}

// ---------------------------------------------------------------- 상호작용

/** 대기 중 먼저(최신 대기 우선), 그다음 요청 시각 내림차순. */
export function sortInteractions(list: readonly Interaction[]): Interaction[] {
  return [...list].sort((a, b) => {
    const ap = a.status === "pending" ? 0 : 1;
    const bp = b.status === "pending" ? 0 : 1;
    if (ap !== bp) return ap - bp;
    return b.created_at - a.created_at;
  });
}

/** 대기 시간(초). 대기 중이면 now까지. */
export function waitSeconds(i: Interaction, nowSec: number): number {
  return Math.max(0, (i.closed_at ?? (i.status === "pending" ? nowSec : i.created_at)) - i.created_at);
}

export interface InteractionStats {
  total: number;
  waiting: number;
  /** 닫힌 요청의 평균 대기(초). 닫힌 것이 없으면 undefined */
  avgWaitSec: number | undefined;
}

export function interactionStats(list: readonly Interaction[]): InteractionStats {
  const closed = list.filter((i) => i.closed_at != null);
  const avg = closed.length === 0 ? undefined : closed.reduce((s, i) => s + ((i.closed_at as number) - i.created_at), 0) / closed.length;
  return { total: list.length, waiting: list.filter((i) => i.status === "pending").length, avgWaitSec: avg };
}

/** 서버 재시작으로 끊긴 요청인가. */
export function isInterruptedInteraction(i: Interaction): boolean {
  return i.status === "expired" && i.close_reason === "interrupted";
}

// ---------------------------------------------------------------- trace

/** 사용자 대기 구간을 뺀 span 목록이 아니라, 선택·강조용으로 노드의 span id를 찾는다. */
export function spanIdsOfNode(spans: readonly TraceSpan[], nodeId: string): string[] {
  return spans.filter((s) => s.node_id === nodeId).map((s) => s.id);
}

/** "실패만" 보기: 실패 상태 span과 그 조상 span만 남긴다(트리가 끊기지 않게). 상태 문자열은 서버 값 그대로 비교. */
export function filterFailedSpans(trace: Trace, failedStatus: string): Trace {
  const spans = trace.spans ?? [];
  const byId = new Map(spans.map((s) => [s.id, s]));
  const keep = new Set<string>();
  for (const s of spans) {
    if (s.status !== failedStatus) continue;
    for (let cur: TraceSpan | undefined = s; cur !== undefined && !keep.has(cur.id); cur = cur.parent_id ? byId.get(cur.parent_id) : undefined) keep.add(cur.id);
  }
  return {
    ...trace,
    spans: spans.filter((s) => keep.has(s.id)),
    links: (trace.links ?? []).filter((l) => keep.has(l.source) && keep.has(l.target)),
  };
}

/** 밀리초 표시: 1초 미만은 `21ms`, 그 이상은 `1.2초` 식 공용 포맷. */
export function formatMs(ms: number): string {
  return ms < 1000 ? `${Math.round(ms)}ms` : formatDurationLib(ms);
}
