import type { WikiLink, WikiPageView } from "@agent-console/contracts/wiki";
import { MarkdownPreview } from "@agent-console/markdown-doc";
import { useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState, type ReactNode, type Ref } from "react";
import { resolveDisplay, type WikiDisplay } from "./display";
import { formatMessage, resolveMessages } from "./messages";
import { linkLabel, linkifySource, parseLinkHref, usableLinks, WIKI_LINK_HREF_PREFIX } from "./linkify";
import { linkBehavior, statusKey } from "./semantics";

/** `handleRef`로 받는 명령형 핸들(오른쪽 패널의 "나가는 링크" 행과 서로 강조·스크롤). */
export interface PageViewHandle {
  /** 본문에서 그 `start`의 링크를 화면 가운데로 스크롤하고 포커스를 둔다. 없으면 false. */
  scrollToLink: (start: number) => boolean;
  /** 제목 글이 같은 첫 제목(대소문자 무시)으로 스크롤한다. 없으면 false. */
  scrollToHeading: (text: string) => boolean;
}

export interface PageViewProps {
  page: WikiPageView;
  /** 해석된 페이지 경로 → 제목. 링크 글자 `label`이 비었을 때만 쓴다. */
  titleOf?: (path: string) => string | undefined;
  display?: WikiDisplay;
  /** 페이지 링크: 같은 위키의 페이지 열기(+ 절). 앱 안 이동. */
  onOpenPage?: (path: string, anchor: string | null) => void;
  /** 페이지 링크의 실제 주소(우클릭 새 탭·접근성). 없으면 `#`. */
  hrefOfPage?: (path: string, anchor: string | null) => string;
  /** 끊긴 링크 팝오버의 [이 페이지 만들기]. 두 번째 인자는 제안 경로(`suggested_path ?? target`). */
  onCreatePage?: (link: WikiLink, suggestedPath: string) => void;
  /** 다른 기능으로 가는 링크(`scheme_target`). 이동할 화면이 없으면 `canOpenScheme`이 false를 돌려 글자만 보인다. */
  onOpenScheme?: (link: WikiLink) => void;
  canOpenScheme?: (link: WikiLink) => boolean;
  readOnly?: boolean;
  readOnlyReason?: string;
  /** 오른쪽 패널에서 가리키는 링크(`start`)를 강조한다. */
  highlightStart?: number | null;
  /** 열 때 스크롤할 절 글. 못 찾으면 `onAnchorMissing`. */
  anchor?: string | null;
  onAnchorMissing?: (anchor: string) => void;
  handleRef?: Ref<PageViewHandle>;
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

const SAFE_SCHEMES = /^(https?|mailto|tel):/i;

/** 주소 통과 규칙: 위키 내부 스킴 + 안전한 스킴 + 스킴 없는 상대 주소. 나머지는 막는다. */
export function wikiUrlTransform(url: string): string {
  if (url.startsWith(WIKI_LINK_HREF_PREFIX)) return url;
  if (SAFE_SCHEMES.test(url)) return url;
  if (!/^[a-z][a-z0-9+.-]*:/i.test(url)) return url;
  return "";
}

function nodeText(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(nodeText).join("");
  return "";
}

/**
 * 페이지 본문 보기. 서버가 준 링크 범위(UTF-16)로 본문을 마크다운 링크로 바꿔 `MarkdownPreview`에 넣는다 — 링크 문법은 웹에 없다.
 * 링크 모양은 `status`로 가른다: 페이지(앱 안 이동) · 끊긴(점선 + 아이콘 + 만들기 팝오버) · 스킴(다른 기능으로) · 폴더 밖(열지 않음) · 모르는 값(글자만).
 */
export function PageView({
  page, titleOf, display, onOpenPage, hrefOfPage, onCreatePage, onOpenScheme, canOpenScheme, readOnly = false, readOnlyReason, highlightStart = null,
  anchor = null, onAnchorMissing, handleRef, messages, className,
}: PageViewProps) {
  const t = resolveMessages(messages);
  const rootRef = useRef<HTMLDivElement>(null);
  const links = useMemo(() => usableLinks(page.content, page.links ?? []), [page.content, page.links]);
  const byStart = useMemo(() => new Map(links.map((l) => [l.start, l] as const)), [links]);
  const source = page.content;
  const transform = useCallback((text: string) => linkifySource(text, links, { ...(titleOf ? { titleOf } : {}) }), [links, titleOf]);
  const [popup, setPopup] = useState<number | null>(null);

  const scrollToLink = useCallback((start: number): boolean => {
    const el = rootRef.current?.querySelector<HTMLElement>(`[data-wiki-link="${start}"]`);
    if (!el) return false;
    el.scrollIntoView?.({ block: "center" });
    el.focus?.();
    return true;
  }, []);
  const scrollToHeading = useCallback((text: string): boolean => {
    const want = text.trim().toLowerCase();
    const hs = rootRef.current?.querySelectorAll<HTMLElement>("h1,h2,h3,h4,h5,h6") ?? [];
    for (const h of hs) {
      if ((h.textContent ?? "").trim().toLowerCase() === want) {
        h.scrollIntoView?.({ block: "start" });
        return true;
      }
    }
    return false;
  }, []);
  useImperativeHandle(handleRef, () => ({ scrollToLink, scrollToHeading }), [scrollToLink, scrollToHeading]);

  const missing = useRef(onAnchorMissing);
  useEffect(() => {
    missing.current = onAnchorMissing;
  });
  useEffect(() => {
    if (!anchor) return;
    const id = requestAnimationFrame(() => {
      if (!scrollToHeading(anchor)) missing.current?.(anchor);
    });
    return () => cancelAnimationFrame(id);
  }, [anchor, page.page.path, scrollToHeading]);

  const renderLink = (href: string | undefined, children: ReactNode): ReactNode => {
    const start = parseLinkHref(href);
    const link = start === null ? undefined : byStart.get(start);
    if (!link) {
      // 위키 링크가 아닌 일반 마크다운 링크: 새 탭, 외부 주소를 서버가 가져오지 않는다(표시만)
      return (
        <a href={href} target="_blank" rel="noopener noreferrer" className="ac-wk-extlink">
          {children}<span className="ac-wk-icon" data-icon="external-link" aria-hidden="true" />
        </a>
      );
    }
    const key = statusKey(link);
    const common = { "data-wiki-link": String(link.start), "data-wiki-status": key, "data-highlight": highlightStart === link.start || undefined } as const;
    const behavior = linkBehavior(link);
    const target = link.target ?? link.raw;
    if (behavior === "page" && link.resolved) {
      const path = link.resolved;
      const anchorText = link.anchor ?? null;
      return (
        <a
          {...common}
          className="ac-wk-link"
          href={hrefOfPage ? hrefOfPage(path, anchorText) : "#"}
          onClick={(e) => {
            if (e.metaKey || e.ctrlKey || e.shiftKey) return;
            e.preventDefault();
            onOpenPage?.(path, anchorText);
          }}
        >
          {children}
        </a>
      );
    }
    if (behavior === "broken") {
      const suggested = link.suggested_path && link.suggested_path !== "" ? link.suggested_path : target;
      const tip = formatMessage(t["link.broken.tip"], { target });
      const open = popup === link.start;
      return (
        <>
          <button
            {...common}
            type="button"
            className="ac-wk-link"
            aria-label={tip}
            title={tip}
            aria-expanded={open}
            onClick={() => setPopup(open ? null : link.start)}
          >
            {children}<span className="ac-wk-icon" data-icon="link-broken" aria-hidden="true" />
          </button>
          {open ? (
            <span className="ac-wk-pop" role="group" aria-label={t["link.broken.popover"]}>
              <span>{formatMessage(t["link.broken.body"], { target })}</span>
              <button
                type="button"
                className="ac-wk-btn"
                data-primary=""
                aria-disabled={readOnly || !onCreatePage || undefined}
                title={readOnly ? readOnlyReason : undefined}
                onClick={() => {
                  if (readOnly || !onCreatePage) return;
                  onCreatePage(link, suggested);
                  setPopup(null);
                }}
              >
                {t["link.broken.create"]}
              </button>
              {readOnly && readOnlyReason ? <span className="ac-wk-muted">{readOnlyReason}</span> : null}
              <button type="button" className="ac-wk-btn" onClick={() => setPopup(null)}>{t["common.close"]}</button>
            </span>
          ) : null}
        </>
      );
    }
    if (behavior === "scheme") {
      const can = onOpenScheme !== undefined && (canOpenScheme ? canOpenScheme(link) : true);
      if (!can) {
        return (
          <span {...common} className="ac-wk-link" tabIndex={0} title={t["link.scheme.off"]} aria-label={`${nodeText(children)}, ${t["link.scheme.off"]}`}>
            {children}
          </span>
        );
      }
      return (
        <button {...common} type="button" className="ac-wk-link" onClick={() => onOpenScheme(link)}>
          {children}<span className="ac-wk-icon" data-icon="external-link" aria-hidden="true" />
        </button>
      );
    }
    if (behavior === "outside") {
      return (
        <span {...common} className="ac-wk-link" role="link" aria-disabled="true" tabIndex={0} title={t["link.outside.tip"]}>
          {children}
        </span>
      );
    }
    // 모르는 상태: 글자만(동작 없음), 표시 표에 이름이 있으면 툴팁
    const d = resolveDisplay(display?.linkStatuses, key);
    return (
      <span {...common} className="ac-wk-link" tabIndex={0} title={d.known ? d.label : link.status || undefined}>
        {children}
      </span>
    );
  };

  return (
    <div ref={rootRef} className={`ac-wk-root ac-wk-prose${className ? ` ${className}` : ""}`} data-linked={links.length > 0 || undefined}>
      {source.trim() === "" ? (
        <p className="ac-wk-muted" role="status">{t["page.empty"]}</p>
      ) : (
        <MarkdownPreview source={source} transformSource={transform} renderLink={renderLink} urlTransform={wikiUrlTransform} />
      )}
    </div>
  );
}

/** 링크 하나의 표시 글자(패널·그래프와 같은 규칙). */
export function pageLinkLabel(link: WikiLink, content: string, titleOf?: (path: string) => string | undefined): string {
  return linkLabel(link, content, titleOf);
}
