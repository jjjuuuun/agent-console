import type { GraphSummary } from "@agent-console/contracts";

/** 서버가 계산한 입구 목록이 있으면 "입구 없음"을 판정한다. 계산하지 않았으면(null) 모른다(undefined). */
export function hasEntry(team: Pick<GraphSummary, "entry_labels">): boolean | undefined {
  return team.entry_labels == null ? undefined : team.entry_labels.length > 0;
}
