/**
 * 새 스펙 대화상자(screen-sdd §4.1): 이름 + 문서 틀 라디오(빈 스펙은 마지막 고정) + 고급(id). 틀 목록·폴더 줄·제출은 모두 props다.
 * 틀 이름·문서 이름은 서버 데이터이고, 틀이 0개면 "빈 스펙"만 남는다. 한글 조합 중 Enter는 제출하지 않는다.
 */
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Banner, Button, Dialog, Disclosure } from "@agent-console/ui";
import type { SpecCreateRequest, SpecTemplateSummary } from "@agent-console/contracts/sdd";
import { useErrorState, raised } from "../../app/errors";
import { useCollator } from "../../i18n";
import { useImeGuard } from "../../lib/ime";
import { SearchBox } from "./parts";
import { SDD_LIMITS } from "./sddConfig";
import { useT } from "@agent-console/i18n";

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
  /** 이 값이 바뀌면(공용에서 가져온 틀 id) 목록에 나타나는 즉시 그 틀을 고른다 */
  selectTemplate?: string | null | undefined;
  /** 처음 이름(가져오기 대화상자에서 넘어올 때) */
  initialName?: string;
  /** 문서 틀 화면 주소(있으면 안내에 링크) */
  templatesHref?: string | undefined;
  /** 쓰기가 막힌 이유(있으면 [스펙 만들기]가 `aria-disabled`) */
  blockedReason?: string | undefined;
  /** 제출. 성공하면 호출자가 이동·닫기를 한다. 실패는 던진다(서버 문장이 맨 위 배너에 보인다) */
  onSubmit: (body: SpecCreateRequest) => Promise<void>;
  /** [공용에서 가져오기…]: 공용 문서 틀을 이 프로젝트로 복사한다(복사가 끝나면 호출자가 틀 목록을 갱신). 없으면 버튼이 없다 */
  onImportFromLibrary?: (() => void) | undefined;
  /** [폴더에서 가져오기…]: 이 대화상자를 닫고 가져오기를 연다 */
  onImport?: ((name: string) => void) | undefined;
  /** 틀 선택을 기억한다(없으면 기억 안 함) */
  onTemplateChosen?: ((id: string | null) => void) | undefined;
}

