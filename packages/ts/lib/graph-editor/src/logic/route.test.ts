import { describe, expect, it } from "vitest";

import type { EdgeEndpoint } from "../shapes/types";
import { BUILTIN_EDGE_SHAPES } from "../shapes/registry";
import type { Point } from "./ops";
import { createAStarRouter, routeFallbackAttrs } from "./route";
import type { RouteEdgeRequest, RouteObstacle } from "./route";

const node = (id: string, x: number, y: number, width = 160, height = 64): RouteObstacle => ({ id, x, y, width, height });
const out = (n: RouteObstacle, k = 0.5): EdgeEndpoint => ({ x: n.x + n.width, y: n.y + n.height * k, side: "right" });
const inp = (n: RouteObstacle, k = 0.5): EdgeEndpoint => ({ x: n.x, y: n.y + n.height * k, side: "left" });
const req = (id: string, a: RouteObstacle, b: RouteObstacle, extra: Partial<RouteEdgeRequest> = {}): RouteEdgeRequest => ({
  id,
  source: out(a),
  target: inp(b),
  sourceNodeId: a.id,
  targetNodeId: b.id,
  ...extra,
});

/** 점 목록의 선분이 부풀린 사각형 안쪽(경계 제외)을 지나는가(8px 간격으로 표본). */
function crosses(points: readonly Point[], r: RouteObstacle, inflate: number): boolean {
  for (let i = 1; i < points.length; i += 1) {
    const a = points[i - 1] as Point;
    const b = points[i] as Point;
    const n = Math.ceil(Math.hypot(b.x - a.x, b.y - a.y) / 2);
    for (let k = 0; k <= n; k += 1) {
      const x = a.x + ((b.x - a.x) * k) / n;
      const y = a.y + ((b.y - a.y) * k) / n;
      if (x > r.x - inflate + 1e-3 && x < r.x + r.width + inflate - 1e-3 && y > r.y - inflate + 1e-3 && y < r.y + r.height + inflate - 1e-3) return true;
    }
  }
  return false;
}
const orthogonal = (pts: readonly Point[]) => pts.every((p, i) => i === 0 || p.x === (pts[i - 1] as Point).x || p.y === (pts[i - 1] as Point).y);

