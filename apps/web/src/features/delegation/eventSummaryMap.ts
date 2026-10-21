import type { RunEvent } from "@agent-console/contracts";
import { formatRunOrdinal } from "./ordinal";
import { delegationMessages as t } from "./messages";

/**
 * 반복·자식 실행 RunEvent 매핑 표 — **이 파일이 이 이벤트 타입 문자열과 payload 키를 쓰는 앱 안의 유일한 곳**이다
 * (screen-delegation.md 0.1 예외, design §5R.9 표 4). 다른 코드는 `parseDelegationEvent`가 만든 결과만 쓴다.
 */
const LOOP_ITERATION = "loop.iteration";
const LOOP_EXHAUSTED = "loop.exhausted";
const CHILD_STARTED = "run.child_started";
const CHILD_FINISHED = "run.child_finished";

/** 반복·자식 실행 이벤트를 화면이 읽는 모양으로 푼 것. */
export type DelegationEventView =
  | { kind: "loop-iteration"; edgeId: string; /** 새로 연 NodeRun 회차(서버 값, 0부터) */ iteration: number; nodeIds: string[] }
  | { kind: "loop-exhausted"; edgeId: string; maxIterations: number | undefined }
  | { kind: "child-started"; childRunId: string; nodeId: string; graphId: string | undefined }
  | { kind: "child-finished"; childRunId: string; nodeId: string; status: string };

const str = (v: unknown): string | undefined => (typeof v === "string" && v !== "" ? v : undefined);
const num = (v: unknown): number | undefined => (typeof v === "number" && Number.isFinite(v) ? v : undefined);

/** 이벤트 하나를 푼다. 이 표의 이벤트가 아니거나 필수 값이 없으면 null(일반 행으로 보인다). */
export function parseDelegationEvent(event: Pick<RunEvent, "type" | "payload">): DelegationEventView | null {
  const p = event.payload ?? {};
  const type = event.type;
  if (type === LOOP_ITERATION) {
    const edgeId = str(p["edge_id"]);
    const iteration = num(p["iteration"]);
    if (edgeId === undefined || iteration === undefined) return null;
    const nodes = Array.isArray(p["nodes"]) ? p["nodes"].filter((n): n is string => typeof n === "string") : [];
    return { kind: "loop-iteration", edgeId, iteration, nodeIds: nodes };
  }
  if (type === LOOP_EXHAUSTED) {
    const edgeId = str(p["edge_id"]);
    if (edgeId === undefined) return null;
    return { kind: "loop-exhausted", edgeId, maxIterations: num(p["max_iterations"]) };
  }
  if (type === CHILD_STARTED) {
    const childRunId = str(p["child_run_id"]);
    const nodeId = str(p["node_id"]);
    if (childRunId === undefined || nodeId === undefined) return null;
    return { kind: "child-started", childRunId, nodeId, graphId: str(p["graph_id"]) };
  }
  if (type === CHILD_FINISHED) {
    const childRunId = str(p["child_run_id"]);
    const nodeId = str(p["node_id"]);
    const status = str(p["status"]);
    if (childRunId === undefined || nodeId === undefined || status === undefined) return null;
    return { kind: "child-finished", childRunId, nodeId, status };
  }
  return null;
}

/**
 * 연결 통과·건너뜀 이벤트(`edge.traversed`·`edge.skipped`)가 싣는 조건 판정 근거 원본(없으면 undefined). payload 키 이름을 쓰는 곳은 이 함수 하나다.
 * 해석은 `mapConditionOutcome`(어댑터)이 한다.
 */
export function conditionPayloadOf(event: Pick<RunEvent, "payload">): unknown {
  const cond = event.payload?.["condition"];
  return cond === null ? undefined : cond;
}

/** 이 이벤트가 부모 Run 자신의 상태를 바꾸는 `run.*` 이벤트가 아니라 자식 Run 알림인가(부모 Run 상태로 읽으면 안 된다). */
export function isChildRunNotice(event: Pick<RunEvent, "type">): boolean {
  return event.type === CHILD_STARTED || event.type === CHILD_FINISHED;
}

export interface EventSummaryContext {
  nodeLabel(nodeId: string): string;
  /** 연결 칩 텍스트(반복 한도 도달 요약에 붙인다). 없으면 생략 */
  edgeLabel?(edgeId: string): string;
  /** 자식 실행의 팀 구성 이름(없으면 이름 칸을 뺀다) */
  teamName?(childRunId: string): string | undefined;
  statusLabel(status: string): string;
  shortId(id: string): string;
}

export interface EventSummary {
  text: string;
  tone: "neutral" | "warning" | "status";
  /** 자식 실행 [열기] 대상 */
  childRunId?: string;
  /** 톤이 `status`일 때 상태 */
  status?: string;
}

/** 새 이벤트 형식의 한 줄 요약(이벤트 목록용). 이 표의 이벤트가 아니면 null — 일반 행으로 둔다. */
export function summarizeDelegationEvent(event: Pick<RunEvent, "type" | "payload">, ctx: EventSummaryContext): EventSummary | null {
  const view = parseDelegationEvent(event);
  if (view === null) return null;
  if (view.kind === "loop-iteration") {
    // 화면 번호는 formatRunOrdinal 한 곳에서 +1 한다. 첫 되돌림 = 값 1 → "2회차"
    return { text: t.run.event.loopIteration(formatRunOrdinal(view.iteration, "iteration"), view.nodeIds.map(ctx.nodeLabel).join(", ")), tone: "neutral" };
  }
  if (view.kind === "loop-exhausted") {
    // 이 이벤트의 iteration은 loop.iteration과 기준이 달라 화면에 쓰지 않는다(max_iterations만).
    return { text: t.run.event.loopExhausted(view.maxIterations ?? 0, ctx.edgeLabel?.(view.edgeId) ?? ""), tone: "warning" };
  }
  if (view.kind === "child-started") {
    return { text: t.run.event.childStarted(ctx.teamName?.(view.childRunId) ?? "", ctx.shortId(view.childRunId)), tone: "neutral", childRunId: view.childRunId };
  }
  return { text: t.run.event.childFinished(ctx.statusLabel(view.status), ctx.teamName?.(view.childRunId) ?? "", ctx.shortId(view.childRunId)), tone: "status", status: view.status, childRunId: view.childRunId };
}
