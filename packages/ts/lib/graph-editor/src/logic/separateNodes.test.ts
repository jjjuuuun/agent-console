import { describe, expect, it } from "vitest";
import { separateNodesVertically } from "./separateNodes";

const r = (id: string, x: number, y: number, height = 100) => ({ id, x, y, width: 100, height });

describe("separateNodesVertically", () => {
  it("겹친 아래 노드를 내려 최소 간격을 맞춘다", () => {
    const out = separateNodesVertically([r("a", 0, 0, 102), r("b", 0, 100)], 8);
    expect(out.get("b")).toBe(10);
    expect(out.has("a")).toBe(false);
  });
  it("내린 노드의 영향이 그 아래 노드에 이어진다", () => {
    const out = separateNodesVertically([r("a", 0, 0, 102), r("b", 0, 100), r("c", 0, 200)], 8);
    expect(out.get("c")).toBe(18);
  });
  it("가로로 겹치지 않으면 옮기지 않는다", () => {
    expect(separateNodesVertically([r("a", 0, 0, 150), r("b", 200, 100)], 8).size).toBe(0);
  });
  it("간격이 충분하면 그대로, minGap 0이면 꺼짐", () => {
    expect(separateNodesVertically([r("a", 0, 0), r("b", 0, 108)], 8).size).toBe(0);
    expect(separateNodesVertically([r("a", 0, 0, 120), r("b", 0, 100)], 0).size).toBe(0);
  });
});
