/// <reference types="node" />
import { createElement } from "react";
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Position } from "@xyflow/react";
import { describe, expect, it, vi } from "vitest";
import type { EdgeTypeDescriptor, Graph, NodeTypeDescriptor } from "@agent-console/contracts";
import { defaultMessages } from "../messages";
import { buildFlowModel } from "../logic/convert";
import { NodeCard } from "./NodeCard";

vi.mock("@xyflow/react", async (orig) => ({
  ...(await orig<object>()),
  // 라벨 칩 포털은 정적 렌더에서 비어 버리므로 그 자리에 그대로 그린다
  EdgeLabelRenderer: ({ children }: { children: ReactNode }) => children,
}));
import { AcEdge } from "./flow";

/**
 * layout이 없는 그래프의 DOM·경로 고정(3R.21 완료 기준). 기대값은 3R.21 이전(커밋 f151a9c)의 NodeCard·AcEdge 출력을
 * 같은 입력으로 만든 것이며, 현재 출력과 글자 단위로 같음을 확인한 뒤 고정했다. 바뀌면 의도된 변경인지 확인한다.
 */
const handle = (p: { id: string }, io: string) => createElement("i", { "data-h": io + ":" + p.id });
const cardProps = (compact: boolean) => ({
  label: "일꾼", typeTitle: "행위자", accent: "red", iconText: "일", width: 200, compact, renderPortHandle: handle,
  inputs: [{ id: "in", label: "받기", side: "left" as const }, { id: "y", label: "y", connected: true, side: "left" as const }],
  outputs: [{ id: "out", label: "내기", side: "right" as const }],
  hintChips: ["c"], badges: ["입구"],
});
const NORMAL = "<div class=\"ac-ge-node ac-status-box ac-text\" style=\"--ac-ge-accent:red;width:200px\" data-labels=\"auto\"><span class=\"ac-ge-node-bar ac-status-keep\" aria-hidden=\"true\"></span><div class=\"ac-ge-node-header ac-status-header\"><span class=\"ac-ge-avatar\" aria-hidden=\"true\">일</span><div class=\"ac-ge-node-titles\"><div class=\"ac-ge-node-label ac-clamp-2\" title=\"일꾼\">일꾼</div><div class=\"ac-ge-node-type ac-ellipsis\" title=\"행위자\">행위자</div></div><span class=\"ac-ge-badges\"><span class=\"ac-ge-badge\">입구</span></span></div><div class=\"ac-ge-ports\"><div class=\"ac-ge-port-row\"><div class=\"ac-ge-port ac-ge-port--in\" data-port=\"in\" title=\"받기\"><i data-h=\"in:in\"></i><span class=\"ac-ge-port-label ac-ellipsis\">받기</span></div><div class=\"ac-ge-port ac-ge-port--out\" data-port=\"out\" title=\"내기\"><i data-h=\"out:out\"></i><span class=\"ac-ge-port-label ac-ellipsis\">내기</span></div></div><div class=\"ac-ge-port-row\"><div class=\"ac-ge-port ac-ge-port--in\" data-port=\"y\" data-connected=\"true\" title=\"y\"><i data-h=\"in:y\"></i><span class=\"ac-ge-port-label ac-ellipsis\">y</span></div><span></span></div></div><div class=\"ac-ge-hint-chips\"><span class=\"ac-ge-hint-chip\">c</span></div></div>";
const COMPACT = "<div class=\"ac-ge-node ac-status-box ac-text\" style=\"--ac-ge-accent:red;width:200px\" data-compact=\"true\" data-labels=\"auto\"><span class=\"ac-ge-node-bar ac-status-keep\" aria-hidden=\"true\"></span><div class=\"ac-ge-node-header ac-status-header\"><span class=\"ac-ge-avatar\" aria-hidden=\"true\">일</span><div class=\"ac-ge-node-titles\"><div class=\"ac-ge-node-label ac-clamp-2\" title=\"일꾼\">일꾼</div><div class=\"ac-ge-node-type ac-ellipsis\" title=\"행위자\">행위자</div></div><span class=\"ac-ge-badges\"><span class=\"ac-ge-badge\">입구</span></span></div><span class=\"ac-ge-chip-handles ac-ge-chip-handles--in\"><span><i data-h=\"in:in\"></i></span><span><i data-h=\"in:y\"></i></span></span><span class=\"ac-ge-chip-handles ac-ge-chip-handles--out\"><span><i data-h=\"out:out\"></i></span></span><div class=\"ac-ge-hint-chips\"><span class=\"ac-ge-hint-chip\">c</span></div></div>";
const EDGE_FULL = "<path id=\"e\" marker-end=\"url(#m)\" class=\"react-flow__edge-path ac-ge-edge\" d=\"M106,20 C200,20 200,90 294,90\" fill=\"none\"></path><path d=\"M106,20 C200,20 200,90 294,90\" fill=\"none\" stroke-opacity=\"0\" stroke-width=\"16\" class=\"react-flow__edge-interaction\"></path><div class=\"ac-ge-edge-chip ac-ellipsis\" style=\"transform:translate(-50%, -50%) translate(200px, 55px)\" data-badged=\"true\" title=\"답변 · 이름\"><span class=\"ac-ge-order\" title=\"o\" aria-label=\"o\">2</span>답변 · 이름<span class=\"ac-ge-hint-chip\">h</span><span class=\"ac-ge-count\" title=\"c\" aria-label=\"c\">×3</span></div>";

