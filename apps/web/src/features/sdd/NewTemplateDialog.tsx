/** 새 문서 틀 대화상자(screen-sdd §11.1): 이름* + 고급(id, 설명). 제출은 props이고 실패는 던진다(서버 문장이 맨 위 배너에 보인다). 한글 조합 중 Enter는 제출하지 않는다. */
import { useId, useRef, useState } from "react";
import { Banner, Button, Dialog, Disclosure } from "@agent-console/ui";
import type { SpecTemplateCreateRequest } from "@agent-console/contracts/sdd";
import { describeError } from "../../app/errors";
import { useImeGuard } from "../../lib/ime";
import { SDD_LIMITS } from "./sddConfig";
import { templateMessages as t } from "./templateMessages";
import { sddMessages as m } from "./messages";

export interface NewTemplateDialogProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (body: SpecTemplateCreateRequest) => Promise<void>;
}

export function NewTemplateDialog({ open, onClose, onSubmit }: NewTemplateDialogProps) {
  const [name, setName] = useState("");
  const [id, setId] = useState("");
  const [description, setDescription] = useState("");
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ref = useRef<HTMLInputElement>(null);
  const ime = useImeGuard();
  const uid = useId();
  const missing = name.trim() === "";

  const submit = async () => {
    setTouched(true);
    if (busy || missing) return;
    setBusy(true);
    setError(null);
    try {
      await onSubmit({ name: name.trim(), ...(id.trim() === "" ? {} : { id: id.trim() }), ...(description.trim() === "" ? {} : { description: description.trim() }) });
    } catch (e) {
      setError(describeError(e, t.create.failed).message);
      setBusy(false);
    }
  };
  const close = () => {
    if (!busy) onClose();
  };

  return (
    <Dialog
      open={open}
      title={t.create.title}
      onClose={close}
      initialFocus={ref}
      actions={
        <>
          <Button onClick={close} disabled={busy}>{m.cancel}</Button>
          <Button variant="primary" loading={busy} onClick={() => void submit()}>{busy ? t.create.submitting : t.create.submit}</Button>
        </>
      }
    >
      <div className="sdd-form" onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && !ime.isIme(e)) void submit(); }}>
        {error === null ? null : <Banner tone="danger">{error}</Banner>}
        <label className="sdd-field" htmlFor={`${uid}-name`}>
          <span className="sdd-label">{t.create.name} *</span>
          <input
            id={`${uid}-name`}
            ref={ref}
            className="sdd-input"
            maxLength={SDD_LIMITS.nameMax}
            value={name}
            aria-required="true"
            aria-invalid={touched && missing ? true : undefined}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.ctrlKey && !e.metaKey && !ime.isIme(e)) void submit(); }}
            {...ime.handlers}
          />
          {touched && missing ? <span className="app-field-error" role="alert">{t.create.nameRequired}</span> : null}
        </label>
        <p className="app-muted">{t.create.hint}</p>
        <Disclosure summary={t.create.advanced}>
          <label className="sdd-field" htmlFor={`${uid}-id`}>
            <span className="sdd-label">{t.create.id}</span>
            <input id={`${uid}-id`} className="sdd-input sdd-mono" placeholder={t.create.idAuto} value={id} onChange={(e) => setId(e.target.value)} />
          </label>
          <label className="sdd-field" htmlFor={`${uid}-desc`}>
            <span className="sdd-label">{t.create.description}</span>
            <input id={`${uid}-desc`} className="sdd-input" value={description} onChange={(e) => setDescription(e.target.value)} />
          </label>
        </Disclosure>
      </div>
    </Dialog>
  );
}
