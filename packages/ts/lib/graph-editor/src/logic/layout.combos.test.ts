import { describe, expect, it } from "vitest";

import { resolveDirection, resolveEdgeShape, resolvePortSide } from "./layout";

// 층 조합 전수: 각 층을 (있음 / 없음 / 모르는 값) 3가지로 두고 모든 조합이 순위 표와 같은 결과를 내는지 본다.
const states = ["set", "none", "unknown"] as const;
type St = (typeof states)[number];
const known = new Set(["a", "b", "c", "d", "e"]);

function product<T>(arr: readonly T[], n: number): T[][] {
  if (n === 0) return [[]];
  return product(arr, n - 1).flatMap((rest) => arr.map((x) => [x, ...rest]));
}

describe("resolveEdgeShape 모든 층 조합", () => {
  const ids = ["a", "b", "c", "d", "e"];
  for (const combo of product<St>(states, 5)) {
    it(combo.join(","), () => {
      const val = (i: number): string | undefined => (combo[i] === "set" ? ids[i] : combo[i] === "unknown" ? "zz" : undefined);
      const r = resolveEdgeShape({
        edge: { shape: val(0) },
        kind: "k",
        graph: { edge_shape_by_kind: val(1) === undefined ? {} : { k: val(1) as string }, edge_shape: val(2) },
        settings: val(3),
        hint: val(4),
        isKnown: (id) => known.has(id),
      });
      const sources = ["edge", "graph-kind", "graph", "settings", "hint"];
      const idx = combo.findIndex((c) => c === "set");
      if (idx < 0) expect(r).toEqual({ value: "bezier", source: "builtin" });
      else expect(r).toEqual({ value: ids[idx], source: sources[idx] });
    });
  }
});

describe("resolveDirection / resolvePortSide 모든 층 조합", () => {
  const dirs = ["tb", "rl", "bt", "lr"];
  const sideOut: Record<string, string> = { tb: "bottom", rl: "left", bt: "top", lr: "right" };
  for (const combo of product<St>(states, 4)) {
    it(combo.join(","), () => {
      const val = (i: number): string | undefined => (combo[i] === "set" ? dirs[i] : combo[i] === "unknown" ? "auto" : undefined);
      const input = { node: { direction: val(0) }, graph: { direction: val(1) }, settings: val(2), hint: val(3) };
      const idx = combo.findIndex((c) => c === "set");
      const expected = idx < 0 ? "lr" : (dirs[idx] as string);
      expect(resolveDirection(input).value).toBe(expected);
      expect(resolvePortSide({ ...input, io: "out", portId: "p" }).side).toBe(sideOut[expected]);
      // 포트별 지정이 있으면 어떤 조합에서도 우선
      const withPort = resolvePortSide({ ...input, node: { ...input.node, ports: { "out:p": "top" } }, io: "out", portId: "p" });
      expect(withPort).toMatchObject({ side: "top", source: "port" });
    });
  }
});
