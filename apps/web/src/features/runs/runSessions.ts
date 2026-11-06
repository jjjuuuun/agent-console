/**
 * 실행 상세의 세션 구분 계산(순수 함수, screen-delegation.md §14.5). 세션 = 서버가 준 백엔드 세션 id 하나이고 같은 id는 같은 세션이다.
 * 세션 수·번호는 trace span 기준이고(실행 중에도 `node` span에 id가 있다), trace가 없거나 id가 없는 NodeRun은 NodeRun의
 * `backend_session_id`로 보충한다. 위임 방식·연결 종류 id는 비교하지 않는다. 세션 id를 아는 것이 하나도 없으면 빈 결과다.
 */
import type { NodeRun, RunEvent, TraceSpan } from "@agent-console/contracts";
import { SUBAGENT_START_EVENT } from "./runsConfig";
import { totalTokens } from "./runsLib";

/** 세션 id를 모르는 이벤트·행을 가리키는 선택 값(화면이 정한 값, 세션 id가 아니다). */
export const NO_SESSION = "@none";

export interface SessionInfo {
  id: string;
  /** 1부터. 첫 시작 시각 오름차순(같으면 id 사전순) */
  number: number;
  /** CSS 색 토큰 참조 */
  color: string;
  /** 이 세션의 첫 실행 노드 id와 이름 */
  nodeId: string | undefined;
  name: string;
  nodeIds: string[];
  /** epoch 초 */
  startedAt: number | undefined;
  endedAt: number | undefined;
  /** 이 세션 안 같은 세션 위임(서브에이전트) 호출 수 */
  subCalls: number;
  tokens: number | undefined;
}

export interface RunSessions {
  list: SessionInfo[];
  byId: Map<string, SessionInfo>;
  /** 노드 id → 그 노드의 (첫) 세션 */
  byNode: Map<string, SessionInfo>;
  /** 세션 id를 알 수 없는 실행 수(trace span 기준) */
  unknownCount: number;
  /** 위임자 노드 id → 같은 세션 위임 호출 수 */
  subByDelegator: Record<string, number>;
  /** 호출이 진행 중인(시작했지만 멈추지 않은) 위임자 노드 */
  subRunning: ReadonlySet<string>;
  /** 총 서브 호출 수 */
  subTotal: number;
}

export const EMPTY_SESSIONS: RunSessions = { list: [], byId: new Map(), byNode: new Map(), unknownCount: 0, subByDelegator: {}, subRunning: new Set(), subTotal: 0 };

interface Raw {
  id: string;
  nodeId?: string;
  start?: number;
  end?: number;
  tokens?: number;
  nodes: Set<string>;
  firstStart: number;
}

export interface DeriveSessionsInput {
  runId: string;
  nodeRuns: readonly NodeRun[];
  spans: readonly TraceSpan[] | undefined;
  events: readonly RunEvent[];
  labelOf(nodeId: string): string;
  /** 서브에이전트 호출 종료 이벤트 종류(진행 중 판정). 생략하면 진행 중 표시를 하지 않는다 */
  subStopType?: string;
}

/** 세션 색 토큰 참조(번호 순서). 변수 이름을 통째로 적어 둔다(토큰 소비 검사가 읽을 수 있게). */
const SESSION_COLORS = ["var(--ac-session-0)", "var(--ac-session-1)", "var(--ac-session-2)", "var(--ac-session-3)", "var(--ac-session-4)", "var(--ac-session-5)"] as const;
const sessionColor = (n: number): string => SESSION_COLORS[(n - 1) % SESSION_COLORS.length] as string;
const finite = (v: number | null | undefined): v is number => typeof v === "number" && Number.isFinite(v);

/** span이 이 실행의 것인가(자식 실행의 span은 그 실행 화면에서 센다). */
const ownSpan = (s: TraceSpan, runId: string): boolean => s.run_id == null || s.run_id === runId;

