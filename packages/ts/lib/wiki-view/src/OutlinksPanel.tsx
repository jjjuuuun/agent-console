import type { WikiLink } from "@agent-console/contracts/wiki";
import { useMemo } from "react";
import { resolveDisplay, type WikiDisplay } from "./display";
import { formatMessage, resolveMessages } from "./messages";
import { linkLabel, usableLinks } from "./linkify";
import { linkBehavior, statusKey } from "./semantics";
import { VirtualList } from "./VirtualList";

export interface OutlinksPanelProps {
  /** 페이지 본문(링크 글자 `label` 대신 원문 조각을 쓸 때와 범위 검사에 필요) */
  content: string;
  links: readonly WikiLink[];
  display?: WikiDisplay;
  titleOf?: (path: string) => string | undefined;
  /** 행 호버·포커스: 본문의 그 링크를 강조한다(null = 해제) */
  onHover?: (link: WikiLink | null) => void;
  /** 행 클릭: 본문의 그 링크 위치로 스크롤 */
  onLocate?: (link: WikiLink) => void;
  /** 행의 [열기]: 대상 페이지(또는 스킴 화면) */
  onOpen?: (link: WikiLink) => void;
  /** 끊긴 링크 행의 [만들기] */
  onCreate?: (link: WikiLink) => void;
  readOnly?: boolean;
  readOnlyReason?: string;
  /** 스킴 대상 역할 이름 같은 보조 글(상태 글 대신) */
  schemeText?: (link: WikiLink) => string | undefined;
  rowHeight?: number;
  height?: number | string;
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

/**
 * 나가는 링크 목록(본문 순서, 같은 대상도 합치지 않는다). 가상 목록. 상태 글자는 `status`로만 정하고 모르는 상태는 원문이다.
 */
export function OutlinksPanel({
  content, links, display, titleOf, onHover, onLocate, onOpen, onCreate, readOnly = false, readOnlyReason, schemeText, rowHeight = 36, height, messages, className,
}: OutlinksPanelProps) {
  const t = resolveMessages(messages);
  const items = useMemo(() => usableLinks(content, links), [content, links]);
  if (items.length === 0) return <p className={`ac-wk-root ac-wk-muted ac-wk-empty${className ? ` ${className}` : ""}`} role="status">{t["outlinks.empty"]}</p>;
  return (
    <div className={`ac-wk-root${className ? ` ${className}` : ""}`} style={height !== undefined ? { height } : undefined}>
      <VirtualList
        items={items}
        rowHeight={rowHeight}
        role="list"
        ariaLabel={t["outlinks.label"] ?? ""}
        getKey={(l, i) => `${l.start}:${i}`}
        renderRow={(link, ctx) => {
          const label = linkLabel(link, content, titleOf);
          const behavior = linkBehavior(link);
          const d = resolveDisplay(display?.linkStatuses, statusKey(link));
          const state =
            behavior === "page" ? link.resolved ?? d.label
              : behavior === "scheme" ? schemeText?.(link) ?? d.label
                : d.label;
          return (
            <div
              role="listitem"
              className="ac-wk-row"
              style={ctx.style}
              data-status={statusKey(link)}
              aria-setsize={ctx.setSize}
              aria-posinset={ctx.posInSet}
              onMouseEnter={() => onHover?.(link)}
              onMouseLeave={() => onHover?.(null)}
              onFocus={() => onHover?.(link)}
              onBlur={() => onHover?.(null)}
            >
              <span className="ac-wk-icon" data-icon={d.icon ?? "neutral"} data-tone={d.tone} aria-hidden="true" />
              <button
                type="button"
                className="ac-wk-linkbtn ac-wk-ellipsis ac-wk-grow"
                title={formatMessage(t["outlinks.locate"], { label })}
                onClick={() => onLocate?.(link)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.nativeEvent.isComposing && onOpen) {
                    e.preventDefault();
                    onOpen(link);
                  }
                }}
              >
                {label}
              </button>
              <span className="ac-wk-muted ac-wk-ellipsis ac-wk-state-text" title={state}>{state}</span>
              {behavior === "broken" && onCreate ? (
                <button
                  type="button"
                  className="ac-wk-iconbtn"
                  aria-label={formatMessage(t["outlinks.create"], { label })}
                  aria-disabled={readOnly || undefined}
                  title={readOnly ? readOnlyReason : t["outlinks.create.tip"]}
                  onClick={() => {
                    if (!readOnly) onCreate(link);
                  }}
                >
                  <span className="ac-wk-icon" data-icon="plus" aria-hidden="true" />
                </button>
              ) : null}
            </div>
          );
        }}
      />
    </div>
  );
}
