import { describe, expect, it } from "vitest";
import type { EdgeTypeDescriptor, Graph, Interaction, NodeRun, Run, RunEvent, Trace } from "@agent-console/contracts";
import { PERIOD_OPTIONS } from "./runsConfig";
import {
  activeCounts,
  buildEventRows,
  buildObserveRows,
  collectPrefixes,
  deriveRunOverlay,
  filterFailedSpans,
  filterRuns,
  formatTokensShort,
  interactionStats,
  mergeEvents,
  observeStats,
  runDurationMs,
  sortInteractions,
  summarizeActors,
  summarizeEvent,
} from "./runsLib";

// 도메인과 무관한 임의 이름: 연결 종류·노드 타입은 서버 데이터라는 가정 그대로 쓴다.
const ev = (seq: number, type: string, extra: Partial<RunEvent> = {}): RunEvent => ({ event_id: `e${seq}`, run_id: "r1", seq, ts: 100 + seq, node_path: [], type, ...extra });
const run = (id: string, status: string, createdAt: number, extra: Partial<Run> = {}): Run => ({ id, graph_id: "g1", graph_version: "v1", status: status as Run["status"], input: {}, origin: "api", created_at: createdAt, ...extra });

describe("filterRuns", () => {
  const now = 1_000_000;
  const runs = [run("a", "running", now - 60, { input: { text: "로그인 화면 스펙" } }), run("b", "completed", now - 3 * 86400), run("c", "failed", now - 40 * 86400)];
  it("기간·상태·검색을 클라이언트에서 거른다", () => {
    expect(filterRuns(runs, { statuses: [], period: "7d", query: "" }, now, PERIOD_OPTIONS).map((r) => r.id)).toEqual(["a", "b"]);
    expect(filterRuns(runs, { statuses: [], period: "all", query: "" }, now, PERIOD_OPTIONS)).toHaveLength(3);
    expect(filterRuns(runs, { statuses: ["failed", "running"], period: "all", query: "" }, now, PERIOD_OPTIONS).map((r) => r.id)).toEqual(["a", "c"]);
    expect(filterRuns(runs, { statuses: [], period: "all", query: "스펙" }, now, PERIOD_OPTIONS).map((r) => r.id)).toEqual(["a"]);
  });
  it("활성 수와 소요", () => {
    expect(activeCounts(runs, "waiting")).toEqual({ running: 1, waiting: 0 });
    expect(runDurationMs(run("x", "running", 0, { started_at: 10 }), 20)).toBe(10_000);
    expect(runDurationMs(run("x", "completed", 0, { started_at: 10, ended_at: 12 }), 99)).toBe(2000);
    expect(runDurationMs(run("x", "queued", 0), 99)).toBeUndefined();
  });
  it("약식 토큰", () => {
    expect([formatTokensShort(300), formatTokensShort(4100), formatTokensShort(22000), formatTokensShort(undefined)]).toEqual(["300", "4.1k", "22k", "–"]);
  });
});

describe("mergeEvents", () => {
  it("같은 seq는 한 번만 적용하고 순서에 틈이 있으면 gap", () => {
    const first = mergeEvents([], [ev(1, "x"), ev(2, "x")]);
    expect(first.gap).toBe(false);
    const dup = mergeEvents(first.events, [ev(2, "x")]);
    expect(dup.added).toBe(0);
    const gap = mergeEvents(first.events, [ev(5, "x")]);
    expect(gap.gap).toBe(true);
    expect(gap.events.map((e) => e.seq)).toEqual([1, 2, 5]);
    expect(mergeEvents(first.events, [ev(3, "x")]).gap).toBe(false);
  });
});

describe("deriveRunOverlay: 이벤트·디스크립터만으로 그래프 상태를 그린다", () => {
  const kinds: EdgeTypeDescriptor[] = [
    { id: "k-flow", title: "넘기기류", scheduling: "flow" },
    { id: "k-call", title: "부르기류", scheduling: "none", invocation: { strategy: "s" } },
    { id: "k-out", title: "답변류", scheduling: "exit" },
  ];
  const graph: Graph = {
    id: "g1",
    name: "g",
    nodes: [
      { id: "n1", type: "t" },
      { id: "n2", type: "t" },
      { id: "n3", type: "t" },
      { id: "u", type: "t2" },
    ],
    edges: [
      { id: "e-flow", source: { node: "n1", port: "o" }, target: { node: "n2", port: "i" }, kind: "k-flow" },
      { id: "e-call", source: { node: "n1", port: "o" }, target: { node: "n3", port: "i" }, kind: "k-call" },
      { id: "e-out", source: { node: "n2", port: "o" }, target: { node: "u", port: "i" }, kind: "k-out" },
    ],
  };
  const nodeRuns: NodeRun[] = [
    { run_id: "r1", node_id: "n1", status: "succeeded" },
    { run_id: "r1", node_id: "n2", status: "waiting" },
  ];
  const pending: Interaction = { id: "i1", run_id: "r1", node_id: "n2", kind: "k", status: "pending", created_at: 1_700_000_000 };

  it("지나간 넘기기에만 순번, 위임은 호출 횟수·서브에이전트 상태, 대기 노드", () => {
    const events = [
      ev(1, "edge.traversed", { payload: { edge_id: "e-flow" } }),
      ev(2, "edge.traversed", { payload: { edge_id: "e-out" } }),
      ev(3, "agent.subagent_started", { node_path: ["n1"], payload: { name: "n3" } }),
      ev(4, "agent.subagent_stopped", { payload: { name: "n3", status: "completed" } }),
      ev(5, "agent.subagent_started", { node_path: ["n1"], payload: { name: "n3" } }),
    ];
    const o = deriveRunOverlay({ graph, edgeTypes: kinds, nodeRuns, events, pending: [pending] });
    expect(o.edgeOrder).toEqual({ "e-flow": 1 });
    expect(o.edgeStates["e-flow"]).toBe("traversed");
    expect(o.edgeCounts).toEqual({ "e-call": 2 });
    expect(o.subagentCalls).toEqual({ n3: 2 });
    expect(o.nodeStates["n3"]?.status).toBe("running");
    expect(o.nodeStates["n2"]?.status).toBe("waiting");
    expect(o.waitingNodes["n2"]?.since).toBe(new Date(1_700_000_000_000).toISOString());
  });

  it("서브에이전트 종료 상태 매핑, 모르는 값은 원문, 건너뛴 노드의 나가는 엣지는 dead", () => {
    const events = [ev(1, "agent.subagent_started", { payload: { name: "n3" } }), ev(2, "agent.subagent_stopped", { payload: { name: "n3", status: "stopped" } })];
    const o = deriveRunOverlay({ graph, edgeTypes: kinds, nodeRuns: [{ run_id: "r1", node_id: "n1", status: "skipped" }], events, pending: [] });
    expect(o.nodeStates["n3"]?.status).toBe("cancelled");
    expect(o.edgeStates["e-flow"]).toBe("dead");
    const odd = deriveRunOverlay({ graph, edgeTypes: kinds, nodeRuns: [], events: [ev(1, "agent.subagent_stopped", { payload: { name: "n3", status: "zzz" } })], pending: [] });
    expect(odd.nodeStates["n3"]?.status).toBe("zzz");
  });

  it("같은 노드의 NodeRun은 시도·반복이 큰 쪽이 이긴다", () => {
    const o = deriveRunOverlay({
      graph,
      edgeTypes: kinds,
      nodeRuns: [
        { run_id: "r1", node_id: "n1", status: "failed", attempt: 1 },
        { run_id: "r1", node_id: "n1", status: "running", attempt: 2 },
      ],
      events: [],
      pending: [],
    });
    expect(o.nodeStates["n1"]?.status).toBe("running");
  });
});

