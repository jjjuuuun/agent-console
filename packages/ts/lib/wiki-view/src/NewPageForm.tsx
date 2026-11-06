import type { WikiPageTemplateInfo, WikiTemplateVariable } from "@agent-console/contracts/wiki";
import { useMemo, useState, type KeyboardEvent } from "react";
import { isComposingEvent, useDomId } from "./hooks";
import { formatMessage, resolveMessages } from "./messages";
import { ancestorFolders } from "./tree";

/** 폼 값(제어형). 틀 id가 null이면 빈 페이지. */
export interface NewPageValue {
  path: string;
  title: string;
  templateId: string | null;
  /** 선언 변수 값(이름 → 글). 서버가 채우는 내장 변수는 입력받지 않는다. */
  variables: Readonly<Record<string, string>>;
}

export interface NewPageFormProps {
  value: NewPageValue;
  onChange: (next: NewPageValue) => void;
  /** 합친 페이지 틀 목록(`GET …/templates`). 0개면 "빈 페이지"만 보인다. */
  templates: readonly WikiPageTemplateInfo[];
  /** 틀을 고르거나 바꿨을 때(호출자가 `templates/{id}/render`로 경로·본문을 받아 `value.path`를 채운다) */
  onTemplateChange?: (templateId: string | null) => void;
  /** 이미 있는 페이지 경로들(폴더 제안·"이미 있는 페이지" 경고용, 최종 판단은 서버 409) */
  existingPaths?: readonly string[];
  onOpenExisting?: (path: string) => void;
  /** 끊긴 링크·메모리에서 온 본문 길이. 있으면 틀 선택이 잠기고 "본문 N자 가져옴"을 보인다. */
  prefilledChars?: number | null;
  /** 칸 아래에 보일 서버 메시지 */
  pathError?: string | null;
  /** 맨 위 배너(규칙 거부·비밀·크기). 서버 메시지 그대로. */
  error?: string | null;
  /** 경로 미리보기(`{pages_root}/{위키}/{경로}.{확장자}`). 만드는 쪽이 정한다. */
  pathPreview?: string | null;
  submitting?: boolean;
  readOnly?: boolean;
  readOnlyReason?: string;
  onSubmit: () => void;
  onCancel?: () => void;
  maxSuggestions?: number;
  messages?: Readonly<Record<string, string>>;
  className?: string;
}

/** 입력 중인 경로에 맞는 폴더 제안(이미 있는 폴더 경로의 앞부분 일치). 최대 `max`. */
export function folderSuggestions(existingPaths: readonly string[], typed: string, max = 8): string[] {
  const needle = typed.toLowerCase();
  const folders = new Set<string>();
  for (const p of existingPaths) for (const f of ancestorFolders(p)) folders.add(`${f}/`);
  return [...folders].filter((f) => f.toLowerCase().startsWith(needle) && f.toLowerCase() !== needle).sort().slice(0, max);
}

/** 틀이 쓰는 변수 중 사용자가 입력할 것(서버가 채우는 내장 변수 제외). */
export function inputVariables(template: WikiPageTemplateInfo | undefined): WikiTemplateVariable[] {
  return (template?.variables ?? []).filter((v) => v.builtin !== true);
}

/**
 * 새 페이지 폼(표현). 경로(폴더 제안·이미 있음 경고) · 제목 · 페이지 틀(라디오, 틀의 선언 변수 입력칸) · 제출.
 * 경로 규칙과 틀 렌더는 서버가 한다 — 웹은 경로를 검사하지 않고 서버 메시지를 칸 아래에 그대로 보인다.
 * 틀 id·이름·경로 틀은 규칙 데이터이고 이 파일에 없다.
 */
