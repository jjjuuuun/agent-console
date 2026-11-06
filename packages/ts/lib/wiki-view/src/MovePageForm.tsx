import type { WikiMoveResult } from "@agent-console/contracts/wiki";
import { useId } from "react";
import { formatMessage, resolveMessages } from "./messages";
import { VirtualList } from "./VirtualList";

export interface MovePageFormProps {
  /** 지금 경로 */
  from: string;
  /** 새 경로(제어형) */
  to: string;
  onToChange: (to: string) => void;
  rewriteLinks: boolean;
  onRewriteLinksChange: (value: boolean) => void;
  /** 가장 최근 `dry_run` 결과(바뀔 페이지·링크). 호출자가 400ms 디바운스·요청 취소를 한다. */
  preview?: WikiMoveResult | null;
  previewLoading?: boolean;
  /** 적용 결과. 건너뛴 페이지(`conflicts`)가 있으면 닫지 않고 목록으로 보인다. */
  result?: WikiMoveResult | null;
  /** 칸 아래 서버 메시지(예: 이미 있는 페이지 409) */
  toError?: string | null;
  /** 저장 안 됨 등 막는 이유 — 있으면 제출이 `aria-disabled` */
  blockedReason?: string;
  readOnly?: boolean;
  readOnlyReason?: string;
  submitting?: boolean;
  onSubmit: () => void;
  onCancel?: () => void;
  /** 건너뛴 페이지의 [열기] */
  onOpenPage?: (path: string) => void;
  rowHeight?: number;
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

/** 미리보기의 합계: 바뀔 페이지 수와 링크 곳 수. */
export function moveTotals(r: WikiMoveResult | null | undefined): { pages: number; links: number } {
  const list = r?.rewritten ?? [];
  return { pages: list.length, links: list.reduce((n, p) => n + p.count, 0) };
}

/**
 * 이름 바꾸기·옮기기 폼(표현). 새 경로 · "링크도 고치기" · 바뀔 페이지 가상 목록(미리보기) · 충돌 목록.
 * 같은 경로면 제출이 막히고, 링크 고치기를 끄면 끊길 링크 수를 경고한다(개수는 미리보기의 `rewritten` 합).
 */
export function MovePageForm({
  from, to, onToChange, rewriteLinks, onRewriteLinksChange, preview = null, previewLoading = false, result = null, toError = null, blockedReason, readOnly = false, readOnlyReason,
  submitting = false, onSubmit, onCancel, onOpenPage, rowHeight = 32, messages, className,
}: MovePageFormProps) {
  const t = resolveMessages(messages);
  const base = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const same = to.trim() === "" || to === from;
  const reason = readOnly ? readOnlyReason : blockedReason;
  const blocked = same || readOnly || blockedReason !== undefined || submitting;
  const shown = result ?? preview;
  const totals = moveTotals(shown);
  const conflicts = result?.conflicts ?? [];
  return (
    <form
      className={`ac-wk-root ac-wk-form${className ? ` ${className}` : ""}`}
      onSubmit={(e) => {
        e.preventDefault();
        if (!blocked) onSubmit();
      }}
    >
      <p className="ac-wk-inline"><span className="ac-wk-muted">{t["move.from"]}</span> <span className="ac-wk-mono">{from}</span></p>
      <div className="ac-wk-field">
        <label htmlFor={`${base}-to`}>{t["move.to"]} *</label>
        <input
          id={`${base}-to`}
          className="ac-wk-input ac-wk-mono"
          value={to}
          disabled={submitting}
          autoComplete="off"
          aria-invalid={toError ? true : undefined}
          aria-describedby={toError ? `${base}-to-err` : undefined}
          onChange={(e) => onToChange(e.target.value)}
        />
        {toError ? <p id={`${base}-to-err`} className="ac-wk-field-error" role="alert">{toError}</p> : null}
      </div>
      <label className="ac-wk-radio">
        <input type="checkbox" checked={rewriteLinks} disabled={submitting} onChange={(e) => onRewriteLinksChange(e.target.checked)} />
        <span>{t["move.rewrite"]}</span>
      </label>
      <p className="ac-wk-muted ac-wk-hint">{t["move.rewrite.hint"]}</p>
      {result && conflicts.length > 0 ? (
        <p className="ac-wk-banner" data-tone="danger" role="alert">
          {formatMessage(t["move.conflicts"], { done: result.rewritten?.length ?? 0, skipped: conflicts.length })}
        </p>
      ) : null}
      {!rewriteLinks ? (
        <p className="ac-wk-banner" data-tone="warning" role="status">
          {formatMessage(t["move.willBreak"], { pages: totals.pages, links: totals.links })}
        </p>
      ) : (
        <div className="ac-wk-move-list" aria-busy={previewLoading || undefined}>
          <p className="ac-wk-inline ac-wk-muted" role="status">
            <span className="ac-wk-grow">{t["move.pages"]}</span>
            {previewLoading ? t["move.loading"] : preview || result ? formatMessage(t["move.totals"], totals) : null}
          </p>
          {shown && (shown.rewritten?.length ?? 0) > 0 ? (
            <VirtualList
              items={shown.rewritten ?? []}
              rowHeight={rowHeight}
              role="list"
              ariaLabel={t["move.pages"] ?? ""}
              height="min(240px, 40vh)"
              getKey={(p) => p.path}
              renderRow={(p, ctx) => (
                <div role="listitem" className="ac-wk-row" style={ctx.style}>
                  <span className="ac-wk-ellipsis ac-wk-grow ac-wk-mono" title={p.path}>{p.path}</span>
                  <span className="ac-wk-muted ac-wk-num">{formatMessage(t["move.count"], { n: p.count })}</span>
                </div>
              )}
            />
          ) : null}
        </div>
      )}
      {conflicts.length > 0 ? (
        <ul className="ac-wk-conflicts" aria-label={t["move.conflicts.label"]}>
          {conflicts.map((c) => (
            <li key={c} className="ac-wk-row" data-tone="danger">
              <span className="ac-wk-ellipsis ac-wk-grow ac-wk-mono" title={c}>{c}</span>
              <span className="ac-wk-muted">{t["move.conflict.row"]}</span>
              {onOpenPage ? <button type="button" className="ac-wk-linkbtn" onClick={() => onOpenPage(c)}>{t["move.conflict.open"]}</button> : null}
            </li>
          ))}
        </ul>
      ) : null}
      <div className="ac-wk-form-foot">
        <span className="ac-wk-grow ac-wk-muted">{reason ?? ""}</span>
        {onCancel ? <button type="button" className="ac-wk-btn" onClick={onCancel}>{t["common.cancel"]}</button> : null}
        <button type="submit" className="ac-wk-btn" data-primary="" aria-disabled={blocked || undefined} title={reason}>
          {submitting ? t["move.submitting"] : t["move.submit"]}
        </button>
      </div>
    </form>
  );
}
