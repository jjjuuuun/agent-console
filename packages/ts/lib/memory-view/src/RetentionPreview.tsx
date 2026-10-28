import type { MemoryRetentionPlan, MemoryRetentionPlanItem, MemoryRetentionResult, MemoryScopeRef } from "@agent-console/contracts/memory";
import { useId, useRef } from "react";
import { formatBytes, formatRelativeTime, formatTimestamp } from "./format";
import { useNowSeconds, useVirtualRows } from "./hooks";
import { formatMessage, messageOr, resolveMessages } from "./messages";

/** 계획 항목의 표시 정보(마지막 쓰기·크기). 계약 계획 항목에 같은 필드가 있어 기본은 항목 값을 쓴다. */
export interface RetentionItemDetail {
  updated_at?: number | null;
  bytes?: number | null;
}

export const RETENTION_MAX_ROWS = 200;
const ROW_HEIGHT = 32;

export interface RetentionPreviewProps {
  /** 정리 계획. null = 아직 미리보기 안 함. */
  plan: MemoryRetentionPlan | null;
  /** 사용한 규칙 수(0이면 호출하지 않고 "규칙이 없습니다"). */
  ruleCount: number;
  loading?: boolean;
  error?: boolean;
  /** 미리보기를 한 시각(Unix epoch 초). */
  previewedAt?: number | null;
  /** 고정으로 제외된 수. 생략하면 계획의 `excluded_pinned`(0이면 문구가 없다), null이면 문구를 숨긴다. */
  excludedPinned?: number | null;
  onPreview: () => void;
  /** [지금 적용]. 확인 창은 앱이 띄운다(미리보기 수를 그 창에 쓸 수 있다). */
  onApply?: () => void;
  /** 적용이 가능한가(저장된 규칙과 같은 규칙으로 미리보기 + 저장 안 된 변경 없음 + 대상 1개 이상은 앱이 판단). */
  canApply?: boolean;
  /** 적용이 꺼진 이유(메시지 키 또는 문장). 버튼 아래 한 줄. */
  applyBlockedReason?: string | null;
  /** 적용 결과 인라인 요약. */
  result?: MemoryRetentionResult | null;
  resultAt?: number | null;
  /** 범위 라벨 글. */
  scopeText?: (scope: MemoryScopeRef) => string;
  /** 항목 → 마지막 쓰기·크기. 생략하면 계획 항목의 `updated_at`·`bytes`, 값이 없으면 "–". */
  detailOf?: (item: MemoryRetentionPlanItem) => RetentionItemDetail | undefined;
  now?: number;
  maxRows?: number;
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

/** 정리 미리보기: 대상 요약 + 가상 표(규칙·동작·범위·키·마지막 쓰기·크기) + [지금 적용]. 호출·확인은 앱이 한다. */
export function RetentionPreview({
  plan, ruleCount, loading = false, error = false, previewedAt, excludedPinned, onPreview, onApply, canApply = false, applyBlockedReason = null, result = null, resultAt,
  scopeText, detailOf, now, maxRows = RETENTION_MAX_ROWS, messages: custom, className,
}: RetentionPreviewProps) {
  const m = resolveMessages(custom);
  const nowSec = useNowSeconds(now);
  const scrollRef = useRef<HTMLDivElement>(null);
  const reasonId = useId();
  const items = plan ? plan.items?.slice(0, maxRows) ?? [] : [];
  const virtual = useVirtualRows({ count: items.length, rowHeight: ROW_HEIGHT, scrollRef, fallbackHeight: 320 });
  const archives = plan?.items?.filter((i) => i.action === "archive").length ?? 0;
  const deletes = plan?.items?.filter((i) => i.action === "delete").length ?? 0;
  const count = plan?.count ?? 0;
  const rest = plan ? Math.max(0, count - items.length) : 0;
  const scopeName = (s: MemoryScopeRef) => scopeText?.(s) ?? `${s.kind}:${s.id ?? ""}`;
  const hasRules = ruleCount > 0;
  const pinnedOut = excludedPinned !== undefined ? excludedPinned : plan?.excluded_pinned ? plan.excluded_pinned : null;

  return (
    <div className={`ac-mem-root ac-mem-retention${className ? ` ${className}` : ""}`}>
      <div className="ac-mem-retention-head">
        <span className="ac-mem-muted">{previewedAt ? formatMessage(m["retention.previewedAt"] as string, { time: formatTimestamp(previewedAt) }) : m["retention.preview"]}</span>
        <button type="button" className="ac-mem-btn" onClick={onPreview} disabled={loading || !hasRules}>{loading ? m["retention.previewing"] : plan ? m["retention.again"] : m["retention.preview"]}</button>
      </div>
      {!hasRules ? (
        <p className="ac-mem-empty">{m["retention.noRules"]}</p>
      ) : error ? (
        <div className="ac-mem-errorblock" role="alert">
          <span>{m["retention.error"]}</span>
          <button type="button" className="ac-mem-btn" onClick={onPreview}>{m["retention.retry"]}</button>
        </div>
      ) : loading ? (
        <div className="ac-mem-spinner" role="status" aria-label={m["retention.previewing"]} />
      ) : plan ? (
        <>
          <p className="ac-mem-retention-summary">
            {formatMessage(m["retention.summary"] as string, { n: count, a: archives, d: deletes })}
            {pinnedOut !== null ? <span className="ac-mem-muted"> ({formatMessage(m["retention.excludedPinned"] as string, { p: pinnedOut })})</span> : null}
          </p>
          {items.length === 0 ? (
            <p className="ac-mem-empty">{m["retention.none"]}</p>
          ) : (
            <div ref={scrollRef} className="ac-mem-table-scroll ac-mem-retention-scroll">
              <div role="table" aria-label={m["retention.table"]} aria-rowcount={items.length + 1} className="ac-mem-grid ac-mem-retention-grid">
                <div role="row" aria-rowindex={1} className="ac-mem-thead">
                  <div role="columnheader" className="ac-mem-th">{m["retention.col.rule"]}</div>
                  <div role="columnheader" className="ac-mem-th">{m["retention.col.action"]}</div>
                  <div role="columnheader" className="ac-mem-th">{m["retention.col.scope"]}</div>
                  <div role="columnheader" className="ac-mem-th">{m["retention.col.key"]}</div>
                  <div role="columnheader" className="ac-mem-th" data-align="right">{m["retention.col.updated"]}</div>
                  <div role="columnheader" className="ac-mem-th" data-align="right">{m["retention.col.size"]}</div>
                </div>
                <div role="rowgroup" className="ac-mem-tbody" style={{ height: virtual.getTotalSize() }}>
                  {virtual.getVirtualItems().map((vi) => {
                    const it = items[vi.index];
                    if (!it) return null;
                    const detail: RetentionItemDetail = detailOf ? detailOf(it) ?? {} : it;
                    const action = messageOr(m, `retention.action.${it.action}`, it.action);
                    return (
                      <div key={`${it.entry_id}:${it.version}`} role="row" aria-rowindex={vi.index + 2} className="ac-mem-tr" style={{ height: vi.size, transform: `translateY(${vi.start}px)` }}>
                        <div role="cell" className="ac-mem-td ac-mem-mono ac-ellipsis" title={it.rule}>{it.rule}</div>
                        <div role="cell" className="ac-mem-td">
                          <span className="ac-mem-chip" data-tone={it.action === "delete" ? "danger" : undefined}>
                            {it.action === "delete" ? <span className="ac-mem-icon ac-mem-icon-failed" aria-hidden="true" /> : null}{action}
                          </span>
                        </div>
                        <div role="cell" className="ac-mem-td ac-ellipsis" title={scopeName(it.scope)}>{scopeName(it.scope)}</div>
                        <div role="cell" className="ac-mem-td ac-ellipsis" title={it.key}>{it.key}</div>
                        <div role="cell" className="ac-mem-td ac-mem-num" data-align="right" title={detail.updated_at ? formatTimestamp(detail.updated_at) : undefined}>
                          {detail.updated_at ? formatRelativeTime(detail.updated_at, nowSec, m) : m["time.never"]}
                        </div>
                        <div role="cell" className="ac-mem-td ac-mem-num" data-align="right">{detail.bytes !== null && detail.bytes !== undefined ? formatBytes(detail.bytes, m) : m["time.never"]}</div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
          {rest > 0 ? <p className="ac-mem-muted">{formatMessage(m["retention.more"] as string, { shown: items.length, n: rest })}</p> : null}
          <p className="ac-mem-muted">{m["retention.stale"]}</p>
        </>
      ) : null}
      {onApply ? (
        <div className="ac-mem-retention-apply">
          <button type="button" className="ac-mem-btn" data-variant="primary" disabled={!canApply} onClick={onApply} aria-describedby={!canApply && applyBlockedReason ? reasonId : undefined}>{m["retention.apply"]}</button>
          {!canApply && applyBlockedReason ? <span id={reasonId} className="ac-mem-muted">{applyBlockedReason}</span> : null}
        </div>
      ) : null}
      {result ? (
        <p className="ac-mem-retention-result" role="status">
          {formatMessage(m["retention.result"] as string, { a: result.archived ?? 0, d: result.deleted ?? 0, s: result.skipped ?? 0, time: resultAt ? formatTimestamp(resultAt) : "" })}
        </p>
      ) : null}
    </div>
  );
}
