import { describe, expect, it } from "vitest";
import type { EdgeLayout, Graph } from "@agent-console/contracts";
import {
  EDGE_LAYOUT_KEY_ORDER,
  RESET_PATH_PATCH,
  applyEdgeLayoutPatch,
  changedLayoutKeys,
  cycleShape,
  insertIndexFor,
  insertWaypoint,
  isRedundantWaypoint,
  lockAxis,
  midpointHandles,
  nearestLabelT,
  nearestOnSegments,
  normalizeEdgeLayout,
  patchEdgeLayout,
  placeWaypoint,
  removeWaypoint,
  reorderWaypoint,
  setEdgeLayout,
  snapLabelT,
} from "./edgeLayoutOps";

const g = (layout?: EdgeLayout): Graph => ({
  id: "g",
  name: "g",
  nodes: [],
  edges: [
    { id: "e1", kind: "k", source: { node: "a", port: "o" }, target: { node: "b", port: "i" }, ...(layout ? { layout } : {}) },
    { id: "e2", kind: "k", source: { node: "a", port: "o" }, target: { node: "c", port: "i" } },
  ],
});

describe("normalizeEdgeLayout (§5.4)", () => {
  it("키 순서는 shape, radius, bend, waypoints, label_t, label_offset이고 모르는 키는 뒤에 그대로 간다", () => {
    const n = normalizeEdgeLayout({ label_offset: { x: 1, y: 2 }, future: { a: 1 }, waypoints: [{ x: 1, y: 2 }], shape: "step", label_t: 0.3, bend: 0.5, radius: 4 });
    expect(Object.keys(n!)).toEqual([...EDGE_LAYOUT_KEY_ORDER, "future"]);
    expect(n!["future"]).toEqual({ a: 1 });
  });
  it("빈 경유점·null·빈 객체는 키째 삭제하고 모두 비면 null", () => {
    expect(normalizeEdgeLayout({ waypoints: [], shape: null, bend: undefined })).toBeNull();
    expect(normalizeEdgeLayout({})).toBeNull();
    expect(normalizeEdgeLayout(null)).toBeNull();
    expect(normalizeEdgeLayout({ waypoints: [], radius: 3 })).toEqual({ radius: 3 });
  });
  it("숫자는 반올림하고 경유점은 16개까지만 남긴다", () => {
    const wps = Array.from({ length: 20 }, (_, i) => ({ x: i + 0.123, y: 0.987 }));
    const n = normalizeEdgeLayout({ waypoints: wps, radius: 8.04, label_t: 0.3333 })!;
    expect(n.waypoints).toHaveLength(16);
    expect(n.waypoints![0]).toEqual({ x: 0.1, y: 1 });
    expect(n.radius).toBe(8);
    expect(n.label_t).toBe(0.33);
  });
});

describe("applyEdgeLayoutPatch / patchEdgeLayout / setEdgeLayout", () => {
  it("패치의 null은 키를 지우고 나머지는 보존한다", () => {
    const next = applyEdgeLayoutPatch({ shape: "step", waypoints: [{ x: 1, y: 1 }], label_t: 0.4, extra: 1 }, RESET_PATH_PATCH);
    expect(next).toEqual({ shape: "step", extra: 1 });
  });
  it("모두 비면 엣지에서 layout 키 자체를 지우고 다른 엣지·그래프 필드는 건드리지 않는다", () => {
    const before = g({ shape: "step" });
    const after = patchEdgeLayout(before, "e1", { shape: null });
    expect("layout" in after.edges![0]!).toBe(false);
    expect(after.edges![1]).toBe(before.edges![1]);
    expect(before.edges![0]!.layout).toEqual({ shape: "step" }); // 입력 불변
  });
  it("setEdgeLayout(null)은 전부 기본으로, 없는 엣지는 무시", () => {
    expect("layout" in setEdgeLayout(g({ shape: "step" }), "e1", null).edges![0]!).toBe(false);
    expect(patchEdgeLayout(g(), "nope", { shape: "x" })).toEqual(g());
  });
});

describe("cycleShape (S 키)", () => {
  const ids = ["a", "b", "c"];
  it("앞으로: 상속 → 첫 값 → … → 마지막 → 상속", () => {
    expect(cycleShape(ids, undefined)).toBe("a");
    expect(cycleShape(ids, "a")).toBe("b");
    expect(cycleShape(ids, "c")).toBeNull();
  });
  it("뒤로: 상속 → 마지막 값, 첫 값 → 상속", () => {
    expect(cycleShape(ids, null, -1)).toBe("c");
    expect(cycleShape(ids, "a", -1)).toBeNull();
  });
  it("알 수 없는 값은 상속처럼 취급, 빈 목록은 상속", () => {
    expect(cycleShape(ids, "zzz")).toBe("a");
    expect(cycleShape([], "a")).toBeNull();
  });
});

