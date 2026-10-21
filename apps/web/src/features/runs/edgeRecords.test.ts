import { describe, expect, it } from "vitest";
import type { RunEvent } from "@agent-console/contracts";
import { edgeRecords, edgeStatus } from "./edgeRecords";

const ev = (seq: number, type: string, payload: Record<string, unknown>): RunEvent => ({ event_id: `e${seq}`, run_id: "r", seq, ts: seq * 10, node_path: [], type, payload });

describe("연결 기록", () => {
  const events = [
    ev(1, "edge.skipped", { edge_id: "e1", reason: "cond", condition: { result: false } }),
    ev(2, "edge.traversed", { edge_id: "e1", condition: { result: true, items: [{ path: "/a", op: "x", result: true }] } }),
    ev(3, "loop.iteration", { edge_id: "e1", iteration: 1, nodes: ["a"] }),
    ev(4, "edge.traversed", { edge_id: "other" }),
    ev(5, "loop.exhausted", { edge_id: "e1", iteration: 3, max_iterations: 3 }),
  ];
  it("이 연결의 평가·반복 기록만 시간순으로 모은다", () => {
    expect(edgeRecords(events, "e1").map((r) => r.kind)).toEqual(["skipped", "passed", "iteration", "exhausted"]);
    expect(edgeRecords(events, "none")).toEqual([]);
  });
  it("상태는 마지막 평가 기준이고 조건 근거를 어댑터로 푼다", () => {
    const st = edgeStatus(edgeRecords(events, "e1"));
    expect(st.status).toBe("passed");
    expect(st.passes).toBe(1);
    expect(st.condition?.items?.[0]?.path).toBe("/a");
  });
  it("건너뜀: 조건 근거가 있으면 조건 거짓, 없으면 상류 건너뜀; 기록이 없으면 아직", () => {
    expect(edgeStatus(edgeRecords([events[0]!], "e1")).status).toBe("skipped-condition");
    expect(edgeStatus(edgeRecords([ev(1, "edge.skipped", { edge_id: "e1" })], "e1")).status).toBe("skipped-upstream");
    expect(edgeStatus([]).status).toBe("none");
  });
  it("해석할 수 없는 근거는 condition이 null(원본은 rawCondition)", () => {
    const st = edgeStatus(edgeRecords([ev(1, "edge.traversed", { edge_id: "e1", condition: "?" })], "e1"));
    expect(st.condition).toBeNull();
    expect(st.rawCondition).toBe("?");
  });
});
