import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type ReactNode, type Ref } from "react";
import { fmt, mergeMessages, type DeepPartial, type LogViewMessages } from "./messages";
import { MAX_SAVED_NAME } from "./savedFilters";
import type { FilterFieldSpec, LogFilterValue, SavedFilter } from "./types";

export interface LogFilterBarProps {
  /** 필터 필드 정의(앱 데이터 한 곳). 이름·입력 방식은 이 목록만 본다. */
  fields: readonly FilterFieldSpec[];
  value: LogFilterValue;
  onChange: (next: LogFilterValue) => void;
  /** 항상 보이는 검색 입력으로 쓸 필터 이름(없으면 검색 입력 없음). */
  searchField?: string;
  searchMaxLength?: number;
  /** 검색 입력 디바운스(ms). IME 조합 중에는 반영하지 않고 Enter는 즉시 반영. */
  debounceMs?: number;
  /** 필드별 제안(autocomplete). 없어도 자유 입력은 막지 않는다. */
  suggestions?: Readonly<Record<string, readonly string[]>>;
  /** 서버 검증 오류(422) 매핑: 필드 이름 -> 메시지. */
  fieldErrors?: Readonly<Record<string, string>>;
  /** select/multiselect 선택지를 동적으로 줄 때(필드의 `options`가 우선). */
  renderSelectOptions?: (name: string) => readonly { value: string; label?: string }[] | undefined;
  savedFilters?: readonly SavedFilter[];
  onSaveFilter?: (name: string) => void;
  onApplySaved?: (filter: SavedFilter) => void;
  onDeleteSaved?: (name: string) => void;
  /** 오른쪽 끝에 놓을 추가 컨트롤(열 구성 등). */
  trailing?: ReactNode;
  inputRef?: Ref<HTMLInputElement>;
  compact?: boolean;
  messages?: DeepPartial<LogViewMessages>;
  ariaLabel?: string;
}

const asList = (v: string | string[] | undefined): string[] => (v === undefined ? [] : Array.isArray(v) ? v : v === "" ? [] : [v]);

/** 칩에 보이는 값 요약: 다중 값은 `, `로 잇고 3개를 넘으면 `+n`. */
function summary(spec: FilterFieldSpec | undefined, values: string[], m: LogViewMessages): string {
  const label = (v: string) => spec?.options?.find((o) => o.value === v)?.label ?? v;
  const shown = values.slice(0, 3).map(label).join(", ");
  return values.length > 3 ? `${shown} ${fmt(m.multiMore, { n: values.length - 3 })}` : shown;
}

