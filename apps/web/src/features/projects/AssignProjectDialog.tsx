import { useId, useState } from "react";
import { Button, Dialog } from "@agent-console/ui";
import { scopeMessages } from "./scopeMessages";

const t = scopeMessages.settings;

export interface AssignTarget {
  id: string;
  name: string;
  folder: string;
  /** 문제 상태 글자(있으면 고를 수 없다) */
  problem?: string | undefined;
  /** 서버가 이 프로젝트를 추천할 때 */
  recommended?: boolean | undefined;
}

export interface AssignProjectDialogProps {
  feature: string;
  count: number;
  targets: readonly AssignTarget[];
  /** 값이 있으면 "프로젝트 폴더에 바로 저장" 체크를 보이고 이 값이 기본(채팅·실행처럼 폴더 기록이 있는 기능만) */
  directDefault?: boolean | undefined;
  busy?: boolean | undefined;
  error?: string | null | undefined;
  onSubmit: (projectId: string, direct: boolean) => void;
  onClose: () => void;
}

/** 프로젝트 없는 이전 기록을 프로젝트에 넣는 대화상자(screen-projects §8.3). 표현 전용. */
export function AssignProjectDialog({ feature, count, targets, directDefault, busy, error, onSubmit, onClose }: AssignProjectDialogProps) {
  const name = useId();
  const sorted = [...targets].sort((a, b) => Number(b.recommended === true) - Number(a.recommended === true));
  const [picked, setPicked] = useState<string | null>(null);
  const [direct, setDirect] = useState(directDefault ?? false);
  return (
    <Dialog
      open
      title={t.assignTitle(feature, count)}
      onClose={busy === true ? () => {} : onClose}
      actions={
        <>
          <Button onClick={onClose} disabled={busy === true}>{t.assignCancel}</Button>
          <Button variant="primary" loading={busy === true} aria-disabled={picked === null} disabled={picked === null} onClick={() => picked !== null && onSubmit(picked, direct)}>{t.assignSubmit}</Button>
        </>
      }
    >
      <fieldset className="prj-assign-list">
        <legend className="ac-sr-only">{t.assignTitle(feature, count)}</legend>
        {sorted.map((x) => (
          <label key={x.id} className="ac-choice prj-assign-row" aria-disabled={x.problem !== undefined}>
            <input type="radio" name={name} value={x.id} checked={picked === x.id} disabled={x.problem !== undefined} onChange={() => setPicked(x.id)} />
            <span className="prj-assign-text">
              <span className="ac-ellipsis"><strong>{x.name}</strong> {x.recommended === true ? <span className="app-muted">{t.assignRecommended}</span> : null}</span>
              <span className="ac-ellipsis app-muted prj-mono" title={x.folder}>{x.folder}</span>
              {x.problem === undefined ? null : <span className="app-muted">{x.problem}</span>}
            </span>
          </label>
        ))}
      </fieldset>
      {directDefault === undefined ? null : (
        <label className="ac-choice">
          <input type="checkbox" checked={direct} onChange={(e) => setDirect(e.target.checked)} />
          <span>{t.assignDirect}</span>
        </label>
      )}
      <p className="app-muted prj-note">{t.assignNote(feature)}</p>
      {error ? <p role="alert" className="prj-danger-text">{error}</p> : null}
    </Dialog>
  );
}
