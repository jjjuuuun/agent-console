import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { RestClient } from "@agent-console/api-client";
import { queryKeys, useApiQuery } from "../../app/queries";

/** 정의 목록·디스크립터 질의 모음. 키는 설정 화면과 공유한다(`["list", 이름]`). */
const loaders = {
  agents: (rest: RestClient) => rest.listAgents(),
  graphs: (rest: RestClient) => rest.listGraphs(),
  nodeTypes: (rest: RestClient) => rest.listNodeTypes(),
  interactionKinds: (rest: RestClient) => rest.listInteractionKinds(),
  importSources: (rest: RestClient) => rest.listImportSources(),
};

export const useAgentList = () => useApiQuery(queryKeys.list("agents"), loaders.agents);
export const useGraphList = () => useApiQuery(queryKeys.list("graphs"), loaders.graphs);
export const useNodeTypes = () => useApiQuery(queryKeys.descriptors("node-types"), loaders.nodeTypes);
export const useInteractionKinds = () => useApiQuery(queryKeys.descriptors("interaction-kinds"), loaders.interactionKinds);
export const useImportSources = () => useApiQuery(queryKeys.descriptors("import-sources"), loaders.importSources, { staleTime: 0 });

/** 쓰기 뒤 모든 목록(`["list", …]`)을 다시 읽게 한다. */
export function useInvalidateLists(): () => Promise<void> {
  const client = useQueryClient();
  return useCallback(() => client.invalidateQueries({ queryKey: ["list"] }), [client]);
}
