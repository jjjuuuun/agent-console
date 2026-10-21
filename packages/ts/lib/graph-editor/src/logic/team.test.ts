import { describe, expect, it } from "vitest";
import type { Graph } from "@agent-console/contracts";
import { teamEdgeTypes as E, teamGraph, teamNodeTypes as N } from "../testing";
import { buildTeamPalette } from "../components/TeamPalette";
import { addNode, checkConnection } from "./ops";
import { buildFlowModel } from "./convert";
import { declaredLabels, evaluateWhen } from "./declared";
import {
  applyGraphPatch,
  applyRoleToggle,
  candidateEdgeKinds,
  canHaveResources,
  deriveNodeBadges,
  deriveResourceChips,
  edgeKindBadge,
  formatElapsed,
  getRoleToggleInfo,
  isChipShape,
} from "./team";
import { defaultMessages } from "../messages";

const ctx = {
  nodeTypes: N,
  edgeTypes: E,
  portsOf: (id: string) => (id === "h1" ? { inputs: [{ name: "hears" }, { name: "asks" }], outputs: [{ name: "says" }] } : undefined),
};

describe("candidateEdgeKinds: connects × role만 비교", () => {
  it("역할이 맞는 종류만 돌려준다", () => {
    expect(candidateEdgeKinds("beta-human", "alpha-actor", E, N).map((k) => k.id)).toEqual(["e-start", "e-pass"]);
    expect(candidateEdgeKinds("alpha-actor", "beta-human", E, N).map((k) => k.id)).toEqual(["e-end", "e-ask", "e-pass"]);
    expect(candidateEdgeKinds("gamma-note", "alpha-actor", E, N).map((k) => k.id)).toEqual(["e-attach"]);
    expect(candidateEdgeKinds("gamma-note", "beta-human", E, N)).toEqual([]);
  });
  it("모르는 노드 타입은 connects 제한이 없는 종류만", () => {
    const free = [...E, { id: "e-free", title: "자유" }];
    expect(candidateEdgeKinds("zzz", "yyy", free, N).map((k) => k.id)).toEqual(["e-free"]);
  });
  it("보조 배지는 속성에서 계산", () => {
    expect(E.map(edgeKindBadge)).toEqual(["entry", "exit", "ask", "flow", "none"]);
    expect(edgeKindBadge({ id: "x", title: "x", scheduling: "none", invocation: { strategy: "s" } })).toBe("delegate");
  });
});

describe("deriveNodeBadges / 칩 카드 판정", () => {
  it("entry 도착=입구, exit 출발=답변, interaction 출발=묻기", () => {
    const g: Graph = {
      ...teamGraph(),
      edges: [
        { id: "1", kind: "e-start", source: { node: "h1", port: "says" }, target: { node: "a1", port: "in" } },
        { id: "2", kind: "e-end", source: { node: "a1", port: "out" }, target: { node: "h1", port: "hears" } },
        { id: "3", kind: "e-ask", source: { node: "a2", port: "out" }, target: { node: "h1", port: "asks" } },
      ],
    };
    expect(deriveNodeBadges("a1", g, E)).toEqual(["entry", "exit"]);
    expect(deriveNodeBadges("a2", g, E)).toEqual(["interaction"]);
    expect(deriveNodeBadges("h1", g, E)).toEqual([]);
  });
  it("executable=false 또는 shape=chip이면 칩, shape=card가 이긴다", () => {
    expect(isChipShape(N[2])).toBe(true);
    expect(isChipShape(N[0])).toBe(false);
    expect(isChipShape({ ...N[2]!, ui_hints: { shape: "card" } })).toBe(false);
    expect(isChipShape({ ...N[0]!, ui_hints: { shape: "chip" } })).toBe(true);
  });
});