export function deriveRunSessions(input: DeriveSessionsInput): RunSessions {
  const raws = new Map<string, Raw>();
  const touch = (id: string, nodeId: string | null | undefined, start: number | null | undefined, end: number | null | undefined, topLevel: boolean): Raw => {
    let r = raws.get(id);
    if (r === undefined) {
      r = { id, nodes: new Set(), firstStart: Infinity };
      raws.set(id, r);
    }
    if (nodeId != null) r.nodes.add(nodeId);
    // 이름·시작은 세션을 연 쪽(부모 없는 span/NodeRun) 기준
    if (topLevel && finite(start) && start < r.firstStart) {
      r.firstStart = start;
      r.start = start;
      if (nodeId != null) r.nodeId = nodeId;
    } else if (topLevel && r.nodeId === undefined && nodeId != null) r.nodeId = nodeId;
    if (finite(end) && (r.end === undefined || end > r.end)) r.end = end;
    return r;
  };

  let unknownCount = 0;
  const spanTokens = new Map<string, number>();
  for (const s of input.spans ?? []) {
    if (!ownSpan(s, input.runId)) continue;
    const topLevel = s.parent_id == null;
    if (typeof s.session_id === "string" && s.session_id !== "") {
      touch(s.session_id, s.node_id, s.started_at, s.ended_at, topLevel);
      const tok = totalTokens(s.usage);
      if (tok !== undefined && topLevel) spanTokens.set(s.session_id, (spanTokens.get(s.session_id) ?? 0) + tok);
    } else if (topLevel && s.node_id != null && s.interaction_id == null) {
      unknownCount += 1;
    }
  }
  // NodeRun 보충: span에서 보지 못한 세션 id, 그리고 span이 없을 때의 폴백
  const nrTokens = new Map<string, number>();
  for (const nr of input.nodeRuns) {
    const id = nr.backend_session_id;
    if (typeof id !== "string" || id === "") continue;
    const known = raws.has(id);
    touch(id, nr.node_id, nr.started_at, nr.ended_at, true);
    if (!known || !spanTokens.has(id)) {
      const tok = totalTokens(nr.usage);
      if (tok !== undefined) nrTokens.set(id, (nrTokens.get(id) ?? 0) + tok);
    }
  }

  // 같은 세션 위임 호출(서브에이전트): 위임자 노드 = 이벤트 경로의 첫 노드
  const subByDelegator: Record<string, number> = {};
  const open: Record<string, number> = {};
  let subTotal = 0;
  for (const e of input.events) {
    const delegator = e.node_path[0];
    if (delegator === undefined) continue;
    if (e.type === SUBAGENT_START_EVENT) {
      subByDelegator[delegator] = (subByDelegator[delegator] ?? 0) + 1;
      open[delegator] = (open[delegator] ?? 0) + 1;
      subTotal += 1;
    } else if (input.subStopType !== undefined && e.type === input.subStopType) {
      open[delegator] = Math.max(0, (open[delegator] ?? 0) - 1);
    }
  }
  const subRunning = new Set(Object.entries(open).filter(([, n]) => n > 0).map(([k]) => k));

  const ordered = [...raws.values()].sort((a, b) => (a.firstStart === b.firstStart ? (a.id < b.id ? -1 : 1) : a.firstStart - b.firstStart));
  const list: SessionInfo[] = ordered.map((r, i) => {
    const nodeId = r.nodeId ?? [...r.nodes][0];
    const tokens = spanTokens.get(r.id) ?? nrTokens.get(r.id);
    return {
      id: r.id,
      number: i + 1,
      color: sessionColor(i + 1),
      nodeId,
      name: nodeId === undefined ? r.id : input.labelOf(nodeId),
      nodeIds: [...r.nodes],
      startedAt: r.start,
      endedAt: r.end,
      subCalls: [...r.nodes].reduce((n, node) => n + (subByDelegator[node] ?? 0), 0),
      tokens,
    };
  });
  const byId = new Map(list.map((s) => [s.id, s]));
  const byNode = new Map<string, SessionInfo>();
  for (const s of list) for (const node of s.nodeIds) if (!byNode.has(node)) byNode.set(node, s);
  return { list, byId, byNode, unknownCount, subByDelegator, subRunning, subTotal };
}

/** 이벤트가 속한 세션: 경로의 첫 노드(위임자)의 세션. 알 수 없으면 undefined. */
export function sessionOfEvent(sessions: RunSessions, event: Pick<RunEvent, "node_path">): SessionInfo | undefined {
  const node = event.node_path[0];
  return node === undefined ? undefined : sessions.byNode.get(node);
}
