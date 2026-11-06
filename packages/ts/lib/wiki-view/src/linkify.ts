/**
 * 서버가 준 링크 범위(`WikiLink.start`/`end`)로 본문을 다루는 순수 함수.
 * 범위는 **UTF-16 코드 유닛** 오프셋이다(JS 문자열 인덱스와 같다). `content.slice`에 그대로 쓰고,
 * 코드 포인트로 바꾸거나 `Array.from`으로 자르지 않는다. 링크 패턴·문법은 웹이 모른다(서버가 범위를 준다).
 */
import type { WikiLink } from "@agent-console/contracts/wiki";
import type { TextMark } from "@agent-console/text-editor";

/** 치환한 링크의 내부 주소 접두. `renderLink`가 이 접두 뒤의 `start` 숫자로 원래 링크를 찾는다. */
export const WIKI_LINK_HREF_PREFIX = "ac-wiki:";

/** 기본 `hrefOf`: `ac-wiki:<start>` */
export function defaultLinkHref(link: Pick<WikiLink, "start">): string {
  return `${WIKI_LINK_HREF_PREFIX}${link.start}`;
}

/** `ac-wiki:<start>` 주소에서 `start`를 읽는다. 아니면 null. */
export function parseLinkHref(href: string | undefined | null): number | null {
  if (!href || !href.startsWith(WIKI_LINK_HREF_PREFIX)) return null;
  const n = Number(href.slice(WIKI_LINK_HREF_PREFIX.length));
  return Number.isInteger(n) && n >= 0 ? n : null;
}

/**
 * 쓸 수 있는 링크만 골라 `start` 오름차순으로 돌려준다.
 * 버리는 것: 정수가 아닌 값·범위가 본문 밖·빈 범위, 앞 링크와 겹치는 링크(앞의 것만 쓴다). 같은 `start`면 입력 순서의 앞.
 */
export function usableLinks<L extends Pick<WikiLink, "start" | "end">>(content: string, links: readonly L[]): L[] {
  const sorted = links
    .map((l, i) => ({ l, i }))
    .filter(({ l }) => Number.isInteger(l.start) && Number.isInteger(l.end) && l.start >= 0 && l.end > l.start && l.end <= content.length)
    .sort((a, b) => a.l.start - b.l.start || a.i - b.i);
  const out: L[] = [];
  let lastEnd = 0;
  for (const { l } of sorted) {
    if (l.start < lastEnd) continue;
    out.push(l);
    lastEnd = l.end;
  }
  return out;
}

/** 마크다운 링크 글자에서 깨질 글자를 이스케이프한다(`\` `[` `]` + 서식을 여는 `` ` `` `*` `_` `<`). */
export function escapeLinkText(text: string): string {
  return text.replace(/[\\[\]`*_<]/g, "\\$&");
}

/** 표시 글자 = `label` → 해석된 페이지 제목 → `target` → 원문 조각. 줄바꿈은 공백 하나로. */
export function linkLabel(link: WikiLink, content: string, titleOf?: (path: string) => string | undefined): string {
  const pick =
    (link.label && link.label !== "" ? link.label : undefined) ??
    (link.resolved && titleOf ? nonEmpty(titleOf(link.resolved)) : undefined) ??
    nonEmpty(link.target ?? undefined) ??
    content.slice(link.start, link.end);
  return pick.replace(/\s+/g, " ").trim();
}

function nonEmpty(s: string | undefined | null): string | undefined {
  return s && s !== "" ? s : undefined;
}

export interface LinkifyOptions {
  /** 해석된 페이지 경로 → 제목(라벨이 없을 때만 씀) */
  titleOf?: (path: string) => string | undefined;
  /** 치환한 링크의 주소. 기본 `ac-wiki:<start>`. */
  hrefOf?: (link: WikiLink) => string;
}

/**
 * 링크 범위를 표준 마크다운 링크(`[글자](주소)`)로 치환한 본문을 돌려준다.
 * `start` 내림차순으로 바꿔 앞쪽 오프셋이 밀리지 않는다. 범위 밖·겹침은 버린다(`usableLinks`).
 */
export function linkifySource(content: string, links: readonly WikiLink[], options: LinkifyOptions = {}): string {
  const hrefOf = options.hrefOf ?? defaultLinkHref;
  const usable = usableLinks(content, links);
  let out = content;
  for (let i = usable.length - 1; i >= 0; i -= 1) {
    const link = usable[i]!;
    const label = escapeLinkText(linkLabel(link, content, options.titleOf));
    const href = hrefOf(link);
    const dest = /[\s()<>]/.test(href) ? `<${href.replace(/[<>]/g, encodeURIComponent)}>` : href;
    out = `${out.slice(0, link.start)}[${label}](${dest})${out.slice(link.end)}`;
  }
  return out;
}

/** 링크 범위 → 편집기 장식. 상태(`status`)는 `data-wiki-status`로만 달고 모양은 호출자 CSS가 정한다. */
export function linkMarks(content: string, links: readonly WikiLink[], className = "ac-wk-mark"): TextMark[] {
  return usableLinks(content, links).map((l) => ({
    from: l.start,
    to: l.end,
    className,
    attrs: { "data-wiki-link": String(l.start), "data-wiki-status": l.status && l.status !== "" ? l.status : "unknown" },
  }));
}
