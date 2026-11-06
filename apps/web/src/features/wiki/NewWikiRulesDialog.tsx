/** 새 위키 규칙 대화상자(screen-wiki §10.1): 이름* + 고급(id, 설명). 제출은 props이고 실패는 던진다(서버 문장이 맨 위 배너에 보인다). 한글 조합 중 Enter는 제출하지 않는다. */
import { useId, useRef, useState } from "react";
import { Banner, Button, Dialog, Disclosure } from "@agent-console/ui";
import { describeError } from "../../app/errors";
import { useImeGuard } from "../../lib/ime";
import { WIKI_RULES_SCREEN } from "./wikiConfig";
import { wikiRulesMessages } from "./rulesScreenMessages";

const t = wikiRulesMessages.newDialog;

/** 서버가 규칙 문서로 받는 최소 본문(종류 이름은 서버가 채운다). */
export interface NewWikiRulesBody {
  name: string;
  id?: string;
  description?: string;
}

export interface NewWikiRulesDialogProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (body: NewWikiRulesBody) => Promise<void>;
}

export function NewWikiRulesDialog({ open, onClose, onSubmit }: NewWikiRulesDialogProps) {
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
      setError(describeError(e, t.failed).message);
      setBusy(false);
    }
  };
  const close = () => {
    if (!busy) onClose();
  };

  return (
    <Dialog
      open={open}
      title={t.title}
      onClose={close}
      initialFocus={ref}
      actions={
        <>
          <Button onClick={close} disabled={busy}>{t.cancel}</Button>
          <Button variant="primary" loading={busy} onClick={() => void submit()}>{busy ? t.creating : t.create}</Button>
        </>
      }
    >
      <div className="wiki-form" onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && !ime.isIme(e)) void submit(); }}>
        {error === null ? null : <Banner tone="danger">{error}</Banner>}
        <label className="wiki-field" htmlFor={`${uid}-name`}>
          <span className="wiki-label">{t.name} *</span>
          <input
            id={`${uid}-name`}
            ref={ref}
            className="wiki-input"
            maxLength={WIKI_RULES_SCREEN.nameMax}
            placeholder={t.namePlaceholder}
            value={name}
            aria-required="true"
            aria-invalid={touched && missing ? true : undefined}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.ctrlKey && !e.metaKey && !ime.isIme(e)) void submit(); }}
            {...ime.handlers}
          />
          {touched && missing ? <span className="app-field-error" role="alert">{t.needName}</span> : null}
        </label>
        <Disclosure summary={t.advanced}>
          <label className="wiki-field" htmlFor={`${uid}-id`}>
            <span className="wiki-label">{t.id}</span>
            <input id={`${uid}-id`} className="wiki-input wiki-mono" value={id} onChange={(e) => setId(e.target.value)} />
            <span className="app-muted wiki-hint">{t.idHint}</span>
          </label>
          <label className="wiki-field" htmlFor={`${uid}-desc`}>
            <span className="wiki-label">{t.description}</span>
            <input id={`${uid}-desc`} className="wiki-input" value={description} onChange={(e) => setDescription(e.target.value)} />
          </label>
        </Disclosure>
      </div>
    </Dialog>
  );
}
