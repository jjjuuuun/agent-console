/** 틀로 저장 대화상자(screen-sdd §10.2): 이 스펙의 문서 목록과 규칙을 문서 틀로 복사한다(원본과 연결하지 않음). 제출은 props. */
import { useId, useRef, useState } from "react";
import { Banner, Button, Choice, Dialog, Disclosure } from "@agent-console/ui";
import type { SaveAsTemplateRequest, TemplateConflictPolicy } from "@agent-console/contracts/sdd";
import { describeError } from "../../app/errors";
import { sddMessages as m } from "./messages";

export interface SaveTemplateDialogProps {
  open: boolean;
  onClose: () => void;
  initialName: string;
  onSubmit: (body: SaveAsTemplateRequest) => Promise<void>;
}

const POLICIES: readonly { id: TemplateConflictPolicy; label: string }[] = [
  { id: "fail", label: m.saveTemplate.conflictFail },
  { id: "overwrite", label: m.saveTemplate.conflictOverwrite },
  { id: "rename", label: m.saveTemplate.conflictRename },
];

export function SaveTemplateDialog({ open, onClose, initialName, onSubmit }: SaveTemplateDialogProps) {
  const [name, setName] = useState(initialName);
  const [id, setId] = useState("");
  const [include, setInclude] = useState(false);
  const [policy, setPolicy] = useState<TemplateConflictPolicy>("fail");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLInputElement>(null);
  const uid = useId();
  const submit = async () => {
    if (busy || name.trim() === "") return;
    setBusy(true);
    setError(null);
    try {
      await onSubmit({ name: name.trim(), ...(id.trim() === "" ? {} : { id: id.trim() }), include_content: include, on_conflict: policy });
    } catch (e) {
      setError(describeError(e, m.problem.generic).message);
      setBusy(false);
    }
  };
  return (
    <Dialog
      open={open}
      title={m.saveTemplate.title}
      onClose={() => { if (!busy) onClose(); }}
      initialFocus={ref}
      actions={
        <>
          <Button onClick={onClose} disabled={busy}>{m.cancel}</Button>
          <Button variant="primary" loading={busy} aria-disabled={name.trim() === "" || undefined} onClick={() => void submit()}>{m.saveTemplate.submit}</Button>
        </>
      }
    >
      <div className="sdd-form">
        {error === null ? null : <Banner tone="danger">{error}</Banner>}
        <label className="sdd-field" htmlFor={`${uid}-name`}>
          <span className="sdd-label">{m.saveTemplate.name} *</span>
          <input id={`${uid}-name`} ref={ref} className="sdd-input" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <fieldset className="sdd-field">
          <legend className="sdd-label">{m.saveTemplate.content}</legend>
          <Choice kind="radio" name={`${uid}-c`} checked={!include} onChange={() => setInclude(false)}>{m.saveTemplate.contentBlank}</Choice>
          <Choice kind="radio" name={`${uid}-c`} checked={include} onChange={() => setInclude(true)}>{m.saveTemplate.contentInclude}</Choice>
        </fieldset>
        <Disclosure summary={m.saveTemplate.advanced}>
          <label className="sdd-field" htmlFor={`${uid}-id`}>
            <span className="sdd-label">{m.saveTemplate.id}</span>
            <input id={`${uid}-id`} className="sdd-input sdd-mono" value={id} onChange={(e) => setId(e.target.value)} />
          </label>
          <fieldset className="sdd-field">
            <legend className="sdd-label">{m.saveTemplate.conflict}</legend>
            {POLICIES.map((p) => <Choice key={p.id} kind="radio" name={`${uid}-p`} checked={policy === p.id} onChange={() => setPolicy(p.id)}>{p.label}</Choice>)}
          </fieldset>
        </Disclosure>
        <p className="app-muted">{m.saveTemplate.note}</p>
      </div>
    </Dialog>
  );
}
