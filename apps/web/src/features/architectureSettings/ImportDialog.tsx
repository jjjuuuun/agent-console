import { useMemo, useState } from "react";
import { Button, Dialog } from "@agent-console/ui";
import { archSettingsMessages as t } from "./messages";
import { parseProfileYaml } from "./yamlProfile";

export interface ImportDialogProps {
  /** 붙여 넣은 YAML을 편집기로 가져온다(문제가 있어도 가져올 수 있다) */
  onImport: (text: string) => void;
  onCancel: () => void;
}

/** YAML 붙여넣기 다이얼로그. [검사]는 형식만 본다(내용 검사는 편집기가 서버에 맡긴다). */
export function ImportDialog({ onImport, onCancel }: ImportDialogProps) {
  const [text, setText] = useState("");
  const [checked, setChecked] = useState(false);
  const parsed = useMemo(() => parseProfileYaml(text), [text]);
  const message = parsed.ok ? null : parsed.message === "" ? t.editor.notMap : parsed.message;
  return (
    <Dialog
      open
      size="lg"
      title={t.dialog.importTitle}
      onClose={onCancel}
      actions={
        <>
          <Button onClick={onCancel}>{t.dialog.cancel}</Button>
          <Button onClick={() => setChecked(true)}>{t.dialog.importCheck}</Button>
          <Button variant="primary" disabled={text.trim() === ""} onClick={() => onImport(text)}>{t.dialog.importToEditor}</Button>
        </>
      }
    >
      <label className="arch-settings-label">
        {t.dialog.importPaste}
        <textarea className="arch-settings-input arch-settings-mono arch-settings-paste" rows={12} value={text} onChange={(e) => { setText(e.target.value); setChecked(false); }} />
      </label>
      {checked ? (
        message === null ? <p role="status" className="arch-settings-ok">{t.editor.ok}</p> : <p role="alert" className="arch-settings-warn">{t.dialog.importParse}: {message}</p>
      ) : null}
    </Dialog>
  );
}
