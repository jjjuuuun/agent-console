/// <reference types="node" />
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import { describe, expect, it } from "vitest";
import type { EdgeLayout, EdgeTypeDescriptor, Graph, NodeTypeDescriptor } from "@agent-console/contracts";
import { NodeCard } from "../components/NodeCard";
import { defaultMessages } from "../messages";
import { BUILTIN_EDGE_SHAPES, createEdgeShapeRegistry } from "../shapes/registry";
import { buildFlowModel } from "./convert";
import { declaredLabels, declaredTexts, readValuePointer } from "./declared";
import { placeHandles } from "./handles";
import type { PortView } from "./ports";

const nodeTypes: NodeTypeDescriptor[] = [
  { id: "t-a", version: 1, title: "A", category: "c", static_ports: { inputs: [{ name: "i1" }, { name: "i2" }], outputs: [{ name: "o1" }] } },
  { id: "t-hinted", version: 1, title: "H", category: "c", static_ports: { inputs: [{ name: "i1" }], outputs: [{ name: "o1" }] }, ui_hints: { direction: "tb" } },
];
const edgeTypes: EdgeTypeDescriptor[] = [
  { id: "k-chip", title: "칩 있음", ui_hints: { chips: [{ value_pointer: "/label", placement: "title" }, { value_pointer: "/tag" }] } },
  { id: "k-plain", title: "칩 없음" },
  { id: "k-shape", title: "모양 힌트", ui_hints: { edge_shape: "step" } },
];
const graph = (over: Partial<Graph> = {}): Graph => ({
  id: "g",
  name: "g",
  nodes: [
    { id: "a", type: "t-a", label: "A", config: {}, position: { x: 0, y: 0 } },
    { id: "b", type: "t-a", label: "B", config: {}, position: { x: 300, y: 0 } },
  ],
  edges: [{ id: "e", kind: "k-plain", source: { node: "a", port: "o1" }, target: { node: "b", port: "i1" } }],
  ...over,
});
const build = (g: Graph, extra: Partial<Parameters<typeof buildFlowModel>[0]> = {}) =>
  buildFlowModel({
    graph: g, nodeTypes, edgeTypes, resolved: new Map(), nodeStates: {}, edgeStates: {},
    selectedNodes: new Set(), selectedEdges: new Set(), positionOverrides: new Map(), readOnly: false,
    messages: defaultMessages, markerId: "m", ...extra,
  });

describe("선언형 칩: value_pointer·placement", () => {
  const msgs = { hintLabels: {} };
  it("RFC 6901 포인터: 중첩·이스케이프·배열, 문자열·숫자만", () => {
    const root = { a: { "b/c": "x", "d~e": 3 }, list: ["p", "q"], empty: "", obj: {}, n: null };
    expect(readValuePointer(root, "/a/b~1c")).toBe("x");
    expect(readValuePointer(root, "/a/d~0e")).toBe("3");
    expect(readValuePointer(root, "/list/1")).toBe("q");
    for (const bad of ["/empty", "/obj", "/n", "/zz", "", "no-slash"]) expect(readValuePointer(root, bad)).toBeUndefined();
  });
  it("declaredTexts는 placement를 돌려주고 declaredLabels는 문구만", () => {
    const hints = { chips: [{ value_pointer: "/label", placement: "title" }, { value_pointer: "/tag" }, { label: "고정" }, { value_pointer: "/none" }] };
    const ctx = { config: { label: "L", tag: "T" } };
    expect(declaredTexts(hints, "chips", ctx, msgs)).toEqual([{ text: "L", placement: "title" }, { text: "T" }, { text: "고정" }]);
    expect(declaredLabels(hints, "chips", ctx, msgs)).toEqual(["L", "T", "고정"]);
  });
  it("엣지 라벨: title 칩은 종류 title 뒤에 붙고 나머지는 작은 칩, 값이 비면 안 그린다", () => {
    const g = graph({ edges: [{ id: "e", kind: "k-chip", source: { node: "a", port: "o1" }, target: { node: "b", port: "i1" }, config: { label: "안녕", tag: "t1" } }] });
    expect(build(g).edges[0]!.data).toMatchObject({ label: "칩 있음 · 안녕", hintChips: ["t1"] });
    const empty = graph({ edges: [{ id: "e", kind: "k-chip", source: { node: "a", port: "o1" }, target: { node: "b", port: "i1" }, config: { label: "" } }] });
    expect(build(empty).edges[0]!.data).toMatchObject({ label: "칩 있음" });
    expect(build(empty).edges[0]!.data!.hintChips).toBeUndefined();
  });
  it("칩 선언이 없는 종류는 config.label을 읽지 않는다(E-4)", () => {
    const g = graph({ edges: [{ id: "e", kind: "k-plain", source: { node: "a", port: "o1" }, target: { node: "b", port: "i1" }, config: { label: "숨김" } }] });
    expect(build(g).edges[0]!.data!.label).toBe("칩 없음");
  });
});

