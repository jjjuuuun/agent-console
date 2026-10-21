import { useState } from "react";
import { Banner, Button, Dialog } from "@agent-console/ui";
import { libraryMessages as t } from "./messages";

export interface DeleteDialogProps {
  open: boolean;
  /** 지울 대상 이름 */
  name: string;
  /** 지우면 영향을 받는 곳(이름 목록). 있으면 "이해했습니다"를 눌러야 지울 수 있다 */
  references?: readonly string[];
  /** 대상별 추가 안내 문구(예: 이 팀으로 만든 대화 n개의 기록은 남습니다) */
  note?: string;
  busy?: boolean;
  error?: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}

/** 삭제 확인(`screens.md` 4.3). 사용처가 있으면 목록을 보여 주고 확인 체크를 요구한다. 열 때마다 새로 시작하도록 `open`일 때만 렌더한다. */
export function DeleteDialog({ open, name, references = [], note, busy, error, onConfirm, onCancel }: DeleteDialogProps) {
  const [understood, setUnderstood] = useState(false);
  const needsAck = references.length > 0;
  return (
    <Dialog
      open={open}
      title={t.delete.title(name)}
      onClose={onCancel}
      actions={
        <>
          <Button onClick={onCancel}>{t.cancel}</Button>
          <Button variant="danger" loading={busy === true} disabled={needsAck && !understood} onClick={onConfirm}>
            {t.delete.action}
          </Button>
        </>
      }
    >
      <div className="lib-form">
        {error ? <Banner tone="danger">{error}</Banner> : null}
        <p className="ac-text">{t.delete.body}</p>
        {note ? <p className="ac-text">{note}</p> : null}
        {needsAck ? (
          <>
            <p className="ac-text">{t.delete.usedBy(references.length)}</p>
            <ul className="lib-ref-list">
              {references.map((r, i) => (
                <li key={`${i}:${r}`}>{r}</li>
              ))}
            </ul>
            <label className="app-check">
              <input type="checkbox" checked={understood} onChange={(e) => setUnderstood(e.target.checked)} />
              {t.delete.understood}
            </label>
          </>
        ) : null}
      </div>
    </Dialog>
  );
}
