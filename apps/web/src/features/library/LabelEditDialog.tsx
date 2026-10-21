import { useRef, useState } from "react";
import { Button, Dialog } from "@agent-console/ui";

export interface LabelEditMessages {
  title: string;
  target: (name: string) => string;
  input: string;
  remove: (label: string) => string;
  empty: string;
  save: string;
  cancel: string;
}

export interface LabelEditDialogProps {
  open: boolean;
  itemName: string;
  labels: readonly string[];
  busy?: boolean;
  onSave: (labels: string[]) => void;
  onClose: () => void;
  messages: LabelEditMessages;
}

/** 라벨 칩 편집 대화상자(열 때마다 새로 마운트해 초기값을 받는다): `Enter` 추가, 입력이 비었을 때 `Backspace`로 마지막 삭제. 저장은 호출자가 한다. */
export function LabelEditDialog({ open, itemName, labels, busy, onSave, onClose, messages: m }: LabelEditDialogProps) {
  const [draft, setDraft] = useState<string[]>([...labels]);
  const [text, setText] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const add = () => {
    const t = text.trim();
    if (t !== "" && !draft.includes(t)) setDraft([...draft, t]);
    setText("");
  };
  return (
    <Dialog
      open={open}
      title={m.title}
      size="sm"
      onClose={onClose}
      initialFocus={input}
      actions={
        <>
          <Button onClick={onClose}>{m.cancel}</Button>
          <Button variant="primary" disabled={busy} onClick={() => onSave(text.trim() !== "" && !draft.includes(text.trim()) ? [...draft, text.trim()] : draft)}>{m.save}</Button>
        </>
      }
    >
      <p className="app-muted">{m.target(itemName)}</p>
      <ul className="lib-chip-list" aria-label={m.title}>
        {draft.length === 0 ? <li className="app-muted">{m.empty}</li> : null}
        {draft.map((l) => (
          <li key={l} className="lib-chip-item">
            <span>{l}</span>
            <button type="button" aria-label={m.remove(l)} onClick={() => setDraft(draft.filter((x) => x !== l))}>×</button>
          </li>
        ))}
      </ul>
      <input
        ref={input}
        className="ac-input"
        aria-label={m.input}
        placeholder={m.input}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.nativeEvent.isComposing) return;
          if (e.key === "Enter") {
            e.preventDefault();
            add();
          } else if (e.key === "Backspace" && text === "" && draft.length > 0) setDraft(draft.slice(0, -1));
        }}
      />
    </Dialog>
  );
}