describe("연결선 모양 결정과 layout 전달", () => {
  it("직접 고친 선(경유점·bend·radius·label_*)은 shape가 없으면 이전 기본 bezier로 읽는다", () => {
    const g = (layout: EdgeLayout) => graph({ edges: [{ id: "e", kind: "k-plain", source: { node: "a", port: "o1" }, target: { node: "b", port: "i1" }, layout }] });
    for (const layout of [{ waypoints: [{ x: 1, y: 2 }] }, { bend: 0.3 }, { radius: 4 }, { label_t: 0.3 }, { label_offset: { x: 1, y: 1 } }] as EdgeLayout[]) {
      expect(build(g(layout)).edges[0]!.data!.shape.id).toBe("bezier");
    }
    // shape가 있으면 값 그대로, 사용자 설정이 있으면 설정이 먼저
    expect(build(g({ shape: "step", bend: 0.3 })).edges[0]!.data!.shape.id).toBe("step");
    expect(build(g({ bend: 0.3 }), { layoutDefaults: { edgeShape: "straight" } }).edges[0]!.data!.shape.id).toBe("straight");
  });
  it("레지스트리에 auto가 없으면 기본은 bezier", () => {
    const only = BUILTIN_EDGE_SHAPES.filter((s) => s.id !== "auto");
    expect(build(graph(), { edgeShapes: createEdgeShapeRegistry(only) }).edges[0]!.data!.shape.id).toBe("bezier");
  });
  it("layout이 없으면 기본 auto(새 기본)·layout 값 없음", () => {
    const d = build(graph()).edges[0]!.data!;
    expect(d.shape.id).toBe("auto");
    for (const k of ["waypoints", "radius", "bend", "labelT", "labelOffset"] as const) expect(d[k]).toBeUndefined();
  });
  it("순서: 엣지 > 그래프(종류별) > 그래프 > 설정 > 힌트. 레지스트리에 없는 값은 건너뛴다", () => {
    const e = (layout?: EdgeLayout) => ({ id: "e", kind: "k-shape", source: { node: "a", port: "o1" }, target: { node: "b", port: "i1" }, ...(layout ? { layout } : {}) });
    const shapeOf = (g: Graph, extra = {}) => build(g, extra).edges[0]!.data!.shape.id;
    expect(shapeOf(graph({ edges: [e()] }))).toBe("step"); // 힌트
    expect(shapeOf(graph({ edges: [e()] }), { layoutDefaults: { edgeShape: "straight" } })).toBe("straight");
    expect(shapeOf(graph({ edges: [e()], ui: { layout: { edge_shape: "auto" } } }), { layoutDefaults: { edgeShape: "straight" } })).toBe("auto");
    expect(shapeOf(graph({ edges: [e()], ui: { layout: { edge_shape: "auto", edge_shape_by_kind: { "k-shape": "smoothstep" } } } }))).toBe("smoothstep");
    expect(shapeOf(graph({ edges: [e({ shape: "straight" })], ui: { layout: { edge_shape_by_kind: { "k-shape": "smoothstep" } } } }))).toBe("straight");
    expect(shapeOf(graph({ edges: [e({ shape: "no-such" })] }))).toBe("step");
  });
  it("확장 모양과 경유점·반경·꺾임·라벨 위치를 넘긴다(라벨 t는 0.1~0.9로 보정)", () => {
    const custom = { ...BUILTIN_EDGE_SHAPES[0]!, id: "custom", title: "사용자" };
    const layout = { shape: "custom", waypoints: [{ x: 1, y: 2 }], radius: 4, bend: 0.3, label_t: 0.99, label_offset: { x: 5, y: -6 } };
    const g = graph({ edges: [{ id: "e", kind: "k-plain", source: { node: "a", port: "o1" }, target: { node: "b", port: "i1" }, layout }] });
    const d = build(g, { edgeShapes: createEdgeShapeRegistry([...BUILTIN_EDGE_SHAPES, custom]) }).edges[0]!.data!;
    expect(d).toMatchObject({ waypoints: [{ x: 1, y: 2 }], radius: 4, bend: 0.3, labelT: 0.9, labelOffset: { x: 5, y: -6 } });
    expect(d.shape.id).toBe("custom");
  });
});

