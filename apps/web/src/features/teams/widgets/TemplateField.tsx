import { useRef } from "react";
import type { SchemaFormFieldProps } from "@agent-console/schema-form";
import { teamMessages as t } from "../messages";

/** `ui:field` 이름. */
export const TEMPLATE_FIELD = "template-text";

export interface TemplateOptions {
  /** 안전 치환에 쓸 수 있는 변수 이름(스키마 설명에서 읽는다) */
  variables: readonly string[];
}

/** 설명 문장("… 변수 a·b·c. …")에서 변수 이름을 뽑는다. 못 찾으면 빈 목록. */
export function parseVariables(description: string | undefined): string[] {
  if (description === undefined) return [];
  const m = /변수\s*([^.。\n]+)/.exec(description);
  if (m === null) return [];
  return [...new Set((m[1] ?? "").split(/[·,、\s]+/).map((s) => s.trim()).filter((s) => /^[A-Za-z_][A-Za-z0-9_]*$/.test(s)))];
}

/** 템플릿 문자열: 텍스트 영역 + 변수 칩(누르면 커서 위치에 `{변수}`를 넣는다). 비우면 null. */
export function TemplateField({ id, value, onChange, label, disabled, readonly, options }: SchemaFormFieldProps) {
  const opts = options as unknown as TemplateOptions;
  const ref = useRef<HTMLTextAreaElement>(null);
  const text = typeof value === "string" ? value : "";
  const locked = disabled || readonly;
  const insert = (name: string) => {
    const el = ref.current;
    const token = `{${name}}`;
    const from = el?.selectionStart ?? text.length;
    const to = el?.selectionEnd ?? text.length;
    onChange(`${text.slice(0, from)}${token}${text.slice(to)}`);
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(from + token.length, from + token.length);
    });
  };
  return (
    <div className="lib-field">
      <label htmlFor={id}>{label}</label>
      <textarea ref={ref} id={id} className="ac-input" rows={3} value={text} disabled={locked} onChange={(e) => onChange(e.target.value === "" ? null : e.target.value)} />
      {opts.variables.length > 0 ? (
        <div className="lib-chips" role="group" aria-label={t.review.variables}>
          {opts.variables.map((v) => (
            <button key={v} type="button" className="lib-chip" disabled={locked} aria-label={t.review.insertVariable(v)} onClick={() => insert(v)}>
              {`{${v}}`}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
