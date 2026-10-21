import type { SchemaFormFieldProps } from "@agent-console/schema-form";

/** `ui:field` 이름. */
export const CHOICE_MULTI_FIELD = "choice-multi";

export interface ChoiceMultiOptions {
  choices: readonly { value: string; label: string; hint?: string }[];
  /** 아무것도 안 골랐을 때(= 비움 = 연결 종류가 허용하는 전부)의 설명 */
  emptyNote?: string;
}

/**
 * 문자열 목록(또는 null)을 체크 상자 묶음으로 고른다. 선택지는 `ui:options.choices`(서버 디스크립터에서 만든 데이터).
 * 아무것도 고르지 않으면 null(비움 = 제한 없음)로 돌려준다. 목록에 없는 현재 값도 잃지 않는다.
 */
export function ChoiceMultiField({ id, value, onChange, label, disabled, readonly, options }: SchemaFormFieldProps) {
  const opts = options as unknown as ChoiceMultiOptions;
  const current = Array.isArray(value) ? (value as unknown[]).filter((v): v is string => typeof v === "string") : [];
  const known = new Set(opts.choices.map((c) => c.value));
  const all = [...opts.choices, ...current.filter((v) => !known.has(v)).map((v) => ({ value: v, label: v }))];
  const locked = disabled || readonly;
  const toggle = (v: string, on: boolean) => {
    const next = on ? [...current, v] : current.filter((x) => x !== v);
    onChange(next.length === 0 ? null : next);
  };
  return (
    <fieldset id={id} className="team-choice-multi" aria-label={label}>
      <legend className="lib-field-label">{label}</legend>
      {all.map((c) => (
        <label key={c.value} className="app-check" title={(c as { hint?: string }).hint}>
          <input type="checkbox" checked={current.includes(c.value)} disabled={locked} onChange={(e) => toggle(c.value, e.target.checked)} />
          {c.label}
        </label>
      ))}
      {current.length === 0 && opts.emptyNote ? <span className="app-muted lib-field-note">{opts.emptyNote}</span> : null}
    </fieldset>
  );
}
