/// <reference types="node" />
import { readFileSync } from "node:fs";
import { describe, expect, it, vi } from "vitest";
import type { Graph } from "@agent-console/contracts";
import { descriptors, edgeTypes, sampleGraph } from "../testing";
import { categoryColorSlot, fnv1a32 } from "./color";
import { buildFlowModel, pickDescriptor } from "./convert";
import { firstGlyph, resolveHints, safeCssColor, safeIconText } from "./hints";
import {
  addEdge,
  addNode,
  centerFreePosition,
  checkConnection,
  decideEdgeKind,
  defaultsFromSchema,
  duplicateNodes,
  moveNodes,
  nextFreePosition,
  removeSelection,
  uniqueLabel,
} from "./ops";
import { summarizeIssues } from "./issues";
import { PortResolver, stableStringify } from "./portResolver";
import { buildNodePorts, parseHandleId } from "./ports";
import { measureNodeSize, textWidth } from "./size";
import { defaultMessages } from "../messages";
import { groupNodeTypes } from "../components/NodePalette";

describe("분류색 해시 (tokens 1.5)", () => {
  it("FNV-1a 32 표준 값", () => {
    expect(fnv1a32("")).toBe(0x811c9dc5);
    expect(fnv1a32("a")).toBe(0xe40c292c);
    expect(fnv1a32("foobar")).toBe(0xbf9cf968);
  });
  it("같은 문자열은 같은 슬롯, 빈 값은 neutral, NFC 정규화", () => {
    expect(categoryColorSlot("분기")).toBe(categoryColorSlot("분기"));
    expect(categoryColorSlot("")).toBe("neutral");
    expect(categoryColorSlot(undefined)).toBe("neutral");
    expect(categoryColorSlot("한")).toBe(categoryColorSlot("한")); // 자모 분리형 = 조합형
    expect([1, 2, 3, 4, 5, 6, 7, 8]).toContain(categoryColorSlot("anything"));
  });
});

describe("ui_hints 해석", () => {
  it("안전한 색만 통과", () => {
    expect(safeCssColor("#3b82f6")).toBe("#3b82f6");
    expect(safeCssColor("rgb(1, 2, 3)")).toBe("rgb(1, 2, 3)");
    expect(safeCssColor("var(--ac-accent)")).toBe("var(--ac-accent)");
    expect(safeCssColor("red")).toBe("red");
    expect(safeCssColor("url(javascript:alert(1))")).toBeUndefined();
    expect(safeCssColor("red; background: url(x)")).toBeUndefined();
    expect(safeCssColor(12)).toBeUndefined();
  });
  it("아이콘은 1~2자, 아니면 제목 첫 글자", () => {
    expect(safeIconText("🙂")).toBe("🙂");
    expect(safeIconText("AB")).toBe("AB");
    expect(safeIconText("ABC")).toBeUndefined();
    expect(firstGlyph("agent")).toBe("A");
    expect(firstGlyph("한글")).toBe("한");
    expect(firstGlyph("  ")).toBe("?");
    expect(resolveHints(null, "라우터")).toEqual({ iconText: "라", color: undefined, dashed: false });
    expect(resolveHints({ icon: "toolong", color: "nope(", dashed: true }, "x")).toEqual({ iconText: "X", color: undefined, dashed: true });
  });
});

describe("노드 크기 (tokens 4절)", () => {
  it("한글은 1em, 영문 소문자 0.56em", () => {
    expect(textWidth("가나", 13)).toBe(26);
    expect(textWidth("ab", 10)).toBeCloseTo(11.2);
  });
  it("폭은 160~320, 8의 배수, 포트 수에 따라 높이가 커진다", () => {
    const small = measureNodeSize({ label: "a", typeTitle: "b", inputLabels: [], outputLabels: [] });
    expect(small.width).toBe(160);
    expect(small.height).toBe(72);
    const big = measureNodeSize({ label: "가".repeat(60), typeTitle: "t".repeat(100), inputLabels: ["i"], outputLabels: Array(6).fill("출력") });
    expect(big.width).toBe(320);
    expect(big.width % 8).toBe(0);
    expect(big.labelLines).toBe(2);
    expect(big.height).toBeGreaterThan(small.height);
  });
});

