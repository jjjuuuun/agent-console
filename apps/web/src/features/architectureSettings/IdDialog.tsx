import { useRef, useState } from "react";
import { Button, Dialog } from "@agent-console/ui";
import { archSettingsMessages as t } from "./messages";

export interface IdDialogProps {
  title: string;
  defaultId: string;
  defaultTitle: string;
  /** 기본·플러그인 프로필 id(같은 id를 쓰면 덮어쓴다는 경고) */
  baseIds: ReadonlySet<string>;
  /** 이미 있는 사용자 프로필 id */
  userIds: ReadonlySet<string>;
  onConfirm: (id: string, title: string) => void;
  onCancel: () => void;
}

/** 새 id와 제목을 묻는 작은 다이얼로그(새 프로필·복제). id 글자 규칙은 서버 검사가 알린다. */
export function IdDialog({ title, defaultId, defaultTitle, baseIds, userIds, onConfirm, onCancel }: IdDialogProps) {
  const [id, setId] = useState(defaultId);
  const [name, setName] = useState(defaultTitle);
  const idRef = useRef<HTMLInputElement>(null);
  const trimmed = id.trim();
  const warn = baseIds.has(trimmed) ? t.dialog.sameId : userIds.has(trimmed) ? t.dialog.idTaken : null;
  const submit = () => {
    if (trimmed !== "") onConfirm(trimmed, name.trim());
  };
  return (
    <Dialog
      open
      size="sm"
      title={title}
      onClose={onCancel}
      initialFocus={idRef}
      actions={
        <>
          <Button onClick={onCancel}>{t.dialog.cancel}</Button>
          <Button variant="primary" disabled={trimmed === ""} onClick={submit}>{t.dialog.ok}</Button>
        </>
      }
    >
      <form className="arch-settings-idform" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <label className="arch-settings-label">
          {t.dialog.id}
          <input ref={idRef} className="arch-settings-input arch-settings-mono" value={id} onChange={(e) => setId(e.target.value)} aria-invalid={trimmed === "" || undefined} />
        </label>
        <label className="arch-settings-label">
          {t.dialog.profileTitle}
          <input className="arch-settings-input" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        {warn === null ? null : <p className="arch-settings-warn" role="status">{warn}</p>}
      </form>
    </Dialog>
  );
}
