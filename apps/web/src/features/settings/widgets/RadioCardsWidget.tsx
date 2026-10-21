import type { ReactNode } from "react";
import type { SchemaFormWidgetProps } from "@agent-console/schema-form";

/** `ui:widget` 이름. */
export const RADIO_CARDS_WIDGET = "radio-cards";

/** `ui:options`: 값별 설명·미리보기를 호출자가 데이터로 준다. 모르는 값은 설명·그림 없이 라디오만 보인다. */
export interface RadioCardsOptions {
  descriptions?: Record<string, string>;
  previews?: Record<string, ReactNode>;
  /** 값 대신 보일 이름 */
  labels?: Record<string, string>;
}

/** enum 값을 카드형 라디오로 고른다. 값 목록은 스키마의 `enum`이다. */
export function RadioCardsWidget({ id, value, onChange, label, disabled, readonly, schema, options }: SchemaFormWidgetProps) {
  const opts = options as RadioCardsOptions;
  const values = Array.isArray(schema["enum"]) ? (schema["enum"] as unknown[]).filter((v): v is string => typeof v === "string") : [];
  return (
    <div role="radiogroup" aria-label={label} className="app-radio-cards">
      {values.map((v) => {
        const checked = value === v;
        const preview = opts.previews?.[v];
        return (
          <label key={v} className="app-radio-card" data-checked={checked ? "true" : "false"}>
            <input type="radio" name={id} value={v} checked={checked} disabled={disabled || readonly} onChange={() => onChange(v)} />
            <span className="app-radio-card-body">
              <span className="app-radio-card-title">{opts.labels?.[v] ?? v}</span>
              {opts.descriptions?.[v] === undefined ? null : <span className="app-muted app-radio-card-desc">{opts.descriptions[v]}</span>}
              {preview === undefined ? null : <span className="app-radio-card-preview" aria-hidden="true">{preview}</span>}
            </span>
          </label>
        );
      })}
    </div>
  );
}

/** 말풍선 와이어(정적 그림): 줄 수와 모양만 다르다. 장식이므로 접근성 트리에서 숨긴다. */
export function WirePreview({ rows }: { rows: readonly { width: number; filled?: boolean }[] }) {
  return (
    <span className="app-wire">
      {rows.map((r, i) => (
        <span key={i} className="app-wire-row" data-filled={r.filled ? "true" : undefined} style={{ width: `${r.width}%` }} />
      ))}
    </span>
  );
}
