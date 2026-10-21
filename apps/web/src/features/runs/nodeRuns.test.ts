import { describe, expect, it } from "vitest";
import type { NodeRun } from "@agent-console/contracts";
import { compareNodeRuns, groupNodeRuns, nodeRunKey, runBadge, runDimensions, runOrdinalText, visibleRun, visibleRuns } from "./nodeRuns";

const nr = (extra: Partial<NodeRun> & { started_at?: number | null }): NodeRun => ({ run_id: "r", node_id: "n1", status: "succeeded", attempt: 1, iteration: 0, call: 0, ...extra }) as NodeRun;

describe("노드 실행 정렬·고르기", () => {
  const a = nr({ iteration: 0, started_at: 10 });
  const b = nr({ iteration: 1, started_at: 20 });
  const c = nr({ iteration: 2, started_at: 30, status: "running" });

  it("시작 시각 순으로 묶고 노드마다 따로 센다", () => {
    const groups = groupNodeRuns([c, nr({ node_id: "n2", started_at: 5 }), a, b]);
    expect(groups.get("n1")?.map((n) => n.iteration)).toEqual([0, 1, 2]);
    expect(groups.get("n2")).toHaveLength(1);
  });
  it("시작 전(queued) 실행은 가장 최신으로 본다", () => {
    expect(compareNodeRuns(nr({ started_at: null }), a)).toBeGreaterThan(0);
  });
  it("보이는 실행: 고르지 않았으면 최신을 따라가고, 고른 것은 새 실행이 생겨도 유지된다(D10)", () => {
    const list = [a, b];
    expect(visibleRun(list, undefined)).toMatchObject({ index: 1, picked: false });
    const picked = nodeRunKey(a);
    expect(visibleRun(list, picked)).toMatchObject({ index: 0, picked: true });
    expect(visibleRun([...list, c], picked)).toMatchObject({ index: 0, picked: true });
    expect(visibleRun([...list, c], undefined)?.run.iteration).toBe(2);
  });
  it("고른 실행이 사라지면 최신으로 돌아가고, 빈 목록은 없다", () => {
    expect(visibleRun([a, b], "9:9:9")).toMatchObject({ index: 1, picked: false });
    expect(visibleRun([], undefined)).toBeUndefined();
  });
  it("노드별 표", () => {
    const groups = groupNodeRuns([a, b]);
    expect(visibleRuns(groups, { n1: nodeRunKey(a) }).get("n1")?.index).toBe(0);
  });
});

describe("실행 열 문구와 배지 (화면 번호는 값 + 1)", () => {
  it("회차만", () => {
    const list = [nr({ iteration: 0 }), nr({ iteration: 1 }), nr({ iteration: 2 })];
    expect(runDimensions(list)).toEqual({ iterations: true, calls: false });
    expect(runOrdinalText(list[2]!, list)).toBe("3회차");
  });
  it("호출만", () => {
    const list = [nr({ call: 0, started_at: 1 }), nr({ call: 1, started_at: 2 })];
    expect(runOrdinalText(list[1]!, list)).toBe("호출 2");
  });
  it("둘 다", () => {
    const list = [nr({ iteration: 0, call: 0 }), nr({ iteration: 1, call: 1 })];
    expect(runOrdinalText(list[1]!, list)).toBe("2회차 · 호출 2");
  });
  it("시도가 1보다 크면 뒤에 붙이고, 갈리는 축이 없으면 시도 번호만", () => {
    const list = [nr({ iteration: 0, attempt: 1 }), nr({ iteration: 1, attempt: 2 })];
    expect(runOrdinalText(list[1]!, list)).toBe("2회차 · 시도 2");
    const retry = [nr({ attempt: 1 }), nr({ attempt: 2 })];
    expect(runOrdinalText(retry[1]!, retry)).toBe("시도 2");
  });
  it("배지: 실행이 1개면 없고, 회차 #n / 호출 ×n / 둘 다 #n · ×m", () => {
    const one = [nr({})];
    expect(runBadge(one, visibleRun(one, undefined)!, "작성자", "완료")).toBeUndefined();
    const iters = [nr({ iteration: 0 }), nr({ iteration: 1 }), nr({ iteration: 2 })];
    expect(runBadge(iters, visibleRun(iters, undefined)!, "작성자", "완료")).toMatchObject({ text: "#3", picked: false });
    const calls = [nr({ call: 0 }), nr({ call: 1 }), nr({ call: 2 }), nr({ call: 3 })];
    expect(runBadge(calls, visibleRun(calls, undefined)!, "작성자", "완료")?.text).toBe("×4");
    const both = [nr({ iteration: 0, call: 0 }), nr({ iteration: 1, call: 1 })];
    expect(runBadge(both, visibleRun(both, undefined)!, "작성자", "완료")?.text).toBe("#2 · ×2");
  });
  it("접근성 이름에 노드·회차·호출·상태·위치가 들어가고 고른 실행은 (고름)이 붙는다", () => {
    const both = [nr({ iteration: 0, call: 0 }), nr({ iteration: 1, call: 1 })];
    const b = runBadge(both, visibleRun(both, nodeRunKey(both[0]!))!, "작성자", "완료")!;
    expect(b.ariaLabel).toBe("작성자, 1회차, 호출 1번째, 완료. 실행 2개 중 1번째 (고름)");
  });
});