describe("포트 해석", () => {
  it("권위 있는 목록 + 엣지가 참조하는 없는 포트는 missing", () => {
    const g = sampleGraph();
    const sink = buildNodePorts("n3", { inputs: [{ name: "in" }], outputs: [] }, g.edges!);
    expect(sink.inputs.map((p) => [p.id, p.missing])).toEqual([["in", undefined], ["extra", true]]);
  });
  it("권위 없는 경우(알 수 없는 타입)는 엣지에서 복원하고 missing 표시하지 않는다", () => {
    const g = sampleGraph();
    const ghost = buildNodePorts("n4", undefined, g.edges!);
    expect(ghost.outputs).toEqual([{ id: "ghost-out", label: "ghost-out" }]);
  });
  it("핸들 id 파싱", () => {
    expect(parseHandleId("in:a:b")).toEqual({ side: "in", port: "a:b" });
    expect(parseHandleId("out:x")).toEqual({ side: "out", port: "x" });
    expect(parseHandleId("zzz")).toBeUndefined();
    expect(parseHandleId(null)).toBeUndefined();
  });
});

describe("편집 연산 (순수, 모르는 필드 보존)", () => {
  const g = sampleGraph();
  it("addNode: label 중복 접미, 스키마 기본값은 채우지 않음, 새 id", () => {
    const d = descriptors[0]!;
    const r1 = addNode(g, { descriptor: d, position: { x: 8, y: 8 } });
    expect(r1.nodeId).toBe("n5");
    expect(r1.graph.nodes!.at(-1)).toMatchObject({ label: "원천 노드", position: { x: 8, y: 8 } });
    expect(r1.graph.nodes!.at(-1)).not.toHaveProperty("config");
    const r2 = addNode(r1.graph, { descriptor: d });
    expect(r2.graph.nodes!.at(-1)!.label).toBe("원천 노드 2");
    expect(r2.graph["custom_field"]).toEqual({ keep: "me" });
    expect(g.nodes).toHaveLength(4); // 원본 불변
  });
  it("addNode: idFactory 주입", () => {
    const r = addNode(g, { descriptor: descriptors[0]!, idFactory: (p, ex) => `${p}-${ex.size}` });
    expect(r.nodeId).toBe("n-4");
  });
  it("uniqueLabel / defaultsFromSchema / nextFreePosition", () => {
    expect(uniqueLabel("a", ["a", "a 2"])).toBe("a 3");
    expect(defaultsFromSchema({ properties: { a: { default: 1 }, o: { type: "object", properties: { b: { default: "x" } } }, z: {} } })).toEqual({ a: 1, o: { b: "x" } });
    expect(defaultsFromSchema(null)).toEqual({});
    expect(nextFreePosition({ id: "g", name: "g" })).toEqual({ x: 0, y: 0 });
    const free = nextFreePosition(g);
    const rightmost = Math.max(...g.nodes!.map((n) => n.position?.x ?? 0));
    expect(free.x).toBe(Math.round((rightmost + 300) / 8) * 8); // 왼쪽 -> 오른쪽
    // 기준 노드의 오른쪽, 겹치면 아래로
    const two = { id: "g", name: "g", nodes: [{ id: "a", type: "t", position: { x: 0, y: 0 } }, { id: "b", type: "t", position: { x: 300, y: 0 } }] };
    expect(nextFreePosition(two, 8, "a")).toEqual({ x: 304, y: 120 });
    expect(nextFreePosition(two, 8, "b")).toEqual({ x: 600, y: 0 });
  });
  it("centerFreePosition: 비어 있으면 격자에 맞춘 중앙, 겹치면 격자(8px)씩 대각선으로 민다", () => {
    const empty = { id: "g", name: "g" };
    expect(centerFreePosition(empty, { x: 203, y: 101 })).toEqual({ x: 200, y: 104 });
    const taken = { id: "g", name: "g", nodes: [{ id: "a", type: "t", position: { x: 200, y: 104 } }] };
    const moved = centerFreePosition(taken, { x: 203, y: 101 });
    expect(moved.x % 8).toBe(0);
    expect(moved.x).toBeGreaterThan(200);
    expect(moved.y).toBe(moved.x - 200 + 104);
    // 밀린 자리는 기존 노드와 겹치지 않는다
    expect(Math.abs(moved.x - 200) >= 260 || Math.abs(moved.y - 104) >= 170).toBe(true);
  });
  it("removeSelection: 노드 삭제 시 붙은 엣지도 삭제, 엣지만 삭제 가능", () => {
    const r = removeSelection(g, { nodeIds: ["n2"], edgeIds: [] });
    expect(r.edges!.map((e) => e.id)).toEqual(["e3"]);
    const r2 = removeSelection(g, { nodeIds: [], edgeIds: ["e1"] });
    expect(r2.nodes).toHaveLength(4);
    expect(r2.edges).toHaveLength(2);
    expect(r2.ui).toEqual(g.ui);
  });
  it("moveNodes: 위치만 바꾸고 나머지 필드 보존", () => {
    const r = moveNodes(g, new Map([["n1", { x: 40, y: 8 }]]));
    expect(r.nodes![0]).toMatchObject({ position: { x: 40, y: 8 }, extra_node_field: 1 });
    expect(r.nodes![1]).toBe(g.nodes![1]);
  });
  it("duplicateNodes: 선택 노드 사이 엣지만 복제, 깊은 복사", () => {
    const r = duplicateNodes(g, ["n2", "n3"]);
    expect(r.newNodeIds).toEqual(["n5", "n6"]);
    expect(r.graph.edges!.slice(3)).toHaveLength(1); // e2(n2→n3)만
    expect(r.graph.edges!.at(-1)).toMatchObject({ id: "e4", source: { node: "n5", port: "a" }, target: { node: "n6", port: "in" } });
    r.graph.nodes![5]!.config!["mut"] = 1;
    expect(g.nodes![2]!.config).toEqual({});
  });
  it("checkConnection: 자기 연결·중복·순환 거부", () => {
    const c = (sn: string, sp: string, tn: string, tp: string) => ({ source: { node: sn, port: sp }, target: { node: tn, port: tp } });
    expect(checkConnection(g, c("n1", "out", "n1", "in"))).toEqual({ ok: false, reason: "self" });
    expect(checkConnection(g, c("n1", "out", "n2", "in"))).toEqual({ ok: false, reason: "duplicate", existingEdgeId: "e1" });
    expect(checkConnection(g, c("n3", "o", "n1", "i"))).toEqual({ ok: false, reason: "cycle" });
    expect(checkConnection(g, c("n1", "out", "n3", "in"))).toEqual({ ok: true });
  });
  it("addEdge: 종류와 id", () => {
    const r = addEdge(g, { source: { node: "n1", port: "out" }, target: { node: "n3", port: "in" } }, "flow-b");
    expect(r.graph.edges!.at(-1)).toEqual({ id: "e4", kind: "flow-b", source: { node: "n1", port: "out" }, target: { node: "n3", port: "in" } });
  });
  it("decideEdgeKind: 하나뿐이면 자동 > 둘 이상이면 선택 UI(기본값이 후보에 있으면 미리 선택, 없으면 첫 항목)", () => {
    expect(decideEdgeKind(["a", "b"], "b")).toEqual({ mode: "ask", choices: ["a", "b"], preselected: "b" });
    expect(decideEdgeKind(["a", "b"], "zzz")).toEqual({ mode: "ask", choices: ["a", "b"], preselected: "a" });
    expect(decideEdgeKind(["a"], "b")).toEqual({ mode: "auto", kind: "a" });
    expect(decideEdgeKind(["a"])).toEqual({ mode: "auto", kind: "a" });
    expect(decideEdgeKind(["a", "b"])).toEqual({ mode: "ask", choices: ["a", "b"], preselected: "a" });
    expect(decideEdgeKind([])).toEqual({ mode: "none" });
  });
});

