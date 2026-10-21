import { describe, expect, it } from "vitest";
import type { EdgeTypeDescriptor, Graph, Interaction, NodeTypeDescriptor, RunEvent } from "@agent-console/contracts";
import { buildAgentView } from "./actors";
import { mergeInteractions } from "./assemble";
import { applyRunEvent, emptyLiveRun, foldRunEvents } from "./liveRun";
import { buildProgressSteps, countHandled, failedChildOf, hasRunningChild } from "./progress";
import { indexById, type NamingContext } from "./team";

// 모든 이름·종류는 임의 값이다.
const nodeTypes: NodeTypeDescriptor[] = [{ id: "nt-1", title: "N" }, { id: "nt-u", title: "U", executable: false }];
const naming: NamingContext = { nodeTypes: indexById(nodeTypes), agents: new Map() };
const kinds = indexById<EdgeTypeDescriptor>([
  { id: "k-flow", title: "순서", scheduling: "flow" },
  { id: "k-loop", title: "되돌림", scheduling: "flow", cycle: { max_iterations: 3 } },
  { id: "k-fail", title: "실패 시", scheduling: "flow", handles_failure: true },
  { id: "k-call", title: "독립 위임", scheduling: "none", invocation: { strategy: "s" } as never },
]);
const graph: Graph = {
  id: "g1",
  name: "부모 팀",
  nodes: [
    { id: "w", type: "nt-1", label: "작성자" },
    { id: "r", type: "nt-1", label: "검토" },
    { id: "t", type: "nt-1", label: "하위 팀 노드" },
    { id: "u", type: "nt-u", label: "사용자" },
  ],
  edges: [
    { id: "e1", source: { node: "w", port: "o" }, target: { node: "r", port: "i" }, kind: "k-flow" },
    { id: "e2", source: { node: "r", port: "o" }, target: { node: "w", port: "i" }, kind: "k-loop" },
    { id: "e3", source: { node: "w", port: "o" }, target: { node: "r", port: "x" }, kind: "k-call" },
    { id: "e4", source: { node: "t", port: "o" }, target: { node: "u", port: "i" }, kind: "k-fail" },
  ],
};
const childGraph: Graph = { id: "g2", name: "자식 팀", nodes: [{ id: "a", type: "nt-1", label: "자식 노드 가" }, { id: "b", type: "nt-1", label: "자식 노드 나" }, { id: "cu", type: "nt-u" }], edges: [{ id: "ce", source: { node: "a", port: "o" }, target: { node: "b", port: "i" }, kind: "k-flow" }] };

const ev = (seq: number, type: string, payload: Record<string, unknown> = {}, node_path: string[] = [], runId = "r1"): RunEvent => ({ event_id: `e${seq}`, run_id: runId, seq, ts: seq, node_path, type, payload });
const base = { graph, kinds, naming };

describe("liveRun: 반복·호출·자식 실행 이벤트", () => {
  it("자식 실행 알림은 부모 Run 상태로 읽지 않는다", () => {
    let live = emptyLiveRun("r1");
    live = applyRunEvent(live, ev(1, "run.running", { status: "running" }));
    live = applyRunEvent(live, ev(2, "run.child_started", { child_run_id: "c1", node_id: "t", graph_id: "g2" }, ["t"]));
    live = applyRunEvent(live, ev(3, "run.child_finished", { child_run_id: "c1", node_id: "t", status: "failed" }, ["t"]));
    expect(live.status).toBe("running");
    expect(live.children).toEqual([{ runId: "c1", nodeId: "t", graphId: "g2", startSeq: 2, finishedStatus: "failed" }]);
  });
  it("호출 실행(node_path 2단계 이상 + call)은 호출 목록에, 스케줄 실행은 노드 상태에 쌓인다", () => {
    const live = foldRunEvents("r1", [
      ev(1, "node.started", { status: "running", call: 0, iteration: 0 }, ["w", "r"]),
      ev(2, "node.completed", { status: "succeeded", call: 0, duration_ms: 1500 }, ["w", "r"]),
      ev(3, "node.started", { status: "running", call: null }, ["w"]),
    ]);
    expect(live.calls).toEqual([{ key: "w/r#0", path: ["w", "r"], delegator: "w", target: "r", call: 0, iteration: 0, status: "succeeded", seq: 1, durationMs: 1500 }]);
    expect(live.nodeStatus).toEqual({ w: "running" });
  });
  it("반복 시작·한도 도달을 기록한다", () => {
    const live = foldRunEvents("r1", [ev(1, "loop.iteration", { edge_id: "e2", iteration: 1, nodes: ["w", "r"] }), ev(2, "loop.exhausted", { edge_id: "e2", iteration: 3, max_iterations: 3 })]);
    expect(live.iterations).toEqual([{ edgeId: "e2", iteration: 1, nodeIds: ["w", "r"], seq: 1 }]);
    expect(live.exhausted).toEqual([{ edgeId: "e2", maxIterations: 3, seq: 2 }]);
  });
});

