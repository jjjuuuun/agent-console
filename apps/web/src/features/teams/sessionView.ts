/**
 * 팀 구성 편집기의 세션 구분 표시 계산(순수 함수, screen-delegation.md §14.4). 방식·연결 종류 id를 비교하지 않고
 * 디스크립터의 `session`·`opens_session` 속성과 연결 구조만 본다. 속성이 없으면 아무것도 만들지 않는다.
 */
import type { DelegationStrategyDescriptor, EdgeSpec, EdgeTypeDescriptor, Graph, NodeTypeDescriptor } from "@agent-console/contracts";
import { KNOWN_DELEGATION_SESSIONS as SESSIONS } from "@agent-console/contracts/constants";
import type { ChipView } from "@agent-console/graph-editor";
import { edgeSessionOf, effectiveStrategyId, sessionChipView, type StrategyAttributeSource } from "../delegation";
import { teamMessages } from "./messages";
import { descriptorOf, edgeKindOf, edgesOf, nodeLabel, nodesOf } from "./teamsLogic";

const m = teamMessages.sessions;
type Strategy = Pick<DelegationStrategyDescriptor, "id"> & StrategyAttributeSource;

/** 연결 id → 세션 값(값이 있는 연결만). */
export function edgeSessionMap(graph: Pick<Graph, "edges">, edgeTypes: readonly EdgeTypeDescriptor[], strategies: readonly Strategy[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const edge of graph.edges ?? []) {
    const v = edgeSessionOf(edge, edgeKindOf(edge, edgeTypes), strategies);
    if (v !== undefined) out[edge.id] = v;
  }
  return out;
}

/**
 * 편집기 `edgeLeadChips`: 세션 값이 있는 연결마다 세션 칩. 그래프의 모든 값이 같으면 아이콘만(균일 축약),
 * 하나라도 다른 값이 생기면 글자 칩으로 돌아간다.
 */
export function edgeLeadChips(graph: Graph, edgeTypes: readonly EdgeTypeDescriptor[], strategies: readonly Strategy[]): Record<string, ChipView> {
  const sessions = edgeSessionMap(graph, edgeTypes, strategies);
  const values = new Set(Object.values(sessions));
  const uniform = values.size <= 1;
  const labels = new Map(nodesOf(graph).map((n) => [n.id, nodeLabel(n)]));
  const out: Record<string, ChipView> = {};
  for (const edge of edgesOf(graph)) {
    const v = sessions[edge.id];
    if (v === undefined) continue;
    const chip = sessionChipView(v, { delegatorLabel: labels.get(edge.source.node) ?? edge.source.node, iconOnly: uniform });
    if (chip !== undefined) out[edge.id] = chip;
  }
  return out;
}

export interface IncomingSession {
  edge: EdgeSpec;
  delegatorId: string;
  delegatorLabel: string;
  session: string;
  /** 이 연결의 유효 방식 id(위임 연결) */
  strategyId: string | undefined;
}

/** 노드로 들어오는 위임 연결 중 세션 값이 있는 것(위임 연결 = 종류의 `invocation`). */
export function incomingSessions(nodeId: string, graph: Graph, edgeTypes: readonly EdgeTypeDescriptor[], strategies: readonly Strategy[]): IncomingSession[] {
  const labels = new Map(nodesOf(graph).map((n) => [n.id, nodeLabel(n)]));
  const out: IncomingSession[] = [];
  for (const edge of edgesOf(graph)) {
    if (edge.target.node !== nodeId) continue;
    const kind = edgeKindOf(edge, edgeTypes);
    if (kind?.invocation == null) continue;
    const session = edgeSessionOf(edge, kind, strategies);
    if (session !== undefined) out.push({ edge, delegatorId: edge.source.node, delegatorLabel: labels.get(edge.source.node) ?? edge.source.node, session, strategyId: effectiveStrategyId(edge, kind) });
  }
  return out;
}

