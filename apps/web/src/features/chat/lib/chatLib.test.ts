import { describe, expect, it } from "vitest";
import type { Agent, ChatTurn, ConversationSummary, EdgeTypeDescriptor, Graph, Interaction, InteractionKindDescriptor, NodeTypeDescriptor, RunEvent, TeamPlanSummary } from "@agent-console/contracts";
import { ApiError } from "@agent-console/api-client";
import { actorLabel, buildAgentView } from "./actors";
import { buildResponse, quoteForResend } from "./answer";
import { assembleTurns, mergeInteractions, streamPlaceholders } from "./assemble";
import { resolveChatSettings } from "./chatSettings";
import { filterConversations, pendingSinceOf, sortConversations, upsertConversation } from "./conversations";
import { closedInteraction, fieldProblems } from "../../interactions";
import { applyRunEvent, emptyLiveRun, foldRunEvents, hasReachedEnd, mergeLiveRuns } from "./liveRun";
import { buildProgressSteps } from "./progress";
import { hasEntry, indexById, replyEdgesOf, summarizeTeam, type NamingContext } from "./team";

// 이름·종류는 모두 임의 값이다(제품 어휘와 무관해야 한다).
const nodeTypes: NodeTypeDescriptor[] = [
  { id: "nt-a", title: "노드 에이", binds: { kind: "kind-agent", field: "ref" } },
  { id: "nt-u", title: "노드 유저" },
];
const agents: Agent[] = [
  { kind: "agent", id: "ag-1", name: "하나", role: "역할 일" } as unknown as Agent,
  { kind: "agent", id: "ag-2", name: "둘" } as unknown as Agent,
];
// binds.kind와 정의의 kind가 같은 경우만 에이전트로 본다.
const bindsKind = (agents[0] as { kind: string }).kind;
nodeTypes[0]!.binds = { kind: bindsKind, field: "ref" };
const naming: NamingContext = { nodeTypes: indexById(nodeTypes), agents: indexById(agents) };

const edgeKinds = indexById<EdgeTypeDescriptor>([
  { id: "e-entry", title: "입구", scheduling: "entry" },
  { id: "e-exit", title: "출구", scheduling: "exit" },
  { id: "e-flow", title: "넘기기 방식", scheduling: "flow", ui_hints: { dashed: true } },
  { id: "e-call", title: "위임 방식", scheduling: "none", invocation: { strategy: "s" } as never },
  { id: "e-ask", title: "묻기", scheduling: "none", interaction: { kinds: ["x"] } },
]);

const graph: Graph = {
  id: "g1",
  name: "팀",
  nodes: [
    { id: "n1", type: "nt-a", config: { ref: "ag-1" } },
    { id: "n2", type: "nt-a", config: { ref: "ag-2" } },
    { id: "u", type: "nt-u", label: "사용자" },
  ],
  edges: [
    { id: "ed1", source: { node: "u", port: "out" }, target: { node: "n1", port: "in" }, kind: "e-entry" },
    { id: "ed2", source: { node: "n1", port: "out" }, target: { node: "u", port: "in" }, kind: "e-exit", config: { stream: false, order: 9, label: "설정에만 있는 값", final: false } },
    { id: "ed3", source: { node: "n1", port: "out" }, target: { node: "n2", port: "in" }, kind: "e-flow" },
    { id: "ed4", source: { node: "n1", port: "out" }, target: { node: "n2", port: "in" }, kind: "e-call" },
    { id: "ed5", source: { node: "n1", port: "out" }, target: { node: "u", port: "asks" }, kind: "e-ask" },
  ],
};

const ev = (seq: number, type: string, payload: Record<string, unknown> = {}, node_path: string[] = [], extra: Partial<RunEvent> = {}): RunEvent => ({
  event_id: `e${seq}`, run_id: "r1", seq, ts: seq, node_path, type, payload, ...extra,
});

function conv(over: Partial<ConversationSummary> & { id: string }): ConversationSummary {
  return { graph_id: "g1", created_at: 1, updated_at: 1, ...over };
}

describe("채팅 설정 합치기", () => {
  it("팀 구성 층의 값이 공통 위에 덮고, null은 상속한다", () => {
    const out = resolveChatSettings({ reply_display: "merged", send_key: "enter" }, { reply_display: null as never, send_key: "mod_enter", answer_with_composer: false }, {});
    expect(out).toEqual({ reply_display: "merged", send_key: "mod_enter", answer_with_composer: false });
  });
  it("스키마 기본값이 바닥이다", () => {
    expect(resolveChatSettings(undefined, undefined).answer_with_composer).toBe(true);
  });
});

