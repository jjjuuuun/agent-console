import { describe, expect, it } from "vitest";

import { portLayoutKey, resolveDirection, resolveEdgeShape, resolvePortSide } from "./layout";

const known = new Set(["bezier", "smoothstep", "step", "straight", "auto"]);
const isKnown = (id: string) => known.has(id);

describe("resolveEdgeShape", () => {
  const all = {
    edge: { shape: "step" },
    kind: "reply",
    graph: { edge_shape_by_kind: { reply: "straight" }, edge_shape: "auto" },
    settings: "smoothstep",
    hint: "bezier",
    isKnown,
  };

  it("모든 층이 있으면 엣지가 이긴다", () => {
    expect(resolveEdgeShape(all)).toEqual({ value: "step", source: "edge" });
  });

  it.each([
    [{ edge: undefined }, "straight", "graph-kind"],
    [{ edge: undefined, graph: { edge_shape: "auto" } }, "auto", "graph"],
    [{ edge: undefined, graph: undefined }, "smoothstep", "settings"],
    [{ edge: undefined, graph: undefined, settings: undefined }, "bezier", "hint"],
    [{ edge: undefined, graph: undefined, settings: undefined, hint: undefined }, "bezier", "builtin"],
  ])("위 층을 지우면 다음 층 %#", (patch, value, source) => {
    expect(resolveEdgeShape({ ...all, ...patch })).toEqual({ value, source });
  });

  it("다른 종류의 종류별 값은 쓰지 않는다", () => {
    const r = resolveEdgeShape({ ...all, edge: undefined, kind: "entry" });
    expect(r).toEqual({ value: "auto", source: "graph" });
  });

  it("모르는 값·빈 문자열·문자열이 아닌 값은 건너뛰고 다음 층으로 간다", () => {
    expect(resolveEdgeShape({ ...all, edge: { shape: "zigzag" } })).toEqual({ value: "straight", source: "graph-kind" });
    expect(resolveEdgeShape({ ...all, edge: { shape: "" }, graph: { edge_shape_by_kind: { reply: "nope" }, edge_shape: "nope2" } })).toEqual({
      value: "smoothstep",
      source: "settings",
    });
    expect(resolveEdgeShape({ ...all, edge: { shape: 3 as unknown as string }, settings: null })).toEqual({ value: "straight", source: "graph-kind" });
  });

  it("전부 모르는 값이면 내장(또는 fallback)", () => {
    const none = { edge: { shape: "x" }, settings: "y", hint: "z", isKnown };
    expect(resolveEdgeShape(none)).toEqual({ value: "bezier", source: "builtin" });
    expect(resolveEdgeShape({ ...none, fallback: "step" })).toEqual({ value: "step", source: "builtin" });
  });

  it("isKnown이 없으면 모든 문자열을 인정한다(플러그인 모양)", () => {
    expect(resolveEdgeShape({ edge: { shape: "zigzag" } })).toEqual({ value: "zigzag", source: "edge" });
  });

  it("입력이 전혀 없으면 bezier", () => {
    expect(resolveEdgeShape({})).toEqual({ value: "bezier", source: "builtin" });
  });
});

describe("resolveDirection", () => {
  const all = { node: { direction: "bt" }, graph: { direction: "rl" }, settings: "tb", hint: "lr" };

  it("노드 → 그래프 → 설정 → 힌트 → 내장 순", () => {
    expect(resolveDirection(all)).toEqual({ value: "bt", source: "node" });
    expect(resolveDirection({ ...all, node: undefined })).toEqual({ value: "rl", source: "graph" });
    expect(resolveDirection({ ...all, node: undefined, graph: undefined })).toEqual({ value: "tb", source: "settings" });
    expect(resolveDirection({ hint: "tb" })).toEqual({ value: "tb", source: "hint" });
    expect(resolveDirection({})).toEqual({ value: "lr", source: "builtin" });
  });

  it("모르는 값과 auto(아직 풀지 않음)는 건너뛴다", () => {
    expect(resolveDirection({ node: { direction: "auto" }, graph: { direction: "diagonal" }, settings: "tb" })).toEqual({
      value: "tb",
      source: "settings",
    });
  });

  it("방향 어휘 표를 주입할 수 있다", () => {
    const directions = { spiral: { in: "top", out: "left" } } as const;
    expect(resolveDirection({ node: { direction: "spiral" }, directions })).toEqual({ value: "spiral", source: "node" });
    expect(resolveDirection({ node: { direction: "lr" }, directions })).toEqual({ value: "lr", source: "builtin" });
  });

  it("Object.prototype 이름을 방향으로 인정하지 않는다", () => {
    expect(resolveDirection({ node: { direction: "constructor" } })).toEqual({ value: "lr", source: "builtin" });
  });
});

