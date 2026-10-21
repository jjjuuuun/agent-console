import { describe, expect, it } from "vitest";
import { fitShift, intersectRects } from "./popoverFit";

const b = { left: 0, top: 0, right: 500, bottom: 400 };
describe("fitShift", () => {
  it("경계 안이면 이동 없음", () => {
    expect(fitShift({ left: 20, top: 20, right: 200, bottom: 200 }, b)).toEqual({ x: 0, y: 0 });
  });
  it("오른쪽으로 넘치면 왼쪽으로 민다", () => {
    expect(fitShift({ left: 300, top: 20, right: 600, bottom: 200 }, b).x).toBe(-108);
  });
  it("위로 넘치면 아래로 민다", () => {
    expect(fitShift({ left: 20, top: -40, right: 200, bottom: 100 }, b).y).toBe(48);
  });
  it("경계보다 크면 왼쪽·위쪽을 맞춘다", () => {
    expect(fitShift({ left: -50, top: -50, right: 700, bottom: 600 }, b)).toEqual({ x: 58, y: 58 });
  });
  it("여백을 바꿀 수 있다", () => {
    expect(fitShift({ left: 400, top: 0, right: 520, bottom: 50 }, b, 0).x).toBe(-20);
  });
});
describe("intersectRects", () => {
  it("교집합", () => {
    expect(intersectRects([b, { left: 100, top: -5, right: 900, bottom: 300 }])).toEqual({ left: 100, top: 0, right: 500, bottom: 300 });
  });
  it("빈 목록은 null, 겹치지 않으면 0 크기", () => {
    expect(intersectRects([])).toBeNull();
    const r = intersectRects([b, { left: 600, top: 0, right: 700, bottom: 10 }]);
    expect(r !== null && r.right - r.left).toBe(0);
  });
});
