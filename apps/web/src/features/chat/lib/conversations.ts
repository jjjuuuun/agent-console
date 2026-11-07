import type { ConversationSummary } from "@agent-console/contracts";
import { CHAT_SORT_MODES, resolveChatSort } from "../../../lib/chatSort";

/** 대화별 가장 오래 기다린 응답 대기의 시작 시각(epoch 초). */
export type PendingSince = ReadonlyMap<string, number>;

type Compare = (a: ConversationSummary, b: ConversationSummary, since: PendingSince) => number;

const byUpdated: Compare = (a, b) => b.updated_at - a.updated_at;

/** 정렬 방식 id → 비교 함수. 새 방식은 `CHAT_SORT_MODES`에 한 줄을 더하고 여기에 비교 함수를 더한다. */
const COMPARATORS: Record<string, Compare> = {
  pending_first: (a, b, since) => {
    const pa = isWaiting(a, since);
    const pb = isWaiting(b, since);
    if (pa !== pb) return pa ? -1 : 1;
    if (pa && pb) return (since.get(a.id) ?? a.updated_at) - (since.get(b.id) ?? b.updated_at);
    return byUpdated(a, b, since);
  },
  updated: byUpdated,
};

/** 응답 대기 중인 대화인가(요약의 개수 또는 대기 목록 중 하나라도). */
export function isWaiting(c: ConversationSummary, since: PendingSince): boolean {
  return (c.pending_interactions ?? 0) > 0 || since.has(c.id);
}

/** `chat.list_sort` 값으로 정렬한 새 배열. 비었거나 모르는 값은 기본(첫 방식). */
export function sortConversations(list: readonly ConversationSummary[], sortValue: string | null | undefined, since: PendingSince = new Map()): ConversationSummary[] {
  const mode = resolveChatSort(sortValue);
  const compare = COMPARATORS[mode.id] ?? COMPARATORS[CHAT_SORT_MODES[0]!.id] ?? byUpdated;
  return [...list].sort((a, b) => compare(a, b, since));
}

/** 요약 갱신을 목록에 반영(있으면 교체, 없으면 앞에 추가). */
export function upsertConversation(list: readonly ConversationSummary[], next: ConversationSummary): ConversationSummary[] {
  return list.some((c) => c.id === next.id) ? list.map((c) => (c.id === next.id ? next : c)) : [next, ...list];
}

/** 팀 구성별 마지막 사용 시각(그 팀의 대화 중 가장 최근 갱신). */
export function lastUsedByGraph(list: readonly ConversationSummary[]): ReadonlyMap<string, number> {
  const out = new Map<string, number>();
  for (const c of list) out.set(c.graph_id, Math.max(out.get(c.graph_id) ?? 0, c.updated_at));
  return out;
}

/** 대기 목록(전역 토픽)에서 대화별 가장 오래된 대기 시작 시각. */
export function pendingSinceOf(items: readonly { conversation_id?: string | null; created_at: number }[]): PendingSince {
  const out = new Map<string, number>();
  for (const i of items) {
    if (i.conversation_id == null) continue;
    out.set(i.conversation_id, Math.min(out.get(i.conversation_id) ?? Infinity, i.created_at));
  }
  return out;
}

/**
 * 질의 캐시 한 항목에 요약 갱신을 반영한다. 배열 목록(`upsertConversation`)과 커서 페이지 목록(`{ pages }`)을 모두 다룬다.
 * 페이지 목록은 있던 자리에서 교체하고, 어느 페이지에도 없으면 첫 페이지 앞에 넣는다. 그 밖의 모양은 그대로 둔다.
 */
export function patchConversationCache<T>(cur: T, next: ConversationSummary): T {
  if (Array.isArray(cur)) return upsertConversation(cur as ConversationSummary[], next) as T;
  const data = cur as { pages?: { items?: readonly ConversationSummary[] }[] } | undefined;
  if (data === undefined || data === null || !Array.isArray(data.pages)) return cur;
  const has = data.pages.some((p) => p.items?.some((c) => c.id === next.id));
  const pages = data.pages.map((p, i) => {
    const items = p.items ?? [];
    if (has) return items.some((c) => c.id === next.id) ? { ...p, items: items.map((c) => (c.id === next.id ? next : c)) } : p;
    return i === 0 ? { ...p, items: [next, ...items] } : p;
  });
  return { ...data, pages } as T;
}
