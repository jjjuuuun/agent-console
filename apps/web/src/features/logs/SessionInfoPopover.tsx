import type { ReactNode } from "react";
import type { LogSessionSummary } from "@agent-console/contracts";
import { Button, Popover } from "@agent-console/ui";
import { logsMessages as t } from "./messages";

export interface SessionInfoPopoverProps {
  session: string;
  summary: LogSessionSummary | undefined;
  /** 이 화면이 센 오류 수(분류 체계 기준) */
  errorCount: number;
  eventCount: number;
  durationMs: number | null;
  open: boolean;
  onOpenChange(open: boolean): void;
  onCopy(text: string): void;
}

const nf = (n: number) => n.toLocaleString("ko-KR");

/** [세션 정보 ▾]: 헤더 한 줄에 못 넣는 값(시작·길이·에이전트·모델·토큰 상세·전체 id·프로젝트 경로)을 비모달 팝오버로 보인다. 값이 없으면 "–". */
export function SessionInfoPopover({ session, summary, errorCount, eventCount, durationMs, open, onOpenChange, onCopy }: SessionInfoPopoverProps) {
  const tok = summary?.tokens;
  const rows: { label: string; value: ReactNode }[] = [
    { label: t.detail.sessionId, value: (<><code className="logs-mono ac-mono-wrap">{session}</code> <Button size="sm" variant="ghost" onClick={() => onCopy(session)}>{t.copy}</Button></>) },
    { label: t.detail.project, value: summary?.project || summary?.cwd ? (<>{summary.project ? <span title={summary.project.id}>{summary.project.label || summary.project.id}</span> : null}{summary.cwd ? <code className="logs-mono ac-mono-wrap">{summary.cwd}</code> : null}</>) : t.dash },
    { label: t.detail.start, value: summary?.first_time != null ? new Date(summary.first_time * 1000).toLocaleString("ko-KR") : t.dash },
    { label: t.detail.length, value: durationMs !== null ? `${Math.round(durationMs / 1000)}${t.detail.seconds}` : t.dash },
    { label: t.detail.agents, value: summary?.thread_count != null ? String(summary.thread_count) : t.dash },
    { label: t.detail.models, value: summary?.models && summary.models.length > 0 ? summary.models.map((m) => <span key={m} className="logs-chip">{m}</span>) : t.dash },
    {
      label: t.detail.tokens,
      value:
        tok?.total != null ? (
          <>
            <span>{nf(tok.total)}</span>
            <span className="app-muted">{t.detail.info.tokensBreakdown(tok.input != null ? nf(tok.input) : t.dash, tok.output != null ? nf(tok.output) : t.dash, tok.cache_read != null ? nf(tok.cache_read) : t.dash, tok.cache_creation != null ? nf(tok.cache_creation) : t.dash)}</span>
          </>
        ) : (
          t.dash
        ),
    },
    { label: t.detail.events, value: nf(summary?.events ?? eventCount) },
    { label: t.detail.errors, value: nf(errorCount) },
  ];
  return (
    <Popover
      open={open}
      onOpenChange={onOpenChange}
      panelRole="dialog"
      panelLabel={t.detail.info.title}
      align="end"
      panelClassName="logs-infopop"
      renderTrigger={(p) => (
        <button {...p} type="button" className="ac-btn" data-variant="secondary" data-size="sm" aria-label={t.detail.infoButton} title={`${t.detail.infoButton} (I)`}>
          <span className="logs-wide">{t.detail.infoButton}</span>
          <span className="logs-narrow">{t.detail.infoShort}</span> ▾
        </button>
      )}
    >
      <dl className="logs-info">
        {rows.map((r) => (
          <div key={r.label} className="logs-info-row">
            <dt>{r.label}</dt>
            <dd>{r.value}</dd>
          </div>
        ))}
      </dl>
    </Popover>
  );
}
