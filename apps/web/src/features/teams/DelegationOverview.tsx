import { useMemo } from "react";
import type { EdgeTypeDescriptor, Graph, NodeTypeDescriptor, WorkspaceSettings } from "@agent-console/contracts";
import { delegationMessages as dm, numberAt, resolveCycleLimit, stringAt, DEFAULT_TEAM_CONVENTIONS } from "../delegation";
import type { NestedInfo } from "../delegation";
import { nodeLabel } from "./teamsLogic";

export interface DelegationOverviewProps {
  graph: Graph;
  nodeTypes: readonly NodeTypeDescriptor[];
  edgeTypes: readonly EdgeTypeDescriptor[];
  workspace: WorkspaceSettings | undefined;
  nested: { currentKind: string | undefined; infos: readonly NestedInfo[] | undefined; open: ((id: string) => void) | undefined } | undefined;
  onSelectEdge(edgeId: string, sourceNodeId: string): void;
  onSelectNode(nodeId: string): void;
}

/**
 * "개요" 탭 보강(screen-delegation.md 2.9): 반복 연결 목록(출발 → 도착, 한도 칩; 클릭하면 그 연결을 선택·이동)과 노드 실행 총량 안내,
 * 중첩된 팀 구성 목록([열기]). 반복 연결은 디스크립터 `cycle`, 중첩 노드는 `binds.kind`로 판정한다. 해당하는 것이 없으면 아무것도 그리지 않는다.
 */
export function DelegationOverview({ graph, nodeTypes, edgeTypes, workspace, nested, onSelectEdge, onSelectNode }: DelegationOverviewProps) {
  const kinds = useMemo(() => new Map(edgeTypes.map((e) => [e.id, e])), [edgeTypes]);
  const types = useMemo(() => new Map(nodeTypes.map((n) => [n.id, n])), [nodeTypes]);
  const nodes = graph.nodes ?? [];
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const loops = (graph.edges ?? []).filter((e) => kinds.get(e.kind)?.cycle != null);
  const nestedNodes = nodes.filter((n) => {
    const binds = types.get(n.type)?.binds;
    return binds != null && nested?.currentKind !== undefined && binds.kind === nested.currentKind;
  });
  if (loops.length === 0 && nestedNodes.length === 0) return null;
  const total = numberAt(graph.settings, DEFAULT_TEAM_CONVENTIONS.settingsFlowMaxNodeRuns) ?? numberAt(workspace, DEFAULT_TEAM_CONVENTIONS.settingsFlowMaxNodeRuns);
  return (
    <>
      {loops.length > 0 ? (
        <section aria-label={dm.nested.loopsTitle}>
          <span className="lib-field-label">{dm.nested.loopsTitle}</span>
          <p className="app-muted lib-field-note" role="status">{dm.nested.loopsInfo(loops.length, total)}</p>
          <ul className="team-problem-list">
            {loops.map((e) => {
              const limit = resolveCycleLimit({ edgeConfig: e.config, teamSettings: graph.settings, commonSettings: workspace, kindDefault: kinds.get(e.kind)?.cycle?.max_iterations });
              const from = byId.get(e.source.node);
              const to = byId.get(e.target.node);
              const label = dm.nested.loopRow(from ? nodeLabel(from) : e.source.node, to ? nodeLabel(to) : e.target.node);
              return (
                <li key={e.id}>
                  <button type="button" className="lib-chip" onClick={() => onSelectEdge(e.id, e.source.node)}>
                    {label}
                    <span className="app-muted"> · {limit.value === undefined ? dm.edge.cycleNoLimit : dm.edge.cycleChip(limit.value)}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}
      {nestedNodes.length > 0 ? (
        <section aria-label={dm.nested.overviewTitle}>
          <span className="lib-field-label">{dm.nested.overviewTitle}</span>
          <ul className="team-problem-list">
            {nestedNodes.map((n) => {
              const binds = types.get(n.type)!.binds!;
              const id = stringAt(n.config, `/${binds.field}`);
              const info = id === undefined ? undefined : nested?.infos?.find((x) => x.id === id);
              return (
                <li key={n.id}>
                  <button type="button" className="app-link-btn" onClick={() => onSelectNode(n.id)}>{dm.nested.overviewRow(nodeLabel(n), info?.name ?? id ?? "")}</button>{" "}
                  {nested?.open !== undefined && info !== undefined && id !== undefined ? (
                    <button type="button" className="app-link-btn" onClick={() => nested.open?.(id)}>{dm.nested.open}</button>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}
    </>
  );
}
