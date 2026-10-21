import { getBezierPath, Position } from "@xyflow/react";
import { describe, expect, it } from "vitest";

import { BUILTIN_EDGE_SHAPES, createEdgeShapeRegistry } from "../shapes/registry";
import type { EdgeEndpoint, EdgeShapeDescriptor, Side } from "../shapes/types";
import { ARROW_GAP, MAX_WAYPOINTS, buildEdgePath, orthogonalPoints, sideNormal } from "./edgePath";
import type { Point } from "./ops";

const registry = createEdgeShapeRegistry();
const shape = (id: string): EdgeShapeDescriptor => {
  const s = registry.get(id);
  if (!s) throw new Error(id);
  return s;
};
const SIDES: Side[] = ["left", "right", "top", "bottom"];
const POS: Record<Side, Position> = { left: Position.Left, right: Position.Right, top: Position.Top, bottom: Position.Bottom };
const src = (side: Side): EdgeEndpoint => ({ x: 100, y: 100, side });
const tgt = (side: Side): EdgeEndpoint => ({ x: 400, y: 260, side });
const near = (a: Point, b: Point) => Math.hypot(a.x - b.x, a.y - b.y) < 1e-6;

describe("registry", () => {
  it("내장 5종이 정해진 순서로 있다", () => {
    expect(registry.list.map((s) => s.id)).toEqual(["bezier", "smoothstep", "step", "straight", "auto"]);
    expect(BUILTIN_EDGE_SHAPES.every((s) => /^M/.test(s.preview))).toBe(true);
  });

  it("모양을 추가·대체할 수 있다(하드코딩 목록 아님)", () => {
    const custom: EdgeShapeDescriptor = { ...shape("straight"), id: "zig", title: "지그재그" };
    const r = createEdgeShapeRegistry([...BUILTIN_EDGE_SHAPES, custom, { ...custom, title: "대체" }]);
    expect(r.has("zig")).toBe(true);
    expect(r.get("zig")?.title).toBe("대체");
    expect(r.list).toHaveLength(6);
    expect(r.has("nope")).toBe(false);
    expect(createEdgeShapeRegistry([]).list).toEqual([]);
  });

  it("지원 속성이 표와 같다", () => {
    const flags = (id: string) => {
      const s = shape(id);
      return [s.supportsWaypoints, s.supportsBend, s.supportsRadius, s.route ?? null];
    };
    expect(flags("bezier")).toEqual([true, false, false, null]);
    expect(flags("smoothstep")).toEqual([true, true, true, null]);
    expect(flags("step")).toEqual([true, true, false, null]);
    expect(flags("straight")).toEqual([true, false, false, null]);
    expect(flags("auto")).toEqual([true, false, true, "obstacle-avoiding"]);
  });
});

describe("bezier 무경유점 = getBezierPath", () => {
  for (const a of SIDES) {
    for (const b of SIDES) {
      it(`${a} -> ${b}`, () => {
        const s = src(a);
        const t = tgt(b);
        const ns = sideNormal(a);
        const nt = sideNormal(b);
        const [expected, lx, ly] = getBezierPath({
          sourceX: s.x + ns.x * ARROW_GAP,
          sourceY: s.y + ns.y * ARROW_GAP,
          targetX: t.x + nt.x * ARROW_GAP,
          targetY: t.y + nt.y * ARROW_GAP,
          sourcePosition: POS[a],
          targetPosition: POS[b],
        });
        const r = buildEdgePath({ source: s, target: t, shape: shape("bezier") });
        expect(r.d).toBe(expected);
        const mid = r.labelAt(0.5);
        expect(mid.x).toBeCloseTo(lx, 6);
        expect(mid.y).toBeCloseTo(ly, 6);
      });
    }
  }

  it("예전 코드와 같은 가로 연결 문자열 스냅샷", () => {
    const r = buildEdgePath({ source: { x: 100, y: 100, side: "right" }, target: { x: 400, y: 260, side: "left" }, shape: shape("bezier") });
    expect(r.d).toBe("M106,100 C250,100 250,260 394,260");
  });
});

