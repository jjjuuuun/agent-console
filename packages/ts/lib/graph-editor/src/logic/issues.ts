import type { Issue } from "@agent-console/contracts";

export interface IssueCounts {
  error: number;
  warning: number;
  /** 그 외 심각도(info 등) */
  other: number;
  /** 가장 높은 심각도: error > warning > other */
  max: "error" | "warning" | "other";
}

export interface IssueSummary {
  /** 노드 id → 집계 (node_id가 있는 이슈) */
  nodes: Map<string, IssueCounts>;
  /** 엣지 id → 집계 (edge_id가 있는 이슈) */
  edges: Map<string, IssueCounts>;
}

function bump(map: Map<string, IssueCounts>, id: string, severity: string): void {
  const cur = map.get(id) ?? { error: 0, warning: 0, other: 0, max: "other" as const };
  if (severity === "error") cur.error += 1;
  else if (severity === "warning") cur.warning += 1;
  else cur.other += 1;
  cur.max = cur.error > 0 ? "error" : cur.warning > 0 ? "warning" : "other";
  map.set(id, cur);
}

/** 검증 이슈를 노드·엣지별로 집계한다(순수 함수). 둘 다 없는 그래프 수준 이슈는 무시. */
export function summarizeIssues(issues: readonly Issue[] | undefined): IssueSummary {
  const out: IssueSummary = { nodes: new Map(), edges: new Map() };
  for (const i of issues ?? []) {
    if (i.node_id !== null && i.node_id !== undefined && i.node_id !== "") bump(out.nodes, i.node_id, i.severity);
    if (i.edge_id !== null && i.edge_id !== undefined && i.edge_id !== "") bump(out.edges, i.edge_id, i.severity);
  }
  return out;
}
