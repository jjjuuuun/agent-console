import type { ResumeNodeOption } from "@agent-console/contracts";

/** 노드의 끊기기 직전 상태 중 "사용자 응답을 기다리던" 것(NodeRun 상태 어휘). */
const WAITING = "waiting";

/**
 * 다시 실행 기본 선택: 디스크립터가 `rerunnable`이라 한 노드 중 응답을 기다리다 끊긴 것만(비용 때문에 실행 중이던 노드는 고르지 않는다).
 * 노드 타입 이름이나 역할로 정하지 않는다. 해당 노드가 없으면 빈 집합(사용자가 고른다).
 */
export function defaultResumeSelection(nodes: readonly ResumeNodeOption[]): Set<string> {
  return new Set(nodes.filter((n) => n.rerunnable && n.status === WAITING).map((n) => n.node_id));
}

/** 선택 중 실행 중이던 노드가 있는가(사용량 경고용). */
export function hasRunningSelected(nodes: readonly ResumeNodeOption[], selected: ReadonlySet<string>): boolean {
  return nodes.some((n) => selected.has(n.node_id) && n.status === "running");
}

/** 다시 실행 가능한 노드가 하나라도 있는가. */
export function anyRerunnable(nodes: readonly ResumeNodeOption[]): boolean {
  return nodes.some((n) => n.rerunnable);
}

/** 서버 422(`details.issues[].node_id`)를 노드별 메시지로. */
export function issuesByNode(details: Readonly<Record<string, unknown>>): Record<string, string> {
  const out: Record<string, string> = {};
  const issues = details["issues"];
  if (!Array.isArray(issues)) return out;
  for (const i of issues as { node_id?: unknown; message?: unknown }[]) {
    if (typeof i?.node_id === "string" && typeof i.message === "string") out[i.node_id] = i.message;
  }
  return out;
}

/** 이 턴을 이어 간 다음 턴이 있는가. */
export function isResumed(turnRunId: string, turns: readonly { resumed_from?: string | null }[]): boolean {
  return turns.some((t) => t.resumed_from === turnRunId);
}

/** 이어 가기 버튼을 보일 턴인가: 마지막 턴이고 끊김이며 아직 이어 가지 않았다(설정 `offer_resume`이 꺼지면 보이지 않는다). */
export function canOfferResume(turn: { run_id: string; status: string }, turns: readonly { run_id: string; resumed_from?: string | null }[], offerResume: unknown): boolean {
  return offerResume !== false && turn.status === "interrupted" && turns[turns.length - 1]?.run_id === turn.run_id;
}