describe("포트 면과 핸들 배치", () => {
  const portsOf = (g: Graph, id: string, extra = {}) => {
    const n = build(g, extra).nodes.find((x) => x.id === id)!;
    return { in: n.data.inputs, out: n.data.outputs };
  };
  it("layout이 없으면 입력=left·출력=right, offset 없음(행 옆)", () => {
    const p = portsOf(graph(), "a");
    expect(p.in.map((x) => x.side)).toEqual(["left", "left"]);
    expect(p.out.map((x) => x.side)).toEqual(["right"]);
    expect([...p.in, ...p.out].every((x) => x.offset === undefined)).toBe(true);
  });
  it("방향 tb: 위·아래 면에 가로 균등 배치(간격 24, 중앙 정렬)", () => {
    const g = graph({ ui: { layout: { direction: "tb" } } });
    const p = portsOf(g, "a");
    expect(p.in.map((x) => x.side)).toEqual(["top", "top"]);
    expect(p.out[0]!.side).toBe("bottom");
    const [x1, x2] = p.in.map((x) => x.offset!);
    expect(x2! - x1!).toBe(24);
    expect((x1! + x2!) / 2).toBeCloseTo(p.out[0]!.offset!, 5);
  });
  it("힌트 방향은 그래프·노드 지정보다 약하고 설정보다도 약하다", () => {
    const g = graph({ nodes: [{ id: "h", type: "t-hinted", label: "H", config: {}, position: { x: 0, y: 0 } }], edges: [] });
    expect(portsOf(g, "h").in[0]!.side).toBe("top");
    expect(portsOf(g, "h", { layoutDefaults: { direction: "rl" } }).in[0]!.side).toBe("right");
    const withNode = graph({ nodes: [{ id: "h", type: "t-hinted", label: "H", config: {}, position: { x: 0, y: 0 }, layout: { direction: "bt" } }], edges: [] });
    expect(portsOf(withNode, "h", { layoutDefaults: { direction: "rl" } }).in[0]!.side).toBe("bottom");
  });
  it("포트별 지정: 한 출력을 왼쪽으로 보내면 왼쪽 핸들이 섞여 세로 균등 배치", () => {
    const g = graph({ nodes: [{ id: "a", type: "t-a", label: "A", config: {}, position: { x: 0, y: 0 }, layout: { ports: { "out:o1": "left" } } }, graph().nodes![1]!] });
    const p = portsOf(g, "a");
    expect(p.out[0]!.side).toBe("left");
    const offs = [...p.in, ...p.out].map((x) => x.offset);
    expect(offs.every((o) => o !== undefined)).toBe(true);
    expect(new Set(offs).size).toBe(3);
  });
  it("rl: 열이 반대인 한 종류 핸들은 자기 행 중앙(행 높이 24)", () => {
    const p = portsOf(graph({ ui: { layout: { direction: "rl" } } }), "a");
    expect(p.in.map((x) => [x.side, x.offset])).toEqual([["right", 12], ["right", 36]]);
    expect(p.out.map((x) => [x.side, x.offset])).toEqual([["left", 12]]);
  });
  it("placeHandles: 많으면 간격을 줄이되 최소 12, 입력을 바꾸지 않는다", () => {
    const mk = (n: number): PortView[] => Array.from({ length: n }, (_, i) => ({ id: `p${i}`, label: "p", side: "top" as const }));
    const inputs = mk(20);
    const r = placeHandles({ inputs, outputs: [], width: 200 });
    const xs = r.inputs.map((p) => p.offset!);
    expect(xs[1]! - xs[0]!).toBe(12);
    expect(inputs[0]!.offset).toBeUndefined();
  });
  it("칩 카드의 좌·우 면은 offset 없이 가장자리 한 점(기존 규칙), 위·아래만 배치", () => {
    const r = placeHandles({ inputs: [{ id: "a", label: "a", side: "right" }], outputs: [{ id: "b", label: "b", side: "top" }], width: 100, compact: true });
    expect(r.inputs[0]!.offset).toBeUndefined();
    expect(r.outputs[0]!.offset).toBeDefined();
  });
});

