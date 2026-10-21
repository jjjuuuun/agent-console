import type { EdgeTypeDescriptor } from "@agent-console/contracts";
import { describe, expect, it } from "vitest";
import { resolveEdgeStyle } from "./edgeStyle";

/** 임의 이름(x1·y2…)의 종류만 쓴다. 속성만 보고 스타일이 정해져야 한다. */
const kind = (over: Partial<EdgeTypeDescriptor> = {}): EdgeTypeDescriptor => ({ id: "x1", title: "임의 종류", ...over });
const strategies = [{ id: "s-c" }, { id: "s-a" }, { id: "s-b" }, { id: "s-d" }, { id: "s-e" }];

describe("resolveEdgeStyle", () => {
  it("속성이 없으면 내장 기본", () => {
    const r = resolveEdgeStyle(kind());
    expect(r).toMatchObject({ color: undefined, dasharray: undefined, iconName: undefined, defaultShape: undefined });
    expect(r.source).toEqual({ color: "builtin", dasharray: "builtin", iconName: "builtin", defaultShape: "builtin" });
  });
  it("알 수 없는 종류(디스크립터 없음)는 속성을 모르므로 기본값을 적용하지 않는다", () => {
    expect(resolveEdgeStyle(undefined, strategies).source.color).toBe("builtin");
  });
  it("실패 처리 속성: 실패 색 + 점선 2 4 + 둥근 끝 + 경고 아이콘", () => {
    const r = resolveEdgeStyle(kind({ handles_failure: true }));
    expect(r.color).toBe("var(--ac-edge-failure)");
    expect(r.dasharray).toBe("var(--ac-edge-pattern-2)");
    expect(r.linecap).toBe("round");
    expect(r.iconName).toBe("triangle-alert");
    expect(r.source.color).toBe("property");
  });
  it("반복 속성: 반복 색 + 반복 아이콘 + 모양 auto, 실선", () => {
    const r = resolveEdgeStyle(kind({ cycle: { max_iterations: 3 } }));
    expect(r.color).toBe("var(--ac-edge-loop)");
    expect(r.dasharray).toBeUndefined();
    expect(r.iconName).toBe("repeat");
    expect(r.defaultShape).toBe("auto");
  });
  it("속성이 여럿이면 처음 맞는 것 하나만(실패 처리 > 반복 > 위임)", () => {
    const r = resolveEdgeStyle(kind({ handles_failure: true, cycle: { max_iterations: 1 }, invocation: { strategy: "s-b" } }), strategies);
    expect(r.iconName).toBe("triangle-alert");
    expect(r.defaultShape).toBeUndefined();
    const r2 = resolveEdgeStyle(kind({ cycle: { max_iterations: 1 }, invocation: { strategy: "s-b" } }), strategies);
    expect(r2.iconName).toBe("repeat");
  });
  it("위임 연결: 방식 id 정렬 순서 % 4 패턴, 연결이 방식을 바꾸면 그 방식", () => {
    const k = kind({ invocation: { strategy: "s-a" } });
    expect(resolveEdgeStyle(k, strategies).dasharray).toBeUndefined(); // 0번 = 실선
    expect(resolveEdgeStyle(kind({ invocation: { strategy: "s-b" } }), strategies).dasharray).toBe("var(--ac-edge-pattern-1)");
    const third = resolveEdgeStyle(kind({ invocation: { strategy: "s-c" } }), strategies);
    expect(third.dasharray).toBe("var(--ac-edge-pattern-2)");
    expect(third.linecap).toBe("round");
    expect(resolveEdgeStyle(kind({ invocation: { strategy: "s-d" } }), strategies).dasharray).toBe("var(--ac-edge-pattern-3)");
    expect(resolveEdgeStyle(kind({ invocation: { strategy: "s-e" } }), strategies).dasharray).toBeUndefined(); // 4번째 = 0번으로 순환
    expect(resolveEdgeStyle(k, strategies, { strategyId: "s-d" }).dasharray).toBe("var(--ac-edge-pattern-3)");
    // 목록 입력 순서가 달라도 같은 결과(id 정렬 기준)
    expect(resolveEdgeStyle(kind({ invocation: { strategy: "s-b" } }), [...strategies].reverse()).dasharray).toBe("var(--ac-edge-pattern-1)");
  });
  it("위임 방식을 목록에서 찾지 못하면 패턴을 정하지 않는다", () => {
    expect(resolveEdgeStyle(kind({ invocation: { strategy: "ghost" } }), strategies).dasharray).toBeUndefined();
    expect(resolveEdgeStyle(kind({ invocation: { strategy: "s-b" } })).dasharray).toBeUndefined();
  });
  it("ui_hints가 항상 이긴다: 색·dashed·아이콘·모양", () => {
    const r = resolveEdgeStyle(kind({ handles_failure: true, ui_hints: { color: "#22aa88", dashed: true, icon: "★", edge_shape: "bezier" } }));
    expect(r).toMatchObject({ color: "#22aa88", dasharray: "var(--ac-edge-pattern-1)", iconName: "★", defaultShape: "bezier" });
    expect(r.source).toEqual({ color: "hint", dasharray: "hint", iconName: "hint", defaultShape: "hint" });
    // 힌트에 없는 키는 속성 기본값
    const partial = resolveEdgeStyle(kind({ cycle: { max_iterations: 2 }, ui_hints: { color: "#123456" } }));
    expect(partial.color).toBe("#123456");
    expect(partial.iconName).toBe("repeat");
    expect(partial.source.iconName).toBe("property");
  });
  it("안전하지 않은 색은 무시하고 속성 기본값으로", () => {
    expect(resolveEdgeStyle(kind({ cycle: { max_iterations: 2 }, ui_hints: { color: "url(javascript:alert(1))" } })).color).toBe("var(--ac-edge-loop)");
  });
  it("종류 id를 바꿔도 결과가 같다", () => {
    const a = resolveEdgeStyle(kind({ id: "x1", handles_failure: true }));
    const b = resolveEdgeStyle(kind({ id: "y2", handles_failure: true }));
    expect(a).toEqual(b);
  });
});
