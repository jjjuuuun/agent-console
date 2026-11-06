/**
 * 새 스펙 대화상자(screen-sdd §4.1): 이름 + 문서 틀 라디오(빈 스펙은 마지막 고정) + 고급(id). 틀 목록·폴더 줄·제출은 모두 props다.
 * 틀 이름·문서 이름은 서버 데이터이고, 틀이 0개면 "빈 스펙"만 남는다. 한글 조합 중 Enter는 제출하지 않는다.
 */
import { useId, useMemo, useRef, useState } from "react";
import { Banner, Button, Dialog, Disclosure } from "@agent-console/ui";
import type { SpecCreateRequest, SpecTemplateSummary } from "@agent-console/contracts/sdd";
import { describeError } from "../../app/errors";
import { useImeGuard } from "../../lib/ime";
import { SearchBox } from "./parts";
import { SDD_LIMITS } from "./sddConfig";
import { sddMessages as m } from "./messages";

export interface NewSpecDialogProps {
  open: boolean;
  onClose: () => void;
  /** 폴더 줄(읽기 전용): 프로젝트 이름과 폴더. 프로젝트가 없는 조립에서는 생략 */
  folder?: { name: string; path: string } | undefined;
  /** 서버가 준 스펙 문서 폴더(저장 위치 줄). 모르면 줄이 없다 */
  specRoot?: string | undefined;
  templates: readonly SpecTemplateSummary[];
  templatesLoading?: boolean;
  /** 처음 선택할 틀 id(마지막으로 쓴 틀). 목록에 없으면 빈 스펙 */
  initialTemplate?: string | null;
  /** 처음 이름(가져오기 대화상자에서 넘어올 때) */
  initialName?: string;
  /** 문서 틀 화면 주소(있으면 안내에 링크) */
  templatesHref?: string | undefined;
  /** 쓰기가 막힌 이유(있으면 [스펙 만들기]가 `aria-disabled`) */
  blockedReason?: string | undefined;
  /** 제출. 성공하면 호출자가 이동·닫기를 한다. 실패는 던진다(서버 문장이 맨 위 배너에 보인다) */
  onSubmit: (body: SpecCreateRequest) => Promise<void>;
  /** [폴더에서 가져오기…]: 이 대화상자를 닫고 가져오기를 연다 */
  onImport?: ((name: string) => void) | undefined;
  /** 틀 선택을 기억한다(없으면 기억 안 함) */
  onTemplateChosen?: ((id: string | null) => void) | undefined;
}

const collator = new Intl.Collator("ko");