function toLocalInput(v: string | undefined): string {
  if (!v) return "";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return "";
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

/**
 * 필터 막대: 검색 입력 + 활성 칩 + [+ 필터] + 즐겨찾는 필터. 필드 정의는 `fields` 데이터만 본다
 * (필터 이름이 늘면 `fields`에 한 줄 추가). 값은 URL 쿼리와 같은 모양(`LogFilterValue`).
 */
export function LogFilterBar(props: LogFilterBarProps) {
  const { fields, value, onChange, searchField, searchMaxLength = 500, debounceMs = 300, suggestions, fieldErrors, renderSelectOptions, savedFilters, onSaveFilter, onApplySaved, onDeleteSaved, trailing, inputRef, compact, ariaLabel } = props;
  const m = useMemo(() => mergeMessages(props.messages), [props.messages]);
  const uid = useId();
  const [editing, setEditing] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [savedOpen, setSavedOpen] = useState(false);
  const [saveName, setSaveName] = useState("");
  const specs = useMemo(() => new Map(fields.map((f) => [f.name, f] as const)), [fields]);

  // 검색 입력: 로컬 상태 + 디바운스. 외부 값이 바뀌면(칩 지우기·저장된 필터 적용) 따라간다.
  const external = searchField ? asList(value[searchField])[0] ?? "" : "";
  const [text, setText] = useState(external);
  const composing = useRef(false);
  const [prevExternal, setPrevExternal] = useState(external);
  if (external !== prevExternal) {
    setPrevExternal(external);
    setText(external);
  }
  const commitSearch = (v: string) => {
    if (!searchField) return;
    const next = { ...value };
    if (v === "") delete next[searchField];
    else next[searchField] = v;
    onChange(next);
  };
  useEffect(() => {
    if (!searchField || text === external || composing.current) return;
    const t = setTimeout(() => commitSearch(text), debounceMs);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text]);

  const activeNames = Object.keys(value).filter((n) => n !== searchField && asList(value[n]).length > 0);
  const orderedNames = [...fields.map((f) => f.name).filter((n) => activeNames.includes(n)), ...activeNames.filter((n) => !specs.has(n))];
  const addable = fields.filter((f) => f.name !== searchField && !activeNames.includes(f.name));

  const setField = (name: string, values: string[]) => {
    const next = { ...value };
    if (values.length === 0) delete next[name];
    else next[name] = values.length === 1 && specs.get(name)?.input !== "multiselect" ? (values[0] as string) : values;
    onChange(next);
  };

  const options = (spec: FilterFieldSpec) => spec.options ?? renderSelectOptions?.(spec.name);

  return (
    <div className="ac-lv-filterbar" role="search" aria-label={ariaLabel ?? m.filterBar} data-compact={compact || undefined}>
      {searchField ? (
        <input
          ref={inputRef}
          type="search"
          className="ac-lv-input"
          aria-label={m.searchLabel}
          placeholder={m.searchPlaceholder}
          maxLength={searchMaxLength}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onCompositionStart={() => (composing.current = true)}
          onCompositionEnd={(e) => {
            composing.current = false;
            setText(e.currentTarget.value);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !composing.current) commitSearch(text);
          }}
        />
      ) : null}
      <ul className="ac-lv-chips" aria-label={m.filterBar}>
        {orderedNames.map((name) => {
          const spec = specs.get(name);
          const values = asList(value[name]);
          const err = fieldErrors?.[name];
          const unknown = !spec;
          const label = spec?.label ?? name;
          const text = `${label}: ${summary(spec, values, m)}`;
          return (
            <li key={name} className="ac-lv-filterchip" data-invalid={err ? true : undefined} data-unknown={unknown || undefined}>
              <button type="button" className="ac-lv-chipmain ac-lv-ellipsis" title={err ? `${text} — ${err}` : text} aria-invalid={err ? true : undefined} onClick={() => setEditing(editing === name ? null : name)} aria-expanded={editing === name}>
                {err ? <span aria-hidden="true">⚠ </span> : null}
                {text}
                {unknown ? <span className="ac-lv-muted"> ({m.unknownFilter})</span> : null}
              </button>
              <button type="button" className="ac-lv-chipx" aria-label={fmt(m.removeFilter, { name: label })} onClick={() => setField(name, [])} onKeyDown={(e) => e.key === "Backspace" && setField(name, [])}>
                ×
              </button>
              {editing === name && spec ? <FieldEditor spec={spec} values={values} options={options(spec)} suggestions={suggestions?.[name]} error={err} m={m} onApply={(v) => { setField(name, v); }} onClose={() => setEditing(null)} idPrefix={`${uid}-${name}`} /> : null}
              {err && editing !== name ? <span className="ac-lv-fielderr" role="alert">{err}</span> : null}
            </li>
          );
        })}
      </ul>
      <div className="ac-lv-addwrap">
        {addable.length > 0 ? (
          <>
            <button type="button" className="ac-lv-btn" aria-haspopup="menu" aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}>
              {m.addFilter}
            </button>
            {menuOpen ? (
              <ul role="menu" className="ac-lv-menu" onKeyDown={(e: KeyboardEvent) => e.key === "Escape" && setMenuOpen(false)}>
                {addable.map((f) => (
                  <li key={f.name} role="none">
                    <button type="button" role="menuitem" onClick={() => { setMenuOpen(false); setEditing(f.name); }}>
                      {f.label}
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
            {editing && !activeNames.includes(editing) && specs.get(editing) ? (
              <div className="ac-lv-popwrap">
                <FieldEditor spec={specs.get(editing) as FilterFieldSpec} values={[]} options={options(specs.get(editing) as FilterFieldSpec)} suggestions={suggestions?.[editing]} error={fieldErrors?.[editing]} m={m} onApply={(v) => setField(editing, v)} onClose={() => setEditing(null)} idPrefix={`${uid}-new`} />
              </div>
            ) : null}
          </>
        ) : null}
      </div>
      {onSaveFilter || savedFilters ? (
        <div className="ac-lv-addwrap">
          <button type="button" className="ac-lv-btn" aria-haspopup="true" aria-expanded={savedOpen} aria-label={m.savedFilters} onClick={() => setSavedOpen(!savedOpen)}>
            ★ ▾
          </button>
          {savedOpen ? (
            <div className="ac-lv-menu ac-lv-saved" role="group" aria-label={m.savedFilters} onKeyDown={(e) => e.key === "Escape" && setSavedOpen(false)}>
              {(savedFilters ?? []).length === 0 ? <p className="ac-lv-muted">{m.noSavedFilters}</p> : null}
              <ul>
                {(savedFilters ?? []).map((f) => (
                  <li key={f.name}>
                    <button type="button" onClick={() => { onApplySaved?.(f); setSavedOpen(false); }} aria-label={fmt(m.applySaved, { name: f.name })}>
                      {f.name}
                    </button>
                    {onDeleteSaved ? (
                      <button type="button" className="ac-lv-chipx" aria-label={fmt(m.deleteSaved, { name: f.name })} onClick={() => onDeleteSaved(f.name)}>
                        ×
                      </button>
                    ) : null}
                  </li>
                ))}
              </ul>
              {onSaveFilter ? (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (saveName.trim()) {
                      onSaveFilter(saveName.trim().slice(0, MAX_SAVED_NAME));
                      setSaveName("");
                    }
                  }}
                >
                  <input className="ac-lv-input" aria-label={m.saveFilterName} maxLength={MAX_SAVED_NAME} value={saveName} onChange={(e) => setSaveName(e.target.value)} />
                  <button type="submit" className="ac-lv-btn" disabled={!saveName.trim()}>
                    {m.saveFilter}
                  </button>
                </form>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
      {trailing}
    </div>
  );
}

interface FieldEditorProps {
  spec: FilterFieldSpec;
  values: string[];
  options: readonly { value: string; label?: string }[] | undefined;
  suggestions: readonly string[] | undefined;
  error: string | undefined;
  m: LogViewMessages;
  onApply: (values: string[]) => void;
  onClose: () => void;
  idPrefix: string;
}

/** 필드 하나의 편집 팝오버(입력 방식은 `spec.input`만 본다). Enter/[확인]으로 적용, Esc로 닫기. */
function FieldEditor({ spec, values, options, suggestions, error, m, onApply, onClose, idPrefix }: FieldEditorProps) {
  const [draft, setDraft] = useState<string[]>(values);
  const ref = useRef<HTMLInputElement | HTMLSelectElement>(null);
  useEffect(() => ref.current?.focus(), []);
  const listId = `${idPrefix}-dl`;
  const commit = (v: string[] = draft) => {
    onApply(v.filter((x) => x !== ""));
    onClose();
  };
  const label = fmt(m.filterValueLabel, { name: spec.label });
  let input: ReactNode;
  if (spec.input === "select") {
    input = (
      <select ref={ref as Ref<HTMLSelectElement>} aria-label={label} value={draft[0] ?? ""} onChange={(e) => commit([e.target.value])}>
        <option value="" />
        {(options ?? []).map((o) => (
          <option key={o.value} value={o.value}>
            {o.label ?? o.value}
          </option>
        ))}
      </select>
    );
  } else if (spec.input === "multiselect") {
    input = (
      <fieldset>
        <legend>{label}</legend>
        {(options ?? []).map((o, i) => (
          <label key={o.value}>
            <input ref={i === 0 ? (ref as Ref<HTMLInputElement>) : undefined} type="checkbox" checked={draft.includes(o.value)} onChange={(e) => setDraft(e.target.checked ? [...draft, o.value] : draft.filter((x) => x !== o.value))} />
            {o.label ?? o.value}
          </label>
        ))}
        {(options ?? []).length === 0 ? (
          <input ref={ref as Ref<HTMLInputElement>} className="ac-lv-input" aria-label={label} value={draft.join(",")} onChange={(e) => setDraft(e.target.value.split(",").map((s) => s.trim()))} />
        ) : null}
      </fieldset>
    );
  } else if (spec.input === "time-range") {
    input = (
      <input
        ref={ref as Ref<HTMLInputElement>}
        type="datetime-local"
        className="ac-lv-input"
        aria-label={label}
        value={toLocalInput(draft[0])}
        onChange={(e) => setDraft(e.target.value ? [new Date(e.target.value).toISOString()] : [])}
      />
    );
  } else {
    input = (
      <>
        <input ref={ref as Ref<HTMLInputElement>} className="ac-lv-input" aria-label={label} placeholder={spec.placeholder} list={suggestions?.length ? listId : undefined} value={draft[0] ?? ""} onChange={(e) => setDraft([e.target.value])} />
        {suggestions?.length ? (
          <datalist id={listId}>
            {suggestions.map((s) => (
              <option key={s} value={s} />
            ))}
          </datalist>
        ) : null}
      </>
    );
  }
  return (
    <div
      className="ac-lv-pop"
      role="dialog"
      aria-label={spec.label}
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.stopPropagation();
          onClose();
        } else if (e.key === "Enter" && (e.target as HTMLElement).tagName !== "SELECT") {
          e.preventDefault();
          commit();
        }
      }}
    >
      {input}
      {error ? <p className="ac-lv-fielderr" role="alert">{error}</p> : null}
      <button type="button" className="ac-lv-btn" onClick={() => commit()}>
        {m.apply}
      </button>
    </div>
  );
}
