/**
 * 키·범위 옮기기. `POST /memory/entries/{id}/move`(`to_scope`·`to_key`): 항목 id와 기록은 그대로 따라간다.
 * 같은 범위·키가 있으면 409 → 필드 아래 오류. 본문이 저장 안 된 상태면 옮길 수 없다(저장하지 않은 변경은 옮겨지지 않는다).
 */
import { useId, useRef, useState } from "react";
import { Button, Dialog } from "@agent-console/ui";
import { ApiError } from "@agent-console/api-client";
import type { MemoryEntry, MemoryEntrySummary, MemoryScopeKindInfo, MemoryScopeRef, MemoryScopeSummary } from "@agent-console/contracts/memory";
import { keyErrorText, sameScope, validateKey } from "@agent-console/memory-view";
import { useApi } from "../../app/ApiContext";
import { describeError } from "../../app/errors";
import { viewMessages } from "./format";
import { memoryMessages as t } from "./messages";
import { pickOf, pickedScope, ScopePicker, type ScopePickerState } from "./ScopePicker";
import { useMemoryContext } from "./useMemoryContext";

export interface MoveDialogProps {
  entry: MemoryEntry | MemoryEntrySummary;
  kinds: readonly MemoryScopeKindInfo[];
  scopes: readonly MemoryScopeSummary[];
  labelOf: (scope: MemoryScopeRef) => string;
  /** 본문에 저장하지 않은 변경이 있다 */
  dirty: boolean;
  onClose: () => void;
  onMoved: (entry: MemoryEntry) => void;
}

export function MoveDialog({ entry, kinds, scopes, labelOf, dirty, onClose, onMoved }: MoveDialogProps) {
  const { rest } = useApi();
  const ctx = useMemoryContext();
  const uid = useId();
  const keyRef = useRef<HTMLInputElement>(null);
  const [pick, setPick] = useState<ScopePickerState>(() => pickOf(entry.scope));
  const [key, setKey] = useState(entry.key);
  const [checked, setChecked] = useState(entry.key);
  const composing = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const target = pickedScope(pick, kinds);
  const keyCode = validateKey(checked);
  const keyError = keyCode === null ? null : keyErrorText(keyCode, checked, viewMessages);
  const changed = target !== null && (!sameScope(target, entry.scope) || key !== entry.key);
  const canMove = changed && keyCode === null && validateKey(key) === null && !dirty && !busy;

  const submit = async () => {
    if (!canMove || target === null) return;
    setBusy(true);
    setError(null);
    try {
      const moved = await rest.moveMemoryEntry(
        entry.id,
        { ...(sameScope(target, entry.scope) ? {} : { to_scope: target }), ...(key === entry.key ? {} : { to_key: key }) },
        entry.version,
      );
      onMoved(moved);
    } catch (e) {
      setError(e instanceof ApiError && e.status === 409 ? t.move.exists : describeError(e, t.move.failed).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open
      title={t.move.title}
      onClose={onClose}
      initialFocus={keyRef}
      actions={
        <>
          <Button onClick={onClose}>{t.cancel}</Button>
          <Button variant="primary" disabled={!canMove} loading={busy} onClick={() => void submit()}>{t.move.submit}</Button>
        </>
      }
    >
      <div className="mem-form">
        <p className="mem-move-current">
          <span className="mem-label">{t.move.current}</span> {labelOf(entry.scope)} / <span className="mem-mono">{entry.key}</span>
        </p>
        <ScopePicker label={t.move.toScope} kinds={kinds} scopes={scopes} state={pick} onChange={setPick} labelOf={labelOf} pickers={ctx.pickers} />
        <div className="mem-field">
          <label htmlFor={`${uid}-key`} className="mem-label">{t.move.toKey}</label>
          <input
            ref={keyRef}
            id={`${uid}-key`}
            className="mem-input mem-mono"
            value={key}
            aria-invalid={keyError !== null || error !== null}
            aria-describedby={`${uid}-err`}
            onCompositionStart={() => (composing.current = true)}
            onCompositionEnd={(e) => {
              composing.current = false;
              setChecked(e.currentTarget.value);
            }}
            onChange={(e) => {
              setKey(e.target.value);
              if (!composing.current) setChecked(e.target.value);
              setError(null);
            }}
          />
          <span id={`${uid}-err`} className="mem-error" role={keyError !== null || error !== null ? "alert" : undefined}>{keyError ?? error ?? ""}</span>
        </div>
        <p className="mem-help">{t.move.hint}</p>
        {dirty ? <p className="mem-error" role="alert">{t.move.dirty}</p> : null}
      </div>
    </Dialog>
  );
}