describe("법선 ARROW_GAP", () => {
  it.each(SIDES)("%s 면: 시작·끝이 면 바깥으로 6px", (side) => {
    for (const id of ["bezier", "smoothstep", "step", "straight", "auto"]) {
      const r = buildEdgePath({ source: src(side), target: tgt(side), shape: shape(id) });
      const n = sideNormal(side);
      const first = r.segments[0]?.from as Point;
      const last = r.segments[r.segments.length - 1]?.to as Point;
      expect(near(first, { x: 100 + n.x * ARROW_GAP, y: 100 + n.y * ARROW_GAP })).toBe(true);
      expect(near(last, { x: 400 + n.x * ARROW_GAP, y: 260 + n.y * ARROW_GAP })).toBe(true);
    }
  });

  it("arrowGap 0이면 핸들 위치", () => {
    const r = buildEdgePath({ source: src("right"), target: tgt("left"), shape: shape("straight"), arrowGap: 0 });
    expect(r.d).toBe("M100,100 L400,260");
  });
});

describe("직각 규칙", () => {
  const wp: Point[][] = [[], [{ x: 250, y: 40 }], [{ x: 250, y: 40 }, { x: 320, y: 300 }, { x: 180, y: 320 }]];
  for (const a of SIDES) {
    for (const b of SIDES) {
      for (const w of wp) {
        it(`${a} -> ${b}, 경유점 ${w.length}`, () => {
          const input = { source: { ...src(a), x: 94, y: 100 }, target: tgt(b), waypoints: w, radius: 8, bend: 0.5, stub: 10 };
          const pts = orthogonalPoints(input);
          // 모든 선분이 수평 또는 수직
          for (let i = 1; i < pts.length; i += 1) {
            const p = pts[i - 1] as Point;
            const q = pts[i] as Point;
            expect(p.x === q.x || p.y === q.y).toBe(true);
          }
          // 경유점을 순서대로 지난다(일직선이면 꺾임점 목록에서 빠질 수 있으니 경로 위의 위치로 확인)
          let prevPos = -1;
          for (const p of w) {
            const pos = arcPosition(pts, p);
            expect(pos).toBeGreaterThanOrEqual(0);
            expect(pos).toBeGreaterThanOrEqual(prevPos);
            prevPos = pos;
          }
          // 시작은 소스 면 바깥으로, 끝은 타깃 면 안쪽으로 스텁 길이 이상의 직선
          const ns = sideNormal(a);
          const nt = sideNormal(b);
          const n = pts.length;
          const p0 = pts[0] as Point;
          const p1 = pts[1] as Point;
          expect(Math.sign(p1.x - p0.x)).toBe(ns.x);
          expect(Math.sign(p1.y - p0.y)).toBe(ns.y);
          expect(Math.hypot(p1.x - p0.x, p1.y - p0.y)).toBeGreaterThanOrEqual(10);
          const q0 = pts[n - 2] as Point;
          const q1 = pts[n - 1] as Point;
          expect(Math.sign(q1.x - q0.x)).toBe(-nt.x + 0);
          expect(Math.sign(q1.y - q0.y)).toBe(-nt.y + 0);
          expect(Math.hypot(q1.x - q0.x, q1.y - q0.y)).toBeGreaterThanOrEqual(10);
        });
      }
    }
  }

  it("우 -> 좌, 경유점 없음: bend 위치에 가운데 선분이 있는 Z자", () => {
    const s = { x: 100, y: 100, side: "right" as const };
    const t = { x: 400, y: 260, side: "left" as const };
    const mid = (bend: number) => {
      const pts = orthogonalPoints({ source: s, target: t, waypoints: [], radius: 0, bend, stub: 16 });
      return pts.filter((p, i) => i > 0 && (pts[i - 1] as Point).x === p.x && (pts[i - 1] as Point).y !== p.y).map((p) => p.x);
    };
    expect(mid(0.5)).toEqual([250]); // 스텁 끝 116..384의 가운데
    expect(mid(0)).toEqual([116]);
    expect(mid(1)).toEqual([384]);
  });

  it("하 -> 상 (수직 흐름)도 Z자", () => {
    const pts = orthogonalPoints({
      source: { x: 100, y: 100, side: "bottom" },
      target: { x: 300, y: 400, side: "top" },
      waypoints: [],
      radius: 0,
      bend: 0.5,
      stub: 16,
    });
    expect(pts).toEqual([
      { x: 100, y: 100 },
      { x: 100, y: 250 },
      { x: 300, y: 250 },
      { x: 300, y: 400 },
    ]);
  });

  it("역주행(소스 오른쪽, 타깃이 왼쪽 뒤)은 스텁을 되짚지 않는다", () => {
    const pts = orthogonalPoints({
      source: { x: 400, y: 100, side: "right" },
      target: { x: 100, y: 260, side: "left" },
      waypoints: [],
      radius: 0,
      bend: 0.5,
      stub: 16,
    });
    for (let i = 2; i < pts.length; i += 1) {
      const a = pts[i - 2] as Point;
      const b = pts[i - 1] as Point;
      const c = pts[i] as Point;
      const dot = (b.x - a.x) * (c.x - b.x) + (b.y - a.y) * (c.y - b.y);
      expect(dot).toBeGreaterThanOrEqual(0);
    }
  });

  it("경로가 같은 점을 두 번 포함하지 않고 일직선 중간 점이 없다", () => {
    const pts = orthogonalPoints({
      source: { x: 0, y: 0, side: "right" },
      target: { x: 200, y: 0, side: "left" },
      waypoints: [{ x: 100, y: 0 }],
      radius: 8,
      bend: 0.5,
      stub: 16,
    });
    expect(pts).toEqual([{ x: 0, y: 0 }, { x: 200, y: 0 }]);
  });

  it("smoothstep 모서리는 Q를 쓰고 step은 쓰지 않는다", () => {
    const base = { source: src("right"), target: tgt("left") };
    expect(buildEdgePath({ ...base, shape: shape("smoothstep") }).d).toContain("Q");
    expect(buildEdgePath({ ...base, shape: shape("step") }).d).not.toContain("Q");
    expect(buildEdgePath({ ...base, shape: shape("smoothstep"), radius: 0 }).d).not.toContain("Q");
  });

  it("radius는 0~24로 자르고 짧은 선분에서는 절반을 넘지 않는다", () => {
    const base = { source: { x: 0, y: 0, side: "right" as const }, target: { x: 40, y: 10, side: "left" as const }, shape: shape("smoothstep") };
    const big = buildEdgePath({ ...base, radius: 100 });
    const small = buildEdgePath({ ...base, radius: 24 });
    expect(big.d).toBe(small.d);
    expect(big.length).toBeGreaterThan(0);
  });

  it("bend는 smoothstep에서만 가운데 선분을 옮긴다(auto/straight는 무시)", () => {
    const base = { source: src("right"), target: tgt("left") };
    expect(buildEdgePath({ ...base, shape: shape("smoothstep"), bend: 0.2 }).d).not.toBe(buildEdgePath({ ...base, shape: shape("smoothstep"), bend: 0.8 }).d);
    expect(buildEdgePath({ ...base, shape: shape("auto"), bend: 0.2 }).d).toBe(buildEdgePath({ ...base, shape: shape("auto"), bend: 0.8 }).d);
  });

  it("경유점이 있으면 bend는 무시한다", () => {
    const base = { source: src("right"), target: tgt("left"), waypoints: [{ x: 250, y: 40 }], shape: shape("smoothstep") };
    expect(buildEdgePath({ ...base, bend: 0.1 }).d).toBe(buildEdgePath({ ...base, bend: 0.9 }).d);
  });
});

