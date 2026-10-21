import { useMemo } from "react";
import type { Agent, ConversationSummary, EdgeTypeDescriptor, GraphSummary, InteractionKindDescriptor, NodeTypeDescriptor } from "@agent-console/contracts";
import { queryKeys, useApiQuery } from "../../app/queries";
import type { RestClient } from "@agent-console/api-client";
import { LOOKUP_REQUIRES } from "../../app/requirements";
import { useRequires } from "../../modules";

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
  graphName(id: string): string | undefined;
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
  const agents = useApiQuery(queryKeys.list("agents"), loadAgents, { enabled: agentsOn });
  const graphs = useApiQuery(queryKeys.list("graphs"), loadGraphs, { enabled: graphsOn });
  const conversations = useApiQuery(queryKeys.list("conversations", { archived: false }), loadConversations, { enabled: conversationsOn });
  const nodeTypes = useApiQuery(queryKeys.descriptors("node-types"), loadNodeTypes);
  const edgeTypes = useApiQuery(queryKeys.descriptors("edge-types"), loadEdgeTypes);
  const kinds = useApiQuery(queryKeys.descriptors("interaction-kinds"), loadKinds);
  return useMemo(() => {
    const a = agents.data ?? EMPTY;
    const g = graphs.data ?? EMPTY;
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
      graphName: (id) => g.find((x) => x.id === id)?.name,
      conversationTitle: (id) => (id === null || id === undefined ? undefined : c.find((x) => x.id === id)?.title),
      edgeTitle: (kind) => (kind === null || kind === undefined ? undefined : (e.find((x) => x.id === kind)?.title ?? kind)),
      edgeIcon: (kind) => (kind === null || kind === undefined ? undefined : (e.find((x) => x.id === kind)?.ui_hints?.icon ?? undefined)),
      kindOf: (id) => k.find((x) => x.id === id),
    };
  }, [agents.data, graphs.data, conversations.data, nodeTypes.data, edgeTypes.data, kinds.data]);
}