describe("입구/답변/묻기 토글 (스케줄링·interaction 속성으로 종류를 찾음)", () => {
  it("entry: 사용자 노드는 connects.source 역할로 찾고 default_ports로 엣지를 만든다", () => {
    const g = teamGraph();
    const info = getRoleToggleInfo("a1", "entry", g, ctx);
    expect(info).toMatchObject({ available: true, on: false, count: 0 });
    expect(info.kinds.map((k) => k.id)).toEqual(["e-start"]);
    expect(info.userNodes).toEqual([{ id: "h1", label: "사용자" }]);
    const res = applyRoleToggle(g, "a1", "entry", true, ctx);
    expect(res.changed).toBe(true);
    const e = res.graph.edges!.find((x) => x.id === res.addedEdgeIds[0])!;
    expect(e).toMatchObject({ kind: "e-start", source: { node: "h1", port: "says" }, target: { node: "a1", port: "in" } });
    expect(g.edges).toHaveLength(1); // 입력 그래프 불변
    expect(getRoleToggleInfo("a1", "entry", res.graph, ctx)).toMatchObject({ on: true, count: 1 });
    // 이미 있으면 다시 만들지 않는다
    expect(applyRoleToggle(res.graph, "a1", "entry", true, ctx)).toMatchObject({ changed: false, reason: "exists" });
    // 끄면 지운다
    const off = applyRoleToggle(res.graph, "a1", "entry", false, ctx);
    expect(off.graph.edges!.map((x) => x.id)).toEqual(["x1"]);
  });
  it("exit: 노드가 출발, 엣지 config는 채우지 않는다(생략 = 기본)", () => {
    const res = applyRoleToggle(teamGraph(), "a2", "exit", true, ctx);
    expect(res.graph.edges!.at(-1)).toMatchObject({ kind: "e-end", source: { node: "a2", port: "out" }, target: { node: "h1", port: "hears" } });
    expect(res.graph.edges!.at(-1)).not.toHaveProperty("config");
  });
  it("interaction 토글은 interaction 속성이 있는 종류를 쓴다", () => {
    const res = applyRoleToggle(teamGraph(), "a1", "interaction", true, ctx);
    expect(res.graph.edges!.at(-1)).toMatchObject({ kind: "e-ask", target: { port: "asks" } });
    expect(getRoleToggleInfo("a1", "interaction", res.graph, ctx).on).toBe(true);
  });
  it("default_ports가 없으면 노드 타입 포트 순서의 첫 포트를 쓴다", () => {
    const noDefaults = E.map((k) => ({ ...k, default_ports: null }));
    const res = applyRoleToggle(teamGraph(), "a1", "entry", true, { ...ctx, edgeTypes: noDefaults });
    expect(res.graph.edges!.at(-1)).toMatchObject({ source: { port: "says" }, target: { port: "in" } });
    // 포트를 알 수 없으면 만들지 않는다
    const none = applyRoleToggle(teamGraph(), "a1", "entry", true, { ...ctx, edgeTypes: noDefaults, portsOf: () => undefined });
    expect(none).toMatchObject({ changed: false, reason: "no-port" });
  });
  it("사용할 수 없는 이유를 돌려준다", () => {
    const noHuman = { ...teamGraph(), nodes: teamGraph().nodes!.filter((n) => n.id !== "h1") };
    expect(getRoleToggleInfo("a1", "entry", noHuman, ctx)).toMatchObject({ available: false, reasonIfUnavailable: "no-counterpart" });
    expect(getRoleToggleInfo("m1", "entry", teamGraph(), ctx)).toMatchObject({ available: false, reasonIfUnavailable: "no-kind" });
    expect(getRoleToggleInfo("a1", "entry", teamGraph(), { ...ctx, edgeTypes: [] })).toMatchObject({ available: false, reasonIfUnavailable: "no-kind" });
  });
  it("종류·상대 노드를 지정할 수 있다", () => {
    const g: Graph = { ...teamGraph(), nodes: [...teamGraph().nodes!, { id: "h2", type: "beta-human", label: "둘째", config: {} }] };
    const res = applyRoleToggle(g, "a1", "entry", true, ctx, { userNodeId: "h2" });
    expect(res.graph.edges!.at(-1)).toMatchObject({ source: { node: "h2" } });
    expect(applyRoleToggle(g, "a1", "entry", true, ctx, { userNodeId: "nope" })).toMatchObject({ changed: false });
  });
});