describe("이벤트 표시", () => {
  it("연속 텍스트 조각은 한 행으로 합친다", () => {
    const events = [ev(1, "agent.text_delta", { actor: "a", payload: { text: "안" } }), ev(2, "agent.text_delta", { actor: "a", payload: { text: "녕" } }), ev(3, "agent.message", { actor: "a", payload: { text: "안녕" } })];
    const rows = buildEventRows(events);
    expect(rows).toHaveLength(2);
    expect(rows[0]?.text).toBe("안녕");
    expect(rows[0]?.count).toBe(2);
  });
  it("모르는 type도 payload로 요약하고 접두·actor 목록은 데이터에서 만든다", () => {
    expect(summarizeEvent(ev(1, "zz.custom", { payload: { status: "ok", extra: 1 } }))).toContain("status=ok");
    expect(summarizeEvent(ev(1, "zz.custom"))).toBe("");
    expect(collectPrefixes([ev(1, "hook.invoked"), ev(2, "zz.a"), ev(3, "hook.completed")])).toEqual(["hook.", "zz."]);
    expect(summarizeActors([ev(1, "x", { actor: "p" }), ev(2, "x", { actor: "p" }), ev(3, "x")]).map((a) => [a.actor, a.count])).toEqual([["p", 2]]);
  });
  it("관측 행·집계: 접두는 인자로 받고 오류·평균을 센다", () => {
    const events = [
      ev(1, "hook.invoked", { payload: { event: "PreToolUse", tool_name: "T" } }),
      ev(2, "mcp.call_completed", { payload: { server: "s", tool: "t", duration_ms: 100, is_error: true } }),
      ev(3, "mcp.call_completed", { payload: { server: "s", tool: "t", duration_ms: 300 } }),
      ev(4, "agent.message"),
    ];
    const rows = buildObserveRows(events, ["hook.", "mcp."]);
    expect(rows).toHaveLength(3);
    expect(rows[1]?.kind).toBe("s · t");
    const stats = observeStats(rows);
    expect(stats).toEqual({ byPrefix: { "hook.": 1, "mcp.": 2 }, errors: 1, avgMs: 200 });
    expect(buildObserveRows(events, ["zz."])).toEqual([]);
  });
});

describe("상호작용·trace", () => {
  const mk = (id: string, status: Interaction["status"], created: number, closed?: number): Interaction => ({ id, run_id: "r", node_id: "n", kind: "k", status, created_at: created, ...(closed ? { closed_at: closed } : {}) });
  it("대기 먼저, 그다음 최신순, 평균 대기는 닫힌 것만", () => {
    const list = [mk("a", "answered", 10, 20), mk("b", "pending", 5), mk("c", "answered", 30, 34)];
    expect(sortInteractions(list).map((i) => i.id)).toEqual(["b", "c", "a"]);
    expect(interactionStats(list)).toEqual({ total: 3, waiting: 1, avgWaitSec: 7 });
    expect(interactionStats([mk("p", "pending", 1)]).avgWaitSec).toBeUndefined();
  });
  it("실패만 보기는 조상 span을 함께 남긴다", () => {
    const trace: Trace = {
      run_id: "r",
      spans: [
        { id: "p", kind: "node" },
        { id: "c1", kind: "delegated", parent_id: "p", status: "failed" },
        { id: "c2", kind: "delegated", parent_id: "p", status: "succeeded" },
        { id: "o", kind: "node", status: "succeeded" },
      ],
      links: [{ source: "p", target: "o" }],
    };
    const out = filterFailedSpans(trace, "failed");
    expect(out.spans?.map((s) => s.id)).toEqual(["p", "c1"]);
    expect(out.links).toEqual([]);
  });
});
