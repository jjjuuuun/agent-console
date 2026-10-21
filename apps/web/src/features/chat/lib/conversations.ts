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

/** 제목 부분 일치(대소문자 무시)와 보관 포함 여부로 거른다. */
export function filterConversations(list: readonly ConversationSummary[], opts: { query: string; includeArchived: boolean }): ConversationSummary[] {
  const q = opts.query.trim().toLowerCase();
  return list.filter((c) => (opts.includeArchived || !c.archived) && (q === "" || (c.title ?? "").toLowerCase().includes(q)));
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