describe("대화 목록 정렬·필터", () => {
  const list = [
    conv({ id: "old", updated_at: 10 }),
    conv({ id: "new", updated_at: 50 }),
    conv({ id: "wait-late", updated_at: 20, pending_interactions: 1 }),
    conv({ id: "wait-early", updated_at: 5, pending_interactions: 2 }),
  ];
  const since = pendingSinceOf([{ conversation_id: "wait-late", created_at: 200 }, { conversation_id: "wait-early", created_at: 100 }]);
  it("기본은 응답 대기 우선(오래 기다린 순), 나머지는 갱신순", () => {
    expect(sortConversations(list, undefined, since).map((c) => c.id)).toEqual(["wait-early", "wait-late", "new", "old"]);
    expect(sortConversations(list, "모르는-값", since).map((c) => c.id)).toEqual(["wait-early", "wait-late", "new", "old"]);
  });
  it("갱신순만", () => {
    expect(sortConversations(list, "updated", since).map((c) => c.id)).toEqual(["new", "wait-late", "old", "wait-early"]);
  });
  it("보관 제외·제목 검색·갱신 반영", () => {
    const l = [conv({ id: "a", title: "로그인 화면" }), conv({ id: "b", title: "배포", archived: true })];
    expect(filterConversations(l, { query: "", includeArchived: false }).map((c) => c.id)).toEqual(["a"]);
    expect(filterConversations(l, { query: "배", includeArchived: true }).map((c) => c.id)).toEqual(["b"]);
    expect(upsertConversation(l, conv({ id: "a", title: "바뀜" })).find((c) => c.id === "a")?.title).toBe("바뀜");
    expect(upsertConversation(l, conv({ id: "z" }))[0]?.id).toBe("z");
  });
});

// 서버가 계산한 계획 요약. 연결 설정(config)의 값과 다르게 두어 화면이 config를 읽지 않음을 확인한다.
const plan: TeamPlanSummary = {
  entries: [{ edge_id: "ed1", node_id: "n1" }],
  answers: [{ edge_id: "ed2", node_id: "n1", label: "최종", order: 2, final: true, stream: true }],
  grants: { n1: { kinds: ["x"] } },
};

describe("팀 구성 계산(연결 종류 이름 없이)", () => {
  it("입구·답변·되묻기 요약은 계획 요약에서 읽는다", () => {
    const s = summarizeTeam(plan, graph, naming);
    expect(s).toEqual({ entries: ["하나"], answers: ["하나"], askers: ["하나"] });
  });
  it("답변 자리(스트림·순서·라벨·마지막 답변)는 계획 요약 값이고 연결 config는 읽지 않는다", () => {
    const [r] = replyEdgesOf(plan);
    expect(r).toMatchObject({ edgeId: "ed2", nodeId: "n1", stream: true, order: 2, label: "최종", final: true });
    expect(replyEdgesOf(undefined)).toEqual([]);
    // 생략된 필드는 계약 기본값(final = true, stream = false)
    expect(replyEdgesOf({ answers: [{ edge_id: "e", node_id: "n" }] })[0]).toMatchObject({ final: true, stream: false, order: null, label: null });
  });
  it("입구 없음은 서버가 계산한 목록이 비었을 때만", () => {
    expect(hasEntry({ entry_labels: [] })).toBe(false);
    expect(hasEntry({ entry_labels: ["a"] })).toBe(true);
    expect(hasEntry({ entry_labels: null })).toBeUndefined();
  });
});

describe("실행 이벤트 접기", () => {
  it("노드 상태·스트리밍·답변·중복 seq", () => {
    let live = emptyLiveRun("r1");
    live = applyRunEvent(live, ev(1, "run.started", { status: "running" }));
    live = applyRunEvent(live, ev(2, "node.started", { status: "running" }, ["n1"]));
    live = applyRunEvent(live, ev(3, "agent.text_delta", { text: "안" }, ["n1"]));
    live = applyRunEvent(live, ev(4, "agent.text_delta", { text: "녕" }, ["n1"]));
    expect(live.streaming).toEqual({ n1: "안녕" });
    expect(live.nodeStatus).toEqual({ n1: "running" });
    expect(applyRunEvent(live, ev(4, "agent.text_delta", { text: "중복" }, ["n1"]))).toBe(live);
    live = applyRunEvent(live, ev(5, "run.reply", { edge_id: "ed2", node_id: "n1", text: "안녕하세요", final: true }, [], { actor: "ag-1" }));
    expect(live.replies).toHaveLength(1);
    expect(live.streaming).toEqual({});
    live = applyRunEvent(live, ev(6, "run.waiting", { status: "waiting" }));
    expect(live.status).toBe("waiting");
    live = applyRunEvent(live, ev(7, "run.resumed"));
    expect(live.status).toBe("running");
  });
  it("서브에이전트 종료 상태를 반영한다", () => {
    const live = foldRunEvents("r1", [
      ev(2, "agent.subagent_stopped", { subagent_id: "s1", status: "completed", duration_ms: 1500 }, ["n1"]),
      ev(1, "agent.subagent_started", { subagent_id: "s1", name: "n2" }, ["n1"]),
    ]);
    expect(live.subagents[0]).toMatchObject({ delegator: "n1", target: "n2", stoppedStatus: "completed", durationMs: 1500 });
  });
});

