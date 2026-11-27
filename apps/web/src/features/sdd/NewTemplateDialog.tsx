/** 새 문서 틀 대화상자(screen-sdd §11.1): 이름* + 고급(id, 설명). 제출은 props이고 실패는 던진다(서버 문장이 맨 위 배너에 보인다). 한글 조합 중 Enter는 제출하지 않는다. */
import { useId, useRef, useState } from "react";
import { Banner, Button, Dialog, Disclosure } from "@agent-console/ui";
import type { SpecTemplateCreateRequest } from "@agent-console/contracts/sdd";
import { isReservedId } from "../library";
import { useErrorState, raised } from "../../app/errors";
import { useImeGuard } from "../../lib/ime";
import { SDD_LIMITS } from "./sddConfig";
import { useT } from "@agent-console/i18n";

export interface NewTemplateDialogProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (body: SpecTemplateCreateRequest) => Promise<void>;
  /** 문서 틀 id로 쓸 수 없는 말(서버 `SddInfo.reserved_template_ids`). 없으면 검사하지 않고 서버 거절 문구만 보인다 */
  reservedIds?: readonly string[] | undefined;
}

export function NewTemplateDialog({ open, onClose, onSubmit, reservedIds = [] }: NewTemplateDialogProps) {
  const t = useT("sdd");
  const [name, setName] = useState("");
  const [id, setId] = useState("");
  const [description, setDescription] = useState("");
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useErrorState(t("template.create.failed"));
  const ref = useRef<HTMLInputElement>(null);
  const ime = useImeGuard();
  const uid = useId();
  const missing = name.trim() === "";
  const reserved = isReservedId(id, reservedIds);

  const submit = async () => {
    setTouched(true);
    if (busy || missing || reserved) return;
    setBusy(true);
    setError(null);
    try {
      await onSubmit({ name: name.trim(), ...(id.trim() === "" ? {} : { id: id.trim() }), ...(description.trim() === "" ? {} : { description: description.trim() }) });
    } catch (e) {
      setError(raised(e));
      setBusy(false);
    }
  };
  const close = () => {
    if (!busy) onClose();
  };

  return (
    <Dialog
      open={open}
      title={t("template.create.title")}
      onClose={close}
      initialFocus={ref}
      actions={
        <>
          <Button onClick={close} disabled={busy}>{t("cancel")}</Button>
          <Button variant="primary" loading={busy} onClick={() => void submit()}>{busy ? t("template.create.submitting") : t("template.create.submit")}</Button>
        </>
      }
    >
      <div className="sdd-form" onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && !ime.isIme(e)) void submit(); }}>
        {error === null ? null : <Banner tone="danger">{error}</Banner>}
        <label className="sdd-field" htmlFor={`${uid}-name`}>
          <span className="sdd-label">{t("template.create.name")} *</span>
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
          {touched && missing ? <span className="app-field-error" role="alert">{t("template.create.nameRequired")}</span> : null}
        </label>
        <p className="app-muted">{t("template.create.hint")}</p>
        <Disclosure summary={t("template.create.advanced")}>
          <label className="sdd-field" htmlFor={`${uid}-id`}>
            <span className="sdd-label">{t("template.create.id")}</span>
            <input id={`${uid}-id`} className="sdd-input sdd-mono" placeholder={t("template.create.idAuto")} value={id} onChange={(e) => setId(e.target.value)} aria-invalid={reserved ? true : undefined} aria-describedby={reserved ? `${uid}-id-note` : undefined} />
            {reserved ? <span id={`${uid}-id-note`} className="app-field-error" role="alert">{t("template.create.idReserved")}</span> : null}
          </label>
          <label className="sdd-field" htmlFor={`${uid}-desc`}>
            <span className="sdd-label">{t("template.create.description")}</span>
            <input id={`${uid}-desc`} className="sdd-input" value={description} onChange={(e) => setDescription(e.target.value)} />
          </label>
        </Disclosure>
      </div>
    </Dialog>
  );
}
