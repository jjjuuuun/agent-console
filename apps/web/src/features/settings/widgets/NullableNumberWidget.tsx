import { useId } from "react";
import type { SchemaFormWidgetProps } from "@agent-console/schema-form";
import { messages as m } from "../../../app/messages";

export const NULLABLE_NUMBER_WIDGET = "nullable-number";

/**
 * 숫자 또는 "정하지 않음"(null). 체크하면 값이 null이고 입력이 잠긴다.
 * 정수 여부·최솟값은 스키마(`type`, `minimum`, `exclusiveMinimum`)에서 읽는다.
 */
export function NullableNumberWidget({ id, value, onChange, onBlur, label, disabled, readonly, schema, errors }: SchemaFormWidgetProps) {
  const checkId = useId();
  const isNull = value === null || value === undefined;
  const type = schema["type"];
  const integer = type === "integer" || (Array.isArray(type) && type.includes("integer"));
  const min = typeof schema["minimum"] === "number" ? schema["minimum"] : undefined;
  return (
    <span className="app-nullable">
      <input
        id={id}
        type="number"
        aria-label={label}
        value={isNull ? "" : String(value)}
        step={integer ? 1 : "any"}
        {...(min === undefined ? {} : { min })}
        disabled={disabled || readonly || isNull}
        aria-invalid={errors.length > 0 || undefined}
        onBlur={onBlur}
        onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
      />
      <label htmlFor={checkId} className="app-check">
        <input
          id={checkId}
          type="checkbox"
          checked={isNull}
          disabled={disabled || readonly}
          onChange={(e) => onChange(e.target.checked ? null : (min ?? 1))}
        />
        {m.settings.nullable.unset}
      </label>
    </span>
  );
}