describe("연결 검사: 순환은 디스크립터 scheduling으로", () => {
  const g: Graph = {
    ...teamGraph(),
    edges: [{ id: "f1", kind: "e-pass", source: { node: "a1", port: "out" }, target: { node: "a2", port: "in" } }],
  };
  const c = { source: { node: "a2", port: "out" }, target: { node: "a1", port: "in" } };
  it("flow 종류로 되돌리면 순환 거부", () => {
    expect(checkConnection(g, c, undefined, { edgeTypes: E, kind: "e-pass" })).toEqual({ ok: false, reason: "cycle" });
  });
  it("flow가 아닌 종류는 순환 검사에서 빠진다", () => {
    expect(checkConnection(g, c, undefined, { edgeTypes: E, kind: "e-attach" })).toEqual({ ok: true });
  });
  it("none/exit 엣지는 기존 경로로 치지 않는다", () => {
    const g2: Graph = { ...g, edges: [{ id: "n", kind: "e-ask", source: { node: "a1", port: "out" }, target: { node: "a2", port: "in" } }] };
    expect(checkConnection(g2, c, undefined, { edgeTypes: E, kind: "e-pass" })).toEqual({ ok: true });
  });
  it("중복은 같은 종류끼리만", () => {
    const same = { source: { node: "a1", port: "out" }, target: { node: "a2", port: "in" } };
    expect(checkConnection(g, same, undefined, { edgeTypes: E, kind: "e-pass" })).toMatchObject({ ok: false, reason: "duplicate" });
    expect(checkConnection(g, same, undefined, { edgeTypes: E, kind: "e-ask" })).toEqual({ ok: true });
  });
});

describe("applyGraphPatch (서버 제안 적용)", () => {
  it("노드·엣지 추가, 엣지 삭제. 이미 있는 id와 끝점 없는 엣지는 건너뛴다", () => {
    const g = teamGraph();
    const res = applyGraphPatch(g, {
      add_nodes: [{ id: "h9", type: "beta-human", label: "새 사용자" }, { id: "a1", type: "x" }],
      add_edges: [
        { id: "n1", kind: "e-start", source: { node: "h9", port: "says" }, target: { node: "a1", port: "in" } },
        { id: "n2", kind: "e-start", source: { node: "ghost", port: "says" }, target: { node: "a1", port: "in" } },
      ],
      remove_edge_ids: ["x1"],
    });
    expect(res.addedNodeIds).toEqual(["h9"]);
    expect(res.addedEdgeIds).toEqual(["n1"]);
    expect(res.removedEdgeIds).toEqual(["x1"]);
    expect(res.graph.edges!.map((e) => e.id)).toEqual(["n1"]);
    expect(g.edges).toHaveLength(1);
    expect(applyGraphPatch(g, undefined).graph.nodes).toHaveLength(4);
  });
});