describe("진행 줄 단계 (buildProgressSteps)", () => {
  it("독립 위임: 위임자 아래 들여 쓰고 별도 세션 배지, 호출이 여러 번이면 호출 번호(+1)", () => {
    const live = foldRunEvents("r1", [
      ev(1, "node.started", { status: "running", call: 0 }, ["w", "r"]),
      ev(2, "node.completed", { status: "succeeded", call: 0 }, ["w", "r"]),
      ev(3, "node.started", { status: "running", call: 1 }, ["w", "r"]),
    ]);
    const steps = buildProgressSteps({ ...base, live });
    expect(steps).toHaveLength(2);
    expect(steps[0]).toMatchObject({ fromLabel: "작성자", toLabel: "검토", methodLabel: "독립 위임", indent: 1, badge: "별도 세션", callLabel: "호출 1", status: "succeeded" });
    expect(steps[1]).toMatchObject({ callLabel: "호출 2", status: "running" });
  });
  it("호출이 한 번이면 호출 번호를 붙이지 않고, 손자 위임은 한 단계 더 들여 쓴다", () => {
    const live = foldRunEvents("r1", [ev(1, "node.started", { status: "running", call: 0 }, ["w", "r", "t"])]);
    const [s] = buildProgressSteps({ ...base, live });
    expect(s?.callLabel).toBeUndefined();
    expect(s?.indent).toBe(2);
  });
  it("반복: 시작 이벤트 하나당 칩 하나, 회차는 값 + 1, 연결 자체의 통과는 칩을 따로 만들지 않는다", () => {
    const live = foldRunEvents("r1", [
      ev(1, "edge.traversed", { edge_id: "e1", source: { node: "w" }, target: { node: "r" } }),
      ev(2, "edge.traversed", { edge_id: "e2", source: { node: "r" }, target: { node: "w" } }),
      ev(3, "loop.iteration", { edge_id: "e2", iteration: 1, nodes: ["w", "r"] }),
      ev(4, "edge.traversed", { edge_id: "e1", source: { node: "w" }, target: { node: "r" } }),
    ]);
    const steps = buildProgressSteps({ ...base, live });
    expect(steps.map((s) => [s.key, s.iterationLabel])).toEqual([["r", undefined], ["loop:e2#1", "2회차"], ["r#2", "2회차"]]);
    expect(steps[1]).toMatchObject({ fromLabel: "검토", toLabel: "작성자", statusLabel: "시작" });
  });
  it("반복 한도 도달은 경고 칩", () => {
    const live = foldRunEvents("r1", [ev(1, "loop.exhausted", { edge_id: "e2", iteration: 3, max_iterations: 3 })]);
    expect(buildProgressSteps({ ...base, live })[0]).toMatchObject({ tone: "warning", statusLabel: "반복 한도 도달 (한도 3회)", fromLabel: "검토", toLabel: "작성자" });
  });
  it("중첩 팀: 칩 하나와 접고 펴는 자식 단계, 진행 숫자는 분모를 알 때만", () => {
    const live = foldRunEvents("r1", [ev(1, "run.child_started", { child_run_id: "c1", node_id: "t", graph_id: "g2" }, ["t"])]);
    const childLive = { c1: foldRunEvents("c1", [ev(1, "edge.traversed", { edge_id: "ce", source: { node: "a" }, target: { node: "b" } }, [], "c1"), ev(2, "node.completed", { status: "succeeded" }, ["a"], "c1"), ev(3, "node.started", { status: "running" }, ["b"], "c1")]) };
    const executableOf = (id: string) => id !== "nt-u";
    const [chip] = buildProgressSteps({ ...base, live, childLive, childGraphs: { g2: childGraph }, childHref: (id) => `/runs/${id}`, executableOf });
    expect(chip).toMatchObject({ key: "child:c1", status: "running", toLabel: "▣ 자식 팀 (중첩 팀)", solo: true, hint: "자식 팀" });
    expect(chip?.child).toEqual({ runId: "c1", href: "/runs/c1", nodeLabel: "하위 팀 노드", progress: { done: 1, total: 2 } });
    expect(chip?.children).toHaveLength(1);
    expect(chip?.children?.[0]).toMatchObject({ indent: 1, fromLabel: "자식 노드 가", toLabel: "자식 노드 나" });
    // 자식 그래프를 아직 모르면 분모를 추측하지 않는다
    const [bare] = buildProgressSteps({ ...base, live, childLive });
    expect(bare?.child?.progress).toBeUndefined();
    expect(bare?.children).toBeUndefined();
    expect(hasRunningChild([chip!])).toBe(true);
  });
  it("자식 실행이 끝나면 칩 상태가 최종 상태로, 실패면 실패한 자식을 찾는다", () => {
    const live = foldRunEvents("r1", [ev(1, "run.child_started", { child_run_id: "c1", node_id: "t", graph_id: "g2" }, ["t"]), ev(2, "run.child_finished", { child_run_id: "c1", node_id: "t", status: "failed" }, ["t"])]);
    const steps = buildProgressSteps({ ...base, live, childGraphs: { g2: childGraph } });
    expect(steps[0]).toMatchObject({ status: "failed", tone: "warning" });
    expect(failedChildOf(steps)).toEqual({ runId: "c1", name: "자식 팀" });
    expect(hasRunningChild(steps)).toBe(false);
  });
  it("실패 처리: 실패한 노드에서 실패 처리 연결이 지나갔으면 처리됨 칩, 푸터 계산에 센다", () => {
    const live = foldRunEvents("r1", [ev(1, "node.failed", { status: "failed" }, ["t"]), ev(2, "edge.traversed", { edge_id: "e4", source: { node: "t" }, target: { node: "u" } })]);
    const steps = buildProgressSteps({ ...base, live });
    const handled = steps.find((s) => s.key === "handled:t");
    expect(handled).toMatchObject({ statusLabel: "실패 → 처리됨", tone: "warning", solo: true });
    expect(countHandled(steps)).toBe(1);
  });
  it("자식 실행 안 노드 링크는 자식 Run으로 간다", () => {
    const live = foldRunEvents("c1", [ev(1, "edge.traversed", { edge_id: "ce", source: { node: "a" }, target: { node: "b" } }, [], "c1")]);
    const [s] = buildProgressSteps({ ...base, graph: childGraph, live, runId: "c1" });
    expect(s?.openTarget).toEqual({ runId: "c1", nodeId: "b" });
  });
});