describe("모양별 경유점", () => {
  const wps = [{ x: 250, y: 40 }];
  for (const id of ["bezier", "straight", "smoothstep", "step", "auto"]) {
    it(`${id}: 경유점 0/1/N`, () => {
      const base = { source: src("right"), target: tgt("left"), shape: shape(id) };
      const none = buildEdgePath(base);
      const one = buildEdgePath({ ...base, waypoints: wps });
      const many = buildEdgePath({ ...base, waypoints: [...wps, { x: 300, y: 300 }, { x: 120, y: 330 }] });
      expect(none.d).not.toBe(one.d);
      expect(one.d).not.toBe(many.d);
      // 경로가 경유점 근처를 지난다
      const nearest = (r: typeof one, p: Point) => Math.min(...r.segments.map((s) => Math.min(Math.hypot(s.from.x - p.x, s.from.y - p.y), Math.hypot(s.to.x - p.x, s.to.y - p.y))));
      expect(nearest(one, wps[0] as Point)).toBeLessThan(id === "smoothstep" || id === "auto" ? 12 : 1e-6);
      expect(many.length).toBeGreaterThan(one.length);
    });
  }

  it("straight는 점들을 잇는 폴리라인", () => {
    const r = buildEdgePath({ source: src("right"), target: tgt("left"), shape: shape("straight"), waypoints: wps });
    expect(r.d).toBe("M106,100 L250,40 L394,260");
    expect(r.segments).toHaveLength(2);
  });

  it("경유점을 지원하지 않는 모양에는 경유점을 넘기지 않는다", () => {
    const noWp = { ...shape("straight"), id: "nowp", supportsWaypoints: false };
    const r = buildEdgePath({ source: src("right"), target: tgt("left"), shape: noWp, waypoints: wps });
    expect(r.d).toBe("M106,100 L394,260");
  });

  it("경유점은 16개까지만 쓰고 유한하지 않은 점은 버린다", () => {
    const many = Array.from({ length: 30 }, (_, i) => ({ x: 120 + i * 5, y: 50 + i }));
    const r = buildEdgePath({ source: src("right"), target: tgt("left"), shape: shape("straight"), waypoints: [...many, { x: Number.NaN, y: 0 }] });
    expect(r.segments).toHaveLength(MAX_WAYPOINTS + 1);
  });

  it("bezier 경유점 곡선은 양 끝에서 면 법선 방향으로 나간다", () => {
    const r = buildEdgePath({ source: src("bottom"), target: tgt("top"), shape: shape("bezier"), waypoints: wps });
    const m = /^M[\d.]+,[\d.]+ C([\d.]+),([\d.]+)/.exec(r.d);
    expect(Number(m?.[1])).toBe(100); // 제어점 x가 시작 x와 같다 = 수직으로 출발
    expect(Number(m?.[2])).toBeGreaterThan(106);
  });
});

