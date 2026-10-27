import type { MemoryVersionSummary } from "@agent-console/contracts/memory";
import { useRef, type KeyboardEvent } from "react";
import { formatRelativeTime, formatSizeDelta, formatTimestamp } from "./format";
import { useNowSeconds } from "./hooks";
import { messageOr, resolveMessages } from "./messages";
import { formatAuthor, type FormatAuthorOptions } from "./scopes";

export interface MemoryVersionListProps {
  versions: readonly MemoryVersionSummary[];
  /** 선택한 버전 번호. */
  selected: number | null;
  onSelect: (version: number) => void;
  /** 항목의 현재 버전(목록에 "현재" 표지). */
  currentVersion?: number;
  loading?: boolean;
  error?: boolean;
  onRetry?: () => void;
  authorOptions?: FormatAuthorOptions;
  /** 지금 시각(Unix epoch 초). */
  now?: number;
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

/** 버전 목록(최신순). 행 40: v번호 · 동작 칩 · 쓴 주체 · 시각 · 크기 변화. ↑↓ 이동. */
export function MemoryVersionList({ versions, selected, onSelect, currentVersion, loading = false, error = false, onRetry, authorOptions, now, messages: custom, className }: MemoryVersionListProps) {
  const m = resolveMessages(custom);
  const nowSec = useNowSeconds(now);
  const sorted = [...versions].sort((a, b) => b.version - a.version);
  const listRef = useRef<HTMLDivElement>(null);
  const focusIndex = Math.max(0, sorted.findIndex((v) => v.version === selected));

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const move = e.key === "ArrowDown" ? 1 : e.key === "ArrowUp" ? -1 : 0;
    if (move === 0 && e.key !== "Home" && e.key !== "End") return;
    e.preventDefault();
    const next = e.key === "Home" ? 0 : e.key === "End" ? sorted.length - 1 : Math.max(0, Math.min(sorted.length - 1, focusIndex + move));
    const target = sorted[next];
    if (!target) return;
    onSelect(target.version);
    queueMicrotask(() => listRef.current?.querySelector<HTMLElement>(`[data-version="${target.version}"]`)?.focus());
  };

  return (
    <div className={`ac-mem-root ac-mem-versions${className ? ` ${className}` : ""}`}>
      <div className="ac-mem-versions-title">{m["history.list"]}</div>
      {error ? (
        <div className="ac-mem-errorblock" role="alert">
          <span>{m["history.error"]}</span>
          {onRetry ? <button type="button" className="ac-mem-btn" onClick={onRetry}>{m["history.retry"]}</button> : null}
        </div>
      ) : loading ? (
        <div className="ac-mem-skeleton-list" aria-busy="true" aria-label={m["history.loading"]}>
          {Array.from({ length: 6 }, (_, i) => <div key={i} className="ac-mem-skeleton" />)}
        </div>
      ) : sorted.length === 0 ? (
        <div className="ac-mem-empty">{m["history.empty"]}</div>
      ) : (
        <div ref={listRef} role="listbox" aria-label={m["history.list"]} className="ac-mem-versions-list" onKeyDown={onKeyDown}>
          {sorted.map((v, i) => {
            const older = sorted[i + 1];
            const a = formatAuthor(v.author, authorOptions);
            const op = messageOr(m, `history.op.${v.op}`, v.op);
            const isSel = v.version === selected;
            const time = formatRelativeTime(v.at, nowSec, m);
            const delta = older ? formatSizeDelta(v.bytes - older.bytes) : null;
            return (
              <div key={v.version} role="option" aria-selected={isSel} tabIndex={i === focusIndex ? 0 : -1} data-version={v.version} data-selected={isSel ? "" : undefined}
                className="ac-mem-version-row" onClick={() => onSelect(v.version)}
                aria-label={`v${v.version}, ${op}, ${a.text}${a.ruleId ? ` ${a.ruleId}` : ""}, ${time}${delta ? `, ${delta}` : ""}${v.version === currentVersion ? `, ${m["history.isCurrent"]}` : ""}`}>
                <span className="ac-mem-mono ac-mem-num">v{v.version}</span>
                <span className="ac-mem-chip">{op}</span>
                <span className="ac-mem-version-author ac-ellipsis" title={a.tooltip}>
                  <span className={a.mono ? "ac-mem-mono" : undefined}>{a.text}</span>{a.ruleId ? <span className="ac-mem-mono"> {a.ruleId}</span> : null}
                </span>
                <span className="ac-mem-muted ac-mem-num" title={formatTimestamp(v.at)}>{time}</span>
                <span className="ac-mem-num ac-mem-version-delta">{delta ?? ""}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
