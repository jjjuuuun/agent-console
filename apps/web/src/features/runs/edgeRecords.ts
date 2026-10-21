import type { RunEvent } from "@agent-console/contracts";
import { conditionPayloadOf, mapConditionOutcome, parseDelegationEvent, type ConditionOutcomeView } from "../delegation";
import { EDGE_SKIPPED_EVENT, EDGE_TRAVERSED_EVENT } from "./runsConfig";

/** 한 연결의 평가 기록 한 건(통과·건너뜀·반복 시작·반복 한도 도달). 시간순. */
export type EdgeRecord =
  | { kind: "passed"; seq: number; ts: number; condition: unknown }
  | { kind: "skipped"; seq: number; ts: number; condition: unknown; reason: string | undefined }
  | { kind: "iteration"; seq: number; ts: number; iteration: number; nodeIds: string[] }
  | { kind: "exhausted"; seq: number; ts: number; maxIterations: number | undefined };

const str = (v: unknown): string | undefined => (typeof v === "string" && v !== "" ? v : undefined);

/** 이벤트에서 이 연결(`edgeId`)에 관한 기록을 모은다. */
export function edgeRecords(events: readonly RunEvent[], edgeId: string): EdgeRecord[] {
  const out: EdgeRecord[] = [];
  for (const e of events) {
    if (str(e.payload?.["edge_id"]) !== edgeId) continue;
    if (e.type === EDGE_TRAVERSED_EVENT) out.push({ kind: "passed", seq: e.seq, ts: e.ts, condition: conditionPayloadOf(e) });
    else if (e.type === EDGE_SKIPPED_EVENT) out.push({ kind: "skipped", seq: e.seq, ts: e.ts, condition: conditionPayloadOf(e), reason: str(e.payload?.["reason"]) });
    else {
      const v = parseDelegationEvent(e);
      if (v?.kind === "loop-iteration") out.push({ kind: "iteration", seq: e.seq, ts: e.ts, iteration: v.iteration, nodeIds: v.nodeIds });
      else if (v?.kind === "loop-exhausted") out.push({ kind: "exhausted", seq: e.seq, ts: e.ts, maxIterations: v.maxIterations });
    }
  }
  return out.sort((a, b) => a.seq - b.seq);
}

export type EdgeStatus = "passed" | "skipped-condition" | "skipped-upstream" | "none";

/** 연결의 마지막 평가 결과: 통과 / 건너뜀(조건 거짓·상류 건너뜀) / 아직 안 지나감. 조건 근거는 마지막 평가의 것. */
export function edgeStatus(records: readonly EdgeRecord[]): { status: EdgeStatus; at?: number; passes: number; condition?: ConditionOutcomeView | null; rawCondition?: unknown } {
  const evals = records.filter((r): r is Extract<EdgeRecord, { kind: "passed" | "skipped" }> => r.kind === "passed" || r.kind === "skipped");
  const passes = evals.filter((r) => r.kind === "passed").length;
  const last = evals[evals.length - 1];
  if (last === undefined) return { status: "none", passes };
  const hasCondition = last.condition !== undefined && last.condition !== null;
  const mapped = hasCondition ? mapConditionOutcome(last.condition) : undefined;
  const base = { at: last.ts, passes, ...(hasCondition ? { condition: mapped ?? null, rawCondition: last.condition } : {}) };
  if (last.kind === "passed") return { status: "passed", ...base };
  return { status: hasCondition ? "skipped-condition" : "skipped-upstream", ...base };
}
