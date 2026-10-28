import { useState, type ReactNode } from "react";
import { Banner, Button, Popover, type Tone } from "@agent-console/ui";
import { messages as appMessages } from "../../app/messages";
import { logsMessages as t } from "./messages";

/** 알림 한 건(데이터). `priority`가 작을수록 먼저 보인다(같으면 `id` 순서 유지). */
export interface LogNotice {
  id: string;
  priority: number;
  tone: Tone;
  /** 줄 안에서는 한 줄로 줄이고, 전체는 툴팁(`title`)으로 본다 */
  text: ReactNode;
  title?: string;
  className?: string;
  /** 줄 안 버튼(예: 새로 고침) */
  action?: { label: string; onClick: () => void };
  /** 있으면 [닫기]를 보인다 */
  onDismiss?: () => void;
}

/** 우선순위로 정렬한다(안정 정렬). 순수 함수 — 정렬 규칙은 호출자가 주는 `priority` 숫자뿐이다. */
export function sortNotices(notices: readonly LogNotice[]): LogNotice[] {
  return notices.map((n, i) => ({ n, i })).sort((a, b) => a.n.priority - b.n.priority || a.i - b.i).map((x) => x.n);
}

function NoticeBanner({ notice, wrap = false }: { notice: LogNotice; wrap?: boolean }) {
  const { action, onDismiss } = notice;
  return (
    <Banner
      role={undefined}
      tone={notice.tone}
      className={["logs-notice", wrap ? "logs-notice--wrap" : "", notice.className ?? ""].filter(Boolean).join(" ")}
      actions={
        action === undefined && onDismiss === undefined ? undefined : (
          <>
            {action === undefined ? null : <Button size="sm" onClick={action.onClick}>{action.label}</Button>}
            {onDismiss === undefined ? null : <Button size="sm" variant="ghost" onClick={onDismiss}>{appMessages.hints.dismiss}</Button>}
          </>
        )
      }
    >
      <span className={wrap ? "logs-notice-text" : "logs-notice-text ac-ellipsis"} title={notice.title}>{notice.text}</span>
    </Banner>
  );
}

export interface NoticeBarProps {
  notices: readonly LogNotice[];
}

/**
 * 알림 줄: 배너 여러 개를 쌓지 않고 우선순위가 가장 높은 하나만 한 줄(32px)로 보인다. 나머지는 "외 n건 [모두 보기 ▾]" 팝오버에 세로로 나열하며
 * 각자의 버튼과 [닫기]가 그대로 동작한다. 알림이 없으면 아무것도 그리지 않는다(세로 공간 0). 영역은 `role="status"` `aria-live="polite"`.
 */
export function NoticeBar({ notices }: NoticeBarProps) {
  const [open, setOpen] = useState(false);
  const sorted = sortNotices(notices);
  const [first, ...rest] = sorted;
  if (first === undefined) return null;
  return (
    <div className="logs-noticebar" role="status" aria-live="polite" data-testid="logs-noticebar">
      <NoticeBanner notice={first} />
      {rest.length === 0 ? null : (
        <Popover
          open={open}
          onOpenChange={setOpen}
          panelRole="dialog"
          panelLabel={t.notice.showAll}
          align="end"
          panelClassName="logs-notice-pop"
          renderTrigger={(p) => (
            <button {...p} type="button" className="ac-btn logs-notice-more" data-variant="ghost" data-size="sm">
              {t.notice.more(rest.length)} <span aria-hidden="true">·</span> {t.notice.showAll} ▾
            </button>
          )}
        >
          <ul className="logs-notice-list">
            {rest.map((n) => (
              <li key={n.id}><NoticeBanner notice={n} wrap /></li>
            ))}
          </ul>
        </Popover>
      )}
    </div>
  );
}