describe("layout 없는 그래프의 DOM 고정", () => {
  it("NodeCard 일반 카드 전체 DOM", () => {
    expect(renderToStaticMarkup(createElement(NodeCard, cardProps(false)))).toBe(NORMAL);
  });
  it("NodeCard 칩 카드 전체 DOM", () => {
    expect(renderToStaticMarkup(createElement(NodeCard, cardProps(true)))).toBe(COMPACT);
  });
  const edgeProps = {
    id: "e", source: "a", target: "b", sourceX: 100, sourceY: 20, targetX: 300, targetY: 90,
    sourcePosition: Position.Right, targetPosition: Position.Left, selected: false,
  };
  it("AcEdge 전체 DOM: 경로 d·라벨 위치·순번·칩·횟수", async () => {
    const { BUILTIN_EDGE_SHAPES } = await import("../shapes/registry");
    const shape = BUILTIN_EDGE_SHAPES.find((s) => s.id === "bezier")!;
    const data = { label: "답변 · 이름", dashed: false, invalid: false, invalidText: "x", markerId: "m", hintChips: ["h"], orderBadge: 2, orderText: "o", countBadge: 3, countText: "c", shape };
    expect(renderToStaticMarkup(createElement(AcEdge as never, { ...edgeProps, data }))).toBe(EDGE_FULL);
  });
  it("reply 연결선: 선언형 칩에서 나온 라벨이 예전 config.label 표시와 같다", () => {
    const nodeTypes: NodeTypeDescriptor[] = [{ id: "n-x", version: 1, title: "X", category: "c", static_ports: { inputs: [{ name: "in" }], outputs: [{ name: "out" }] } }];
    const edgeTypes: EdgeTypeDescriptor[] = [{ id: "k-reply", title: "답변", ui_hints: { chips: [{ value_pointer: "/label", placement: "title" }] } }];
    const g: Graph = {
      id: "g", name: "g",
      nodes: [{ id: "a", type: "n-x", label: "A", config: {}, position: { x: 0, y: 0 } }, { id: "b", type: "n-x", label: "B", config: {}, position: { x: 300, y: 0 } }],
      edges: [{ id: "e", kind: "k-reply", source: { node: "a", port: "out" }, target: { node: "b", port: "in" }, config: { label: "이름" } }],
    };
    const m = buildFlowModel({
      graph: g, nodeTypes, edgeTypes, resolved: new Map(), nodeStates: {}, edgeStates: {}, selectedNodes: new Set(),
      selectedEdges: new Set(), positionOverrides: new Map(), readOnly: false, messages: defaultMessages, markerId: "m", layoutDefaults: { edgeShape: "bezier" },
    });
    const html = renderToStaticMarkup(createElement(AcEdge as never, { ...edgeProps, data: m.edges[0]!.data }));
    expect(html).toBe(
      EDGE_FULL.replace(/<span class="ac-ge-order".*?<\/span>/, "")
        .replace(/<span class="ac-ge-hint-chip">h<\/span>/, "")
        .replace(/<span class="ac-ge-count".*?<\/span>/, "")
        .replace(' data-badged="true"', ""),
    );
  });
});
