import { useState } from "react";
import type { ModelInfo } from "@agent-console/contracts";
import type { SchemaFormWidgetProps } from "@agent-console/schema-form";

/** `ui:widget` 이름. */
export const MODEL_WIDGET = "model-select";

export interface ModelOptions {
  /** 고른 백엔드가 알려 준 모델(없으면 직접 입력만) */
  models: readonly ModelInfo[];
  /** 목록을 불러오다 실패했다 */
  failed: boolean;
  emptyLabel: string;
  customLabel: string;
  failedNote: string;
}

const CUSTOM = "\u0000custom";

/** 모델: 백엔드가 준 목록에서 고르거나 "직접 입력". 목록에 없는 현재 값은 직접 입력으로 보인다. */
export function ModelWidget({ id, value, onChange, onBlur, label, disabled, readonly, options, errors }: SchemaFormWidgetProps) {
  const opts = options as unknown as ModelOptions;
  const current = typeof value === "string" ? value : "";
  const known = opts.models.some((m) => m.id === current);
  const [forceCustom, setForceCustom] = useState(false);
  const custom = forceCustom || (current !== "" && !known) || (opts.models.length === 0 && current !== "");
  const locked = disabled || readonly;
  return (
    <span className="lib-model">
      {opts.models.length > 0 || !custom ? (
        <select
          id={id}
          aria-label={label}
          value={custom ? CUSTOM : current}
          disabled={locked}
          aria-invalid={errors.length > 0 || undefined}
          onBlur={onBlur}
          onChange={(e) => {
            if (e.target.value === CUSTOM) {
              setForceCustom(true);
              return;
            }
            setForceCustom(false);
            onChange(e.target.value === "" ? null : e.target.value);
          }}
        >
          <option value="">{opts.emptyLabel}</option>
          {opts.models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.title ? `${m.title} (${m.id})` : m.id}
            </option>
          ))}
          <option value={CUSTOM}>{opts.customLabel}</option>
        </select>
      ) : null}
      {custom ? (
        <input
          className="ac-input"
          aria-label={opts.customLabel}
          value={current}
          disabled={locked}
          onBlur={onBlur}
          onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)}
        />
      ) : null}
      {opts.failed ? <span className="app-muted lib-field-note">{opts.failedNote}</span> : null}
    </span>
  );
}
