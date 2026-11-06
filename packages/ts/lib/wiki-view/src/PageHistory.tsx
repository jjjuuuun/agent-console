import type { WikiPageVersion } from "@agent-console/contracts/wiki";
import { ToneChip } from "@agent-console/markdown-doc";
import { AuthorChip, OpChip } from "./Chips";
import type { WikiDisplay } from "./display";
import { formatAbsolute, formatRelative } from "./format";
import { useNowSeconds } from "./hooks";
import { formatMessage, resolveMessages } from "./messages";
import { VirtualList } from "./VirtualList";

export interface PageHistoryProps {
  /** 최신이 위(서버 순서 그대로) */
  versions: readonly WikiPageVersion[];
  /** 서버가 보관 수로 지운 버전이 있음(`WikiHistoryPage.pruned`). false면 번호 간격으로 추측하지 않는다. */
  pruned?: boolean;
  /** 지금 페이지 본문과 해시가 같은 버전 번호(`현재` 칩) */
  currentVersion?: number | null;
  /** 보고 있는 버전 */
  selectedVersion?: number | null;
  display?: WikiDisplay;
  /** 기록 저장소가 없다(탭은 보이고 안내만). 다른 prop은 무시된다. */
  unavailable?: boolean;
  /** 기록 저장소 문제가 프로젝트 연동일 때만 [프로젝트 설정 보기]를 준다. */
  onOpenProjectSettings?: () => void;
  onSelect?: (version: WikiPageVersion) => void;
  onCompare?: (version: WikiPageVersion) => void;
  onRestore?: (version: WikiPageVersion) => void;
  /** 쓴 주체 칩의 실행 링크 */
  onOpenRun?: (runId: string, rootRunId: string | null) => void;
  /** 되돌리기를 막는 이유(저장 안 됨·읽기 전용). 있으면 [되돌리기]가 `aria-disabled`. */
  restoreDisabledReason?: string;
  now?: number;
  rowHeight?: number;
  height?: number | string;
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

/**
 * 페이지 기록(가상 목록). 행 = 버전 + 동작 칩 + 상대 시각 + 쓴 주체 칩 + 메시지, 오른쪽에 [비교]·[되돌리기].
 * 동작·쓴 주체 종류는 열린 문자열이고 이름·톤은 `display`가 정한다. 기록 없음·기록 저장소 없음은 각자 안내를 보인다.
 */
export function PageHistory({
  versions, pruned = false, currentVersion = null, selectedVersion = null, display, unavailable = false, onOpenProjectSettings, onSelect, onCompare, onRestore, onOpenRun,
  restoreDisabledReason, now, rowHeight = 56, height, messages, className,
}: PageHistoryProps) {
  const t = resolveMessages(messages);
  const at = useNowSeconds(now);
  const root = `ac-wk-root${className ? ` ${className}` : ""}`;
  if (unavailable) {
    return (
      <div className={`${root} ac-wk-state-block`} role="status" data-state="history-unavailable">
        <span className="ac-wk-icon" data-icon="history" aria-hidden="true" />
        <p className="ac-wk-state-title">{t["history.unavailable.title"]}</p>
        <p className="ac-wk-muted">{t["history.unavailable.body"]}</p>
        {onOpenProjectSettings ? <button type="button" className="ac-wk-btn" onClick={onOpenProjectSettings}>{t["history.unavailable.settings"]}</button> : null}
      </div>
    );
  }
  if (versions.length === 0) return <p className={`${root} ac-wk-muted ac-wk-empty`} role="status">{t["history.empty"]}</p>;
  return (
    <div className={root} style={{ display: "flex", flexDirection: "column", ...(height !== undefined ? { height } : {}) }}>
      <VirtualList
        items={versions}
        rowHeight={rowHeight}
        role="list"
        ariaLabel={t["history.label"] ?? ""}
        getKey={(v) => String(v.version)}
        renderRow={(v, ctx) => {
          const rel = formatRelative(v.at, at, t);
          const disabled = restoreDisabledReason !== undefined;
          return (
            <div
              role="listitem"
              className="ac-wk-row ac-wk-history-row"
              style={ctx.style}
              data-selected={selectedVersion === v.version || undefined}
              aria-setsize={ctx.setSize}
              aria-posinset={ctx.posInSet}
            >
              <div className="ac-wk-grow ac-wk-stack">
                <div className="ac-wk-inline">
                  <button type="button" className="ac-wk-linkbtn ac-wk-mono" aria-current={selectedVersion === v.version || undefined} onClick={() => onSelect?.(v)}>
                    v{v.version}
                  </button>
                  <OpChip op={v.op} {...(display ? { display } : {})} />
                  {currentVersion === v.version ? <ToneChip label={t["history.current"] ?? ""} tone="info" /> : null}
                  <time className="ac-wk-muted" dateTime={new Date(v.at * 1000).toISOString()} title={formatAbsolute(v.at)}>{rel}</time>
                </div>
                <div className="ac-wk-inline">
                  <AuthorChip author={v.author} {...(display ? { display } : {})} {...(onOpenRun ? { onOpenRun } : {})} messages={messages ?? {}} />
                  {v.message ? <span className="ac-wk-muted ac-wk-ellipsis" title={v.message}>{v.message}</span> : null}
                </div>
              </div>
              {onCompare ? (
                <button type="button" className="ac-wk-iconbtn" aria-label={formatMessage(t["history.compare"], { v: v.version })} title={t["history.compare.tip"]} onClick={() => onCompare(v)}>
                  <span className="ac-wk-icon" data-icon="diff" aria-hidden="true" />
                </button>
              ) : null}
              {onRestore ? (
                <button
                  type="button"
                  className="ac-wk-iconbtn"
                  aria-label={formatMessage(t["history.restore"], { v: v.version })}
                  aria-disabled={disabled || undefined}
                  title={disabled ? restoreDisabledReason : t["history.restore.tip"]}
                  onClick={() => {
                    if (!disabled) onRestore(v);
                  }}
                >
                  <span className="ac-wk-icon" data-icon="undo" aria-hidden="true" />
                </button>
              ) : null}
            </div>
          );
        }}
      />
      {pruned ? <p className="ac-wk-muted ac-wk-footnote">{t["history.pruned"]}</p> : null}
    </div>
  );
}
