/** 중첩 팀 경로 노드 id의 구분자(서버 `project.outside_folder` 등의 `node_id`, 예: `T/a`, `T/T/a`). */
export const NODE_PATH_SEPARATOR = "/";

export interface ResolvedNodePath {
  /** 현재 그래프에서 강조할 노드 id(경로형이면 첫 조각, 중첩 팀 노드) */
  nodeId: string;
  /** 첫 조각 뒤에 이어지는 경로(없으면 빈 문자열) */
  rest: string;
}

/**
 * 서버가 준 노드 id를 현재(루트) 그래프의 노드로 푼다. 그대로 있으면 그 id, 없고 경로형이면 첫 조각(팀 노드)과 나머지 경로,
 * 어디에도 없으면 undefined(호출자가 조용히 넘기지 말고 알려야 한다).
 * @param hasNode 현재 그래프에 그 id의 노드가 있는가
 */
export function resolveNodePath(id: string, hasNode: (nodeId: string) => boolean): ResolvedNodePath | undefined {
  if (hasNode(id)) return { nodeId: id, rest: "" };
  const at = id.indexOf(NODE_PATH_SEPARATOR);
  if (at <= 0) return undefined;
  const head = id.slice(0, at);
  return hasNode(head) ? { nodeId: head, rest: id.slice(at + 1) } : undefined;
}
