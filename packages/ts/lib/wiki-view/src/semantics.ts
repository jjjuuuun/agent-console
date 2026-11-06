/**
 * 링크 상태 해석. 상태는 서버가 채운 `WikiLink.status`(열린 문자열)만 본다 — 불리언 조합으로 만들지 않는다.
 * 계약의 문서 상수(`KNOWN_WIKI_LINK_STATUSES`)에 있는 값만 동작을 갖고, 모르는 값은 중립(글자만, 동작 없음)이다.
 */
import { KNOWN_WIKI_LINK_STATUSES } from "@agent-console/contracts/constants";
import type { WikiLink } from "@agent-console/contracts/wiki";

/** 링크가 하는 일 */
export type LinkBehavior = "page" | "broken" | "scheme" | "outside" | "neutral";

/** 상태 문자열 → 동작. 모르는 값은 `neutral`. */
export function linkBehavior(link: Pick<WikiLink, "status">): LinkBehavior {
  switch (link.status) {
    case KNOWN_WIKI_LINK_STATUSES.OK: return "page";
    case KNOWN_WIKI_LINK_STATUSES.BROKEN: return "broken";
    case KNOWN_WIKI_LINK_STATUSES.SCHEME: return "scheme";
    case KNOWN_WIKI_LINK_STATUSES.OUTSIDE: return "outside";
    default: return "neutral";
  }
}

/** 상태가 비었으면 모르는 값으로 본다. 표시 표 조회용 키. */
export function statusKey(link: Pick<WikiLink, "status">): string {
  return link.status && link.status !== "" ? link.status : "unknown";
}