export function NewSpecDialog(props: NewSpecDialogProps) {
  const collator = useCollator();
  const t = useT("sdd");
  const { open, onClose, folder, specRoot, templates, templatesLoading = false, initialTemplate = null, initialName = "", selectTemplate = null, templatesHref, blockedReason, onSubmit, onImport, onImportFromLibrary, onTemplateChosen } = props;
  const sorted = useMemo(() => [...templates].sort((a, b) => collator.compare(a.name ?? a.id, b.name ?? b.id)), [templates, collator]);
  const [name, setName] = useState(initialName);
  const [id, setId] = useState("");
  const [pick, setPick] = useState<string | null>(initialTemplate !== null && templates.some((t) => t.id === initialTemplate) ? initialTemplate : null);
  const [query, setQuery] = useState("");
  const appliedSelect = useRef<string | null>(null);
  useEffect(() => {
    // 같은 요청은 한 번만 적용한다(목록을 다시 읽어도 사용자가 고른 틀을 덮어쓰지 않는다)
    if (selectTemplate === null || appliedSelect.current === selectTemplate || !templates.some((t) => t.id === selectTemplate)) return;
    appliedSelect.current = selectTemplate;
    setPick(selectTemplate);
  }, [selectTemplate, templates]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useErrorState(t("problem.generic"));
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
      setError(raised(e));
      setBusy(false);
    }
  };

  const guardedClose = () => {
    if (!busy) onClose();
  };

  return (
    <Dialog
      open={open}
      title={t("new.title")}
      onClose={guardedClose}
      size="md"
      initialFocus={nameRef}
      actions={
        <>
          {specRoot === undefined || specRoot === "" ? null : <span className="sdd-dialog-note app-muted">{t("new.saveLocation", { path: specRoot })}</span>}
          <Button onClick={guardedClose} disabled={busy}>{t("cancel")}</Button>
          <Button
            variant="primary"
            loading={busy}
            aria-disabled={blocked || undefined}
            title={blocked ? blockedReason : undefined}
            onClick={() => void submit()}
          >
            {busy ? t("new.submitting") : t("new.submit")}
          </Button>
        </>
      }
    >
      <div className="sdd-form" onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && !ime.isIme(e)) void submit(); }}>
        {error === null ? null : <Banner tone="danger">{error}</Banner>}
        {folder === undefined ? null : (
          <div className="sdd-field">
            <span className="sdd-label">{t("new.folder")}</span>
            <span className="sdd-readonly"><strong>{folder.name}</strong> <span className="ac-mono-wrap app-muted">{folder.path}</span></span>
          </div>
        )}
        <label className="sdd-field" htmlFor={`${uid}-name`}>
          <span className="sdd-label">{t("new.name")} *</span>
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
          {touched && nameMissing ? <span className="app-field-error" role="alert">{t("new.nameRequired")}</span> : null}
        </label>
        <fieldset className="sdd-field sdd-radios">
          <legend className="sdd-label">{t("new.template")}</legend>
          {templates.length >= SDD_LIMITS.templateSearchMin ? <SearchBox value={query} onCommit={setQuery} label={t("new.search")} delayMs={150} /> : null}
          {templatesLoading ? <p className="app-muted" role="status">{t("loading")}</p> : null}
          {!templatesLoading && templates.length === 0 ? (
            <p className="app-muted" data-testid="sdd-no-templates">
              {t("new.noTemplates")}
              {templatesHref === undefined ? null : <> <a className="app-link-btn" href={templatesHref}>{t("templatesTitle")}</a></>}
            </p>
          ) : null}
          {shown.map((tpl) => {
            const warnings = (tpl.issues ?? []).length;
            return (
              <label key={tpl.id} className="sdd-radio" data-checked={selectedTemplate === tpl.id || undefined}>
                <input type="radio" name={`${uid}-tpl`} checked={selectedTemplate === tpl.id} onChange={() => setPick(tpl.id)} />
                <span className="sdd-radio-body">
                  <span className="sdd-radio-title ac-ellipsis">{tpl.name !== undefined && tpl.name !== "" ? tpl.name : tpl.id}</span>
                  <span className="app-muted">{(tpl.run_profiles ?? []).length > 0 ? t("new.templateMetaProfiles", { docs: (tpl.documents ?? []).length, profiles: (tpl.run_profiles ?? []).length }) : t("new.templateMeta", { docs: (tpl.documents ?? []).length })}</span>
                  {tpl.description === undefined || tpl.description === "" ? null : <span className="app-muted ac-ellipsis">{tpl.description}</span>}
                </span>
                {warnings > 0 ? <span className="sdd-warn-chip" data-tone="warning">{t("new.templateWarn", { count: warnings })}</span> : null}
              </label>
            );
          })}
          {onImportFromLibrary === undefined ? null : (
            <button
              type="button"
              className="app-link-btn sdd-import-library"
              disabled={busy}
              aria-disabled={blocked || undefined}
              title={blocked ? blockedReason : undefined}
              onClick={() => { if (!blocked) onImportFromLibrary(); }}
            >
              ＋ {t("new.importFromLibrary")}
            </button>
          )}
          <label className="sdd-radio" data-checked={selectedTemplate === null || undefined}>
            <input type="radio" name={`${uid}-tpl`} checked={selectedTemplate === null} onChange={() => setPick(null)} />
            <span className="sdd-radio-body">
              <span className="sdd-radio-title">{t("new.blank")}</span>
              <span className="app-muted">{t("new.blankHint")}</span>
            </span>
          </label>
        </fieldset>
        <Disclosure summary={t("new.advanced")}>
          <label className="sdd-field" htmlFor={`${uid}-id`}>
            <span className="sdd-label">{t("new.id")}</span>
            <input id={`${uid}-id`} className="sdd-input sdd-mono" placeholder={t("new.idAuto")} value={id} onChange={(e) => setId(e.target.value)} />
          </label>
        </Disclosure>
        {onImport === undefined ? null : (
          <p className="app-muted">
            {t("new.haveFolder")}{" "}
            <button type="button" className="app-link-btn" disabled={busy} onClick={() => onImport(name)}>{t("list.import")}</button>
          </p>
        )}
      </div>
    </Dialog>
  );
}
