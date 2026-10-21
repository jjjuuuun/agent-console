import type { NodeRun } from "@agent-console/contracts";
import { delegationMessages as dm, displayNumber, formatRunOrdinal } from "../delegation";

/**
 * 한 노드의 여러 실행(NodeRun: 회차·호출·시도) 다루기. 순수 함수이며 서버 값(0부터)을 그대로 받는다.
 * 화면 번호(+1)는 `formatRunOrdinal` 한 곳에서만 바꾼다.
 */

/** 한 노드 안에서 NodeRun을 가르는 키(시도:회차:호출). 사용자가 고른 실행을 기억하는 데 쓴다. */
export function nodeRunKey(n: Pick<NodeRun, "attempt" | "iteration" | "call">): string {
  return `${n.attempt ?? 1}:${n.iteration ?? 0}:${n.call ?? 0}`;
}

/** 시간 순서(오래된 것 먼저). 시작 전(`started_at` 없음)은 가장 최신으로 본다. 같으면 회차 → 호출 → 시도. */
export function compareNodeRuns(a: NodeRun, b: NodeRun): number {
  const as = a.started_at ?? Number.POSITIVE_INFINITY;
  const bs = b.started_at ?? Number.POSITIVE_INFINITY;
  if (as !== bs) return as < bs ? -1 : 1;
  return (a.iteration ?? 0) - (b.iteration ?? 0) || (a.call ?? 0) - (b.call ?? 0) || (a.attempt ?? 1) - (b.attempt ?? 1);
}

/** 노드별 실행 목록(오래된 것 위). */
export function groupNodeRuns(nodeRuns: readonly NodeRun[]): Map<string, NodeRun[]> {
  const map = new Map<string, NodeRun[]>();
  for (const n of nodeRuns) {
    const list = map.get(n.node_id);
    if (list === undefined) map.set(n.node_id, [n]);
    else list.push(n);
  }
  for (const list of map.values()) list.sort(compareNodeRuns);
  return map;
}

export interface VisibleRun {
  run: NodeRun;
  /** 목록 안 위치(0부터) */
  index: number;
  /** 사용자가 골랐는가(아니면 최신을 따라간다) */
  picked: boolean;
}

/** 보이는 실행: 사용자가 고른 실행이 있으면 그것, 없으면 최신. 고른 실행이 사라졌으면 최신. */
export function visibleRun(list: readonly NodeRun[], pickedKey: string | undefined): VisibleRun | undefined {
  if (list.length === 0) return undefined;
  if (pickedKey !== undefined) {
    const at = list.findIndex((n) => nodeRunKey(n) === pickedKey);
    if (at >= 0) return { run: list[at]!, index: at, picked: true };
  }
  return { run: list[list.length - 1]!, index: list.length - 1, picked: false };
}

/** 노드별 보이는 실행 표. */
export function visibleRuns(groups: ReadonlyMap<string, NodeRun[]>, picks: Readonly<Record<string, string>>): Map<string, VisibleRun> {
  const out = new Map<string, VisibleRun>();
  for (const [node, list] of groups) {
    const v = visibleRun(list, picks[node]);
    if (v !== undefined) out.set(node, v);
  }
  return out;
}

const distinct = (list: readonly NodeRun[], pick: (n: NodeRun) => number): number => new Set(list.map(pick)).size;

/** 이 노드의 실행이 회차로 갈리는가 / 호출로 갈리는가. */
export function runDimensions(list: readonly NodeRun[]): { iterations: boolean; calls: boolean } {
  return { iterations: distinct(list, (n) => n.iteration ?? 0) > 1, calls: distinct(list, (n) => n.call ?? 0) > 1 };
}

/** "실행" 열 문구: 회차만 `N회차`, 호출만 `호출 N`, 둘 다 `A회차 · 호출 B`, 시도가 1보다 크면 뒤에 `· 시도 N`. 갈리는 축이 없으면 시도 번호. */
export function runOrdinalText(run: NodeRun, list: readonly NodeRun[]): string {
  const { iterations, calls } = runDimensions(list);
  const parts: string[] = [];
  if (iterations) parts.push(formatRunOrdinal(run.iteration ?? 0, "iteration"));
  if (calls) parts.push(formatRunOrdinal(run.call ?? 0, "call"));
  if ((run.attempt ?? 1) > 1 || parts.length === 0) parts.push(dm.run.attempt(run.attempt ?? 1));
  return parts.join(" · ");
}

export interface RunBadgeText {
  text: string;
  ariaLabel: string;
  picked: boolean;
}

/**
 * 그래프 노드의 회차·호출 배지(실행이 2개 이상일 때만): 회차만 `#3`, 호출만 `×4`(호출 수), 둘 다 `#3 · ×2`.
 * 번호는 보이는 실행 기준이고 화면 값은 +1이다. 접근성 이름에 노드·실행 위치·상태가 들어간다.
 */
export function runBadge(list: readonly NodeRun[], v: VisibleRun, nodeLabel: string, statusLabel: string): RunBadgeText | undefined {
  if (list.length < 2) return undefined;
  const { iterations, calls } = runDimensions(list);
  const text: string[] = [];
  const aria: string[] = [];
  if (iterations) {
    text.push(`#${displayNumber(v.run.iteration ?? 0)}`);
    aria.push(formatRunOrdinal(v.run.iteration ?? 0, "iteration"));
  }
  if (calls) {
    text.push(`×${distinct(list, (n) => n.call ?? 0)}`);
    aria.push(`${formatRunOrdinal(v.run.call ?? 0, "call")}번째`);
  }
  if (text.length === 0) {
    text.push(`#${v.run.attempt ?? 1}`);
    aria.push(dm.run.attempt(v.run.attempt ?? 1));
  }
  return { text: text.join(" · "), ariaLabel: dm.run.badgeAria(nodeLabel, aria.join(", "), statusLabel, list.length, v.index + 1, v.picked), picked: v.picked };
}
