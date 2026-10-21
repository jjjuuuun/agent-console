import type { ReplyDisplay, ReplyItem } from "./types";

const KNOWN: readonly ReplyDisplay[] = ["separate", "merged", "final_only"];

/** 설정 값을 표시 방식으로. 모르는 값·빈 값은 `separate`. */
export function normalizeReplyDisplay(value: string | null | undefined): ReplyDisplay {
  return (KNOWN as readonly string[]).includes(value ?? "") ? (value as ReplyDisplay) : "separate";
}

/** `order` 오름차순, 같은 값(또는 없음)은 도착 순. 원본은 바꾸지 않는다. */
export function sortReplies<T extends ReplyItem>(replies: readonly T[]): T[] {
  return replies
    .map((r, i) => ({ r, i }))
    .sort((a, b) => {
      const ao = a.r.order ?? Number.POSITIVE_INFINITY;
      const bo = b.r.order ?? Number.POSITIVE_INFINITY;
      if (ao !== bo) return ao < bo ? -1 : 1;
      return a.i - b.i;
    })
    .map((x) => x.r);
}

/** `final`이 명시적으로 false인 것만 중간 결과. 값이 없으면 최종으로 본다. */
export function isIntermediate(reply: ReplyItem): boolean {
  return reply.final === false;
}

/** 중간 결과의 펼침 상태. 사용자가 정한 값이 있으면 그것, 없으면 실행 중 펼침·완료 후 접힘. */
export function isReplyExpanded(reply: ReplyItem, turnDone: boolean, userChoice?: Record<string, boolean>): boolean {
  if (!isIntermediate(reply)) return true;
  const chosen = userChoice?.[reply.edge_id];
  return chosen ?? !turnDone;
}

/** 표시 방식에 따라 화면에 낼 답변과 숨긴 개수. */
export function selectVisibleReplies(replies: readonly ReplyItem[], display: ReplyDisplay): { visible: ReplyItem[]; hidden: number } {
  const sorted = sortReplies(replies);
  if (display !== "final_only") return { visible: sorted, hidden: 0 };
  const visible = sorted.filter((r) => !isIntermediate(r));
  return { visible, hidden: sorted.length - visible.length };
}
