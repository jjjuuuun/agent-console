import { useState } from "react";
import { Banner, Button, Dialog } from "@agent-console/ui";
import type { Issue } from "@agent-console/contracts";
import { scopeMessages } from "./scopeMessages";

const t = scopeMessages.settings;

export interface RecordsMoveOutcome {
  moved: number;
  skipped: number;
  failed: readonly Issue[];
}

export interface RecordsMoveDialogProps {
  projectName: string;
  folder: string;
  chats: number;
  runs: number;
  busy?: boolean | undefined;
  /** 마지막 시도 결과(실패가 있으면 닫지 않고 보인다) */
  outcome?: RecordsMoveOutcome | null | undefined;
  /** 요청 전체가 실패했을 때(409 등) 맨 위 오류 줄 */
  error?: string | null | undefined;
  onSubmit: (removeSource: boolean) => void;
  onClose: () => void;
}

/** 앱에 남은 기록을 프로젝트 폴더로 옮기는 대화상자(screen-projects §4.6.3). 표현 전용: 호출 순서(채팅 → 실행)는 호출자가 맡는다. */
export function RecordsMoveDialog({ projectName, folder, chats, runs, busy, outcome, error, onSubmit, onClose }: RecordsMoveDialogProps) {
  const [remove, setRemove] = useState(true);
  const total = chats + runs;
  const failed = outcome?.failed ?? [];
  return (
    <Dialog
      open
      title={t.moveTitle(projectName)}
      onClose={busy === true ? () => {} : onClose}
      actions={
        <>
          <Button onClick={onClose} disabled={busy === true}>{failed.length > 0 ? t.moveClose : t.assignCancel}</Button>
          <Button variant="primary" loading={busy === true} onClick={() => onSubmit(remove)}>{busy === true ? t.moveBusy : failed.length > 0 ? t.moveRetry : t.moveSubmit(total)}</Button>
        </>
      }
    >
      {error ? <Banner tone="danger">{error}</Banner> : null}
      {failed.length > 0 && outcome ? (
        <Banner tone="warning" title={t.movePartial(outcome.moved + failed.length, outcome.moved)}>
          <details>
            <summary>{t.moveFailures}</summary>
            <ul>{failed.map((f, i) => <li key={`${f.code}:${i}`}>{f.message}</li>)}</ul>
          </details>
        </Banner>
      ) : null}
      <p className="prj-mono prj-wrap" title={folder}>{folder}</p>
      <p>{t.moveScope(chats, runs)}</p>
      <label className="ac-choice">
        <input type="checkbox" checked={remove} onChange={(e) => setRemove(e.target.checked)} />
        <span>{t.moveRemove}</span>
      </label>
      <p className="app-muted prj-note">{t.moveRemoveHelp}</p>
      <ul className="app-muted prj-note">{t.moveNotes.map((n) => <li key={n}>{n}</li>)}</ul>
    </Dialog>
  );
}
