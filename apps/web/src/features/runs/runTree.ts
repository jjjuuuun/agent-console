import type { Run } from "@agent-console/contracts";
import { isActiveRun } from "./runsLib";

/** 자식 Run(중첩 팀) 트리의 순수 계산. 시각은 epoch 초, 부모 관계는 `parent_run_id`. */

/** 루트부터 `current`까지의 체인(둘 다 포함). 끊기면(조회되지 않은 조상) 찾은 데까지 맨 위를 루트로 본다. */
export function ancestorChain(all: readonly Run[], current: Run): Run[] {
  const byId = new Map(all.map((r) => [r.id, r]));
  byId.set(current.id, current);
  const chain: Run[] = [current];
  const seen = new Set([current.id]);
  for (let cur: Run | undefined = current; cur?.parent_run_id != null; ) {
    const parent = byId.get(cur.parent_run_id);
    if (parent === undefined || seen.has(parent.id)) break;
    seen.add(parent.id);
    chain.unshift(parent);
    cur = parent;
  }
  return chain;
}

/** 직접 자식(만든 순). 서버가 `children`을 채웠으면 그것, 아니면 후손 목록에서 `parent_run_id`가 같은 것. */
export function directChildren(runId: string, snapshotChildren: readonly Run[] | null | undefined, descendants: readonly Run[]): Run[] {
  const list = snapshotChildren ?? descendants.filter((r) => r.parent_run_id === runId);
  return [...list].sort((a, b) => a.created_at - b.created_at);
}

/** 이 Run 아래(자식·손자…)의 활성 상태 Run. */
export function activeDescendants(descendants: readonly Run[], runId: string): Run[] {
  const ids = new Set<string>([runId]);
  const out: Run[] = [];
  // 부모가 먼저 나오도록 만든 순으로 훑는다
  for (const r of [...descendants].sort((a, b) => a.created_at - b.created_at)) {
    if (r.parent_run_id != null && ids.has(r.parent_run_id)) {
      ids.add(r.id);
      if (isActiveRun(r.status)) out.push(r);
    }
  }
  return out;
}

/** 직접 자식 중 실패한 수(부모가 완료여도 보조 줄에 알린다). */
export function failedChildCount(children: readonly Run[]): number {
  return children.filter((c) => c.status === "failed").length;
}

/** 같은 부모 노드에서 만든 자식 Run 중 몇 번째인가(0부터). 같은 노드에서 둘 이상일 때 "검토 · 2회차"로 보인다. */
export function siblingIndex(children: readonly Run[], child: Run): { index: number; total: number } {
  const same = children.filter((c) => c.parent_node_id === child.parent_node_id).sort((a, b) => a.created_at - b.created_at);
  return { index: Math.max(0, same.findIndex((c) => c.id === child.id)), total: same.length };
}

/** 동시 구독 상한 안에서 구독할 Run과 폴링으로 맡길 Run을 가른다(앞에서부터 상한까지 구독). */
export function splitSubscriptions(activeIds: readonly string[], limit: number): { subscribe: string[]; poll: string[] } {
  return { subscribe: activeIds.slice(0, limit), poll: activeIds.slice(limit) };
}
