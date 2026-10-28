import { useId, useMemo, useRef, useState } from "react";
import type { Issue } from "@agent-console/contracts";
import { Button, Dialog } from "@agent-console/ui";
import { IssueList } from "./IssueList";
import { LIMITS } from "./memorySettingsConfig";
import { memorySettingsMessages as t } from "./messages";
import { useDebouncedCheck } from "./useDebouncedCheck";

export type KindEditorMode = "new" | "edit" | "view" | "clone";

export interface KindEditorValue {
  id: string;
  label: string;
  description: string;
  template: string;
}

export interface KindEditorDialogProps {
  mode: KindEditorMode;
  title: string;
  initial: KindEditorValue;
  /** 이미 목록에 있는 id(새 종류·복제에서 같은 id면 덮어쓴다는 안내) */
  takenIds: ReadonlySet<string>;
  /** 틀 입력 아래 칩(서버 스키마의 예시). 비면 칩 줄이 없다 */
  examples: readonly string[];
  /** 편집 중인 값을 설정 섹션에 넣어 서버 검사한다(저장을 막지 않는다) */
  check: (value: KindEditorValue) => Promise<readonly Issue[]>;
  onApply: (value: KindEditorValue) => void;
  onClose: () => void;
  /** 검사 지연(ms, 테스트에서 줄인다) */
  checkDelayMs?: number;
}

/** 범위 종류 편집기(대화상자). 서버 검사는 입력이 멈춘 뒤 자동이고 오류가 있으면 [적용]이 꺼진다. 서버 호출은 `check`로 받는다. */
export function KindEditorDialog({ mode, title, initial, takenIds, examples, check, onApply, onClose, checkDelayMs = LIMITS.checkDelayMs }: KindEditorDialogProps) {
  const [value, setValue] = useState(initial);
  const [composing, setComposing] = useState(false);
  const readOnly = mode === "view";
  const idEditable = mode === "new" || mode === "clone";
  const templateRef = useRef<HTMLInputElement>(null);
  const ids = { label: useId(), id: useId(), description: useId(), template: useId(), help: useId() };
  const id = value.id.trim();
  const labelOk = value.label.trim() !== "";
  const runnable = !readOnly && id !== "" && labelOk;
  const key = useMemo(() => JSON.stringify([id, value.label, value.description, value.template]), [id, value.label, value.description, value.template]);
  const result = useDebouncedCheck(key, () => check({ ...value, id }), runnable, checkDelayMs, composing);
  const errors = result.issues.filter((i) => i.severity === "error").length;
  const blocked = readOnly || !runnable || result.phase === "checking" || errors > 0;
  const set = (patch: Partial<KindEditorValue>) => setValue((v) => ({ ...v, ...patch }));
  const insert = (text: string) => {
    const el = templateRef.current;
    const at = el?.selectionStart ?? value.template.length;
    const end = el?.selectionEnd ?? at;
    set({ template: value.template.slice(0, at) + text + value.template.slice(end) });
  };
  const warn = idEditable && id !== "" && takenIds.has(id) ? t.kindEditor.idTaken : null;
  return (
    <Dialog
      open
      size="lg"
      title={title}
      onClose={onClose}
      actions={
        <>
          <Button onClick={onClose}>{readOnly ? t.close : t.cancel}</Button>
          {readOnly ? null : <Button variant="primary" disabled={blocked} onClick={() => onApply({ ...value, id })}>{t.apply}</Button>}
        </>
      }
    >
      <form
        className="memset-form"
        onSubmit={(e) => { e.preventDefault(); if (!blocked) onApply({ ...value, id }); }}
        onCompositionStart={() => setComposing(true)}
        onCompositionEnd={() => setComposing(false)}
      >
        <label className="memset-label" htmlFor={ids.label}>{t.kindEditor.label}</label>
        <input id={ids.label} className="memset-input" value={value.label} readOnly={readOnly} onChange={(e) => set({ label: e.target.value })} aria-invalid={!labelOk || undefined} />
        <label className="memset-label" htmlFor={ids.id}>{t.kindEditor.id}</label>
        <input id={ids.id} className="memset-input memset-mono" value={value.id} readOnly={!idEditable} onChange={(e) => set({ id: e.target.value })} aria-describedby={idEditable ? ids.help : undefined} />
        {idEditable ? <p id={ids.help} className="memset-note app-muted">{t.kindEditor.idHelp}</p> : null}
        {warn === null ? null : <p className="memset-warn" role="status">{warn}</p>}
        <label className="memset-label" htmlFor={ids.description}>{t.kindEditor.description}</label>
        <input id={ids.description} className="memset-input" value={value.description} readOnly={readOnly} onChange={(e) => set({ description: e.target.value })} />
        <label className="memset-label" htmlFor={ids.template}>{t.kindEditor.template}</label>
        <input ref={templateRef} id={ids.template} className="memset-input memset-mono" value={value.template} readOnly={readOnly} onChange={(e) => set({ template: e.target.value })} />
        {readOnly || examples.length === 0 ? null : (
          <div className="memset-chips" role="group" aria-label={t.kindEditor.examples}>
            <span className="app-muted memset-note">{t.kindEditor.examples}</span>
            {examples.map((x) => (
              <button key={x} type="button" className="memset-chip" aria-label={t.kindEditor.insert(x)} onClick={() => insert(x)}>{x}</button>
            ))}
          </div>
        )}
        <p className="memset-note app-muted">{t.kindEditor.templateHelp}</p>
        {readOnly ? null : (
          <div className="memset-check" aria-live="polite">
            <h4 className="memset-subtitle">{t.kindEditor.issues}</h4>
            {!runnable ? <p className="memset-note app-muted">{id === "" ? t.kindEditor.idEmpty : t.kindEditor.labelEmpty}</p> : result.phase === "checking" ? (
              <p className="memset-note app-muted">{t.kindEditor.checking}</p>
            ) : result.phase === "failed" ? (
              <p className="memset-note memset-warn">{t.kindEditor.checkFailed} <Button size="sm" onClick={result.retry}>{t.retry}</Button></p>
            ) : result.issues.length === 0 ? (
              <p className="memset-note app-muted">{t.kindEditor.checkOk}</p>
            ) : (
              <IssueList issues={result.issues} label={t.kindEditor.issues} />
            )}
          </div>
        )}
      </form>
    </Dialog>
  );
}