describe("팔레트 구역 (binds × 정의 목록, hidden 제외)", () => {
  const lists = {
    things: [
      { id: "t1", name: "가나다 에이전트", description: "설명", usageCount: 2 },
      { id: "t2", name: "라마바", groupLabel: "에이전트" },
    ],
  };
  it("binds 있는 타입 × 목록 + binds 없는 타입(기본 노드), 숨김 제외", () => {
    const r = buildTeamPalette(N, lists, {}, "", "기타");
    expect(r.sections.map((s) => [s.kind, s.title, s.empty])).toEqual([
      ["things", "에이전트", false], // 구역은 표시 이름 순(한국어 로케일)
      ["docs", "docs", true], // 정의 0개 → 빈 안내 구역
    ]);
    expect(r.sections[0]!.subgroups[0]!.items.map((i) => i.id)).toEqual(["t1", "t2"]);
    expect(r.base.flatMap((g) => g.items.map((t) => t.id))).toEqual(["beta-human"]);
    expect(JSON.stringify(r)).not.toContain("delta-secret");
  });
  it("검색은 정의 이름·설명에도 걸린다", () => {
    const r = buildTeamPalette(N, lists, { docs: "문서" }, "라마", "기타");
    expect(r.sections.find((s) => s.kind === "things")!.subgroups[0]!.items.map((i) => i.id)).toEqual(["t2"]);
    expect(r.base).toEqual([]);
  });
  it("addNode: 정의 노드는 label=정의 이름, config[binds.field]=정의 id", () => {
    const { graph } = addNode(teamGraph(), { descriptor: N[0]!, definition: { id: "t9", name: "새 정의" } });
    expect(graph.nodes!.at(-1)).toMatchObject({ type: "alpha-actor", label: "새 정의", config: { thing_ref: "t9" } });
  });
});

describe("리소스 보기", () => {
  it("canHaveResources: connects + executable", () => {
    const g = teamGraph();
    expect(canHaveResources(g.nodes![1]!, N, E)).toBe(true); // doer
    expect(canHaveResources(g.nodes![0]!, N, E)).toBe(false); // human
    expect(canHaveResources(g.nodes![3]!, N, E)).toBe(false); // 실행되지 않는 노드
  });
  it("deriveResourceChips: 숨겨진 노드에서 나가는 연결의 도착 노드별로 타입 단위 집계", () => {
    const chips = deriveResourceChips(teamGraph(), N, (d) => d?.ui_hints?.icon ?? "?");
    expect(chips.get("a1")).toEqual([{ key: "gamma-note", iconText: "M", title: "메모", count: 1, names: ["지침"] }]);
    expect(chips.has("a2")).toBe(false);
  });
});

describe("경과 표시", () => {
  it("초·분·시간 템플릿은 messages", () => {
    expect(formatElapsed(12_900, defaultMessages)).toBe("12초");
    expect(formatElapsed(65_000, defaultMessages)).toBe("1분 5초");
    expect(formatElapsed(7_380_000, defaultMessages)).toBe("2시간 3분");
    expect(formatElapsed(-5, defaultMessages)).toBe("0초");
  });
});

