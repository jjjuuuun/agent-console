import { useId, useState } from "react";
import { Button } from "@agent-console/ui";
import type { SchemaFormFieldProps } from "@agent-console/schema-form";
import { messages as m } from "../../../app/messages";
import { useImeGuard } from "../../../lib/ime";

/** `ui:field` 이름. */
export const KEY_VALUE_MAP_FIELD = "key-value-map";

export interface KeyValueMapOptions {
  keyLabel?: string;
  valueLabel?: string;
  addLabel?: string;
  /** 키 자동완성 후보(데이터) */
  keySuggestions?: readonly string[];
  /** 있으면 값은 이 목록에서 고른다(없으면 자유 입력) */
  valueChoices?: readonly { value: string; label: string; hint?: string }[];
  /** 키 형식 검사: 오류 문구를 돌려주면 그 행에 표시 */
  validateKey?: (key: string) => string | undefined;
  /** 행 아래 보조 문구(예: "스키마 기본: …") */
  rowNote?: (key: string, value: string) => string | undefined;
}

/**
 * 문자열 키 → 문자열 값 맵 편집기(병합 규칙, 창 표시 이름 등 공용). 의미는 호출자가 옵션으로 준다.
 * 값은 `{키: 값}` 객체이며 행 추가·삭제·키 바꾸기를 지원한다. 키가 겹치면 그 행에 오류를 보인다.
 */
export function KeyValueMapField({ id, value, onChange, label, disabled, readonly, options }: SchemaFormFieldProps) {
  const opts = options as KeyValueMapOptions;
  const listId = useId();
  const entries = Object.entries(value !== null && typeof value === "object" ? (value as Record<string, string>) : {});
  // 새 행은 키가 비어 있는 동안 객체에 넣을 수 없으므로 로컬 초안으로 둔다
  const ime = useImeGuard();
  const [drafts, setDrafts] = useState<number[]>([]);
  const [draftKeys, setDraftKeys] = useState<Record<number, string>>({});
  const locked = disabled || readonly;
  const emit = (next: [string, string][]) => onChange(Object.fromEntries(next));

  const commitDraft = (n: number) => {
    const key = (draftKeys[n] ?? "").trim();
    if (key === "" || entries.some(([k]) => k === key)) return;
    emit([...entries, [key, opts.valueChoices?.[0]?.value ?? ""]]);
    setDrafts((d) => d.filter((x) => x !== n));
    setDraftKeys(({ [n]: _gone, ...rest }) => (void _gone, rest));
  };

  return (
    <div className="app-kv" role="group" aria-label={label}>
      {opts.keySuggestions === undefined ? null : (
        <datalist id={listId}>
          {opts.keySuggestions.map((s) => (
            <option key={s} value={s} />
          ))}
        </datalist>
      )}
      {entries.length === 0 && drafts.length === 0 ? <p className="app-muted">{m.settings.keyValue.empty}</p> : null}
      {entries.map(([k, v], i) => {
        const problem = opts.validateKey?.(k);
        const note = opts.rowNote?.(k, v);
        return (
          <div key={`${i}`} className="app-kv-row">
            <input
              aria-label={`${opts.keyLabel ?? m.settings.keyValue.key} ${i + 1}`}
              list={opts.keySuggestions === undefined ? undefined : listId}
              value={k}
              disabled={locked}
              aria-invalid={problem !== undefined || undefined}
              onChange={(e) => emit(entries.map(([ek, ev], j): [string, string] => (j === i ? [e.target.value, ev] : [ek, ev])))}
            />
            {opts.valueChoices === undefined ? (
              <input
                aria-label={`${opts.valueLabel ?? m.settings.keyValue.value} ${i + 1}`}
                value={v}
                disabled={locked}
                onChange={(e) => emit(entries.map(([ek, ev], j): [string, string] => (j === i ? [ek, e.target.value] : [ek, ev])))}
              />
            ) : (
              <select
                aria-label={`${opts.valueLabel ?? m.settings.keyValue.value} ${i + 1}`}
                value={v}
                disabled={locked}
                onChange={(e) => emit(entries.map(([ek, ev], j): [string, string] => (j === i ? [ek, e.target.value] : [ek, ev])))}
              >
                {opts.valueChoices.some((c) => c.value === v) ? null : <option value={v}>{v}</option>}
                {opts.valueChoices.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.hint ? `${c.label} — ${c.hint}` : c.label}
                  </option>
                ))}
              </select>
            )}
            <Button size="sm" disabled={locked} aria-label={`${m.settings.keyValue.remove}: ${k}`} onClick={() => emit(entries.filter((_, j) => j !== i))}>
              {m.settings.keyValue.remove}
            </Button>
            {problem === undefined ? null : <span className="app-field-error" role="alert">{problem}</span>}
            {note === undefined ? null : <span className="app-muted app-kv-note">{note}</span>}
          </div>
        );
      })}
      {drafts.map((n) => {
        const key = (draftKeys[n] ?? "").trim();
        const dup = entries.some(([k]) => k === key);
        return (
          <div key={`d${n}`} className="app-kv-row">
            <input
              autoFocus
              aria-label={`${opts.keyLabel ?? m.settings.keyValue.key} (${m.settings.keyValue.add})`}
              list={opts.keySuggestions === undefined ? undefined : listId}
              value={draftKeys[n] ?? ""}
              aria-invalid={dup || undefined}
              onChange={(e) => setDraftKeys((d) => ({ ...d, [n]: e.target.value }))}
              onBlur={() => commitDraft(n)}
              {...ime.handlers}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !ime.isIme(e)) {
                  e.preventDefault();
                  commitDraft(n);
                }
              }}
            />
            {dup ? <span className="app-field-error" role="alert">{m.settings.keyValue.duplicate}</span> : null}
          </div>
        );
      })}
      <Button
        size="sm"
        id={id}
        disabled={locked}
        onClick={() => setDrafts((d) => [...d, (d.at(-1) ?? 0) + 1])}
      >
        {opts.addLabel ?? m.settings.keyValue.add}
      </Button>
    </div>
  );
}
