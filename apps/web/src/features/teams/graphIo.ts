import type { RestClient, Versioned } from "@agent-console/api-client";
import { compactGraph } from "../../lib/serialize";
import type { Graph } from "@agent-console/contracts";

/** 팀 구성을 읽는다. 서버는 저장 원문(지정한 필드만)을 주므로 그대로 쓴다. 버전은 `ETag`. */
export async function loadGraph(rest: RestClient, id: string): Promise<Versioned<Graph>> {
  const got = await rest.getGraph(id);
  return { value: got.graph, version_hash: got.version_hash };
}

/** 저장(`If-Match`). 서버가 저장한 것은 보낸 문서(지정한 필드만)와 같으므로 보낸 문서를 기준 값으로 돌려준다. */
export async function saveGraph(rest: RestClient, graph: Graph, versionHash: string | undefined): Promise<Versioned<Graph>> {
  const body = compactGraph(graph);
  const saved = await rest.updateGraph(body.id, body, versionHash ?? "");
  return { value: body, version_hash: saved.version_hash };
}
