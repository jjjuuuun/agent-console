import type { CSSProperties, ReactNode } from "react";
import type { LogViewMessages } from "./messages";
import type { ListSlots } from "./types";

/** 범주 색 점 + 이름 칩. 색 단독 의미 금지: 이름 텍스트가 항상 함께 있다. */
export function CategoryChip({ name, color, title }: { name: string; color?: string; title?: string }) {
  return (
    <span className="ac-lv-chip" title={title ?? name}>
      {color ? <span className="ac-lv-dot" style={{ background: color }} aria-hidden="true" /> : null}
      <span className="ac-lv-ellipsis">{name}</span>
    </span>
  );
}

export function NeutralChip({ children, title }: { children: ReactNode; title?: string }) {
  return (
    <span className="ac-lv-chip" title={title}>
      <span className="ac-lv-ellipsis">{children}</span>
    </span>
  );
}

export function ErrorIcon() {
  return (
    <svg className="ac-lv-erricon" width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
      <circle cx="7" cy="7" r="6" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <path d="M4.8 4.8l4.4 4.4M9.2 4.8l-4.4 4.4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export function Skeleton({ rows = 3, label, style }: { rows?: number; label: string; style?: CSSProperties }) {
  return (
    <div className="ac-lv-skeleton" role="status" aria-label={label} style={style}>
      {Array.from({ length: rows }, (_, i) => (
        <span key={i} className="ac-lv-skeleton-row" />
      ))}
    </div>
  );
}

/** 영역 오류 블록: `message` + [다시 시도] + 접힌 상세. */
export function ErrorBlock({ error, onRetry, m }: { error: { message: string; detail?: string }; onRetry?: (() => void) | undefined; m: LogViewMessages }) {
  return (
    <div className="ac-lv-error" role="alert">
      <strong>{m.errorTitle}</strong>
      <span>{error.message}</span>
      {error.detail ? (
        <details>
          <summary>{m.more}</summary>
          <code>{error.detail}</code>
        </details>
      ) : null}
      {onRetry ? (
        <button type="button" className="ac-lv-btn" onClick={onRetry}>
          {m.retry}
        </button>
      ) : null}
    </div>
  );
}

/** 공통 목록 상태. 상태가 있으면 그 블록을, 없으면 null. */
export function listStateBlock(slots: ListSlots, count: number, m: LogViewMessages, skeletonRows = 8): ReactNode {
  if (slots.error) return slots.renderError ? slots.renderError(slots.error, slots.onRetry) : <ErrorBlock error={slots.error} onRetry={slots.onRetry} m={m} />;
  if (slots.loading && count === 0) return slots.renderLoading ? slots.renderLoading() : <Skeleton rows={skeletonRows} label={m.loading} />;
  if (!slots.loading && count === 0) return slots.renderEmpty ? slots.renderEmpty() : <p className="ac-lv-empty">{m.empty}</p>;
  return null;
}
