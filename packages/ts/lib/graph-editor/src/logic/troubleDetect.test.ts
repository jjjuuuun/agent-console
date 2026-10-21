import { describe, expect, it } from "vitest";
import { detectEdgeTrouble } from "./troubleDetect";
import type { TroubleEdge, TroubleNode } from "./troubleDetect";

const node = (id: string, x: number, y: number, w = 100, h = 40): TroubleNode => ({ id, x, y, width: w, height: h });
const seg = (x1: number, y1: number, x2: number, y2: number) => ({ from: { x: x1, y: y1 }, to: { x: x2, y: y2 } });
const edge = (over: Partial<TroubleEdge> & { id: string }): TroubleEdge => ({
  sourceNode: "a",
  targetNode: "b",
  source: { x: 100, y: 20, side: "right" },
  target: { x: 400, y: 20, side: "left" },
  segments: [seg(100, 20, 400, 20)],
  ...over,
});

describe("detectEdgeTrouble (graph-edges §10)", () => {
  const nodes = [node("a", 0, 0), node("b", 400, 0), node("m", 200, 0)];
  it("자기 끝점이 아닌 노드 사각형을 지나는 선을 찾는다", () => {
    const r = detectEdgeTrouble(nodes, [edge({ id: "e1" })]);
    expect(r).toEqual([{ edgeId: "e1", reasons: ["crosses-node"], crossedNodes: ["m"] }]);
  });
  it("자기 끝점 노드를 지나는 것과 사각형 경계에 스치는 것은 문제가 아니다", () => {
    expect(detectEdgeTrouble([node("a", 0, 0), node("b", 400, 0)], [edge({ id: "e1" })])).toEqual([]);
    expect(detectEdgeTrouble([...nodes.slice(0, 2), node("m", 200, 19)], [edge({ id: "e1" })])).toEqual([]);
    expect(detectEdgeTrouble([...nodes.slice(0, 2), node("m", 200, 17)], [edge({ id: "e1" })])).toHaveLength(1);
  });
  it("엣지가 자기 끝점 노드 안쪽을 가로지르면 crosses-own-node로 센다(고리 연결·자체 회피 엣지는 제외)", () => {
    const own = edge({ id: "e1", source: { x: 100, y: 20, side: "right" }, target: { x: 400, y: 20, side: "left" }, segments: [seg(100, 20, 50, 20), seg(50, 20, 400, 20)] });
    const r = detectEdgeTrouble([node("a", 0, 0), node("b", 400, 0)], [own]);
    expect(r).toEqual([{ edgeId: "e1", reasons: ["crosses-own-node"], crossedNodes: ["a"] }]);
    expect(detectEdgeTrouble([node("a", 0, 0), node("b", 400, 0)], [{ ...own, selfAvoiding: true }])).toEqual([]);
    expect(detectEdgeTrouble([node("a", 0, 0)], [{ ...own, targetNode: "a" }])).toEqual([]);
  });
  it("자체 회피 라우터가 그리는 엣지는 가로지름을 검사하지 않는다", () => {
    expect(detectEdgeTrouble(nodes, [edge({ id: "e1", selfAvoiding: true })])).toEqual([]);
  });
  it("소스 핸들이 타깃 반대 방향이면 노드를 감싼다고 본다(소스·타깃 양쪽)", () => {
    const backwards = edge({ id: "e2", source: { x: 100, y: 20, side: "right" }, target: { x: 0, y: 120, side: "left" }, segments: [] });
    expect(detectEdgeTrouble([node("a", 0, 0), node("b", 0, 100)], [backwards])[0]?.reasons).toEqual(["wraps-node"]);
    const targetAway = edge({ id: "e3", source: { x: 0, y: 0, side: "bottom" }, target: { x: 0, y: 100, side: "bottom" }, segments: [] });
    expect(detectEdgeTrouble([], [targetAway])[0]?.reasons).toEqual(["wraps-node"]);
    // 4R.20: 자체 회피 라우터가 그리는 엣지는 되돌아가는 연결이어도 문제가 아니다
    expect(detectEdgeTrouble([node("a", 0, 0), node("b", 0, 100)], [{ ...backwards, selfAvoiding: true }])).toEqual([]);
    const fine = edge({ id: "e4", source: { x: 0, y: 0, side: "bottom" }, target: { x: 0, y: 100, side: "top" }, segments: [] });
    expect(detectEdgeTrouble([], [fine])).toEqual([]);
  });
  it("허용 오차를 줄 수 있고 결과는 id 순이다", () => {
    const e = edge({ id: "z", source: { x: 100, y: 0, side: "right" }, target: { x: 95, y: 0, side: "left" }, segments: [] });
    expect(detectEdgeTrouble([], [e])).toHaveLength(1);
    expect(detectEdgeTrouble([], [e], { wrapTolerance: 10 })).toEqual([]);
    expect(detectEdgeTrouble(nodes, [edge({ id: "b" }), edge({ id: "a" })]).map((t) => t.edgeId)).toEqual(["a", "b"]);
  });
  it("문제 없는 그래프와 빈 입력", () => {
    expect(detectEdgeTrouble([], [])).toEqual([]);
  });
});
