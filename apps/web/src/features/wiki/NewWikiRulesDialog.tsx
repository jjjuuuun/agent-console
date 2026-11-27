/** 새 위키 규칙 대화상자(screen-wiki §10.1): 이름* + id(이름에서 제안, 직접 고침) + 고급(설명). 제출은 props이고 실패는 던진다(서버 문장이 맨 위 배너에 보인다). 한글 조합 중 Enter는 제출하지 않는다. */
import { useId, useRef, useState } from "react";
import { DefinitionIdField, useDefinitionId, useKindReservedIds } from "../library";
import { Banner, Button, Dialog, Disclosure } from "@agent-console/ui";
import { useErrorState, raised } from "../../app/errors";
import { useImeGuard } from "../../lib/ime";
import { WIKI_RULES_SCREEN } from "./wikiConfig";
import { useT } from "@agent-console/i18n";

/** 서버가 규칙 문서로 받는 최소 본문(종류 이름은 서버가 채운다). */
export interface NewWikiRulesBody {
  name: string;
  id: string;
  description?: string;
}

export interface NewWikiRulesDialogProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (body: NewWikiRulesBody) => Promise<void>;
  /** 이미 있는 규칙 id(중복을 입력 즉시 알린다) */
  existingIds: ReadonlySet<string>;
  /** 이름이 한글뿐일 때 id 제안에 쓸 기본 이름(`WikiInfo.rules_kind`). 모르면 생략 */
  fallbackId?: string;
  /** 규칙 문서의 정의 종류(`WikiInfo.rules_kind`). 주면 서버가 준 예약어를 id 칸이 입력 즉시 안내한다 */
  kind?: string | undefined;
}

export function NewWikiRulesDialog({ open, onClose, onSubmit, existingIds, fallbackId, kind }: NewWikiRulesDialogProps) {
  const t = useT("wiki");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useErrorState(t("rules.newDialog.failed"));
  const ref = useRef<HTMLInputElement>(null);
  const ime = useImeGuard();
  const uid = useId();
  const missing = name.trim() === "";
  const defId = useDefinitionId(name, existingIds, fallbackId ?? t("rules.newDialog.fallbackId"), useKindReservedIds(kind));

  // id가 규칙에 안 맞거나 겹치면 제출이 막힌다: disabled 대신 aria-disabled + 칸 아래 오류 문장 연결
  const idBlocked = defId.problem !== undefined;

  const submit = async () => {
    setTouched(true);
    if (busy || missing || defId.invalid) return;
    setBusy(true);
    setError(null);
    try {
      await onSubmit({ name: name.trim(), id: defId.id.trim(), ...(description.trim() === "" ? {} : { description: description.trim() }) });
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
      title={t("rules.newDialog.title")}
      onClose={close}
      initialFocus={ref}
      actions={
        <>
          <Button onClick={close} disabled={busy}>{t("rules.newDialog.cancel")}</Button>
          <Button variant="primary" loading={busy} aria-disabled={idBlocked || undefined} aria-describedby={idBlocked ? `${uid}-idnote` : undefined} onClick={() => void submit()}>{busy ? t("rules.newDialog.creating") : t("rules.newDialog.create")}</Button>
        </>
      }
    >
      <div className="wiki-form" onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && !ime.isIme(e)) void submit(); }}>
        {error === null ? null : <Banner tone="danger">{error}</Banner>}
        <label className="wiki-field" htmlFor={`${uid}-name`}>
          <span className="wiki-label">{t("rules.newDialog.name")} *</span>
          <input
            id={`${uid}-name`}
            ref={ref}
            className="wiki-input"
            maxLength={WIKI_RULES_SCREEN.nameMax}
            placeholder={t("rules.newDialog.namePlaceholder")}
            value={name}
            aria-required="true"
            aria-invalid={touched && missing ? true : undefined}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.ctrlKey && !e.metaKey && !ime.isIme(e)) void submit(); }}
            {...ime.handlers}
          />
          {touched && missing ? <span className="app-field-error" role="alert">{t("rules.newDialog.needName")}</span> : null}
        </label>
        <DefinitionIdField id={defId.id} problem={defId.problem} onChange={defId.setId} inputId={`${uid}-id`} noteId={`${uid}-idnote`} />
        <Disclosure summary={t("rules.newDialog.advanced")}>
          <label className="wiki-field" htmlFor={`${uid}-desc`}>
            <span className="wiki-label">{t("rules.newDialog.description")}</span>
            <input id={`${uid}-desc`} className="wiki-input" value={description} onChange={(e) => setDescription(e.target.value)} />
          </label>
        </Disclosure>
      </div>
    </Dialog>
  );
}
