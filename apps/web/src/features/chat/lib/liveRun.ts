import type { ChatReply, ErrorInfo, RunEvent, RunStatus } from "@agent-console/contracts";
import { parseDelegationEvent } from "../../delegation";

/** 실행 이벤트를 접어 만든 한 Run의 화면용 상태. 순수 데이터이며 `applyRunEvent`로만 바꾼다. */
export interface LiveRun {
  runId: string;
  /** 마지막으로 반영한 seq(중복·역순 이벤트는 버린다) */
  lastSeq: number;
  /** `run.*` 이벤트로 알게 된 Run 상태 */
  status?: RunStatus;
  error?: ErrorInfo;
  /** `run.reply` 순서(도착 순) */
  replies: ChatReply[];
  /** 노드 id → 스트리밍 중인 텍스트 */
  streaming: Record<string, string>;
  /** 노드 id → 노드 실행 상태 */
  nodeStatus: Record<string, string>;
  nodeDurationMs: Record<string, number>;
  edges: { edgeId: string; from: string; to: string; seq: number }[];
  /** 사유(`reason`)가 붙은 건너뜀 노드(예: 이어 가기의 상류). 사유 문자열은 서버 값 그대로 */
  skipped: { nodeId: string; reason: string; seq: number }[];
  subagents: { id: string; delegator: string; target: string; seq: number; stoppedStatus?: string; durationMs?: number }[];
  /** 독립 위임으로 불린 호출 실행(`node.*` 이벤트의 `node_path` 길이 ≥ 2, `call` 있음). 키 = 경로 + 호출 번호 */
  calls: { key: string; path: string[]; delegator: string; target: string; call: number; iteration: number; status: string; seq: number; durationMs?: number }[];
  /** 반복 연결이 반복 영역을 다시 연 기록(반복 시작 이벤트) */
  iterations: { edgeId: string; iteration: number; nodeIds: string[]; seq: number }[];
  /** 반복 한도에 닿은 연결(반복 한도 도달 이벤트) */
  exhausted: { edgeId: string; maxIterations: number | undefined; seq: number }[];
  /** 이 Run이 만든 자식 Run(중첩 팀). 부모 Run 상태가 아니다 */
  children: { runId: string; nodeId: string; graphId: string | undefined; startSeq: number; finishedStatus?: string }[];
}

export function emptyLiveRun(runId: string): LiveRun {
  return { runId, lastSeq: 0, replies: [], streaming: {}, nodeStatus: {}, nodeDurationMs: {}, edges: [], skipped: [], subagents: [], calls: [], iterations: [], exhausted: [], children: [] };
}

const NODE_SUFFIX_STATUS: Record<string, string> = {
  started: "running",
  waiting: "waiting",
  resumed: "running",
  completed: "succeeded",
  failed: "failed",
  skipped: "skipped",
  cancelled: "cancelled",
  queued: "queued",
};

function str(v: unknown): string | undefined {
  return typeof v === "string" && v !== "" ? v : undefined;
}

function suffix(type: string): string {
  return type.slice(type.indexOf(".") + 1);
}