export function NewSpecDialog(props: NewSpecDialogProps) {
  const { open, onClose, folder, specRoot, templates, templatesLoading = false, initialTemplate = null, initialName = "", templatesHref, blockedReason, onSubmit, onImport, onTemplateChosen } = props;
  const sorted = useMemo(() => [...templates].sort((a, b) => collator.compare(a.name ?? a.id, b.name ?? b.id)), [templates]);
  const [name, setName] = useState(initialName);
  const [id, setId] = useState("");
  const [pick, setPick] = useState<string | null>(initialTemplate !== null && templates.some((t) => t.id === initialTemplate) ? initialTemplate : null);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [touched, setTouched] = useState(false);
  const nameRef = useRef<HTMLInputElement>(null);
  const ime = useImeGuard();
  const uid = useId();
  const blocked = blockedReason !== undefined && blockedReason !== "";
  const nameMissing = name.trim() === "";
  const shown = query.trim() === "" ? sorted : sorted.filter((t) => `${t.name ?? ""} ${t.id}`.toLowerCase().includes(query.trim().toLowerCase()));
  const selectedTemplate = pick !== null && templates.some((t) => t.id === pick) ? pick : null;

  const submit = async () => {
    setTouched(true);
    if (busy || blocked || nameMissing) return;
    setBusy(true);
    setError(null);
    try {
      onTemplateChosen?.(selectedTemplate);
      await onSubmit({ name: name.trim(), ...(id.trim() === "" ? {} : { id: id.trim() }), ...(selectedTemplate === null ? {} : { template: selectedTemplate }) });
    } catch (e) {
      setError(describeError(e, m.problem.generic).message);
      setBusy(false);
    }
  };

  const guardedClose = () => {
    if (!busy) onClose();
  };

  return (
    <Dialog
      open={open}
      title={m.new.title}
      onClose={guardedClose}
      size="md"
      initialFocus={nameRef}
      actions={
        <>
          {specRoot === undefined || specRoot === "" ? null : <span className="sdd-dialog-note app-muted">{m.new.saveLocation(specRoot)}</span>}
          <Button onClick={guardedClose} disabled={busy}>{m.cancel}</Button>
          <Button
            variant="primary"
            loading={busy}
            aria-disabled={blocked || undefined}
            title={blocked ? blockedReason : undefined}
            onClick={() => void submit()}
          >
            {busy ? m.new.submitting : m.new.submit}
          </Button>
        </>
      }
    >
      <div className="sdd-form" onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && !ime.isIme(e)) void submit(); }}>
        {error === null ? null : <Banner tone="danger">{error}</Banner>}
        {folder === undefined ? null : (
          <div className="sdd-field">
            <span className="sdd-label">{m.new.folder}</span>
            <span className="sdd-readonly"><strong>{folder.name}</strong> <span className="ac-mono-wrap app-muted">{folder.path}</span></span>
          </div>
        )}
        <label className="sdd-field" htmlFor={`${uid}-name`}>
          <span className="sdd-label">{m.new.name} *</span>
          <input
            id={`${uid}-name`}
            ref={nameRef}
            className="sdd-input"
            maxLength={SDD_LIMITS.nameMax}
            value={name}
            aria-required="true"
            aria-invalid={touched && nameMissing ? true : undefined}
            onChange={(e) => setName(e.target.value)}
            {...ime.handlers}
          />
          {touched && nameMissing ? <span className="app-field-error" role="alert">{m.new.nameRequired}</span> : null}
        </label>
        <fieldset className="sdd-field sdd-radios">
          <legend className="sdd-label">{m.new.template}</legend>
          {templates.length >= SDD_LIMITS.templateSearchMin ? <SearchBox value={query} onCommit={setQuery} label={m.new.search} delayMs={150} /> : null}
          {templatesLoading ? <p className="app-muted" role="status">{m.loading}</p> : null}
          {!templatesLoading && templates.length === 0 ? (
            <p className="app-muted" data-testid="sdd-no-templates">
              {m.new.noTemplates}
              {templatesHref === undefined ? null : <> <a className="app-link-btn" href={templatesHref}>{m.templatesTitle}</a></>}
            </p>
          ) : null}
          {shown.map((t) => {
            const warnings = (t.issues ?? []).length;
            return (
              <label key={t.id} className="sdd-radio" data-checked={selectedTemplate === t.id || undefined}>
                <input type="radio" name={`${uid}-tpl`} checked={selectedTemplate === t.id} onChange={() => setPick(t.id)} />
                <span className="sdd-radio-body">
                  <span className="sdd-radio-title ac-ellipsis">{t.name !== undefined && t.name !== "" ? t.name : t.id}</span>
                  <span className="app-muted">{m.new.templateMeta((t.documents ?? []).length, (t.run_profiles ?? []).length)}</span>
                  {t.description === undefined || t.description === "" ? null : <span className="app-muted ac-ellipsis">{t.description}</span>}
                </span>
                {warnings > 0 ? <span className="sdd-warn-chip" data-tone="warning">{m.new.templateWarn(warnings)}</span> : null}
              </label>
            );
          })}
          <label className="sdd-radio" data-checked={selectedTemplate === null || undefined}>
            <input type="radio" name={`${uid}-tpl`} checked={selectedTemplate === null} onChange={() => setPick(null)} />
            <span className="sdd-radio-body">
              <span className="sdd-radio-title">{m.new.blank}</span>
              <span className="app-muted">{m.new.blankHint}</span>
            </span>
          </label>
        </fieldset>
        <Disclosure summary={m.new.advanced}>
          <label className="sdd-field" htmlFor={`${uid}-id`}>
            <span className="sdd-label">{m.new.id}</span>
            <input id={`${uid}-id`} className="sdd-input sdd-mono" placeholder={m.new.idAuto} value={id} onChange={(e) => setId(e.target.value)} />
          </label>
        </Disclosure>
        {onImport === undefined ? null : (
          <p className="app-muted">
            {m.new.haveFolder}{" "}
            <button type="button" className="app-link-btn" disabled={busy} onClick={() => onImport(name)}>{m.list.import}</button>
          </p>
        )}
      </div>
    </Dialog>
  );
}
