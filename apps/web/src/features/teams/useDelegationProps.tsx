import { useMemo, type ReactNode } from "react";
import type { DelegationStrategyDescriptor, EdgeTypeDescriptor, Graph, GraphSummary, NodeTypeDescriptor, WorkspaceSettings } from "@agent-console/contracts";
import type { BindSummary, ChipView, DefinitionItem } from "@agent-console/graph-editor";
import { CONFIG_WIDGETS, deriveAllEdgeChips, deriveBindSummaries, edgeStrategyIds, nestedDefinitionList, nestedInfoOf, useConditionOperators, useRenderIcon, type NestedInfo } from "../delegation";
import { DEFINITION_KINDS } from "../library";
import { usageCounts } from "./teamsLogic";

export interface DelegationPropsInput {
  graphId: string;
  /** 편집 중인 초안(없으면 아무것도 만들지 않는다) */
  graph: Graph | undefined;
  nodeTypes: readonly NodeTypeDescriptor[];
  edgeTypes: readonly EdgeTypeDescriptor[];
  strategies: readonly DelegationStrategyDescriptor[];
  workspace: WorkspaceSettings | undefined;
  /** 팀 구성 요약 목록(중첩 후보 이름·노드 수). 아직 못 읽었으면 undefined */
  summaries: readonly GraphSummary[] | undefined;
  /** 정의 종류(`binds.kind`) 표시 이름 표 */
  kindTitles: Readonly<Record<string, string>>;
  /** [열기]. 정의 종류 라우트를 못 찾으면 undefined(버튼 없음) */
  openNested: ((id: string) => void) | undefined;
  /** 반복 한도 칩 클릭: 그 연결을 선택하고 한도 필드로 포커스 */
  onLimitChip?: ((edgeId: string) => void) | undefined;
}

export interface DelegationProps {
  edgeExtraChips: Record<string, ChipView[]>;
  edgeStrategyIds: Record<string, string>;
  bindSummaries: Record<string, BindSummary>;
  /** 팔레트 "정의에서 만드는 노드"의 중첩 정의 목록. 키는 `binds.kind`가 지금 편집 종류인 하나 */
  nestedList: readonly DefinitionItem[] | undefined;
  nested: { currentKind: string | undefined; infos: readonly NestedInfo[] | undefined; kindTitle: string | undefined; open: ((id: string) => void) | undefined };
  renderIcon: (name: string) => ReactNode;
}

/**
 * 팀 구성 편집기에 위임·반복·조건·중첩 팀 표시를 얹는 데이터를 만든다(편집기 props로 넘길 값). 서버를 직접 부르지 않고
 * 연산자 목록·팀 요약은 호출 쪽이 읽은 값을 받는다. 종류 이름은 쓰지 않고 디스크립터 속성만 본다.
 */
export function useDelegationProps(i: DelegationPropsInput): DelegationProps {
  const ops = useConditionOperators();
  const renderIcon = useRenderIcon();
  const currentKind = DEFINITION_KINDS.graph;
  const infos = useMemo(() => (i.summaries === undefined ? undefined : nestedInfoOf(i.summaries)), [i.summaries]);
  const teamSettings = i.graph?.settings;
  const edgeExtraChips = useMemo(
    () => (i.graph === undefined ? {} : deriveAllEdgeChips(i.graph, i.edgeTypes, { strategies: i.strategies, operators: ops.operators, teamSettings, commonSettings: i.workspace, widgets: CONFIG_WIDGETS, ...(i.onLimitChip ? { onLimitChipActivate: i.onLimitChip } : {}) })),
    [i.graph, i.edgeTypes, i.strategies, ops.operators, teamSettings, i.workspace, i.onLimitChip],
  );
  const strategyIds = useMemo(() => (i.graph === undefined ? {} : edgeStrategyIds(i.graph, i.edgeTypes)), [i.graph, i.edgeTypes]);
  const kindTitle = currentKind === undefined ? undefined : i.kindTitles[currentKind];
  const bindSummaries = useMemo(
    () => (i.graph === undefined ? {} : deriveBindSummaries(i.graph.nodes ?? [], i.nodeTypes, { currentKind, currentId: i.graphId, infos, kindTitle, open: i.openNested })),
    [i.graph, i.nodeTypes, currentKind, i.graphId, infos, kindTitle, i.openNested],
  );
  const nestedList = useMemo(() => {
    if (infos === undefined || i.graph === undefined) return undefined;
    const counts = usageCounts(i.graph, i.nodeTypes);
    return nestedDefinitionList(infos, i.graphId, (id) => counts.get(`${currentKind}:${id}`) ?? 0);
  }, [infos, i.graph, i.nodeTypes, i.graphId, currentKind]);
  const nested = useMemo(() => ({ currentKind, infos, kindTitle, open: i.openNested }), [currentKind, infos, kindTitle, i.openNested]);
  return { edgeExtraChips, edgeStrategyIds: strategyIds, bindSummaries, nestedList, nested, renderIcon };
}