describe("진행 줄", () => {
  it("방식 라벨·점선은 디스크립터에서, 서브에이전트는 들여쓴다", () => {
    const live = foldRunEvents("r1", [
      ev(1, "edge.traversed", { edge_id: "ed1", source: { node: "u", port: "out" }, target: { node: "n1", port: "in" } }),
      ev(2, "node.started", { status: "running" }, ["n1"]),
      ev(3, "edge.traversed", { edge_id: "ed3", source: { node: "n1", port: "out" }, target: { node: "n2", port: "in" } }),
      ev(4, "node.completed", { status: "succeeded", duration_ms: 2000 }, ["n2"]),
      ev(5, "agent.subagent_started", { subagent_id: "s1", name: "n2" }, ["n1"]),
    ]);
    const steps = buildProgressSteps({ live, graph, kinds: edgeKinds, naming });
    expect(steps).toHaveLength(2); // 입구 연결은 제외
    expect(steps[0]).toMatchObject({ fromLabel: "하나", toLabel: "둘", methodLabel: "넘기기 방식", methodDashed: true, status: "succeeded", durationMs: 2000, indent: 0 });
    expect(steps[1]).toMatchObject({ methodLabel: "위임 방식", status: "running", indent: 1 });
  });
});

describe("턴 조립", () => {
  const turn: ChatTurn = { run_id: "r1", user_text: "질문", status: "running", replies: [], interactions: [] };
  it("스트림이 켜진 답변 노드는 빈 placeholder를 둔다(노드가 일하는 동안, 답변이 오기 전까지)", () => {
    const live = foldRunEvents("r1", [ev(1, "node.started", { status: "running" }, ["n1"])]);
    const out = assembleTurns({ serverTurns: [turn], live: { r1: live }, interactions: new Map(), replyEdges: replyEdgesOf(plan), agentOfNode: () => "ag-1" });
    expect(out[0]!.replies).toEqual([expect.objectContaining({ edge_id: "ed2", node_id: "n1", text: "", agent_id: "ag-1", order: 2, label: "최종" })]);
    expect(streamPlaceholders(live, replyEdgesOf(plan), [{ edge_id: "ed2", node_id: "n1", text: "x" }], () => null)).toEqual([]);
  });
  it("서버가 끝났다고 한 턴은 서버 값, 상호작용은 최신 상태로 덮는다", () => {
    const done: ChatTurn = { ...turn, status: "completed", replies: [{ edge_id: "x", node_id: "n1", text: "끝" }], interactions: [{ id: "i1", run_id: "r1", node_id: "n1", kind: "k", status: "pending", created_at: 1 }] };
    const latest = new Map<string, Interaction>([["i1", { ...done.interactions![0]!, status: "answered" }]]);
    const live = foldRunEvents("r1", [ev(1, "run.started", { status: "running" })]);
    const out = assembleTurns({ serverTurns: [done], live: { r1: live }, interactions: latest, replyEdges: [], agentOfNode: () => null });
    expect(out[0]!.status).toBe("completed");
    expect(out[0]!.replies).toHaveLength(1);
    expect(out[0]!.interactions![0]!.status).toBe("answered");
    expect(mergeInteractions(done, new Map([["i2", { id: "i2", run_id: "r1", node_id: "n", kind: "k", status: "pending", created_at: 2 }]]))).toHaveLength(2);
  });
  it("진행 중 턴은 실시간 상태(waiting)를 따른다", () => {
    const live = foldRunEvents("r1", [ev(1, "run.waiting", { status: "waiting" })]);
    expect(assembleTurns({ serverTurns: [turn], live: { r1: live }, interactions: new Map(), replyEdges: [], agentOfNode: () => null })[0]!.status).toBe("waiting");
  });
});

