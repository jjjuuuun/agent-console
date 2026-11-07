import type { ComponentType } from "react";
import type { SchemaFormFieldProps } from "@agent-console/schema-form";

/** 문자열 목록이 아닌 값(모르는 모양)은 빈 목록으로 본다. 값은 지우지 않고 사용자가 고칠 때만 바뀐다. */
export function toTags(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
}

/** `ui:widget: "example.tags"` 필드. 쉼표로 나눈 태그 문자열 목록을 한 칸에서 고친다. */
export function TagsField({ id, value, onChange, onBlur, label, required, disabled, readonly, errors }: SchemaFormFieldProps) {
  const errorId = `${id}-errors`;
  return (
    <div>
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        type="text"
        value={toTags(value).join(", ")}
        required={required}
        disabled={disabled}
        readOnly={readonly}
        aria-invalid={errors.length > 0}
        aria-describedby={errors.length > 0 ? errorId : undefined}
        onBlur={onBlur}
        onChange={(e) =>
          onChange(
            e.target.value
              .split(",")
              .map((t) => t.trim())
              .filter((t) => t !== ""),
          )
        }
      />
      {errors.length > 0 ? (
        <p id={errorId} role="alert">
          {errors.join(" ")}
        </p>
      ) : null}
    </div>
  );
}

/** 설정 폼 위젯 한 줄(X51). `apps/web`의 레지스트리 항목(`{ Component }`)과 같은 모양이다. */
export interface ConfigWidgetEntry {
  Component: ComponentType<SchemaFormFieldProps>;
}

/** `ui:widget` 이름 → 위젯. 앱 레지스트리에 이 표를 펼쳐 넣는다. */
export const configWidgets: Readonly<Record<string, ConfigWidgetEntry>> = { "example.tags": { Component: TagsField } };