describe("PortResolver (디바운스·캐시·마지막 응답 채택)", () => {
  const make = (resolve: (t: string, c: unknown) => Promise<{ outputs: { name: string }[] }>) => {
    vi.useFakeTimers();
    return new PortResolver({ resolve });
  };
  it("연속 변경은 마지막 것만 호출(디바운스)하고, 같은 (타입, config)는 캐시", async () => {
    const resolve = vi.fn(async (_t: string, c: unknown) => ({ outputs: [{ name: JSON.stringify(c) }] }));
    const r = make(resolve);
    try {
      r.request("n", "t", { a: 1 });
      r.request("n", "t", { a: 2 });
      expect(r.get("n").loading).toBe(true);
      await vi.advanceTimersByTimeAsync(299);
      expect(resolve).not.toHaveBeenCalled();
      await vi.advanceTimersByTimeAsync(2);
      expect(resolve).toHaveBeenCalledTimes(1);
      expect(r.get("n").ports?.outputs?.[0]?.name).toBe('{"a":2}');
      // 키 순서가 달라도 같은 config → 호출 없음
      r.request("m", "t", { a: 2 });
      expect(r.get("m").ports?.outputs?.[0]?.name).toBe('{"a":2}');
      expect(resolve).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });
  it("경합: 먼저 보낸 느린 응답이 늦게 와도 마지막 요청의 응답을 채택", async () => {
    const resolvers: Array<(v: { outputs: { name: string }[] }) => void> = [];
    const resolve = vi.fn(() => new Promise<{ outputs: { name: string }[] }>((res) => resolvers.push(res)));
    const r = make(resolve);
    try {
      r.request("n", "t", { v: 1 });
      await vi.advanceTimersByTimeAsync(300);
      r.request("n", "t", { v: 2 });
      await vi.advanceTimersByTimeAsync(300);
      expect(resolve).toHaveBeenCalledTimes(2);
      resolvers[1]!({ outputs: [{ name: "second" }] });
      await vi.advanceTimersByTimeAsync(0);
      resolvers[0]!({ outputs: [{ name: "first" }] });
      await vi.advanceTimersByTimeAsync(0);
      expect(r.get("n").ports?.outputs?.[0]?.name).toBe("second");
    } finally {
      vi.useRealTimers();
    }
  });
  it("실패하면 이전 포트를 유지하고 failed 표시", async () => {
    let fail = false;
    const resolve = vi.fn(async () => {
      if (fail) throw new Error("x");
      return { outputs: [{ name: "ok" }] };
    });
    const r = make(resolve);
    try {
      r.request("n", "t", { v: 1 });
      await vi.advanceTimersByTimeAsync(300);
      fail = true;
      r.request("n", "t", { v: 2 });
      await vi.advanceTimersByTimeAsync(300);
      expect(r.get("n")).toMatchObject({ failed: true, loading: false });
      expect(r.get("n").ports?.outputs?.[0]?.name).toBe("ok");
    } finally {
      vi.useRealTimers();
    }
  });
  it("stableStringify는 키 순서 무관", () => {
    expect(stableStringify({ b: 1, a: [2, { d: 1, c: 2 }] })).toBe(stableStringify({ a: [2, { c: 2, d: 1 }], b: 1 }));
  });
});

describe("그래프 → 흐름 모델 변환", () => {
  const base = {
    nodeTypes: descriptors,
    edgeTypes,
    resolved: new Map(),
    nodeStates: {},
    edgeStates: { e1: "traversed" },
    selectedNodes: new Set<string>(),
    selectedEdges: new Set<string>(),
    positionOverrides: new Map(),
    readOnly: false,
    messages: defaultMessages,
    markerId: "m",
  };
  it("노드·엣지 수와 핸들 id, 알 수 없는 타입 처리, 무효 엣지", () => {
    const m = buildFlowModel({ ...base, graph: sampleGraph() });
    expect(m.nodes.map((n) => n.id)).toEqual(["n1", "n2", "n3", "n4"]);
    expect(m.nodes[3]!.data.unknownType).toBe("ghost-type-not-registered");
    expect(m.nodes[3]!.data.accent).toBe("var(--ac-cat-neutral)");
    const e1 = m.edges.find((e) => e.id === "e1")!;
    expect(e1).toMatchObject({ sourceHandle: "out:out", targetHandle: "in:in" });
    expect(e1.className).toContain("ac-ge-edge--traversed");
    expect(e1.className).toContain("ac-ge-edge--dashed"); // 엣지 타입 ui_hints.dashed
    // n3는 정적 포트에 'extra'가 있어 유효, n2는 동적 포트 미계산이라 무효 표시 안 함
    expect(m.edges.every((e) => !e.data!.invalid)).toBe(true);
    // 정적 포트에서 사라진 포트를 가리키는 엣지는 무효
    const g: Graph = sampleGraph();
    g.edges!.push({ id: "e9", kind: "flow-a", source: { node: "n1", port: "removed" }, target: { node: "n3", port: "in" } });
    const m2 = buildFlowModel({ ...base, graph: g });
    expect(m2.edges.find((e) => e.id === "e9")!.data!.invalid).toBe(true);
  });
  it("끝점 노드가 없는 엣지는 건너뛰고, 드래그 오버라이드가 위치에 우선", () => {
    const g = sampleGraph();
    g.edges!.push({ id: "e8", kind: "flow-a", source: { node: "nope", port: "o" }, target: { node: "n1", port: "i" } });
    const m = buildFlowModel({ ...base, graph: g, positionOverrides: new Map([["n1", { x: 5, y: 6 }]]) });
    expect(m.edges.some((e) => e.id === "e8")).toBe(false);
    expect(m.nodes[0]!.position).toEqual({ x: 5, y: 6 });
  });
  it("엣지 이슈는 무효 스타일(포트 소실 무효와 같은 클래스)로, 노드 이슈는 issueCount로 변환", () => {
    const issues = summarizeIssues([{ severity: "error", code: "c", message: "m", edge_id: "e1", node_id: "n2" }]);
    const m = buildFlowModel({ ...base, graph: sampleGraph(), issues });
    expect(m.edges.find((e) => e.id === "e1")!.className).toContain("ac-ge-edge--invalid");
    expect(m.edges.find((e) => e.id === "e2")!.className).not.toContain("ac-ge-edge--invalid");
    expect(m.nodes[1]!.data.issueCount).toEqual({ error: 1, warning: 0 });
    expect(m.nodes[0]!.data.issueCount).toBeUndefined();
  });
  it("pickDescriptor: type_version 일치 > 최신", () => {
    const v1 = { id: "x", version: 1, title: "v1" };
    const v2 = { id: "x", version: 2, title: "v2" };
    expect(pickDescriptor({ id: "n", type: "x" }, [v1, v2])?.title).toBe("v2");
    expect(pickDescriptor({ id: "n", type: "x", type_version: 1 }, [v1, v2])?.title).toBe("v1");
    expect(pickDescriptor({ id: "n", type: "y" }, [v1, v2])).toBeUndefined();
  });
});

describe("팔레트 그룹", () => {
  it("category 문자열 그대로, 한국어 정렬, 빈 category는 기타, 최신 버전만", () => {
    const groups = groupNodeTypes([...descriptors, { id: "zeta-source", version: 0, title: "구버전", category: "흐름-가" }], "", "기타");
    expect(groups.map((g) => g.category)).toEqual(["기타", "분기", "흐름-가"]);
    expect(groups[2]!.items).toHaveLength(1);
    expect(groupNodeTypes(descriptors, "SINK", "기타")).toHaveLength(1);
  });
});

describe("패키지 경계", () => {
  it("공개 API 파일(index.ts, types.ts)에 React Flow가 나오지 않는다", () => {
    for (const f of ["../index.ts", "../types.ts"]) {
      expect(readFileSync(new URL(f, import.meta.url), "utf8")).not.toContain("@xyflow");
    }
  });
  it("노드 타입 id 비교 분기가 없다(소스에 테스트 타입 이름이 등장하지 않음)", () => {
    for (const f of ["../components/NodeCard.tsx", "../components/flow.tsx", "./convert.ts", "../components/GraphEditor.tsx"]) {
      const src = readFileSync(new URL(f, import.meta.url), "utf8");
      expect(src).not.toMatch(/zeta-source|omega-splitter|kappa-sink|["']router["']|["']agent["']/);
    }
  });
});

describe("이슈 집계", () => {
  const issue = (severity: string, extra: Record<string, unknown>) => ({ severity, code: "c", message: "m", ...extra }) as never;
  it("노드·엣지별 오류/경고 수와 최대 심각도", () => {
    const s = summarizeIssues([
      issue("warning", { node_id: "n1" }),
      issue("error", { node_id: "n1" }),
      issue("error", { node_id: "n1", edge_id: "e1" }),
      issue("info", { node_id: "n2" }),
      issue("error", {}),
    ]);
    expect(s.nodes.get("n1")).toEqual({ error: 2, warning: 1, other: 0, max: "error" });
    expect(s.nodes.get("n2")).toMatchObject({ other: 1, max: "other" });
    expect(s.edges.get("e1")).toMatchObject({ error: 1 });
    expect(summarizeIssues(undefined).nodes.size).toBe(0);
  });
  it("checkConnection: 포트 존재·방향 검증(선택 인자)", () => {
    const g = sampleGraph();
    const lookup = (id: string) => (id === "n1" ? { inputs: [], outputs: ["out"] } : id === "n3" ? { inputs: ["in"], outputs: [] } : undefined);
    const c = (sp: string, tp: string) => ({ source: { node: "n1", port: sp }, target: { node: "n3", port: tp } });
    expect(checkConnection(g, c("out", "in"), lookup)).toEqual({ ok: true });
    expect(checkConnection(g, c("nope", "in"), lookup)).toEqual({ ok: false, reason: "port" });
    expect(checkConnection(g, c("out", "out"), lookup)).toEqual({ ok: false, reason: "port" });
    expect(checkConnection(g, { source: { node: "n3", port: "in" }, target: { node: "n1", port: "out" } }, lookup)).toEqual({ ok: false, reason: "port" });
  });
});
