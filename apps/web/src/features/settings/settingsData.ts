import type { RestClient } from "@agent-console/api-client";
import { queryKeys, useApiQuery } from "../../app/queries";

/** 설정 화면이 쓰는 서버 목록·디스크립터 질의. 각 질의는 독립이라 한 곳이 실패해도 다른 섹션은 영향이 없다. */
const loaders = {
  edgeTypes: (rest: RestClient) => rest.listEdgeTypes(),
  mergeStrategies: (rest: RestClient) => rest.listMergeStrategies(),
  backends: (rest: RestClient) => rest.listBackends(),
  delegationStrategies: (rest: RestClient) => rest.listDelegationStrategies(),
  resourceTypes: (rest: RestClient) => rest.listResourceTypes(),
  usageSources: (rest: RestClient) => rest.listUsageSources(),
  usageReport: (rest: RestClient) => rest.getUsage(),
  serverInfo: (rest: RestClient) => rest.getServerInfo(),
  presets: (rest: RestClient) => rest.listPresets(),
  resources: (rest: RestClient) => rest.listResources(),
};

export const useEdgeTypes = () => useApiQuery(queryKeys.descriptors("edge-types"), loaders.edgeTypes);
export const useMergeStrategies = () => useApiQuery(queryKeys.descriptors("merge-strategies"), loaders.mergeStrategies);
export const useBackends = () => useApiQuery(queryKeys.descriptors("backends"), loaders.backends);
export const useDelegationStrategies = () => useApiQuery(queryKeys.descriptors("delegation-strategies"), loaders.delegationStrategies);
export const useResourceTypes = () => useApiQuery(queryKeys.descriptors("resource-types"), loaders.resourceTypes);
export const useUsageSources = () => useApiQuery(queryKeys.descriptors("usage-sources"), loaders.usageSources);
export const useUsageReport = () => useApiQuery(queryKeys.list("usage"), loaders.usageReport);
export const useServerInfo = () => useApiQuery(queryKeys.descriptors("server-info"), loaders.serverInfo);
export const usePresets = () => useApiQuery(queryKeys.list("presets"), loaders.presets);
export const useResourceList = () => useApiQuery(queryKeys.list("resources"), loaders.resources);