describe("buildFlowModel: 엣지 칩·배지·리소스 보기", () => {
  const base = (graph: Graph, over: Partial<Parameters<typeof buildFlowModel>[0]> = {}) =>
    buildFlowModel({
      graph,
      nodeTypes: N,
      edgeTypes: E,
      resolved: new Map(),
      nodeStates: {},
      edgeStates: {},
      selectedNodes: new Set(),
      selectedEdges: new Set(),
      positionOverrides: new Map(),
      readOnly: false,
      messages: defaultMessages,
      markerId: "m",
      ...over,
    });
  const g: Graph = {
    ...teamGraph(),
    edges: [
      { id: "u", kind: "mystery", source: { node: "a1", port: "out" }, target: { node: "a2", port: "in" } },
      { id: "p", kind: "e-pass", source: { node: "a2", port: "out" }, target: { node: "h1", port: "x" }, label: "라벨", config: {} },
      { id: "r", kind: "e-attach", source: { node: "m1", port: "o" }, target: { node: "a1", port: "in" } },
    ],
  };
  it("모르는 종류는 '알 수 없는 연결 종류', 종류 title · 라벨, 순번·횟수", () => {
    const m = base(g, { edgeOrder: { p: 2 }, edgeCounts: { p: 3 } });
    const byId = new Map(m.edges.map((e) => [e.id, e.data!]));
    expect(byId.get("u")!.label).toBe("알 수 없는 연결 종류: mystery");
    expect(byId.get("p")).toMatchObject({ label: "넘김선 · 라벨", orderBadge: 2, orderText: "2번째로 지나감", countBadge: 3, countText: "3회" });
  });
  it("리소스 보기를 끄면 executable=false 노드와 그 연결이 빠지고 칩이 붙는다. 켜면 칩 카드", () => {
    const off = base(g, { showResources: false });
    expect(off.nodes.map((n) => n.id)).toEqual(["h1", "a1", "a2"]);
    expect(off.edges.map((e) => e.id)).toEqual(["u", "p"]);
    expect(off.nodes.find((n) => n.id === "a1")!.data.resourceChips).toHaveLength(1);
    const on = base(g);
    expect(on.nodes.map((n) => n.id)).toContain("m1");
    expect(on.nodes.find((n) => n.id === "m1")!.data.compact).toBe(true);
    expect(on.nodes.find((n) => n.id === "a1")!.data.resourceChips).toBeUndefined();
  });
  it("waiting 노드 경과 문구와 앱 배지", () => {
    const m = base(g, { waitingNodes: { h1: { since: "2026-01-01T00:00:00Z" } }, nowMs: Date.parse("2026-01-01T00:00:12Z"), nodeBadgesOverride: { a1: ["×3"] } });
    expect(m.nodes.find((n) => n.id === "h1")!.data.waitingText).toBe("응답 대기 12초");
    expect(m.nodes.find((n) => n.id === "a1")!.data.badges).toEqual(["×3"]);
  });
});

describe("선언형 배지·칩 (ui_hints.badges/chips)", () => {
  const msgs = { hintLabels: { k1: "문구1" } };
  it("config_path 존재·값 비교·in·AND/OR, label_key → label 폴백", () => {
    const hints = {
      badges: [
        { label_key: "k1", when: { config_path: "a.b" } },
        { label: "같음", when: { config_path: "mode", equals: "x" } },
        { label: "다름", when: { config_path: "mode", not_equals: "x" } },
        { label: "없음", when: { config_path: "a.zz", exists: false } },
        { label: "안에", when: { config_path: "mode", in: ["x", "y"] } },
        { label: "또는", when: [{ config_path: "nope" }, { config_path: "mode", equals: "x" }] },
        { label: "항상" },
        { label_key: "unmapped" },
        { label: "모르는키", when: { config_path: "mode", wat: 1 } },
        { label: "경로없는값검사", when: { equals: 1 } },
        "garbage",
      ],
    };
    expect(declaredLabels(hints, "badges", { config: { a: { b: 0 }, mode: "x" } }, msgs)).toEqual(["문구1", "같음", "없음", "안에", "또는", "항상", "unmapped"]);
    expect(declaredLabels(hints, "chips", {}, msgs)).toEqual([]);
    expect(declaredLabels(undefined, "badges", {}, msgs)).toEqual([]);
  });
  it("연결 속성 조건: incoming/outgoing scheduling", () => {
    expect(evaluateWhen({ incoming_scheduling: "flow" }, { incomingScheduling: ["flow", "entry"] })).toBe(true);
    expect(evaluateWhen({ incoming_scheduling: "flow" }, { incomingScheduling: ["entry"] })).toBe(false);
    expect(evaluateWhen({ config_path: "r", incoming_scheduling: "flow" }, { config: { r: {} }, incomingScheduling: ["flow"] })).toBe(true);
    expect(evaluateWhen({ outgoing_scheduling: "exit" }, { outgoingScheduling: ["exit"] })).toBe(true);
  });
  it("buildFlowModel: 노드 배지·칩과 엣지 칩에 반영", () => {
    const nodeTypes = [
      ...N,
      {
        id: "zz-gate", title: "문지기", role: "human",
        ui_hints: {
          badges: [{ label_key: "bd", when: { config_path: "cfgx", incoming_scheduling: "flow" } }],
          chips: [{ label: "칩", when: { config_path: "cfgx", equals: 2 } }],
        },
      },
    ];
    const edgeTypes = [...E, { id: "zz-edge", title: "임의선", scheduling: "none" as const, ui_hints: { chips: [{ label_key: "mid", when: { config_path: "flag", equals: false } }] } }];
    const g: Graph = {
      id: "g", name: "g",
      nodes: [
        { id: "z1", type: "zz-gate", config: { cfgx: 2 } },
        { id: "z2", type: "zz-gate", config: { cfgx: 2 } },
        { id: "a1", type: "alpha-actor", config: {} },
      ],
      edges: [
        { id: "q", kind: "zz-edge", source: { node: "a1", port: "out" }, target: { node: "z1", port: "in" }, config: { flag: false } },
        { id: "w", kind: "e-pass", source: { node: "a1", port: "out" }, target: { node: "z2", port: "in" } },
      ],
    };
    const m = buildFlowModel({
      graph: g, nodeTypes, edgeTypes, resolved: new Map(), nodeStates: {}, edgeStates: {}, selectedNodes: new Set(), selectedEdges: new Set(),
      positionOverrides: new Map(), readOnly: false, markerId: "m",
      messages: { ...defaultMessages, hintLabels: { bd: "배지문구", mid: "중간" } },
    });
    const z1 = m.nodes.find((n) => n.id === "z1")!.data;
    const z2 = m.nodes.find((n) => n.id === "z2")!.data;
    expect(z1.badges).toBeUndefined(); // 들어오는 연결이 flow가 아니므로
    expect(z2.badges).toEqual(["배지문구"]);
    expect(z2.hintChips).toEqual(["칩"]);
    expect(m.edges.find((e) => e.id === "q")!.data!.hintChips).toEqual(["중간"]);
    expect(m.edges.find((e) => e.id === "w")!.data!.hintChips).toBeUndefined();
  });
});

