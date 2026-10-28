/**
 * 메모리 화면이 이름을 풀 때 쓰는 앱 층 데이터: 프로젝트 전환기 값, 프로젝트에서 보이는 팀 구성 id,
 * 맥락 필드(`graph_id`·`project_id`·`agent_id`) → 이름 풀이, 쓴 주체의 에이전트 이름 풀이.
 * 정의 목록 역할이 꺼져 있으면 해당 풀이기를 주지 않는다(모르면 "삭제됨"이라고 단정하지 않는다).
 */
import { useMemo } from "react";
import { KNOWN_MEMORY_CONTEXT_FIELDS } from "@agent-console/contracts/constants";
import type { FormatAuthorOptions, NameResolution, ScopeNameResolvers } from "@agent-console/memory-view";
import { queryKeys, useApiQuery } from "../../app/queries";
import { LOOKUP_REQUIRES } from "../../app/requirements";
import { useRequires } from "../../modules";
import { useProjects } from "../projects";

const NAME_FIELDS = { agent: "agent_id" } as const;

function resolver(names: ReadonlyMap<string, string> | undefined): ((id: string) => NameResolution) | undefined {
  if (names === undefined) return undefined;
  return (id) => {
    const name = names.get(id);
    return name === undefined ? { status: "deleted" } : { status: "named", name };
  };
}

export interface MemoryContext {
  /** 프로젝트 전환기 값. null = 모든 프로젝트이거나 프로젝트 기능이 꺼져 있음 */
  project: string | null;
  projectName: string | null;
  /** 현재 프로젝트에서 보이는 팀 구성 id */
  graphIds: readonly string[];
  resolvers: ScopeNameResolvers;
  authorOptions: FormatAuthorOptions;
  /** 새 항목의 범위 id를 정의 목록에서 고르는 보조 선택지(맥락 필드 이름 → [id, 이름]). 목록 역할이 없으면 비어 있음 */
  pickers: Readonly<Record<string, readonly (readonly [string, string])[]>>;
}

export function useMemoryContext(): MemoryContext {
  const projects = useProjects();
  // 이름 풀이용 목록은 그 기능이 켜져 있을 때만 읽는다(꺼졌으면 풀이기를 주지 않아 id 원문이 보이고 "삭제됨"이라고 단정하지 않는다).
  const graphsOn = useRequires(LOOKUP_REQUIRES.graphs).phase === "met";
  const agentsOn = useRequires(LOOKUP_REQUIRES.agents).phase === "met";
  const graphs = useApiQuery(queryKeys.list("graphs"), (rest) => rest.listGraphs(), { enabled: graphsOn, meta: { silentBackgroundError: true } });
  const agents = useApiQuery(queryKeys.list("agents"), (rest) => rest.listAgents(), { enabled: agentsOn, meta: { silentBackgroundError: true } });

  const project = projects.enabled ? projects.current : null;
  const graphList = graphs.data;
  const visibleGraphs = useMemo(() => (graphList === undefined ? [] : projects.filter(graphList, (g) => g.project)), [graphList, projects]);
  const graphIds = useMemo(() => visibleGraphs.map((g) => g.id), [visibleGraphs]);

  const graphNames = useMemo(() => (graphList === undefined ? undefined : new Map(graphList.map((g) => [g.id, g.name] as const))), [graphList]);
  const agentNames = useMemo(() => (agents.data === undefined ? undefined : new Map(agents.data.map((a) => [a.id, a.name] as const))), [agents.data]);
  const projectNames = projects.enabled && !projects.loading ? projects.names : undefined;

  const resolvers = useMemo<ScopeNameResolvers>(() => {
    const out: Record<string, (id: string) => NameResolution> = {};
    const g = resolver(graphNames);
    if (g) out[KNOWN_MEMORY_CONTEXT_FIELDS.GRAPH_ID] = g;
    const p = resolver(projectNames);
    if (p) out[KNOWN_MEMORY_CONTEXT_FIELDS.PROJECT_ID] = p;
    const a = resolver(agentNames);
    if (a) out[NAME_FIELDS.agent] = a;
    return out;
  }, [graphNames, projectNames, agentNames]);

  const authorOptions = useMemo<FormatAuthorOptions>(() => {
    const resolveAgent = resolver(agentNames);
    return resolveAgent === undefined ? {} : { resolveAgent };
  }, [agentNames]);

  const pickers = useMemo(() => {
    const out: Record<string, readonly (readonly [string, string])[]> = {};
    if (graphList !== undefined) out[KNOWN_MEMORY_CONTEXT_FIELDS.GRAPH_ID] = visibleGraphs.map((g) => [g.id, g.name] as const);
    if (projects.enabled) out[KNOWN_MEMORY_CONTEXT_FIELDS.PROJECT_ID] = projects.projects.map((p) => [p.id, p.name] as const);
    return out;
  }, [graphList, visibleGraphs, projects.enabled, projects.projects]);

  return { project, projectName: project === null ? null : (projects.names.get(project) ?? project), graphIds, resolvers, authorOptions, pickers };
}
