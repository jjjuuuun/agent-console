import { Button, Spinner } from "@agent-console/ui";
import { teamMessages as t } from "./messages";

export interface DraftNoticeProps {
  /** 지금 보이는 결과가 저장 전 초안 기준인가 */
  isDraft: boolean;
  /** 초안 계산 중 */
  updating?: boolean;
  /** 계산 실패(마지막 성공 결과는 호출자가 유지한다). 서버 메시지는 그대로 보인다 */
  error?: Error | null;
  onRetry?: () => void;
}

/** 초안 기준 결과 위의 알림: `저장 전 초안 기준` 칩, 갱신 중 스피너, 실패 줄 + [다시 시도]. 초안이 아니면 아무것도 그리지 않는다. */
export function DraftNotice({ isDraft, updating = false, error = null, onRetry }: DraftNoticeProps) {
  if (!isDraft) return null;
  return (
    <div className="team-draft-notice">
      <span className="app-sev team-draft-chip" data-severity="info">
        <span aria-hidden="true">ℹ</span> {t.draft.chip}
      </span>
      {updating ? (
        <span role="status" className="app-muted team-draft-updating">
          <Spinner /> <span className="ac-sr-only">{t.draft.updating}</span>
        </span>
      ) : null}
      {error ? (
        <span role="alert" className="app-sev" data-severity="error">
          {t.draft.failed}
          {error.message ? <span className="app-muted"> ({error.message})</span> : null}{" "}
          {onRetry ? <Button size="sm" onClick={onRetry}>{t.draft.retry}</Button> : null}
        </span>
      ) : null}
    </div>
  );
}
