/** 틀로 저장 대화상자(screen-sdd §10.2): 이 스펙의 문서 목록과 규칙을 문서 틀로 복사한다(원본과 연결하지 않음). 제출은 props. */
import { useId, useRef, useState } from "react";
import { Banner, Button, Choice, Dialog, Disclosure } from "@agent-console/ui";
import type { SaveAsTemplateRequest, TemplateConflictPolicy } from "@agent-console/contracts/sdd";
import { isReservedId } from "../library";
import { useErrorState, raised } from "../../app/errors";
import { useT } from "@agent-console/i18n";

export interface SaveTemplateDialogProps {
  open: boolean;
  onClose: () => void;
  initialName: string;
  onSubmit: (body: SaveAsTemplateRequest) => Promise<void>;
  /** 문서 틀 id로 쓸 수 없는 말(서버 `SddInfo.reserved_template_ids`). 없으면 검사하지 않고 서버 거절 문구만 보인다 */
  reservedIds?: readonly string[] | undefined;
}

/** 같은 id가 있을 때의 처리(계약 `TemplateConflictPolicy`) → 문구 키 */
const POLICIES: readonly { id: TemplateConflictPolicy; labelKey: string }[] = [
  { id: "fail", labelKey: "saveTemplate.conflictFail" },
  { id: "overwrite", labelKey: "saveTemplate.conflictOverwrite" },
  { id: "rename", labelKey: "saveTemplate.conflictRename" },
];

export function SaveTemplateDialog({ open, onClose, initialName, onSubmit, reservedIds = [] }: SaveTemplateDialogProps) {
  const t = useT("sdd");
  const [name, setName] = useState(initialName);
  const [id, setId] = useState("");
  const [include, setInclude] = useState(false);
  const [policy, setPolicy] = useState<TemplateConflictPolicy>("fail");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useErrorState(t("problem.generic"));
  const ref = useRef<HTMLInputElement>(null);
  const uid = useId();
  const reserved = isReservedId(id, reservedIds);
  const submit = async () => {
    if (busy || name.trim() === "" || reserved) return;
    setBusy(true);
    setError(null);
    try {
      await onSubmit({ name: name.trim(), ...(id.trim() === "" ? {} : { id: id.trim() }), include_content: include, on_conflict: policy });
    } catch (e) {
      setError(raised(e));
      setBusy(false);
    }
  };
  return (
    <Dialog
      open={open}
      title={t("saveTemplate.title")}
      onClose={() => { if (!busy) onClose(); }}
      initialFocus={ref}
      actions={
        <>
          <Button onClick={onClose} disabled={busy}>{t("cancel")}</Button>
          <Button variant="primary" loading={busy} aria-disabled={name.trim() === "" || reserved || undefined} onClick={() => void submit()}>{t("saveTemplate.submit")}</Button>
        </>
      }
    >
      <div className="sdd-form">
        {error === null ? null : <Banner tone="danger">{error}</Banner>}
        <label className="sdd-field" htmlFor={`${uid}-name`}>
          <span className="sdd-label">{t("saveTemplate.name")} *</span>
          <input id={`${uid}-name`} ref={ref} className="sdd-input" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <fieldset className="sdd-field">
          <legend className="sdd-label">{t("saveTemplate.content")}</legend>
          <Choice kind="radio" name={`${uid}-c`} checked={!include} onChange={() => setInclude(false)}>{t("saveTemplate.contentBlank")}</Choice>
          <Choice kind="radio" name={`${uid}-c`} checked={include} onChange={() => setInclude(true)}>{t("saveTemplate.contentInclude")}</Choice>
        </fieldset>
        <Disclosure summary={t("saveTemplate.advanced")}>
          <label className="sdd-field" htmlFor={`${uid}-id`}>
            <span className="sdd-label">{t("saveTemplate.id")}</span>
            <input id={`${uid}-id`} className="sdd-input sdd-mono" value={id} onChange={(e) => setId(e.target.value)} aria-invalid={reserved ? true : undefined} aria-describedby={reserved ? `${uid}-id-note` : undefined} />
            {reserved ? <span id={`${uid}-id-note`} className="app-field-error" role="alert">{t("saveTemplate.idReserved")}</span> : null}
          </label>
          <fieldset className="sdd-field">
            <legend className="sdd-label">{t("saveTemplate.conflict")}</legend>
            {POLICIES.map((p) => <Choice key={p.id} kind="radio" name={`${uid}-p`} checked={policy === p.id} onChange={() => setPolicy(p.id)}>{t(p.labelKey)}</Choice>)}
          </fieldset>
        </Disclosure>
        <p className="app-muted">{t("saveTemplate.note")}</p>
      </div>
    </Dialog>
  );
}