describe("A* 자동 경로", () => {
  it("장애물이 없으면 꺾임이 적은 직각 경로", () => {
    const a = node("a", 0, 0);
    const b = node("b", 320, 0);
    const r = createAStarRouter({ maxMillis: 60_000 }).route([req("e", a, b)], [a, b]).get("e")!;
    expect(r.fallback).toBe(false);
    expect(orthogonal(r.points)).toBe(true);
    expect(r.points.length).toBeLessThanOrEqual(2); // 같은 높이면 직선
    expect(r.path.d.startsWith("M")).toBe(true);
  });

  it("중간 노드를 패딩 16 바깥으로 돌아간다", () => {
    const a = node("a", 0, 0);
    const mid = node("m", 240, -40, 160, 144);
    const b = node("b", 640, 0);
    const r = createAStarRouter({ maxMillis: 60_000 }).route([req("e", a, b)], [a, mid, b]).get("e")!;
    expect(r.fallback).toBe(false);
    expect(orthogonal(r.points)).toBe(true);
    expect(crosses(r.points, mid, 16)).toBe(false);
    expect(crosses(r.points, a, 0)).toBe(false);
  });

  it("되돌아가는 연결은 자기 노드 몸 위를 지나지 않고 바깥을 돈다", () => {
    const a = node("a", 400, 0);
    const b = node("b", 0, 0); // a 출력(오른쪽) -> b 입력(왼쪽): 왼쪽으로 되돌아감
    const r = createAStarRouter({ maxMillis: 60_000 }).route([req("e", a, b)], [a, b]).get("e")!;
    expect(r.fallback).toBe(false);
    expect(crosses(r.points, a, 0)).toBe(false);
    expect(crosses(r.points, b, 0)).toBe(false);
    // 스텁은 면 바깥으로 먼저 나간다
    expect((r.points[1] as Point).x).toBeGreaterThan(a.x + a.width);
  });

  it("스텁 구간은 장애물을 무시한다(노드 사이가 좁아도 연결)", () => {
    const a = node("a", 0, 0);
    const b = node("b", 200, 0); // 간격 40 < 패딩*2+스텁
    const r = createAStarRouter({ maxMillis: 60_000 }).route([req("e", a, b)], [a, b]).get("e")!;
    expect(r.fallback).toBe(false);
  });

  it("경유점을 순서대로 지난다", () => {
    const a = node("a", 0, 0);
    const b = node("b", 400, 0);
    const wps = [{ x: 248, y: 200 }, { x: 304, y: -120 }];
    const r = createAStarRouter({ maxMillis: 60_000 }).route([req("e", a, b, { waypoints: wps })], [a, b]).get("e")!;
    const idx = wps.map((w) => r.points.findIndex((p) => p.x === w.x && p.y === w.y));
    // 꺾임점이 아니라 선분 위일 수 있으므로 선분 위 포함 여부로 확인
    const onPath = (w: Point) => r.points.some((p, i) => {
      const q = r.points[i - 1];
      if (!q) return false;
      return (w.x === p.x && w.x === q.x && w.y >= Math.min(p.y, q.y) && w.y <= Math.max(p.y, q.y)) || (w.y === p.y && w.y === q.y && w.x >= Math.min(p.x, q.x) && w.x <= Math.max(p.x, q.x));
    });
    expect(wps.every(onPath)).toBe(true);
    expect(idx).toBeDefined();
  });

  it("탐색 상한을 넘으면 smoothstep으로 대체하고 표식을 켠다", () => {
    const a = node("a", 0, 0);
    const b = node("b", 2000, 1200);
    const r = createAStarRouter({ maxExpansions: 5 }).route([req("e", a, b)], [a, b]).get("e")!;
    expect(r.fallback).toBe(true);
    expect(routeFallbackAttrs(r)).toEqual({ "data-route-fallback": "true" });
    expect(orthogonal(r.points)).toBe(true);
    expect(routeFallbackAttrs({ fallback: false })).toEqual({});
  });

  it("시간 상한(주입한 시계)을 넘어도 대체한다", () => {
    const a = node("a", 0, 0);
    const b = node("b", 4000, 3000);
    let t = 0;
    const r = createAStarRouter({ now: () => (t += 10) }).route([req("e", a, b, { waypoints: [{ x: 1000, y: 2000 }] })], [a, b]).get("e")!;
    expect(r.fallback).toBe(true);
  });

  it("비용을 인자로 바꾼다: 교차 비용이 크면 우회하고 0이면 가로지른다", () => {
    const a = node("a", 0, 0);
    const b = node("b", 400, 0);
    const c = node("c", 200, 200, 80, 40);
    const d = node("d", 200, -200, 80, 40);
    const reqs: RouteEdgeRequest[] = [
      req("e1", a, b),
      { id: "e2", source: { x: 240, y: 200, side: "top" }, target: { x: 240, y: -160, side: "bottom" }, sourceNodeId: "c", targetNodeId: "d" },
    ];
    const nodes = [a, b, c, d];
    /** 두 꺾은선이 서로 엇갈리는 횟수(끝점만 닿는 경우 제외). */
    const countCrossings = (p: readonly Point[], q: readonly Point[]): number => {
      let n = 0;
      for (let i = 1; i < p.length; i += 1) {
        for (let j = 1; j < q.length; j += 1) {
          const a0 = p[i - 1]!, a1 = p[i]!, c0 = q[j - 1]!, c1 = q[j]!;
          const aH = a0.y === a1.y;
          if (aH === (c0.y === c1.y)) continue;
          const [h0, h1, v0, v1] = aH ? [a0, a1, c0, c1] : [c0, c1, a0, a1];
          if (v0.x > Math.min(h0.x, h1.x) && v0.x < Math.max(h0.x, h1.x) && h0.y > Math.min(v0.y, v1.y) && h0.y < Math.max(v0.y, v1.y)) n += 1;
        }
      }
      return n;
    };
    const run = (cross: number) => {
      const res = createAStarRouter({ maxMillis: 60_000, costs: { cross } }).route(reqs, nodes);
      expect(res.get("e2")!.fallback).toBe(false);
      return countCrossings(res.get("e1")!.points, res.get("e2")!.points);
    };
    expect(run(1000)).toBe(0);
    expect(run(0)).toBe(1);
  });

  it("같은 입력은 메모에서 나오고, 노드를 옮기면 다시 계산한다", () => {
    const a = node("a", 0, 0);
    const b = node("b", 320, 120);
    const router = createAStarRouter({ maxMillis: 60_000 });
    const reqs = [req("e1", a, b), req("e2", b, a)];
    const first = router.route(reqs, [a, b]);
    expect(router.stats()).toMatchObject({ hits: 0, misses: 2 });
    const second = router.route(reqs, [b, a]); // 순서가 달라도 같은 입력
    expect(router.stats()).toMatchObject({ hits: 2, misses: 2 });
    expect(second.get("e1")).toBe(first.get("e1"));
    const moved = { ...b, x: 336 };
    router.route([req("e1", a, moved), req("e2", moved, a)], [a, moved]);
    expect(router.stats().misses).toBe(4);
    // 엣지 id 순으로 계산: 뒤 엣지를 바꿔도 앞 엣지는 메모를 쓴다
    router.route([req("e1", a, moved), { ...req("e2", moved, a), radius: 4 }], [a, moved]);
    expect(router.stats()).toMatchObject({ hits: 3, misses: 5 });
    router.clearCache();
    router.route(reqs, [a, b]);
    expect(router.stats().misses).toBe(7);
  });

  it("결과 순서는 엣지 id 순", () => {
    const a = node("a", 0, 0);
    const b = node("b", 320, 0);
    const r = createAStarRouter({ maxMillis: 60_000 }).route([req("z", a, b), req("m", a, b)], [a, b]);
    expect([...r.keys()]).toEqual(["m", "z"]);
  });

  it("모양 auto의 build는 장애물 없이도 경유점을 지나는 직각 경로", () => {
    const auto = BUILTIN_EDGE_SHAPES.find((s) => s.id === "auto")!;
    const res = auto.build({ source: { x: 0, y: 0, side: "right" }, target: { x: 300, y: 100, side: "left" }, waypoints: [], radius: 8, bend: 0.5, stub: 10 });
    expect(res.length).toBeGreaterThan(300);
    expect(res.d).toMatch(/^M/);
  });
});