describe("경유점 연산", () => {
  const p = (x: number, y: number) => ({ x, y });
  it("끼우기·옮기기·지우기·순서 바꾸기, 상한 16에서는 null", () => {
    const base = [p(0, 0), p(10, 10)];
    expect(insertWaypoint(base, 1, p(5, 5))).toEqual([p(0, 0), p(5, 5), p(10, 10)]);
    expect(removeWaypoint(base, 0)).toEqual([p(10, 10)]);
    expect(reorderWaypoint(base, 0, 1)).toEqual([p(10, 10), p(0, 0)]);
    expect(reorderWaypoint(base, 0, 5)).toEqual(base);
    expect(insertWaypoint(Array.from({ length: 16 }, () => p(0, 0)), 0, p(1, 1))).toBeNull();
  });
  it("일직선 판정: 앞뒤 점을 잇는 선에서 tolerance 이내면 중복", () => {
    const src = p(0, 0);
    const tgt = p(100, 0);
    expect(isRedundantWaypoint(src, [p(50, 5)], tgt, 0, 6)).toBe(true);
    expect(isRedundantWaypoint(src, [p(50, 7)], tgt, 0, 6)).toBe(false);
    // 선분 바깥으로 벗어난 점은 일직선이 아니다
    expect(isRedundantWaypoint(src, [p(150, 0)], tgt, 0, 6)).toBe(false);
    // 이웃이 경유점이면 그 점을 기준으로 본다
    expect(isRedundantWaypoint(src, [p(0, 50), p(50, 50)], tgt, 0, 6)).toBe(false);
    expect(isRedundantWaypoint(src, [], tgt, 0, 6)).toBe(false);
  });
  it("placeWaypoint: 격자 스냅, Alt는 스냅 해제, Shift는 축 고정", () => {
    const prev = p(0, 0);
    expect(placeWaypoint(p(13, 21), { prev, shift: false, alt: false, grid: 8 })).toEqual(p(16, 24));
    expect(placeWaypoint(p(13, 21), { prev, shift: false, alt: true, grid: 8 })).toEqual(p(13, 21));
    expect(placeWaypoint(p(40, 5), { prev: p(0, 0), shift: true, alt: false, grid: 8 })).toEqual(p(40, 0));
    expect(lockAxis(p(0, 0), p(3, 9))).toEqual(p(0, 9));
  });
  it("가장 가까운 선분 투영과 삽입 자리", () => {
    const segs = [{ from: p(0, 0), to: p(100, 0) }, { from: p(100, 0), to: p(100, 100) }];
    expect(nearestOnSegments(segs, p(50, 10))).toMatchObject({ point: p(50, 0), distance: 10, index: 0 });
    expect(nearestOnSegments([], p(1, 1))).toBeNull();
    // 소스(0,0) → 경유점(100,0) → 타깃(100,100): 두 번째 구간 근처에 끼우면 경유점 뒤(index 1)
    expect(insertIndexFor(p(0, 0), [p(100, 0)], p(100, 100), p(100, 60))).toBe(1);
    expect(insertIndexFor(p(0, 0), [p(100, 0)], p(100, 100), p(40, 0))).toBe(0);
  });
  it("중점 핸들 수는 경유점 수 + 1이고 경로 위에 놓인다", () => {
    const segs = [{ from: p(0, 0), to: p(100, 0) }];
    const mids = midpointHandles(p(0, 0), [p(100, 0)], p(100, 0), segs);
    expect(mids).toHaveLength(2);
    expect(mids[0]).toEqual(p(50, 0));
  });
});

describe("라벨 위치", () => {
  it("0.05 단위 반올림, 0.1~0.9로 자름", () => {
    expect(snapLabelT(0.33)).toBe(0.35);
    expect(snapLabelT(0)).toBe(0.1);
    expect(snapLabelT(2)).toBe(0.9);
  });
  it("labelAt을 훑어 가장 가까운 t를 찾는다(경로 모양에 의존하지 않음)", () => {
    const labelAt = (t: number) => ({ x: t * 100, y: 0, angle: 0 });
    expect(nearestLabelT(labelAt, { x: 31, y: 40 })).toBe(0.3);
    expect(nearestLabelT(labelAt, { x: -50, y: 0 })).toBe(0.1);
    expect(nearestLabelT(labelAt, { x: 500, y: 0 })).toBe(0.9);
  });
});

describe("changedLayoutKeys", () => {
  it("저장 키 순서대로 알려진 키만", () => {
    expect(changedLayoutKeys({ label_t: 0.3, shape: "x", waypoints: [{ x: 1, y: 1 }], other: 1 })).toEqual(["shape", "waypoints", "label_t"]);
    expect(changedLayoutKeys(null)).toEqual([]);
  });
});