export type NodeSessionMode =
  | { mode: "none" }
  | { mode: "same"; delegators: string[]; edgeId: string; delegatorId: string; strategyId: string | undefined }
  | { mode: "mixed"; count: number; items: IncomingSession[] };

/** 노드 카드 칩·노드 패널 첫 줄이 쓰는 판정: 모두 같은 세션 / 섞임 / 해당 없음(별도뿐이면 칩 없음). */
export function nodeSessionMode(items: readonly IncomingSession[]): NodeSessionMode {
  const same = items.filter((i) => i.session === SESSIONS.SAME);
  if (same.length === 0) return { mode: "none" };
  if (same.length < items.length) return { mode: "mixed", count: items.length, items: [...items] };
  return { mode: "same", delegators: [...new Set(same.map((i) => i.delegatorLabel))], edgeId: same[0]!.edge.id, delegatorId: same[0]!.delegatorId, strategyId: same[0]!.strategyId };
}

/** 노드 카드 맨 아래 칩 문구. */
export function sessionFootText(mode: NodeSessionMode): { title: string; full: string } | undefined {
  if (mode.mode === "none") return undefined;
  if (mode.mode === "mixed") return { title: m.nodeMany(mode.count), full: m.nodeMany(mode.count) };
  const first = mode.delegators[0] ?? "";
  const text = mode.delegators.length > 1 ? m.nodeInsideMore(first, mode.delegators.length - 1) : m.nodeInside(first);
  return { title: text, full: text };
}

/** 편집기 `nodeAnnotations`: 같은 세션 위임 대상 노드에 `{위임자} 세션 안` 칩(별도 세션 대상에는 달지 않는다). */
export function nodeFootAnnotations(graph: Graph, edgeTypes: readonly EdgeTypeDescriptor[], strategies: readonly Strategy[]): Record<string, { foot: ChipView }> {
  const out: Record<string, { foot: ChipView }> = {};
  for (const node of nodesOf(graph)) {
    const text = sessionFootText(nodeSessionMode(incomingSessions(node.id, graph, edgeTypes, strategies)));
    if (text !== undefined) out[node.id] = { foot: { key: "session-in", title: text.title, fullTitle: text.full, iconName: "corner-down-right", tone: "neutral" } };
  }
  return out;
}

/**
 * 팀 개요 요약 `별도 세션 N · 같은 세션 안 M`. 집계 대상 = `opens_session`이 false가 아니고 세션 값이 있는 연결에 한 번이라도 닿은 노드.
 * M = 들어오는 위임 연결이 모두 같은 세션인 노드, N = 나머지. 세션 값이 있는 연결이 없으면 undefined(요약을 숨긴다).
 */
export function sessionSummary(graph: Graph, nodeTypes: readonly NodeTypeDescriptor[], edgeTypes: readonly EdgeTypeDescriptor[], strategies: readonly Strategy[]): { separate: number; same: number } | undefined {
  const sessions = edgeSessionMap(graph, edgeTypes, strategies);
  const touched = new Set<string>();
  for (const edge of edgesOf(graph)) {
    if (sessions[edge.id] === undefined) continue;
    touched.add(edge.source.node);
    touched.add(edge.target.node);
  }
  if (touched.size === 0) return undefined;
  let same = 0;
  let separate = 0;
  for (const node of nodesOf(graph)) {
    if (!touched.has(node.id)) continue;
    if (descriptorOf(node, nodeTypes)?.opens_session === false) continue;
    if (nodeSessionMode(incomingSessions(node.id, graph, edgeTypes, strategies)).mode === "same") same += 1;
    else separate += 1;
  }
  return { separate, same };
}

/** 서버 목록 요약(`GraphSummary.session_summary`)을 `{separate, same}`으로. null·없음이면 undefined(요약을 숨긴다). */
export function summaryFromServer(summary: { nodes: number; delegated?: Record<string, number> } | null | undefined): { separate: number; same: number } | undefined {
  if (summary == null) return undefined;
  const same = summary.delegated?.[SESSIONS.SAME] ?? 0;
  return { separate: Math.max(0, summary.nodes - same), same };
}
