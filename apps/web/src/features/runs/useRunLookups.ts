import { useMemo } from "react";
import { useQueries } from "@tanstack/react-query";
import type { Agent, ConversationSummary, EdgeTypeDescriptor, GraphSummary, InteractionKindDescriptor, NodeTypeDescriptor } from "@agent-console/contracts";
import { queryKeys, useApiQuery } from "../../app/queries";
import type { RestClient } from "@agent-console/api-client";
import { LOOKUP_REQUIRES } from "../../app/requirements";
import { useRequires } from "../../modules";
import { useApi } from "../../app/ApiContext";
import { useProjects } from "../projects";

const loadAgents = (rest: RestClient) => rest.listAgents();
const loadGraphs = (rest: RestClient) => rest.listGraphs();
const loadConversations = (rest: RestClient) => rest.listConversations({ archived: false });
const loadNodeTypes = (rest: RestClient) => rest.listNodeTypes();
const loadEdgeTypes = (rest: RestClient) => rest.listEdgeTypes();
const loadKinds = (rest: RestClient) => rest.listInteractionKinds();

export interface RunLookups {
  agents: readonly Agent[];
  graphs: readonly GraphSummary[];
  conversations: readonly ConversationSummary[];
  nodeTypes: readonly NodeTypeDescriptor[];
  edgeTypes: readonly EdgeTypeDescriptor[];
  interactionKinds: readonly InteractionKindDescriptor[];
  agentName(id: string | null | undefined): string;
  /** 팀 구성 이름. `projectId`를 주면 그 프로젝트 공간을 먼저 보고, 없으면 공용을 포함한 모든 공간에서 찾는다 */
  graphName(id: string, projectId?: string | null): string | undefined;
  conversationTitle(id: string | null | undefined): string | undefined;
  edgeTitle(kind: string | null | undefined): string | undefined;
  /** 연결 종류 디스크립터의 `ui_hints.icon`(위임 흐름 방식 아이콘). 없으면 undefined */
  edgeIcon(kind: string | null | undefined): string | undefined;
  kindOf(id: string): InteractionKindDescriptor | undefined;
}

const EMPTY: readonly never[] = [];

/**
 * 이름 해석용 목록(에이전트·팀 구성·대화)과 디스크립터(노드 타입·연결 종류·상호작용 종류)를 읽는다.
 * 목록 질의 키는 다른 화면과 공유한다. 로딩 중에는 빈 목록이고, 이름을 못 찾으면 id 원문을 쓴다.
 */
export function useRunLookups(): RunLookups {
  // 이름 해석용 목록은 그 기능이 켜져 있을 때만 읽는다(꺼졌으면 id 원문). 기능 독립: 채팅·정의가 꺼져도 실행 화면은 동작한다.
  const agentsOn = useRequires(LOOKUP_REQUIRES.agents).phase === "met";
  const graphsOn = useRequires(LOOKUP_REQUIRES.graphs).phase === "met";
  const conversationsOn = useRequires(LOOKUP_REQUIRES.conversations).phase === "met";
  const { space } = useApi();
  const projects = useProjects();
  // 프로젝트 구성 실행도 이름을 풀 수 있게 등록된 프로젝트 공간의 구성 목록도 읽는다(대화상자와 같은 질의 키).
  const spaceIds = useMemo(() => projects.views.map((v) => v.project.id), [projects.views]);
  const spaceGraphData = useQueries({
    queries: spaceIds.map((pid) => ({
      queryKey: ["list", "graphs", "space", pid] as const,
      queryFn: () => space(pid).listGraphs(),
      enabled: graphsOn,
      retry: false,
      meta: { silentBackgroundError: true },
    })),
    combine: (results) => results.map((r) => r.data),
  });
  const agents = useApiQuery(queryKeys.list("agents"), loadAgents, { enabled: agentsOn });
  const graphs = useApiQuery(queryKeys.list("graphs"), loadGraphs, { enabled: graphsOn });
  const conversations = useApiQuery(queryKeys.list("conversations", { archived: false }), loadConversations, { enabled: conversationsOn });
  const nodeTypes = useApiQuery(queryKeys.descriptors("node-types"), loadNodeTypes);
  const edgeTypes = useApiQuery(queryKeys.descriptors("edge-types"), loadEdgeTypes);
  const kinds = useApiQuery(queryKeys.descriptors("interaction-kinds"), loadKinds);
  return useMemo(() => {
    const a = agents.data ?? EMPTY;
    const library = graphs.data ?? EMPTY;
    const byProject = new Map<string, readonly GraphSummary[]>();
    spaceIds.forEach((pid, i) => byProject.set(pid, spaceGraphData[i] ?? EMPTY));
    const seen = new Set(library.map((x) => x.id));
    const g: GraphSummary[] = [...library];
    for (const list of byProject.values()) {
      for (const x of list) {
        if (seen.has(x.id)) continue;
        seen.add(x.id);
        g.push(x);
      }
    }
    const c = conversations.data ?? EMPTY;
    const e = edgeTypes.data ?? EMPTY;
    const k = kinds.data ?? EMPTY;
    return {
      agents: a,
      graphs: g,
      conversations: c,
      nodeTypes: nodeTypes.data ?? EMPTY,
      edgeTypes: e,
      interactionKinds: k,
      agentName: (id) => (id === null || id === undefined || id === "" ? "" : (a.find((x) => x.id === id)?.name ?? id)),
      graphName: (id, projectId) => {
        const own = projectId === null || projectId === undefined ? undefined : byProject.get(projectId)?.find((x) => x.id === id)?.name;
        return own ?? library.find((x) => x.id === id)?.name ?? g.find((x) => x.id === id)?.name;
      },
      conversationTitle: (id) => (id === null || id === undefined ? undefined : c.find((x) => x.id === id)?.title),
      edgeTitle: (kind) => (kind === null || kind === undefined ? undefined : (e.find((x) => x.id === kind)?.title ?? kind)),
      edgeIcon: (kind) => (kind === null || kind === undefined ? undefined : (e.find((x) => x.id === kind)?.ui_hints?.icon ?? undefined)),
      kindOf: (id) => k.find((x) => x.id === id),
    };
  }, [agents.data, graphs.data, spaceIds, spaceGraphData, conversations.data, nodeTypes.data, edgeTypes.data, kinds.data]);
}
