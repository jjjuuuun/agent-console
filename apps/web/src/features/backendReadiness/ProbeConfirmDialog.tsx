import { useId, useRef, useState } from "react";
import { Button, Dialog } from "@agent-console/ui";
import { messages as m } from "../../app/messages";

export interface ProbeConfirmDialogProps {
  open: boolean;
  /** 비용 안내(백엔드가 준 `probe_cost_note`, 없으면 `cost_note`). 빈 값이면 일반 문장만 */
  costNote?: string | undefined;
  onCancel: () => void;
  /** @param remember "다음부터 묻지 않기"를 체크했는가 */
  onConfirm: (remember: boolean) => void;
}

/** [연결 테스트] 확인 다이얼로그. 기본 포커스는 [테스트 실행](Enter), Esc는 취소. */
export function ProbeConfirmDialog({ open, costNote, onCancel, onConfirm }: ProbeConfirmDialogProps) {
  const t = m.backendReadiness;
  const runRef = useRef<HTMLButtonElement>(null);
  const [remember, setRemember] = useState(false);
  const checkId = useId();
  return (
    <Dialog
      open={open}
      size="sm"
      title={t.probeDialogTitle}
      onClose={onCancel}
      initialFocus={runRef}
      actions={
        <>
          <Button onClick={onCancel}>{t.probeDialogCancel}</Button>
          <Button ref={runRef} variant="primary" onClick={() => onConfirm(remember)}>
            {t.probeDialogRun}
          </Button>
        </>
      }
    >
      <p className="ac-text">{t.probeDialogBody}</p>
      {costNote ? <p className="app-muted" data-testid="probe-cost-note">{costNote}</p> : null}
      <label className="ac-choice" htmlFor={checkId}>
        <input id={checkId} type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
        <span>{t.probeDialogRemember}</span>
      </label>
    </Dialog>
  );
}