describe("NodeCard: 기본 구성은 DOM이 늘지 않는다", () => {
  const h = (p: PortView, io: string) => createElement("i", { "data-h": `${io}:${p.id}` });
  const render = (inputs: PortView[], outputs: PortView[]) =>
    renderToStaticMarkup(createElement(NodeCard, { label: "L", typeTitle: "T", accent: "red", iconText: "L", width: 200, inputs, outputs, renderPortHandle: h }));
  it("lr 기본: 핸들은 포트 행 안, 층·글리프·표식 없음", () => {
    const html = render([{ id: "i", label: "i", side: "left" }], [{ id: "o", label: "o", side: "right" }]);
    expect(html).toContain('<i data-h="in:i"></i>');
    for (const bad of ["ac-ge-handle-layer", "ac-ge-port-glyph", "data-placed", "data-hot", "ac-ge-handle-slot"]) expect(html).not.toContain(bad);
  });
  it("위·아래 면: 핸들이 노드 층의 자리로 옮겨지고 행에는 글리프와 접근성 라벨이 남는다", () => {
    const html = render([{ id: "i", label: "받기", side: "top", offset: 50 }], [{ id: "o", label: "내기", side: "bottom", offset: 50 }]);
    expect(html).toContain("ac-ge-handle-layer--edges");
    expect(html).toContain("ac-ge-handle-slot--top");
    expect(html).toContain("ac-ge-handle-slot--bottom");
    expect(html).toContain("↑");
    expect(html).toContain("↓");
    expect(html.match(/data-h=/g)).toHaveLength(2);
    expect(html).toContain("ac-ge-port-label");
  });
});

describe("하드코딩 점검: 엣지 config의 키 이름을 읽지 않는다(E-4)", () => {
  it("편집기 소스에 config 의 label 키 접근이 없다", () => {
    const root = join(__dirname, "..");
    const files: string[] = [];
    const walk = (dir: string): void => {
      for (const name of readdirSync(dir)) {
        const p = join(dir, name);
        if (statSync(p).isDirectory()) walk(p);
        else if (/\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) && name !== "testing.ts") files.push(p);
      }
    };
    walk(root);
    expect(files.length).toBeGreaterThan(10);
    const hits = files.flatMap((f) =>
      readFileSync(f, "utf8").split("\n").flatMap((line, i) => (/config\??\.(label)\b|config\??\.?\[\s*["'`]label["'`]\s*\]/.test(line) ? [`${f}:${i + 1}`] : [])),
    );
    expect(hits).toEqual([]);
  });
});
