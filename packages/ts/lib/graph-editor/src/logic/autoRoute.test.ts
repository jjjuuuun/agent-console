import { describe, expect, it } from "vitest";
import { buildRouteInput, faceAnchor, handleEndpoint, routePreview } from "./autoRoute";
import type { HandleBox, PreviewNode, RouteNodeGeometry } from "./autoRoute";
import { createAStarRouter } from "./route";

const box = (id: string, x: number, y: number, position: HandleBox["position"], w = 8, h = 8): HandleBox => ({ id, x, y, width: w, height: h, position });
const node = (id: string, x: number, y: number, source: HandleBox[] = [], target: HandleBox[] = []): RouteNodeGeometry => ({ id, x, y, width: 160, height: 80, source, target });

describe("handleEndpoint: React Flow의 핸들 끝점 규칙과 같다", () => {
  const n = node("a", 100, 50);
  it("면에 맞닿은 변의 중앙", () => {
    expect(handleEndpoint(n, box("h", 152, 36, "right"))).toEqual({ x: 100 + 152 + 8, y: 50 + 36 + 4, side: "right" });
    expect(handleEndpoint(n, box("h", -4, 36, "left"))).toEqual({ x: 96, y: 90, side: "left" });
    expect(handleEndpoint(n, box("h", 40, -4, "top"))).toEqual({ x: 144, y: 46, side: "top" });
    expect(handleEndpoint(n, box("h", 40, 76, "bottom"))).toEqual({ x: 144, y: 134, side: "bottom" });
  });
});

describe("buildRouteInput", () => {
  const nodes = new Map([
    ["a", node("a", 0, 0, [box("out:x", 156, 36, "right")])],
    ["b", node("b", 400, 0, [], [box("in:y", -4, 36, "left")])],
  ]);
  it("엣지의 두 핸들 좌표와 모든 노드 장애물을 만든다", () => {
    const { requests, obstacles } = buildRouteInput([{ id: "e", source: "a", target: "b", sourceHandle: "out:x", targetHandle: "in:y", waypoints: [{ x: 1, y: 2 }], radius: 4 }], nodes);
    expect(obstacles.map((o) => o.id)).toEqual(["a", "b"]);
    expect(requests).toHaveLength(1);
    expect(requests[0]).toMatchObject({ id: "e", source: { x: 164, y: 40, side: "right" }, target: { x: 396, y: 40, side: "left" }, sourceNodeId: "a", targetNodeId: "b", radius: 4, waypoints: [{ x: 1, y: 2 }] });
  });
  it("측정되지 않은 핸들·모르는 노드의 엣지는 요청에서 뺀다", () => {
    const { requests } = buildRouteInput(
      [
        { id: "e1", source: "a", target: "b", sourceHandle: "nope", targetHandle: "in:y" },
        { id: "e2", source: "a", target: "zzz", sourceHandle: "out:x", targetHandle: "in:y" },
      ],
      nodes,
    );
    expect(requests).toEqual([]);
  });
});

describe("routePreview: 새 위치 기준 라우터 경로", () => {
  const sides = (m: [string, "left" | "right" | "top" | "bottom"][] = []) => new Map(m);
  const pn = (id: string, x: number, y: number): PreviewNode => ({ id, x, y, width: 160, height: 80, inputSides: sides(), outputSides: sides() });
  it("가운데 노드를 피해 돌아가고 모든 엣지를 한 번의 route() 호출로 계산한다", () => {
    const base = createAStarRouter();
    let calls = 0;
    const router = { id: base.id, route: (...a: Parameters<typeof base.route>) => (calls += 1, base.route(...a)) };
    const nodes = [pn("a", 0, 0), pn("mid", 240, -20), pn("b", 480, 0), pn("c", 480, 200)];
    const out = routePreview(router, nodes, [
      { id: "e1", source: { node: "a", port: "o" }, target: { node: "b", port: "i" } },
      { id: "e2", source: { node: "a", port: "o" }, target: { node: "c", port: "i" } },
    ]);
    expect(calls).toBe(1);
    expect([...out.keys()]).toEqual(["e1", "e2"]);
    const e1 = out.get("e1")!;
    // 가운데 노드(240..400, -20..60)의 안쪽을 지나는 점이 없다
    expect(e1.points.some((p) => p.x > 240 && p.x < 400 && p.y > -20 && p.y < 60)).toBe(false);
    expect(e1.path.d.startsWith("M")).toBe(true);
  });
  it("faceAnchor는 면 중앙", () => {
    expect(faceAnchor({ x: 0, y: 0, width: 100, height: 40 }, "bottom")).toEqual({ x: 50, y: 40, side: "bottom" });
  });
});
