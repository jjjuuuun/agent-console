import { describe, expect, it } from "vitest";
import type { Graph } from "@agent-console/contracts";
import { LAYOUT_HISTORY_LIMIT, LayoutHistory, sameGraphIgnoringUi } from "./layoutHistory";

const g = (n: number, ui?: Record<string, unknown>): Graph => ({ id: "g", name: "g", nodes: [{ id: "a", type: "t", position: { x: n, y: 0 } }], ...(ui ? { ui } : {}) });

describe("LayoutHistory (§2.4)", () => {
  it("깊이는 30단계이고 넘치면 오래된 것부터 버린다", () => {
    expect(LAYOUT_HISTORY_LIMIT).toBe(30);
    const h = new LayoutHistory();
    for (let i = 0; i < 40; i++) h.record(g(i), g(i + 1));
    expect(h.undoSize).toBe(30);
    let cur = g(40);
    let steps = 0;
    for (;;) {
      const prev = h.undo(cur);
      if (prev === null) break;
      cur = prev;
      steps += 1;
    }
    expect(steps).toBe(30);
    expect(cur.nodes![0]!.position!.x).toBe(10);
  });
  it("undo 후 redo로 되돌아오고, 새 변경을 기록하면 redo는 비워진다", () => {
    const h = new LayoutHistory();
    h.record(g(0), g(1));
    h.record(g(1), g(2));
    const u1 = h.undo(g(2))!;
    expect(u1.nodes![0]!.position!.x).toBe(1);
    expect(h.redoSize).toBe(1);
    const r = h.redo(u1)!;
    expect(r.nodes![0]!.position!.x).toBe(2);
    h.undo(r);
    h.record(g(1), g(9));
    expect(h.redoSize).toBe(0);
    expect(h.redo(g(9))).toBeNull();
  });
  it("현재 그래프가 맨 위 항목의 결과와 다르면(다른 편집이 끼었음) 스택을 비우고 null", () => {
    const h = new LayoutHistory();
    h.record(g(0), g(1));
    expect(h.undo(g(5))).toBeNull();
    expect(h.undoSize).toBe(0);
  });
  it("결과가 같은 변경은 기록하지 않고, ui(viewport)는 비교에서 빼며 복원할 때 현재 ui를 유지한다", () => {
    const h = new LayoutHistory();
    h.record(g(0), g(0));
    expect(h.undoSize).toBe(0);
    h.record(g(0, { viewport: { zoom: 1 } }), g(1, { viewport: { zoom: 1 } }));
    const now = g(1, { viewport: { zoom: 3 } });
    expect(sameGraphIgnoringUi(now, g(1))).toBe(true);
    const prev = h.undo(now)!;
    expect(prev.nodes![0]!.position!.x).toBe(0);
    expect(prev.ui).toEqual({ viewport: { zoom: 3 } });
  });
  it("ui.layout(그래프 기본 방향·모양)은 비교하고 복원하되, ui의 나머지 키는 현재 값을 유지한다", () => {
    const h = new LayoutHistory();
    const before = g(0, { viewport: { zoom: 1 } });
    const after = g(0, { viewport: { zoom: 1 }, layout: { direction: "tb" } });
    expect(sameGraphIgnoringUi(before, after)).toBe(false);
    h.record(before, after); // 좌표는 같고 ui.layout만 바뀐 정리도 한 단계다
    expect(h.undoSize).toBe(1);
    const now = g(0, { viewport: { zoom: 5 }, layout: { direction: "tb" } });
    const prev = h.undo(now)!;
    expect(prev.ui).toEqual({ viewport: { zoom: 5 } });
    const again = h.redo(prev)!;
    expect(again.ui).toEqual({ viewport: { zoom: 5 }, layout: { direction: "tb" } });
  });
});