describe("턴의 상호작용은 루트 기준", () => {
  const turn = { run_id: "root", user_text: "x", status: "waiting", interactions: [] } as never;
  const i = (id: string, extra: Partial<Interaction>): Interaction => ({ id, run_id: "root", kind: "k", status: "pending", created_at: 1, node_id: "n", ...extra }) as Interaction;
  it("루트 실행 id를 root_run_id로 가진 자식 실행 요청도 더한다(시간순)", () => {
    const latest = new Map([["a", i("a", { created_at: 3 })], ["b", i("b", { run_id: "child", root_run_id: "root", created_at: 2 })], ["c", i("c", { run_id: "child", root_run_id: "other" })]]);
    expect(mergeInteractions(turn, latest).map((x) => x.id)).toEqual(["b", "a"]);
  });
});

describe("답변 머리: 독립 위임 대상", () => {
  it("위임 호출로 불린 대상 노드의 답변은 위임자 이름을 달고, 호출이 없던 노드는 그대로", () => {
    const naming2: NamingContext = { nodeTypes: indexById([{ id: "nt-1", title: "N", binds: { kind: "k", field: "ref" } } as NodeTypeDescriptor]), agents: indexById([{ kind: "k", id: "ag1", name: "하나" }, { kind: "k", id: "ag2", name: "둘" }] as never) };
    const g: Graph = { id: "g", name: "g", nodes: [{ id: "a", type: "nt-1", config: { ref: "ag1" } }, { id: "b", type: "nt-1", config: { ref: "ag2" } }], edges: [] };
    const turns = [{ run_id: "r", user_text: "x", status: "completed", replies: [{ edge_id: "e1", node_id: "a", agent_id: "ag1", final: true, text: "가" }, { edge_id: "e2", node_id: "b", agent_id: "ag2", final: true, text: "나" }] }] as never;
    const view = buildAgentView(turns, { graph: g, naming: naming2 }, new Map([["b", "작성자"]]));
    expect(view("ag2")).toMatchObject({ name: "둘", delegatedBy: "작성자" });
    expect(view("ag1").delegatedBy).toBeUndefined();
    expect(buildAgentView(turns, { graph: g, naming: naming2 })("ag2").delegatedBy).toBeUndefined();
  });
});
