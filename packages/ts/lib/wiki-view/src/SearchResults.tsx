import type { WikiSearchHit } from "@agent-console/contracts/wiki";
import { useImperativeHandle, useState, type Ref } from "react";
import { useDomId } from "./hooks";
import { formatMessage, resolveMessages } from "./messages";
import { splitByMarks } from "./marks";
import { VirtualList } from "./VirtualList";

/** 입력 칸 같은 바깥 요소가 방향키·Enter를 넘길 때 쓰는 핸들. */
export interface SearchResultsHandle {
  /** 활성 행을 `delta`만큼 옮긴다(끝에서 멈춤). */
  move: (delta: number) => void;
  /** 활성 행을 연다. 결과가 없으면 false. */
  openActive: () => boolean;
}

export interface SearchResultsProps {
  hits: readonly WikiSearchHit[];
  /** 검색어(0건 안내에 쓴다) */
  query: string;
  /** 검색이 저하된 방식(파일을 하나씩 읽는 폴백 등)으로 돌았다 */
  degraded?: boolean;
  /** 결과가 상한에서 잘렸다 */
  truncated?: boolean;
  /** 활성 행(제어형). 생략하면 안에서 관리. */
  activeIndex?: number;
  onActiveChange?: (index: number) => void;
  onOpen?: (hit: WikiSearchHit) => void;
  /** 목록 요소 id 접두. 바깥 입력 칸이 `aria-activedescendant`로 가리키려면 `searchOptionId(id, index)`와 같은 값을 쓴다. */
  id?: string;
  handleRef?: Ref<SearchResultsHandle>;
  rowHeight?: number;
  maxHeight?: number | string;
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

/** 행 id 규칙(입력 칸의 `aria-activedescendant`용). */
export function searchOptionId(id: string, index: number): string {
  return `${id}-opt${index}`;
}

/**
 * 본문 검색 결과(가상 `listbox`). 행 = 제목 + 경로(mono) + 조각 2줄. 강조는 서버 `marks`(조각 문자열 기준 UTF-16)이고 `<mark>`가 아니라 강조 span이다.
 * 조각은 글자일 뿐 HTML이 아니다. 방향키·Enter는 바깥 입력 칸이 `handleRef`로 넘기거나 이 목록에 포커스가 있을 때 받는다.
 */
export function SearchResults({
  hits, query, degraded = false, truncated = false, activeIndex, onActiveChange, onOpen, id, handleRef, rowHeight = 56, maxHeight = "min(480px, 60vh)", messages, className,
}: SearchResultsProps) {
  const t = resolveMessages(messages);
  const auto = useDomId();
  const base = id ?? auto;
  const [inner, setInner] = useState(0);
  const current = Math.min(Math.max(activeIndex ?? inner, 0), Math.max(hits.length - 1, 0));
  const set = (i: number) => {
    const next = Math.min(Math.max(0, i), Math.max(hits.length - 1, 0));
    setInner(next);
    onActiveChange?.(next);
  };
  useImperativeHandle(
    handleRef,
    () => ({
      move: (d: number) => set(current + d),
      openActive: () => {
        const h = hits[current];
        if (!h) return false;
        onOpen?.(h);
        return true;
      },
    }),
    // set/current/hits/onOpen이 바뀌면 핸들도 새로 만든다
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [current, hits, onOpen, onActiveChange],
  );
  const root = `ac-wk-root ac-wk-search${className ? ` ${className}` : ""}`;
  return (
    <div className={root} style={{ display: "flex", flexDirection: "column" }}>
      {degraded ? <p className="ac-wk-banner" data-tone="info" role="status">{t["search.degraded"]}</p> : null}
      {hits.length === 0 ? (
        <p className="ac-wk-muted ac-wk-empty" role="status">{formatMessage(t["search.empty"], { query })}</p>
      ) : (
        <VirtualList
          items={hits}
          rowHeight={rowHeight}
          role="listbox"
          ariaLabel={t["search.label"] ?? ""}
          maxHeight={maxHeight}
          height="auto"
          tabIndex={-1}
          activeDescendant={searchOptionId(base, current)}
          activeIndex={current}
          onKeyDown={(e) => {
            if (e.nativeEvent.isComposing) return;
            if (e.key === "ArrowDown") { e.preventDefault(); set(current + 1); }
            else if (e.key === "ArrowUp") { e.preventDefault(); set(current - 1); }
            else if (e.key === "Enter") { e.preventDefault(); const h = hits[current]; if (h) onOpen?.(h); }
          }}
          getKey={(h, i) => `${h.path}:${i}`}
          renderRow={(hit, ctx) => {
            const snippet = hit.snippet ?? "";
            const segs = splitByMarks(snippet, hit.marks);
            return (
              <div
                id={searchOptionId(base, ctx.index)}
                role="option"
                aria-selected={ctx.index === current}
                aria-setsize={ctx.setSize}
                aria-posinset={ctx.posInSet}
                className="ac-wk-hit"
                data-active={ctx.index === current || undefined}
                style={ctx.style}
                onMouseMove={() => ctx.index !== current && set(ctx.index)}
                onClick={() => onOpen?.(hit)}
              >
                <span className="ac-wk-hit-title ac-wk-ellipsis">{hit.title && hit.title !== "" ? hit.title : hit.path}</span>
                <span className="ac-wk-hit-path ac-wk-mono ac-wk-muted ac-wk-ellipsis">{hit.path}</span>
                {snippet !== "" ? (
                  <span className="ac-wk-hit-snippet">
                    {segs.map((s, i) => (s.marked ? <span key={i} className="ac-wk-hl" data-hl="">{s.text}</span> : <span key={i}>{s.text}</span>))}
                  </span>
                ) : null}
              </div>
            );
          }}
        />
      )}
      {truncated ? <p className="ac-wk-muted ac-wk-footnote">{t["search.truncated"]}</p> : null}
    </div>
  );
}
