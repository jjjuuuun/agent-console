import { useRef, useState } from "react";
import { Button, Dialog } from "@agent-console/ui";
import { versionMessages as t } from "./messages";

export interface RestoreIssue {
  path: string;
  message: string;
}

export interface RestoreDialogProps {
  open: boolean;
  /** 되돌릴 버전 해시 앞 8자 */
  hash8: string;
  /** 현재 -> 그 버전으로 바뀌는 수. 계산 중이면 undefined */
  summary: { fields: number; content: number } | undefined;
  /** 저장 안 된 변경이 있다 */
  dirty: boolean;
  busy: boolean;
  /** 422 저장 전 검사 실패: 서버 이슈(메시지 그대로) */
  issues: readonly RestoreIssue[] | null;
  /** 그 밖의 오류 문구(네트워크 등) */
  error: string | null;
  onConfirm: (message: string) => void;
  onCancel: () => void;
}

/** 되돌리기 확인(끌 수 없음). 기본 포커스는 [취소]. 확인·메시지 입력·오류 영역만 있고 서버를 모른다. */
export function RestoreDialog({ open, hash8, summary, dirty, busy, issues, error, onConfirm, onCancel }: RestoreDialogProps) {
  const cancel = useRef<HTMLButtonElement>(null);
  const [message, setMessage] = useState("");
  return (
    <Dialog
      open={open}
      title={t.restore.title(hash8)}
      onClose={busy ? () => {} : onCancel}
      initialFocus={cancel}
      actions={
        <>
          <Button ref={cancel} disabled={busy} onClick={onCancel}>
            {t.restore.cancel}
          </Button>
          <Button variant="primary" loading={busy} onClick={() => onConfirm(message.trim())}>
            {t.restore.confirm}
          </Button>
        </>
      }
    >
      <div className="ver-restore">
        <p className="ac-text">{t.restore.body}</p>
        <p className="app-muted ver-note" role="status">
          {summary === undefined ? t.restore.summaryLoading : t.restore.summary(summary.fields, summary.content)}
        </p>
        {dirty ? <p className="ver-warn">{t.restore.unsaved}</p> : null}
        <label className="ver-restore-message">
          <span>{t.restore.messageLabel}</span>
          <input className="ac-input" value={message} placeholder={t.restore.messagePlaceholder(hash8)} onChange={(e) => setMessage(e.target.value)} disabled={busy} />
        </label>
        <p className="app-muted ver-note">{t.restore.scope}</p>
        {issues !== null ? (
          <div role="alert" className="ver-issues">
            <p>
              <strong>{t.restore.issuesTitle}</strong> {t.restore.issuesHelp}
            </p>
            <ul>
              {issues.map((issue, i) => (
                <li key={i}>
                  {issue.path === "" ? null : <span className="lib-mono app-muted">{issue.path} </span>}
                  <span className="app-wrap">{issue.message}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {error !== null ? (
          <p role="alert" className="ver-error app-wrap">
            {error}
          </p>
        ) : null}
      </div>
    </Dialog>
  );
}