/** 이벤트 하나를 반영한 새 상태. 이미 본 seq(`<= lastSeq`)는 같은 객체를 돌려준다. */
export function applyRunEvent(live: LiveRun, ev: RunEvent): LiveRun {
  if (ev.seq <= live.lastSeq) return live;
  const next: LiveRun = { ...live, lastSeq: ev.seq };
  const p = ev.payload ?? {};
  const type = ev.type;
  const topNode = ev.node_path[0];

  // 반복·자식 실행 이벤트(매핑 표 한 파일에서 푼다). `run.child_*`는 부모 Run 자신의 상태가 아니라 자식 알림이다.
  const delegation = parseDelegationEvent(ev);
  if (delegation !== null) {
    switch (delegation.kind) {
      case "loop-iteration":
        next.iterations = [...live.iterations, { edgeId: delegation.edgeId, iteration: delegation.iteration, nodeIds: delegation.nodeIds, seq: ev.seq }];
        break;
      case "loop-exhausted":
        next.exhausted = [...live.exhausted, { edgeId: delegation.edgeId, maxIterations: delegation.maxIterations, seq: ev.seq }];
        break;
      case "child-started":
        next.children = [...live.children.filter((c) => c.runId !== delegation.childRunId), { runId: delegation.childRunId, nodeId: delegation.nodeId, graphId: delegation.graphId, startSeq: ev.seq }];
        break;
      case "child-finished":
        next.children = live.children.some((c) => c.runId === delegation.childRunId)
          ? live.children.map((c) => (c.runId === delegation.childRunId ? { ...c, finishedStatus: delegation.status } : c))
          : [...live.children, { runId: delegation.childRunId, nodeId: delegation.nodeId, graphId: undefined, startSeq: ev.seq, finishedStatus: delegation.status }];
        break;
    }
    return next;
  }
  if (type.startsWith("run.") && type !== "run.reply") {
    const status = str(p["status"]) ?? suffix(type);
    next.status = (type === "run.resumed" ? "running" : status) as RunStatus;
    const err = p["error"];
    if (typeof err === "object" && err !== null) next.error = err as ErrorInfo;
    return next;
  }
  // 호출 실행: 위임자가 부른 대상 노드(별도 세션). 스케줄 실행은 `call`이 null이다.
  if (type.startsWith("node.") && ev.node_path.length >= 2 && typeof p["call"] === "number") {
    const target = ev.node_path[ev.node_path.length - 1]!;
    const delegator = ev.node_path[ev.node_path.length - 2]!;
    const call = p["call"] as number;
    const key = `${ev.node_path.join("/")}#${call}`;
    const status = str(p["status"]) ?? NODE_SUFFIX_STATUS[suffix(type)] ?? suffix(type);
    const iteration = typeof p["iteration"] === "number" ? (p["iteration"] as number) : 0;
    const duration = typeof p["duration_ms"] === "number" ? (p["duration_ms"] as number) : undefined;
    const known = live.calls.some((c) => c.key === key);
    next.calls = known
      ? live.calls.map((c) => (c.key === key ? { ...c, status, ...(duration !== undefined ? { durationMs: duration } : {}) } : c))
      : [...live.calls, { key, path: [...ev.node_path], delegator, target, call, iteration, status, seq: ev.seq, ...(duration !== undefined ? { durationMs: duration } : {}) }];
    return next;
  }
  if (type.startsWith("node.") && topNode !== undefined && ev.node_path.length === 1) {
    next.nodeStatus = { ...live.nodeStatus, [topNode]: str(p["status"]) ?? NODE_SUFFIX_STATUS[suffix(type)] ?? suffix(type) };
    const reason = str(p["reason"]);
    if (type === "node.skipped" && reason !== undefined) next.skipped = [...live.skipped.filter((x) => x.nodeId !== topNode), { nodeId: topNode, reason, seq: ev.seq }];
    if (typeof p["duration_ms"] === "number") next.nodeDurationMs = { ...live.nodeDurationMs, [topNode]: p["duration_ms"] };
    if (type === "node.started") {
      const { [topNode]: _drop, ...rest } = live.streaming;
      void _drop;
      next.streaming = rest;
    }
    return next;
  }
  if (type === "agent.text_delta" && topNode !== undefined && ev.node_path.length === 1) {
    next.streaming = { ...live.streaming, [topNode]: (live.streaming[topNode] ?? "") + (str(p["text"]) ?? (typeof p["text"] === "string" ? p["text"] : "")) };
    return next;
  }
  if (type === "run.reply") {
    const node = str(p["node_id"]) ?? topNode;
    const edge = str(p["edge_id"]);
    if (node === undefined || edge === undefined) return next;
    const reply: ChatReply = {
      edge_id: edge,
      node_id: node,
      agent_id: ev.actor ?? null,
      label: typeof p["label"] === "string" ? p["label"] : null,
      order: typeof p["order"] === "number" ? p["order"] : null,
      final: p["final"] !== false,
      text: typeof p["text"] === "string" ? p["text"] : "",
    };
    const { [node]: _drop, ...rest } = live.streaming;
    void _drop;
    next.replies = [...live.replies, reply];
    next.streaming = rest;
    return next;
  }
  if (type === "edge.traversed") {
    const edgeId = str(p["edge_id"]);
    const from = (p["source"] as { node?: unknown } | undefined)?.node;
    const to = (p["target"] as { node?: unknown } | undefined)?.node;
    if (edgeId !== undefined && typeof from === "string" && typeof to === "string") next.edges = [...live.edges, { edgeId, from, to, seq: ev.seq }];
    return next;
  }
  if (type === "agent.subagent_started") {
    const id = str(p["subagent_id"]);
    const target = str(p["name"]);
    if (id !== undefined && target !== undefined && topNode !== undefined) next.subagents = [...live.subagents, { id, delegator: topNode, target, seq: ev.seq }];
    return next;
  }
  if (type === "agent.subagent_stopped") {
    const id = str(p["subagent_id"]);
    next.subagents = live.subagents.map((s) =>
      s.id === id ? { ...s, stoppedStatus: str(p["status"]) ?? "completed", ...(typeof p["duration_ms"] === "number" ? { durationMs: p["duration_ms"] } : {}) } : s,
    );
    return next;
  }
  return next;
}

/** 이벤트 목록(순서 무관)을 한 번에 접는다. */
export function foldRunEvents(runId: string, events: readonly RunEvent[], from: LiveRun = emptyLiveRun(runId)): LiveRun {
  return [...events].sort((a, b) => a.seq - b.seq).reduce(applyRunEvent, from);
}

/** 실행 상태 중 아직 끝나지 않은 것. */
export function isActiveStatus(status: string | null | undefined): boolean {
  return status === "running" || status === "waiting" || status === "paused" || status === "queued";
}

/**
 * 같은 Run의 두 가지 출처(WS 구독 누적, 저장된 이벤트 읽기)를 합친다. 더 많이 반영한(`lastSeq`가 큰) 쪽을 쓴다.
 * 구독이 끊긴 뒤 남은 낡은 누적이 새로 읽은 기록을 덮지 않게 한다.
 */
export function mergeLiveRuns(a: Readonly<Record<string, LiveRun>>, b: Readonly<Record<string, LiveRun>>): Record<string, LiveRun> {
  const out: Record<string, LiveRun> = { ...a };
  for (const [id, lv] of Object.entries(b)) {
    const cur = out[id];
    if (cur === undefined || lv.lastSeq >= cur.lastSeq) out[id] = lv;
  }
  return out;
}

const TERMINAL: ReadonlySet<string> = new Set<RunStatus>(["completed", "failed", "cancelled", "interrupted"]);

/** 이 Run의 종료 상태(`run.<종료>`)까지 반영했는가. 서버 계약상 종료 이벤트가 그 Run의 마지막 이벤트다. */
export function hasReachedEnd(live: LiveRun | undefined): boolean {
  return live?.status !== undefined && TERMINAL.has(live.status);
}
