import { describe, expect, it } from "vitest";
import { nudgeParallel } from "./nudge";
import type { NudgeEdge } from "./nudge";
import { createAStarRouter } from "./route";

// 두 엣지가 y=100 줄의 x 100..300 구간을 공유하는 Z자 경로
const z = (id: string, y0: number, y1: number): NudgeEdge => ({
  id,
  points: [{ x: 0, y: y0 }, { x: 40, y: y0 }, { x: 40, y: 100 }, { x: 300, y: 100 }, { x: 300, y: y1 }, { x: 340, y: y1 }],
});

describe("nudgeParallel: 겹침 완화", () => {
  it("같은 줄에서 겹치는 선분을 6px 간격으로 벌린다(가운데 정렬, id 순)", () => {
    const out = nudgeParallel([z("b", 20, 180), z("a", 60, 140)], [], 6);
    const ya = out.get("a")!.map((p) => p.y);
    const yb = out.get("b")!.map((p) => p.y);
    // 공유 선분(인덱스 2·3)만 이동: a는 -3, b는 +3
    expect([ya[2], ya[3]]).toEqual([97, 97]);
    expect([yb[2], yb[3]]).toEqual([103, 103]);
    // 끝점은 그대로
    expect(out.get("a")![0]).toEqual({ x: 0, y: 60 });
    expect(out.get("b")!.at(-1)).toEqual({ x: 340, y: 180 });
  });

  it("겹치지 않으면 아무것도 바꾸지 않고, 3개면 6px씩 3줄", () => {
    const a: NudgeEdge = { id: "a", points: [{ x: 0, y: 0 }, { x: 40, y: 0 }, { x: 40, y: 50 }, { x: 100, y: 50 }, { x: 100, y: 0 }, { x: 140, y: 0 }] };
    const b: NudgeEdge = { id: "b", points: [{ x: 0, y: 200 }, { x: 40, y: 200 }, { x: 40, y: 300 }, { x: 100, y: 300 }, { x: 100, y: 200 }, { x: 140, y: 200 }] };
    expect(nudgeParallel([a, b], [], 6).size).toBe(0);
    const out = nudgeParallel([z("a", 20, 180), z("b", 60, 140), z("c", 40, 160)], [], 6);
    expect([out.get("a")![2]!.y, out.get("b")?.[2]?.y ?? 100, out.get("c")![2]!.y]).toEqual([94, 100, 106]);
  });

  it("잠긴 엣지(경유점 등)는 움직이지 않고 자리만 차지한다", () => {
    const locked = { ...z("a", 20, 180), locked: true };
    const out = nudgeParallel([locked, z("b", 60, 140)], [], 6);
    expect(out.has("a")).toBe(false);
    expect(out.get("b")![2]!.y).toBe(106);
  });

  it("벌린 선분이 다른 노드의 패딩 사각형을 지나면 그대로 둔다", () => {
    const wall = { id: "w", x: 150, y: 104, width: 40, height: 20 };
    const out = nudgeParallel([z("a", 20, 180), z("b", 60, 140)], [wall], 6, 16);
    expect(out.size).toBe(0);
  });

  it("gap 0이면 끈다", () => {
    expect(nudgeParallel([z("a", 20, 180), z("b", 60, 140)], [], 0).size).toBe(0);
  });
});

describe("라우터 옵션 nudge", () => {
  const n = (id: string, x: number, y: number) => ({ id, x, y, width: 160, height: 64 });
  const reqs = (ids: string[]) =>
    ids.map((id, i) => ({
      id,
      source: { x: 160, y: 32 + i * 4, side: "right" as const },
      target: { x: 800, y: 32 + i * 4, side: "left" as const },
      sourceNodeId: "s",
      targetNodeId: "t",
    }));
  it("기본값은 켜짐(6px), nudge: 0이면 끈다. 겹침이 없으면 둘이 같다", () => {
    const nodes = [n("s", 0, 0), n("t", 800, 0)];
    const on = createAStarRouter({ maxMillis: 60_000 }).route(reqs(["a", "b"]), nodes);
    const off = createAStarRouter({ maxMillis: 60_000, nudge: 0 }).route(reqs(["a", "b"]), nodes);
    expect([...on.values()].every((r) => !r.fallback)).toBe(true);
    expect([...off.values()].every((r) => !r.fallback)).toBe(true);
  });
});