describe("성능", () => {
  // 5.2R.42: 기본 실행은 작업량(A* 확장 수·재계산 횟수·fallback)을 단언한다. 결정적이라 부하와 무관하다.
  // 벽시계 중앙값 비교는 AGENT_CONSOLE_PERF=strict일 때만 한다(전용 장비에서 회귀 확인용).
  // 시간 상한(maxMillis)은 고부하에서 fallback을 만들므로 여기서는 크게 잡아 끈다.
  const build = () => {
    const nodes: RouteObstacle[] = [];
    for (let i = 0; i < 100; i += 1) nodes.push(node(`n${i}`, (i % 10) * 280, Math.floor(i / 10) * 160));
    let seed = 7;
    const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
    const reqs: RouteEdgeRequest[] = [];
    for (let i = 0; i < 200; i += 1) {
      const a = nodes[Math.floor(rnd() * 100)]!;
      const b = nodes[Math.floor(rnd() * 100)]!;
      if (a === b) { i -= 1; continue; }
      reqs.push(req(`e${String(i).padStart(3, "0")}`, a, b));
    }
    return { nodes, reqs };
  };
  const newRouter = () => createAStarRouter({ maxMillis: 600_000, maxExpansions: 1_000_000 });
  /** 엣지 200개·노드 100개 전체 재계산 확장 수 상한. 실측값에 실측 51574의 약 1.5배 여유(라우터 비용 모델을 바꾸면 갱신). */
  const MAX_TOTAL_EXPANSIONS = 80_000;

  it("엣지 200개·노드 100개 전체 재계산의 작업량이 상한 안(결정적)", () => {
    const { nodes, reqs } = build();
    const router = newRouter();
    const res = router.route(reqs, nodes);
    expect(res.size).toBe(200);
    const st = router.stats();
    expect(st.fallbacks).toBe(0);
    expect(st.misses).toBe(200); // 엣지마다 한 번씩 계산
    expect(st.expansions).toBeGreaterThan(0);
    expect(st.expansions).toBeLessThanOrEqual(MAX_TOTAL_EXPANSIONS);
    // 같은 입력 재호출은 전부 메모 적중: 추가 계산 0
    router.route(reqs, nodes);
    expect(router.stats()).toMatchObject({ misses: 200, hits: 200, expansions: st.expansions });
    // 결정성: 새 라우터도 같은 확장 수
    const other = newRouter();
    other.route(reqs, nodes);
    expect(other.stats().expansions).toBe(st.expansions);
  });

  it.skipIf(process.env["AGENT_CONSOLE_PERF"] !== "strict")("[strict] 전체 재계산 5회 중앙값이 100ms 안", () => {
    const { nodes, reqs } = build();
    const router = newRouter();
    router.route(reqs, nodes); // 워밍업
    const times: number[] = [];
    for (let k = 0; k < 5; k += 1) {
      router.clearCache();
      const t0 = performance.now();
      router.route(reqs, nodes);
      times.push(performance.now() - t0);
    }
    times.sort((x, y) => x - y);
    expect(times[2]!).toBeLessThan(100);
  });
});