describe("resolvePortSide", () => {
  it("기본은 lr: 입력 왼쪽, 출력 오른쪽", () => {
    expect(resolvePortSide({ io: "in", portId: "in" })).toEqual({ side: "left", source: "builtin", direction: "lr" });
    expect(resolvePortSide({ io: "out", portId: "result" })).toEqual({ side: "right", source: "builtin", direction: "lr" });
  });

  it("방향 4종의 입력/출력 면", () => {
    const sides = (direction: string) => [
      resolvePortSide({ io: "in", portId: "a", node: { direction } }).side,
      resolvePortSide({ io: "out", portId: "a", node: { direction } }).side,
    ];
    expect(sides("lr")).toEqual(["left", "right"]);
    expect(sides("tb")).toEqual(["top", "bottom"]);
    expect(sides("rl")).toEqual(["right", "left"]);
    expect(sides("bt")).toEqual(["bottom", "top"]);
  });

  it("포트별 지정이 방향보다 우선하고 다른 포트에는 영향이 없다", () => {
    const node = { direction: "tb", ports: { [portLayoutKey("out", "result")]: "right" } };
    expect(resolvePortSide({ io: "out", portId: "result", node })).toEqual({ side: "right", source: "port", direction: "tb" });
    expect(resolvePortSide({ io: "out", portId: "other", node })).toEqual({ side: "bottom", source: "node", direction: "tb" });
    expect(resolvePortSide({ io: "in", portId: "result", node }).side).toBe("top");
  });

  it("포트 면이 auto이고 파생 면이 있으면 파생 면을 쓴다(저장값은 그대로)", () => {
    const node = { direction: "tb", ports: { "in:p": "auto" } };
    expect(resolvePortSide({ io: "in", portId: "p", node, autoSide: "left" })).toEqual({ side: "left", source: "auto", direction: "tb" });
    // auto가 아닌 값에는 파생 면이 영향을 주지 않는다
    expect(resolvePortSide({ io: "in", portId: "p", node: { ports: { "in:p": "right" } }, autoSide: "left" }).side).toBe("right");
    expect(resolvePortSide({ io: "in", portId: "p", node: { direction: "tb", ports: { "in:p": "middle" } }, autoSide: "left" }).side).toBe("top"); // 모르는 값은 건너뜀
  });

  it("포트 면이 모르는 값이거나 auto인데 파생 면이 없으면 방향 층으로 떨어진다", () => {
    expect(resolvePortSide({ io: "in", portId: "p", node: { ports: { "in:p": "auto" } }, graph: { direction: "rl" } })).toEqual({
      side: "right",
      source: "graph",
      direction: "rl",
    });
    expect(resolvePortSide({ io: "in", portId: "p", node: { ports: { "in:p": "middle" } }, hint: "bt" })).toEqual({
      side: "bottom",
      source: "hint",
      direction: "bt",
    });
  });

  it("방향 층의 모든 출처가 면으로 이어진다(그래프/설정/힌트)", () => {
    expect(resolvePortSide({ io: "out", portId: "p", graph: { direction: "tb" } }).side).toBe("bottom");
    expect(resolvePortSide({ io: "out", portId: "p", settings: "rl" }).side).toBe("left");
    expect(resolvePortSide({ io: "out", portId: "p", hint: "bt" }).side).toBe("top");
  });
});
