/**
 * 채팅 화면 테스트 전용 하네스(앱 코드에서 import하지 않는다). 종류·이름은 임의 값이다.
 */
import { vi } from "vitest";
import type { Agent, ChatTurn, ConversationSummary, EdgeTypeDescriptor, Graph, GraphSummary, Interaction, InteractionKindDescriptor, NodeTypeDescriptor, RunEvent, TeamPlanSummary } from "@agent-console/contracts";
import { createFakeClients } from "../../../testing/fakes";

export const nodeTypes: NodeTypeDescriptor[] = [
  { id: "nt-a", title: "노드 에이", binds: { kind: "kind-lib", field: "ref" } },
  { id: "nt-u", title: "노드 유저" },
];
export const agents = [
  { kind: "kind-lib", id: "ag-1", name: "하나", role: "역할 일" },
  { kind: "kind-lib", id: "ag-2", name: "둘" },
] as unknown as Agent[];
export const edgeTypes: EdgeTypeDescriptor[] = [
  { id: "e-entry", title: "입구", scheduling: "entry" },
  { id: "e-exit", title: "출구", scheduling: "exit" },
  { id: "e-flow", title: "넘기기 방식", scheduling: "flow" },
];
export const graph: Graph = {
  id: "g1",
  name: "팀 하나",
  nodes: [
    { id: "n1", type: "nt-a", config: { ref: "ag-1" } },
    { id: "n2", type: "nt-a", config: { ref: "ag-2" } },
    { id: "u", type: "nt-u", label: "사용자" },
  ],
  edges: [
    { id: "ed1", source: { node: "u", port: "out" }, target: { node: "n1", port: "in" }, kind: "e-entry" },
    { id: "ed2", source: { node: "n1", port: "out" }, target: { node: "u", port: "in" }, kind: "e-exit" },
    { id: "ed3", source: { node: "n1", port: "out" }, target: { node: "n2", port: "in" }, kind: "e-flow" },
  ],
};
/** 서버가 계산하는 계획 요약. 연결 config에는 아무 값도 없고 화면은 이 값만 읽는다. */
export const graphPlan: TeamPlanSummary = {
  entries: [{ edge_id: "ed1", node_id: "n1" }],
  answers: [{ edge_id: "ed2", node_id: "n1", agent_id: "ag-1", final: true, stream: true }],
  grants: { n1: { kinds: ["kind-z"] } },
};
export const graphSummaries: GraphSummary[] = [
  { id: "g1", name: "팀 하나", description: "첫 팀", version_hash: "h1", node_count: 3, edge_count: 3, entry_labels: ["하나"] },
  { id: "g2", name: "입구 없는 팀", version_hash: "h2", node_count: 1, edge_count: 0, entry_labels: [] },
  { id: "g3", name: "팀 셋", version_hash: "h3", node_count: 2, edge_count: 1, entry_labels: ["둘"] },
];
export const kinds: InteractionKindDescriptor[] = [
  { id: "kind-z", title: "임의 질문", free_text_path: "/response", ui_hints: { renderer: "renderer-x" }, response_schema: { type: "object", properties: { response: { type: "string", title: "답변칸" } } } },
  { id: "kind-w", title: "다른 요청", ui_hints: { renderer: "renderer-y" }, response_schema: { type: "object", properties: { pick: { type: "string", title: "고르기" } } } },
];

export function pending(over: Partial<Interaction> = {}): Interaction {
  return { id: "i1", run_id: "r1", conversation_id: "c1", node_id: "n1", node_path: ["n1"], actor: "ag-1", kind: "kind-z", status: "pending", title: "어느 쪽으로 할까요?", created_at: 1000, payload: {}, ...over };
}

export function turn(over: Partial<ChatTurn> = {}): ChatTurn {
  return { run_id: "r1", user_text: "로그인 화면 써줘", status: "waiting", replies: [], interactions: [pending()], started_at: 1000, ...over };
}

