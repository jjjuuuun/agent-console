import type { EdgeTypeDescriptor, Graph, NodeRun, NodeTypeDescriptor, Run } from "@agent-console/contracts";
import type { BindSummary, EdgeBadge } from "@agent-console/graph-editor";
import { delegationMessages as dm, formatRunOrdinal, stringAt } from "../delegation";
import type { RunOverlay } from "./runsLib";
import { siblingIndex } from "./runTree";

/** 실행 상세 그래프에 얹는 반복·조건·실패 처리·중첩 팀 표시 계산(순수 함수). 판정은 디스크립터 속성(`cycle`)과 이벤트 결과(`RunOverlay`)로만 한다. */

/** 연결 배지: 반복 연결 통과 횟수 `↻×k`, 한도 도달 `↻×k 한도 m회 도달`(warning), 조건이 맞지 않아 건너뜀 `✕`. 종류 패턴은 건드리지 않는다. */
export function buildEdgeBadges(graph: Pick<Graph, "edges"> | undefined, edgeTypes: readonly EdgeTypeDescriptor[], overlay: Pick<RunOverlay, "edgeTraversals" | "exhausted" | "conditionSkipped">): Record<string, EdgeBadge[]> {
  const kinds = new Map(edgeTypes.map((e) => [e.id, e]));
  const out: Record<string, EdgeBadge[]> = {};
  for (const edge of graph?.edges ?? []) {
    const badges: EdgeBadge[] = [];
    const k = overlay.edgeTraversals[edge.id] ?? 0;
    const cycle = kinds.get(edge.kind)?.cycle != null;
    const hasExhausted = edge.id in overlay.exhausted;
    if (cycle && (k > 0 || hasExhausted)) {
      const max = overlay.exhausted[edge.id];
      if (hasExhausted && max !== undefined) badges.push({ text: dm.run.exhaustedBadge(k, max), ariaLabel: dm.run.exhaustedAria(k, max), tone: "warning" });
      else if (hasExhausted) badges.push({ text: `${dm.run.loopBadge(k)} ▲`, ariaLabel: dm.run.judgement.exhaustedNoLimit, tone: "warning" });
      else badges.push({ text: dm.run.loopBadge(k), ariaLabel: dm.run.loopBadgeAria(k), tone: "neutral" });
    }
    if (overlay.conditionSkipped[edge.id] === true) badges.push({ text: "✕", ariaLabel: dm.run.judgement.conditionFalse, tone: "neutral" });
    if (badges.length > 0) out[edge.id] = badges;
  }
  return out;
}

/** 한도 도달 줄: 출발 노드 카드 아래 "반복 한도에 도달했습니다 (한도 m회)". 노드 id → 문구. */
export function exhaustedLines(graph: Pick<Graph, "edges"> | undefined, overlay: Pick<RunOverlay, "exhausted">): Record<string, string> {
  const out: Record<string, string> = {};
  for (const edge of graph?.edges ?? []) {
    if (!(edge.id in overlay.exhausted)) continue;
    const max = overlay.exhausted[edge.id];
    out[edge.source.node] = max === undefined ? dm.run.judgement.exhaustedNoLimit : dm.run.exhaustedLine(max);
  }
  return out;
}

export interface ChildForNode {
  /** 보이는 실행에 대응하는 자식 Run. 대응이 모호하면 undefined */
  child: Run | undefined;
  /** 이 노드가 만든 모든 자식 Run */
  all: Run[];
  ambiguous: boolean;
}

/**
 * 노드의 보이는 실행에 속한 자식 Run. NodeRun ↔ 자식 Run 대응은 `parent_node_id`와 시간 순서다.
 * 노드의 NodeRun 수와 자식 수가 같으면 순서대로 짝짓고, 다르면 모호하다(모든 자식을 목록으로 보인다).
 */
export function childForNodeRun(nodeId: string, runs: readonly NodeRun[], visibleIndex: number, children: readonly Run[]): ChildForNode {
  const all = children.filter((c) => c.parent_node_id === nodeId).sort((a, b) => a.created_at - b.created_at);
  if (all.length === 0) return { child: undefined, all, ambiguous: false };
  if (all.length === 1 && runs.length <= 1) return { child: all[0], all, ambiguous: false };
  if (all.length === runs.length) return { child: all[visibleIndex], all, ambiguous: false };
  return { child: undefined, all, ambiguous: true };
}

export interface NestedSummaryInput {
  nodes: Graph["nodes"];
  nodeTypes: readonly NodeTypeDescriptor[];
  /** 지금 화면의 정의 종류(`binds.kind`와 비교만 한다) */
  currentKind: string | undefined;
  children: readonly Run[];
  nodeRunsOf(nodeId: string): readonly NodeRun[];
  visibleIndexOf(nodeId: string): number;
  teamName(graphId: string): string;
  statusLabel(status: string): string;
  shortId(id: string): string;
  onOpen(runId: string): void;
}

/** 중첩 노드 카드에 얹는 자식 실행 한 줄(`자식 실행 r-7c1b · 실행 중` + [열기 ↗]). 자식이 없으면 요약을 만들지 않는다. */
export function nestedRunSummaries(i: NestedSummaryInput): Record<string, BindSummary> {
  const types = new Map(i.nodeTypes.map((n) => [n.id, n]));
  const out: Record<string, BindSummary> = {};
  for (const node of i.nodes ?? []) {
    const binds = types.get(node.type)?.binds;
    if (binds == null || i.currentKind === undefined || binds.kind !== i.currentKind) continue;
    const { child, all, ambiguous } = childForNodeRun(node.id, i.nodeRunsOf(node.id), i.visibleIndexOf(node.id), i.children);
    const ref = stringAt(node.config, `/${binds.field}`);
    if (all.length === 0) continue;
    if (child === undefined && ambiguous) {
      out[node.id] = { title: node.label ?? node.id, subtitle: dm.run.child.menu(all.length), meta: all.map((c) => i.shortId(c.id)).join(", ") };
      continue;
    }
    if (child === undefined) continue;
    out[node.id] = {
      title: i.teamName(child.graph_id) || ref || node.label || node.id,
      subtitle: dm.run.child.cardLine(i.shortId(child.id), i.statusLabel(child.status)),
      open: { label: dm.run.child.open, onOpen: () => i.onOpen(child.id) },
    };
  }
  return out;
}

/** 부모 노드 문구: 같은 노드에서 자식이 여럿이면 "검토 · 2회차". */
export function childNodeText(children: readonly Run[], child: Run, nodeLabel: (id: string) => string): string {
  const label = child.parent_node_id == null ? "" : nodeLabel(child.parent_node_id);
  const { index, total } = siblingIndex(children, child);
  return total > 1 ? dm.run.child.nodeIter(label, formatRunOrdinal(index, "iteration")) : label;
}
