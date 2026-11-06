/**
 * 실행 상세 그래프에 얹는 세션 표시 계산(순수 함수, screen-delegation.md §14.5.2): 노드 왼쪽 띠·`S{n}` 표식·`서브 m` 표식,
 * 같은 세션 위임 대상(NodeRun 없음)의 `↳ {위임자} 세션 안 · S{n}` 칩과 `대기(호출 전)` 글자. 방식·연결 종류 id는 쓰지 않고 `session` 속성만 본다.
 */
import type { DelegationStrategyDescriptor, EdgeTypeDescriptor, Graph } from "@agent-console/contracts";
import { KNOWN_DELEGATION_SESSIONS as SESSIONS } from "@agent-console/contracts/constants";
import type { NodeAnnotation } from "@agent-console/graph-editor";
import { edgeSessionOf } from "../delegation";
import { runsMessages as t } from "./messages";
import type { RunSessions } from "./runSessions";

export interface SessionAnnotationInput {
  graph: Pick<Graph, "nodes" | "edges"> | undefined;
  edgeTypes: readonly EdgeTypeDescriptor[];
  strategies: readonly DelegationStrategyDescriptor[];
  sessions: RunSessions;
  nodeLabel(nodeId: string): string;
  /** 강조 중인 세션 id(그 세션의 노드는 윤곽, 나머지는 흐리게) */
  selectedSessionId: string | null;
  /** 이미 호출이 있었던 노드(서브에이전트 호출 수 > 0) */
  calledNodes: ReadonlySet<string>;
  /** `서브 m` 표식을 누르면 */
  onOpenSubs(nodeId: string): void;
}

export function buildSessionAnnotations(i: SessionAnnotationInput): Record<string, NodeAnnotation> {
  const out: Record<string, NodeAnnotation> = {};
  const { sessions } = i;
  const selected = i.selectedSessionId === null ? undefined : sessions.byId.get(i.selectedSessionId);
  const kinds = new Map(i.edgeTypes.map((k) => [k.id, k]));
  const set = (id: string, patch: NodeAnnotation) => {
    out[id] = { ...(out[id] ?? {}), ...patch };
  };
  for (const node of i.graph?.nodes ?? []) {
    const s = sessions.byNode.get(node.id);
    const sub = sessions.subByDelegator[node.id] ?? 0;
    if (s !== undefined) {
      set(node.id, {
        stripColor: s.color,
        lead: { key: "session", text: t.sessions.badge(s.number), ariaLabel: t.sessions.badgeAria(s.number, s.name), dotColor: s.color },
      });
    }
    if (sub > 0) {
      const tag = { key: "sub", text: t.sessions.subBadge(sub), ariaLabel: t.sessions.subBadgeAria(sub), pulse: sessions.subRunning.has(node.id), onClick: () => i.onOpenSubs(node.id) };
      set(node.id, { tags: [tag] });
    }
    if (selected !== undefined) set(node.id, { emphasis: s?.id === selected.id ? "on" : "dim" });
  }
  // 같은 세션 위임 대상: 자기 세션이 없고(NodeRun 없음) 들어오는 위임 연결의 세션이 같은 세션인 노드
  for (const edge of i.graph?.edges ?? []) {
    const kind = kinds.get(edge.kind);
    if (kind?.invocation == null) continue;
    if (edgeSessionOf(edge, kind, i.strategies) !== SESSIONS.SAME) continue;
    const target = edge.target.node;
    if (sessions.byNode.has(target)) continue;
    const delegator = edge.source.node;
    const base = t.sessions.nodeInside(i.nodeLabel(delegator), sessions.byNode.get(delegator)?.number);
    const title = i.calledNodes.has(target) ? base : `${base} · ${t.sessions.notCalledYet}`;
    set(target, { foot: { key: "session-in", title, fullTitle: title, iconName: "corner-down-right", tone: "neutral" } });
  }
  return out;
}