describe("입력창 답변 응답 만들기(판정은 chat 패키지 resolveAnswerSurface)", () => {
  const descriptor: InteractionKindDescriptor = { id: "kind-z", title: "임의", free_text_path: "/deep/text" };
  const pend = (over: Partial<Interaction> = {}): Interaction => ({ id: "i1", run_id: "r1", node_id: "n", kind: "kind-z", status: "pending", created_at: 1, ...over });
  it("응답은 free_text_path 자리에 텍스트를 넣는다", () => {
    expect(buildResponse(descriptor, "답")).toEqual({ deep: { text: "답" } });
    expect(() => buildResponse({ free_text_path: null }, "x")).toThrow();
  });
  it("끊긴 질문을 인용 초안으로 만든다", () => {
    const i = pend({ payload: { questions: [{ question: "어느 쪽?\n둘째 줄", options: [{ label: "가" }, { label: "나" }] }] } });
    const text = quoteForResend(i, "요청자", ({ who, question }) => `> (${who}의 질문) ${question}`, (o) => `선택지: ${o.join(" / ")}`);
    expect(text).toBe("> (요청자의 질문) 어느 쪽?\n선택지: 가 / 나\n\n");
  });
});

describe("요청자 표기", () => {
  const ctx = { graph, naming };
  const texts = { inside: (p: string, n: string) => `${p} 안의 ${n}` };
  const base: Interaction = { id: "i", run_id: "r", node_id: "n1", kind: "k", status: "pending", created_at: 1 };
  it("주 에이전트는 이름 · 역할", () => {
    expect(actorLabel({ ...base, actor: "ag-1", node_path: ["n1"] }, ctx, texts)).toBe("하나 · 역할 일");
    expect(actorLabel({ ...base, actor: "ag-2", node_path: ["n2"] }, ctx, texts)).toBe("둘");
  });
  it("서브에이전트는 위임자 안의 대상", () => {
    expect(actorLabel({ ...base, actor: "ag-2", node_path: ["n1", "n2"] }, ctx, texts)).toBe("하나 안의 둘");
  });
  it("에이전트가 없으면 노드 이름", () => {
    expect(actorLabel({ ...base, node_id: "u", node_path: ["u"] }, ctx, texts)).toBe("사용자");
  });
  it("위임받은 에이전트의 답변은 위임자 이름을 달고 노드 id도 이름으로 푼다", () => {
    const turns: ChatTurn[] = [{ run_id: "r", user_text: "", status: "completed", replies: [{ edge_id: "ed2", node_id: "n1", agent_id: "ag-2", text: "t" }] }];
    const view = buildAgentView(turns, ctx);
    expect(view("ag-2")).toMatchObject({ name: "둘", parentName: "하나" });
    expect(view("n1")).toMatchObject({ name: "하나", role: "역할 일" });
    expect(view("?")).toEqual({ name: "?" });
  });
});

describe("서버 오류 해석", () => {
  it("422 필드 오류와 409의 현재 상태", () => {
    const e422 = new ApiError(422, { code: "validation_failed", message: "m", details: { errors: [{ loc: ["body", "response", "answers"], msg: "필수" }, { path: "/x", message: "틀림" }] } });
    expect(fieldProblems(e422)).toEqual([{ path: "/answers", message: "필수" }, { path: "/x", message: "틀림" }]);
    const e409 = new ApiError(409, { code: "interaction_closed", message: "닫힘", details: { interaction: { id: "i1", status: "answered" } } });
    expect(closedInteraction(e409)?.id).toBe("i1");
    expect(closedInteraction(new ApiError(409, { code: "x", message: "m" }))).toBeUndefined();
  });
});

describe("mergeLiveRuns·hasReachedEnd (B-3)", () => {
  const ev = (seq: number, type: string, payload: Record<string, unknown> = {}) =>
    ({ event_id: `e${seq}`, run_id: "r", seq, ts: seq, type, node_path: [], payload }) as never;
  it("더 많이 반영한 쪽을 쓰고 종료 이벤트로 끝을 안다", () => {
    const partial = foldRunEvents("r", [ev(1, "run.started")]);
    const full = foldRunEvents("r", [ev(1, "run.started"), ev(2, "run.completed", { status: "completed" })]);
    expect(hasReachedEnd(partial)).toBe(false);
    expect(hasReachedEnd(full)).toBe(true);
    expect(mergeLiveRuns({ r: full }, { r: partial }).r).toBe(full);
    expect(mergeLiveRuns({ r: partial }, { r: full }).r).toBe(full);
  });
});
