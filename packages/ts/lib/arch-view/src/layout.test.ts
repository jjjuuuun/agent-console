import { describe, expect, it } from "vitest";
import {
  checkLayout, chipWidthCap, distanceToRect, edgePath, ensureVisible, fitChip, fitViewport, gridLayout, nearestInDirection,
  pathData, polylineMidpoint, rectsOverlap, segmentsIntersect, zoomAround, EDGE_GAP,
} from "./layout";
import { defaultProfileView, sampleCell, sampleEdge } from "./testing";
import type { Rect } from "./types";

describe("gridLayout / edgePath", () => {
  it("좌표가 있는 칸은 중심 좌표를 왼쪽 위로 바꾸고 크기를 지킨다", () => {
    const r = gridLayout({ cells: [sampleCell("a", { x: 130, y: 130 })] });
    expect(r.a).toEqual({ x: 40, y: 96, w: 180, h: 68 });
  });
  it("좌표 없는 칸은 선언 순서대로 격자에 놓이고 서로·기존 칸과 겹치지 않는다", () => {
    const cells = [sampleCell("fixed", { x: 100, y: 100 }), ...["a", "b", "c", "d", "e", "f"].map((i) => sampleCell(i))];
    const r = gridLayout({ cells, canvas: { width: 700, height: 600 } });
    const rects = cells.map((c) => r[c.id] as Rect);
    for (let i = 0; i < rects.length; i++) for (let j = i + 1; j < rects.length; j++) expect(rectsOverlap(rects[i] as Rect, rects[j] as Rect)).toBe(false);
    expect((r.a as Rect).y).toBeGreaterThan((r.fixed as Rect).y + 68);
    expect((r.b as Rect).x).toBeGreaterThan((r.a as Rect).x);
  });
  it("points가 있으면 그대로(6px을 다시 더하지 않는다)", () => {
    expect(edgePath([[226, 130], [374, 130]], null, null)).toEqual([[226, 130], [374, 130]]);
  });
  it("points가 없으면 두 칸 경계 사이 직선, 양 끝은 경계에서 6px 바깥", () => {
    const a: Rect = { x: 0, y: 0, w: 100, h: 50 };
    const b: Rect = { x: 300, y: 0, w: 100, h: 50 };
    const p = edgePath(undefined, a, b);
    expect(p).toEqual([[106, 25], [294, 25]]);
    expect(distanceToRect(p[0]!, a)).toBeCloseTo(EDGE_GAP);
    expect(distanceToRect(p[1]!, b)).toBeCloseTo(EDGE_GAP);
    expect(edgePath(undefined, a, { x: 0, y: 0, w: 100, h: 50 })).toEqual([]);
    expect(edgePath(undefined, a, undefined)).toEqual([]);
  });
  it("pathData·polylineMidpoint", () => {
    expect(pathData([[0, 0], [10, 0], [10, 5]])).toBe("M0 0 L10 0 L10 5");
    expect(polylineMidpoint([[0, 0], [10, 0], [10, 10]])).toEqual([10, 0]);
  });
});

describe("칩 폭 규칙", () => {
  it("가로 선분은 길이−28·120·label_max_w 중 최소, 세로 선분은 길이와 무관", () => {
    expect(chipWidthCap({ length: 148, horizontal: true })).toBe(120);
    expect(chipWidthCap({ length: 100, horizontal: true })).toBe(72);
    expect(chipWidthCap({ length: 70, horizontal: false }, 92)).toBe(92);
    expect(chipWidthCap({ length: 400, horizontal: true }, 60)).toBe(60);
  });
  it("상한을 넘으면 횟수 약식 → 오류 아이콘만 → 라벨 말줄임 순서", () => {
    const m = (t: string) => t.length * 7;
    const content = { label: "abcdef", count: "12,400", countShort: "12.4k", errors: "오류 3" };
    const wide = fitChip(content, 300, m);
    expect(wide).toMatchObject({ count: "12,400", errorsIconOnly: false, labelClipped: false });
    // 전체 폭 152, 횟수 약식 145, 오류 아이콘만 117
    expect(fitChip(content, 150, m)).toMatchObject({ count: "12.4k", errorsIconOnly: false, labelClipped: false });
    expect(fitChip(content, 140, m)).toMatchObject({ count: "12.4k", errorsIconOnly: true, labelClipped: false });
    const tiny = fitChip(content, 100, m);
    expect(tiny).toMatchObject({ errorsIconOnly: true, labelClipped: true, width: 100 });
  });
});

