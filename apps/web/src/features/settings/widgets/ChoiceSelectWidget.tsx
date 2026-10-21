import type { SchemaFormWidgetProps } from "@agent-console/schema-form";

export interface Choice {
  value: string;
  label: string;
}

/** 위젯 이름(uiSchema `ui:widget`에 쓰는 값). */
export const CHOICE_SELECT_WIDGET = "choice-select";

/**
 * 서버에서 받은 목록(`ui:options.choices`) 중 하나를 고른다. 비우면 `null`.
 * 목록에 없는 현재 값도 잃지 않도록 항목으로 보여 준다.
 */
export function ChoiceSelectWidget({ id, value, onChange, onBlur, label, disabled, readonly, options, errors }: SchemaFormWidgetProps) {
  const choices = Array.isArray(options["choices"]) ? (options["choices"] as Choice[]) : [];
  const emptyLabel = typeof options["emptyLabel"] === "string" ? options["emptyLabel"] : "";
  const current = typeof value === "string" ? value : "";
  const known = choices.some((c) => c.value === current);
  return (
    <select
      id={id}
      aria-label={label}
      value={current}
      disabled={disabled || readonly}
      aria-invalid={errors.length > 0 || undefined}
      onBlur={onBlur}
      onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)}
    >
      <option value="">{emptyLabel}</option>
      {current !== "" && !known ? <option value={current}>{current}</option> : null}
      {choices.map((c) => (
        <option key={c.value} value={c.value}>
          {c.label}
        </option>
      ))}
    </select>
  );
}