export function conversation(over: Partial<ConversationSummary> & { id: string }): ConversationSummary {
  return { graph_id: "g1", title: over.id, created_at: 1, updated_at: 1, ...over };
}

export interface Harness {
  clients: ReturnType<typeof createFakeClients>["clients"];
  rest: ReturnType<typeof createFakeClients>["rest"];
  ws: ReturnType<typeof createFakeClients>["ws"];
  /** `run:<id>` 구독자에게 이벤트를 보낸다 */
  emitRunEvent(runId: string, event: Partial<RunEvent> & { type: string; seq: number }): void;
  emitConversation(summary: ConversationSummary): void;
  subscribedRuns(): string[];
}

/** 대화 `c1`(응답 대기 1건)이 열려 있는 기본 서버 상태. `overrides`로 REST 응답을 바꾼다. */
export function createHarness(overrides: Record<string, unknown> = {}): Harness {
  const conversations = [
    conversation({ id: "c1", title: "로그인 화면 스펙", updated_at: 100, pending_interactions: 1, last_status: "waiting" }),
    conversation({ id: "c2", title: "버그 원인 분석", updated_at: 900, last_status: "completed" }),
  ];
  const base = {
    listConversations: vi.fn(async () => conversations),
    getConversation: vi.fn(async (id: string) => ({ ...(conversations.find((c) => c.id === id) ?? conversations[0]!), sessions: {} })),
    listGraphs: vi.fn(async () => graphSummaries),
    getGraph: vi.fn(async (id: string) => ({ graph: { ...graph, id }, version_hash: "h" })),
    getGraphPlan: vi.fn(async () => graphPlan),
    listAgents: vi.fn(async () => agents),
    listNodeTypes: vi.fn(async () => nodeTypes),
    listEdgeTypes: vi.fn(async () => edgeTypes),
    listInteractionKinds: vi.fn(async () => kinds),
    listTurns: vi.fn(async () => [turn()]),
    listQueue: vi.fn(async () => []),
    listRunEvents: vi.fn(async () => []),
    listResources: vi.fn(async () => []),
    respondInteraction: vi.fn(async (_run: string, id: string) => pending({ id, status: "answered", closed_at: 1005 })),
    postMessage: vi.fn(async () => ({ run: { id: "r2", status: "running" } })),
    cancelRun: vi.fn(async () => ({})),
    createConversation: vi.fn(async (req: { graph_id: string }) => conversation({ id: "c9", graph_id: req.graph_id })),
    updateConversation: vi.fn(async (id: string) => conversation({ id })),
  };
  const { clients, rest, ws } = createFakeClients({ ...base, ...overrides });
  const runHandlers = new Map<string, Set<(e: RunEvent) => void>>();
  const convHandlers = new Set<(s: ConversationSummary) => void>();
  Object.assign(ws, {
    subscribeRun: vi.fn((runId: string, handler: (e: RunEvent) => void) => {
      const set = runHandlers.get(runId) ?? new Set();
      set.add(handler);
      runHandlers.set(runId, set);
      return { topic: `run:${runId}`, unsubscribe: () => set.delete(handler) };
    }),
    subscribeConversation: vi.fn((_id: string, handler: (s: ConversationSummary) => void) => {
      convHandlers.add(handler);
      return { topic: "conversation", unsubscribe: () => convHandlers.delete(handler) };
    }),
  });
  return {
    clients,
    rest,
    ws,
    emitRunEvent: (runId, event) => {
      const full = { event_id: `e${event.seq}`, run_id: runId, ts: event.seq, node_path: [], payload: {}, ...event } as RunEvent;
      runHandlers.get(runId)?.forEach((h) => h(full));
    },
    emitConversation: (summary) => convHandlers.forEach((h) => h(summary)),
    subscribedRuns: () => [...runHandlers.entries()].filter(([, set]) => set.size > 0).map(([id]) => id),
  };
}
