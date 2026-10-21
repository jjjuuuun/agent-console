import { describe, expect, it } from "vitest";

import type { EdgeEndpoint } from "../shapes/types";
import type { Point } from "./ops";
import { createAStarRouter } from "./route";
import type { RouteEdgeRequest, RouteObstacle } from "./route";

const node = (id: string, x: number, y: number, width = 160, height = 64): RouteObstacle => ({ id, x, y, width, height });
const out = (n: RouteObstacle): EdgeEndpoint => ({ x: n.x + n.width, y: n.y + n.height / 2, side: "right" });
const inp = (n: RouteObstacle): EdgeEndpoint => ({ x: n.x, y: n.y + n.height / 2, side: "left" });

function scenario() {
  const nodes: RouteObstacle[] = [];
  for (let i = 0; i < 100; i += 1) nodes.push(node(`n${i}`, (i % 10) * 280, Math.floor(i / 10) * 160));
  let seed = 7;
  const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
  const reqs: RouteEdgeRequest[] = [];
  for (let i = 0; i < 200; i += 1) {
    const a = nodes[Math.floor(rnd() * 100)]!;
    const b = nodes[Math.floor(rnd() * 100)]!;
    if (a === b) { i -= 1; continue; }
    reqs.push({ id: `e${String(i).padStart(3, "0")}`, source: out(a), target: inp(b), sourceNodeId: a.id, targetNodeId: b.id });
  }
  return { nodes, reqs };
}

/** 선분이 사각형(inflate 만큼 부풀림) 내부를 정확히 관통하는가(축 정렬 선분이라 해석적으로 검사). */
function pierces(points: readonly Point[], r: RouteObstacle, inf: number): boolean {
  const x0 = r.x - inf, x1 = r.x + r.width + inf, y0 = r.y - inf, y1 = r.y + r.height + inf;
  for (let i = 1; i < points.length; i += 1) {
    const a = points[i - 1]!, b = points[i]!;
    const lx = Math.min(a.x, b.x), hx = Math.max(a.x, b.x), ly = Math.min(a.y, b.y), hy = Math.max(a.y, b.y);
    if (lx < x1 - 1e-3 && hx > x0 + 1e-3 && ly < y1 - 1e-3 && hy > y0 + 1e-3) return true;
  }
  return false;
}

describe("QA: 성능 시나리오 관통·결정성", () => {
  it("노드 비관통(자기 노드 0, 타 노드 16) + 결정성", () => {
    const { nodes, reqs } = scenario();
    const router = createAStarRouter({ maxMillis: 60_000, maxExpansions: 1_000_000 });
    const last = router.route(reqs, nodes);
    let bad = 0, badOwn = 0, nonOrtho = 0;
    for (const q of reqs) {
      const r = last.get(q.id)!;
      for (const n of nodes) {
        const own = n.id === q.sourceNodeId || n.id === q.targetNodeId;
        if (pierces(r.points, n, own ? 0 : 16)) {
          if (own) badOwn += 1;
          else bad += 1;
        }
      }
      if (!r.points.every((p: Point, i: number) => i === 0 || p.x === r.points[i - 1]!.x || p.y === r.points[i - 1]!.y)) nonOrtho++;
    }
    // 결정성
    const again = createAStarRouter({ maxMillis: 60_000, maxExpansions: 1_000_000 }).route([...reqs].reverse(), [...nodes].reverse());
    let diff = 0;
    for (const q of reqs) if (again.get(q.id)!.path.d !== last.get(q.id)!.path.d) diff++;
    expect(nonOrtho).toBe(0);
    expect(router.stats().fallbacks).toBe(0);
    expect(bad).toBe(0);
    expect(badOwn).toBe(0);
    expect(diff).toBe(0);
  });
});