export function NewPageForm({
  value, onChange, templates, onTemplateChange, existingPaths = [], onOpenExisting, prefilledChars = null, pathError = null, error = null, pathPreview = null, submitting = false,
  readOnly = false, readOnlyReason, onSubmit, onCancel, maxSuggestions = 8, messages, className,
}: NewPageFormProps) {
  const t = resolveMessages(messages);
  const base = useDomId();
  const [open, setOpen] = useState(false);
  const [pick, setPick] = useState(-1);
  const suggestions = useMemo(() => folderSuggestions(existingPaths, value.path, maxSuggestions), [existingPaths, value.path, maxSuggestions]);
  const exists = value.path !== "" && existingPaths.includes(value.path);
  const selected = templates.find((x) => x.id === value.templateId);
  const vars = inputVariables(selected);
  const locked = prefilledChars !== null;
  const blocked = readOnly || value.path.trim() === "" || submitting;
  const set = (patch: Partial<NewPageValue>) => onChange({ ...value, ...patch });
  const choose = (id: string | null) => {
    set({ templateId: id, variables: {} });
    onTemplateChange?.(id);
  };
  const listOpen = open && suggestions.length > 0;
  const onPathKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (isComposingEvent(e)) return;
    if (e.key === "ArrowDown" && suggestions.length > 0) {
      e.preventDefault();
      setOpen(true);
      setPick((p) => Math.min(p + 1, suggestions.length - 1));
    } else if (e.key === "ArrowUp" && listOpen) {
      e.preventDefault();
      setPick((p) => Math.max(p - 1, 0));
    } else if ((e.key === "Tab" || e.key === "Enter") && listOpen && pick >= 0) {
      e.preventDefault();
      set({ path: suggestions[pick]! });
      setPick(-1);
    } else if (e.key === "Escape" && listOpen) {
      e.stopPropagation();
      setOpen(false);
    }
  };
  return (
    <form
      className={`ac-wk-root ac-wk-form${className ? ` ${className}` : ""}`}
      onSubmit={(e) => {
        e.preventDefault();
        if (!blocked) onSubmit();
      }}
    >
      {error ? <p className="ac-wk-banner" data-tone="danger" role="alert">{error}</p> : null}
      <div className="ac-wk-field">
        <label htmlFor={`${base}-path`}>{t["new.path"]} *</label>
        <input
          id={`${base}-path`}
          className="ac-wk-input ac-wk-mono"
          role="combobox"
          aria-expanded={listOpen}
          aria-controls={`${base}-sug`}
          aria-autocomplete="list"
          aria-activedescendant={listOpen && pick >= 0 ? `${base}-sug${pick}` : undefined}
          aria-invalid={pathError ? true : undefined}
          aria-describedby={pathError ? `${base}-path-err` : undefined}
          value={value.path}
          disabled={submitting}
          autoComplete="off"
          onChange={(e) => {
            set({ path: e.target.value });
            setOpen(true);
            setPick(-1);
          }}
          onKeyDown={onPathKey}
          onBlur={() => setOpen(false)}
        />
        <ul id={`${base}-sug`} role="listbox" aria-label={t["new.suggestions"]} hidden={!listOpen} className="ac-wk-suggest">
          {suggestions.map((s, i) => (
            <li key={s} id={`${base}-sug${i}`} role="option" aria-selected={i === pick} onMouseDown={(e) => { e.preventDefault(); set({ path: s }); setPick(-1); }}>
              <span className="ac-wk-mono">{s}</span>
            </li>
          ))}
        </ul>
        {pathError ? <p id={`${base}-path-err`} className="ac-wk-field-error" role="alert">{pathError}</p> : null}
        {exists && !pathError ? (
          <p className="ac-wk-field-warn" role="status">
            {t["new.exists"]}{" "}
            {onOpenExisting ? <button type="button" className="ac-wk-linkbtn" onClick={() => onOpenExisting(value.path)}>{t["new.exists.open"]}</button> : null}
          </p>
        ) : null}
      </div>
      <div className="ac-wk-field">
        <label htmlFor={`${base}-title`}>{t["new.title"]}</label>
        <input id={`${base}-title`} className="ac-wk-input" value={value.title} disabled={submitting} aria-describedby={`${base}-title-hint`} onChange={(e) => set({ title: e.target.value })} />
        <p id={`${base}-title-hint`} className="ac-wk-muted ac-wk-hint">{t["new.title.hint"]}</p>
      </div>
      <fieldset className="ac-wk-field" disabled={submitting || locked}>
        <legend>{t["new.template"]}</legend>
        <label className="ac-wk-radio">
          <input type="radio" name={`${base}-tpl`} checked={value.templateId === null} disabled={submitting || locked} onChange={() => choose(null)} />
          <span>{t["new.template.blank"]}</span>
        </label>
        {templates.map((x) => (
          <label key={x.id} className="ac-wk-radio">
            <input type="radio" name={`${base}-tpl`} checked={value.templateId === x.id} disabled={submitting || locked} onChange={() => choose(x.id)} />
            <span className="ac-wk-grow">
              <span className="ac-wk-ellipsis">{x.title && x.title !== "" ? x.title : x.id}</span>
              {x.path ? <span className="ac-wk-mono ac-wk-muted ac-wk-ellipsis">{formatMessage(t["new.template.path"], { path: x.path })}</span> : null}
            </span>
          </label>
        ))}
      </fieldset>
      {locked ? <p className="ac-wk-muted ac-wk-hint">{formatMessage(t["new.prefilled"], { n: prefilledChars })}</p> : null}
      {!locked && vars.length > 0 ? (
        <fieldset className="ac-wk-field" disabled={submitting}>
          <legend>{t["new.variables"]}</legend>
          {vars.map((v) => (
            <div key={v.name} className="ac-wk-field">
              <label htmlFor={`${base}-v-${v.name}`}>{v.title && v.title !== "" ? v.title : v.name}</label>
              <input
                id={`${base}-v-${v.name}`}
                className="ac-wk-input"
                value={value.variables[v.name] ?? ""}
                placeholder={v.example ?? undefined}
                aria-describedby={v.description ? `${base}-v-${v.name}-d` : undefined}
                onChange={(e) => set({ variables: { ...value.variables, [v.name]: e.target.value } })}
              />
              {v.description ? <p id={`${base}-v-${v.name}-d`} className="ac-wk-muted ac-wk-hint">{v.description}</p> : null}
            </div>
          ))}
        </fieldset>
      ) : null}
      <div className="ac-wk-form-foot">
        {pathPreview ? <span className="ac-wk-mono ac-wk-muted ac-wk-ellipsis ac-wk-grow" title={pathPreview}>{pathPreview}</span> : <span className="ac-wk-grow" />}
        {readOnly && readOnlyReason ? <span className="ac-wk-muted">{readOnlyReason}</span> : null}
        {onCancel ? <button type="button" className="ac-wk-btn" onClick={onCancel}>{t["common.cancel"]}</button> : null}
        <button type="submit" className="ac-wk-btn" data-primary="" aria-disabled={blocked || undefined} title={readOnly ? readOnlyReason : undefined}>
          {submitting ? t["new.submitting"] : t["new.submit"]}
        </button>
      </div>
    </form>
  );
}