describe("토글 후보가 여럿이면 대신 고르지 않는다", () => {
  const g: Graph = { ...teamGraph(), nodes: [...teamGraph().nodes!, { id: "h2", type: "beta-human", label: "둘째", config: {} }] };
  it("ambiguous → 지정하면 적용", () => {
    expect(applyRoleToggle(g, "a1", "entry", true, ctx)).toMatchObject({ changed: false, reason: "ambiguous" });
    expect(applyRoleToggle(g, "a1", "entry", true, ctx, { userNodeId: "h2" }).changed).toBe(true);
  });
});

describe("백엔드 선언(1R.29)과 해석 일치", () => {
  const badge = { label_key: "review", label: "검토", when: { config_path: "review", incoming_scheduling: "flow" } };
  const chip = { label_key: "intermediate", label: "중간 결과", when: { config_path: "final", equals: false } };
  const m = { hintLabels: {} };
  it("user 배지: review 설정 + flow 입력일 때만", () => {
    const h = { badges: [badge] };
    expect(declaredLabels(h, "badges", { config: { review: { message: "x" } }, incomingScheduling: ["flow"] }, m)).toEqual(["검토"]);
    expect(declaredLabels(h, "badges", { config: { review: { message: "x" } }, incomingScheduling: ["entry"] }, m)).toEqual([]);
    expect(declaredLabels(h, "badges", { config: {}, incomingScheduling: ["flow"] }, m)).toEqual([]);
    expect(declaredLabels(h, "badges", { config: { review: null }, incomingScheduling: ["flow"] }, m)).toEqual([]);
  });
  it("reply 칩: final === false 일 때만(없음·true는 숨김)", () => {
    const h = { chips: [chip] };
    expect(declaredLabels(h, "chips", { config: { final: false } }, m)).toEqual(["중간 결과"]);
    expect(declaredLabels(h, "chips", { config: { final: true } }, m)).toEqual([]);
    expect(declaredLabels(h, "chips", { config: {} }, m)).toEqual([]);
  });
});