describe("checkLayout (기본 프로필 §9 좌표)", () => {
  const view = defaultProfileView();
  it("칸 16개·연결 21개가 명세 표대로 들어 있다", () => {
    expect(view.cells).toHaveLength(16);
    expect(view.edges).toHaveLength(21);
    expect((view.edges ?? []).filter((e) => e.kind === "structural")).toHaveLength(8);
  });
  it("칸–칸, 연결–칸, 연결–연결, 칩–칩, 칩–칸, 칩–다른 연결 겹침·교차가 0", () => {
    expect(checkLayout(view)).toEqual([]);
  });
  it("모든 연결의 시작·끝은 from·to 칸 경계에서 6px 바깥(오차 1px)", () => {
    const rects = gridLayout(view);
    for (const e of view.edges ?? []) {
      const pts = edgePath(e.points, rects[e.from], rects[e.to]);
      expect(Math.abs(distanceToRect(pts[0]!, rects[e.from]!) - 6), e.id).toBeLessThanOrEqual(1);
      expect(Math.abs(distanceToRect(pts[pts.length - 1]!, rects[e.to]!) - 6), e.id).toBeLessThanOrEqual(1);
    }
  });
  it("칸 위를 지나는 연결·겹친 칸·교차하는 연결·겹친 칩을 잡아낸다(검사기 자신)", () => {
    const cells = [sampleCell("a", { x: 100, y: 100 }), sampleCell("b", { x: 150, y: 100 }), sampleCell("c", { x: 600, y: 100 })];
    const edges = [
      sampleEdge("e1", "a", "c", { points: [[0, 100], [700, 100]], label_at: [400, 100] }),
      sampleEdge("e2", "a", "c", { points: [[400, 0], [400, 200]], label_at: [400, 100] }),
    ];
    const kinds = new Set(checkLayout({ cells, edges }).map((i) => i.kind));
    expect(kinds).toEqual(new Set(["cell-cell", "edge-cell", "edge-edge", "chip-chip", "chip-edge"]));
    expect(segmentsIntersect([0, 0], [10, 10], [0, 10], [10, 0])).toBe(true);
    expect(segmentsIntersect([0, 0], [10, 0], [0, 5], [10, 5])).toBe(false);
  });
});

describe("확대·이동", () => {
  const canvas = { width: 1520, height: 812 };
  it("width 맞춤은 하한 0.6, contain은 하한 없음", () => {
    expect(fitViewport("width", canvas, { width: 756, height: 400 }).zoom).toBe(0.6);
    expect(fitViewport("width", canvas, { width: 1204, height: 400 }).zoom).toBeCloseTo((1204 - 32) / 1520);
    expect(fitViewport("contain", canvas, { width: 420, height: 240 }).zoom).toBeCloseTo((240 - 32) / 812);
    // 좁은 칸(실행 상세 탭 388폭)에서도 전체가 보인다: 0.25 아래로도 내려간다.
    expect(fitViewport("contain", canvas, { width: 388, height: 240 }).zoom).toBeCloseTo((388 - 32) / 1520);
    expect(fitViewport("contain", canvas, { width: 100, height: 100 }).zoom).toBe(0.05);
    expect(fitViewport("width", canvas, { width: 0, height: 0 }).zoom).toBe(1);
  });
  it("zoomAround는 기준 점을 고정", () => {
    const v = zoomAround({ x: 16, y: 16, zoom: 1 }, 2, { x: 216, y: 116 });
    expect(v.zoom).toBe(2);
    expect(v.x).toBe(216 - (216 - 16) * 2);
  });
  it("ensureVisible은 보이면 null, 아니면 최소만 옮긴다", () => {
    const v = { x: 0, y: 0, zoom: 1 };
    const size = { width: 400, height: 300 };
    expect(ensureVisible({ x: 50, y: 50, w: 100, h: 60 }, v, size)).toBeNull();
    const moved = ensureVisible({ x: 380, y: 50, w: 100, h: 60 }, v, size)!;
    expect(moved.x).toBe(-96); // 오른쪽 끝이 (400-16)에 닿도록
    expect(moved.y).toBe(0);
  });
  it("방향키: 가장 가까운 칸, 없으면 null", () => {
    const r = gridLayout(defaultProfileView());
    expect(nearestInDirection(r, "input", "right")).toBe("sdk");
    expect(nearestInDirection(r, "input", "down")).toBe("rules");
    expect(nearestInDirection(r, "input", "left")).toBeNull();
    expect(nearestInDirection(r, "input", "up")).toBeNull();
    expect(nearestInDirection(r, "ghost", "up")).toBeNull();
  });
});
