import { describe, expect, it } from "vitest";
import { NEUTRAL_EDGE_STYLE, NEUTRAL_TONE, defaultEdgeStyles, defaultTones, isTokenVar, resolveEdgeStyle, resolveTone } from "./defaults";

describe("X24 대응표", () => {
  it("기본 tone·style은 토큰 변수로 대응한다", () => {
    expect(resolveTone("blue")).toBe("--ac-cat-1");
    expect(resolveEdgeStyle("request").stroke).toBe("--ac-cat-7");
    expect(Object.values(defaultTones).every(isTokenVar)).toBe(true);
    expect(Object.values(defaultEdgeStyles).every((s) => isTokenVar(s.stroke))).toBe(true);
  });
  it("모르는 값·없음은 중립(점선)", () => {
    expect(resolveTone("whatever")).toBe(NEUTRAL_TONE);
    expect(resolveTone(null)).toBe(NEUTRAL_TONE);
    expect(resolveTone("constructor")).toBe(NEUTRAL_TONE);
    expect(resolveEdgeStyle("whatever")).toEqual(NEUTRAL_EDGE_STYLE);
    expect(resolveEdgeStyle("toString")).toEqual(NEUTRAL_EDGE_STYLE);
    expect(NEUTRAL_EDGE_STYLE.dash).toBeTruthy();
  });
  it("prop으로 더한 이름도 토큰 변수만 받는다(임의 색 거부)", () => {
    expect(resolveTone("mine", { mine: "--ac-cat-3" })).toBe("--ac-cat-3");
    for (const bad of ["#ff0000", "red", "rgb(0,0,0)", "--evil", "var(--evil)", "--ac-x;color:red"]) {
      expect(resolveTone("mine", { mine: bad })).toBe(NEUTRAL_TONE);
      expect(resolveEdgeStyle("mine", { mine: { stroke: bad } })).toEqual(NEUTRAL_EDGE_STYLE);
    }
    expect(resolveEdgeStyle("mine", { mine: { stroke: "--ac-cat-2", dash: "dotted" } })).toEqual({ stroke: "--ac-cat-2" });
    expect(resolveEdgeStyle("mine", { mine: { stroke: "--ac-cat-2", dash: "--ac-edge-pattern-2" } }).dash).toBe("--ac-edge-pattern-2");
  });
});
