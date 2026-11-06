/** 스펙 이름 바꾸기 대화상자(screen-sdd §5 머리 메뉴·§3 행 메뉴 공용). 저장은 `onSubmit`이 하고, 실패는 던지면 이 대화상자가 문구를 보인다. */
import { useState } from "react";
import { Button, Dialog } from "@agent-console/ui";
import { describeError } from "../../app/errors";
import { sddMessages as m } from "./messages";

export interface SpecRenameDialogProps {
  open: boolean;
  /** 열 때 칸에 채울 지금 이름 */
  initialName: string;
  onClose: () => void;
  /** 새 이름(앞뒤 공백 제거, 비어 있지 않음). 성공하면 호출자가 닫는다 */
  onSubmit: (name: string) => Promise<void>;
}

export function SpecRenameDialog({ open, initialName, onClose, onSubmit }: SpecRenameDialogProps) {
  const [name, setName] = useState(initialName);
  const [error, setError] = useState<string | null>(null);
  const submit = async () => {
    if (name.trim() === "") return;
    try {
      await onSubmit(name.trim());
    } catch (e) {
      setError(describeError(e, m.problem.generic).message);
    }
  };
  return (
    <Dialog
      open={open}
      title={m.rename.title}
      onClose={onClose}
      actions={<><Button onClick={onClose}>{m.cancel}</Button><Button variant="primary" aria-disabled={name.trim() === "" || undefined} onClick={() => void submit()}>{m.rename.submit}</Button></>}
    >
      <label className="sdd-field">
        <span className="sdd-label">{m.rename.name}</span>
        <input className="sdd-input" value={name} onChange={(e) => setName(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.nativeEvent.isComposing) void submit(); }} />
      </label>
      {error === null ? null : <p className="app-field-error" role="alert">{error}</p>}
    </Dialog>
  );
}