describe("길이·라벨", () => {
  it("직선: 길이와 중점", () => {
    const r = buildEdgePath({ source: { x: 0, y: 0, side: "right" }, target: { x: 112, y: 0, side: "left" }, shape: shape("straight"), arrowGap: 0 });
    expect(r.length).toBe(112);
    expect(r.labelAt(0.5)).toEqual({ x: 56, y: 0, angle: 0 });
    expect(r.labelAt(-1).x).toBe(0);
    expect(r.labelAt(2).x).toBe(112);
  });

  it("직각 경로의 라벨은 경로 위에 있다", () => {
    const r = buildEdgePath({ source: src("right"), target: tgt("left"), shape: shape("smoothstep") });
    for (const t of [0.1, 0.3, 0.5, 0.9]) {
      const p = r.labelAt(t);
      const dist = Math.min(...r.segments.map((s) => distToSegment(p, s.from, s.to)));
      expect(dist).toBeLessThan(1e-6);
    }
  });

  it("같은 점에서 시작·끝나도 깨지지 않는다", () => {
    const r = buildEdgePath({ source: { x: 0, y: 0, side: "right" }, target: { x: 0, y: 0, side: "right" }, shape: shape("straight"), arrowGap: 0 });
    expect(r.length).toBe(0);
    expect(r.labelAt(0.5)).toEqual({ x: 0, y: 0, angle: 0 });
  });
});

function distToSegment(p: Point, a: Point, b: Point): number {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len2 = dx * dx + dy * dy;
  const k = len2 === 0 ? 0 : Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / len2));
  return Math.hypot(p.x - (a.x + k * dx), p.y - (a.y + k * dy));
}

/** 꺾임점 목록으로 이은 경로에서 점 p가 놓인 위치(시작부터의 거리). 경로 위에 없으면 -1. */
function arcPosition(pts: readonly Point[], p: Point): number {
  let acc = 0;
  for (let i = 1; i < pts.length; i += 1) {
    const a = pts[i - 1] as Point;
    const b = pts[i] as Point;
    if (distToSegment(p, a, b) < 1e-6) return acc + Math.hypot(p.x - a.x, p.y - a.y);
    acc += Math.hypot(b.x - a.x, b.y - a.y);
  }
  return -1;
}
