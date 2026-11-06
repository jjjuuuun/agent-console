import { useQuery } from "@tanstack/react-query";
import type { Graph } from "@agent-console/contracts";
import { useApi } from "../../app/ApiContext";
import { queryKeys, useApiQuery, useWorkspaceSettings } from "../../app/queries";
import { useBackendReadiness } from "../backendReadiness";
import { graphBackendIds } from "./graphBackends";

/**
 * 그래프가 쓰는 백엔드 중 로그인이 필요한데 로그인되어 있지 않은 것이 있는지 알려 준다(시작을 막는 데 쓴다).
 * `projectId`는 그래프가 속한 공간(에이전트 정의를 그 공간에서 찾는다, null = 공용).
 * 로그인 개념이 있는 백엔드(`capabilities.login`)만 대상이고, 그래프를 아직 모르거나 상태를 못 읽으면 막지 않는다.
 */
export function useGraphLoginGate(graph: Graph | undefined, projectId: string | null = null): { signedOut: boolean; backendId: string | undefined } {
  const { rest, space } = useApi();
  const { readiness, isPending } = useBackendReadiness();
  const backends = useQuery({ queryKey: ["descriptors", "backends"], queryFn: () => rest.listBackends(), staleTime: 60_000, retry: false, meta: { silentBackgroundError: true } });
  const agents = useQuery({ queryKey: ["list", "agents", "space", projectId] as const, queryFn: () => space(projectId).listAgents(), enabled: graph !== undefined, retry: false });
  const nodeTypes = useApiQuery(queryKeys.descriptors("node-types"), (r) => r.listNodeTypes(), { staleTime: 60_000, enabled: graph !== undefined });
  const settings = useWorkspaceSettings();
  const defaultBackend = settings.data?.value.agent_defaults?.backend;
  const none = { signedOut: false, backendId: undefined };
  if (graph === undefined || isPending || backends.data === undefined || agents.data === undefined || nodeTypes.data === undefined) return none;
  const used = graphBackendIds({ graph, nodeTypes: nodeTypes.data, agents: agents.data, defaultBackend });
  for (const b of backends.data) {
    if (b.capabilities?.login !== true || !used.has(b.id)) continue;
    const tone = readiness[b.id]?.tone;
    if (tone !== undefined && tone !== "ok" && tone !== "unknown") return { signedOut: true, backendId: b.id };
  }
  return none;
}
