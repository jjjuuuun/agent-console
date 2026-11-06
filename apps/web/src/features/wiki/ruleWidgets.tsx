/**
 * 위키 규칙 폼에 더하는 스키마 위젯(계약 `KNOWN_UI_WIDGETS`): `glob`(걸 페이지 경로 모양)과 `template-text`(스키마 `x-ui.variables`로 변수 칩을 붙인 입력 틀).
 * 문서 틀 폼 위젯 8종(`condition`·`regex` 등)은 스펙 기능의 것을 그대로 쓰고 이 둘만 같은 이름으로 덮어쓰거나 더한다.
 * 글롭은 웹이 해석하지 않는다 — 형식 오류는 서버 검사 메시지를 칸 아래에 보인다. 변수 목록은 스키마가 정한다(코드에 변수 이름이 없다).
 */
import { useRef, type ComponentType } from "react";
import { KNOWN_UI_WIDGETS } from "@agent-console/contracts/constants";
import type { SchemaFormFieldProps } from "@agent-console/schema-form";
import { ShapedField, type ItemRenderArgs } from "../sdd";
import { resolveRef, unwrapNullable, type SchemaNode } from "../../lib/schemaTools";
import { variableToken, xuiVariables } from "./rulesSchema";
import { wikiRulesMessages } from "./rulesScreenMessages";

const w = wikiRulesMessages.widgets;

/** 글롭 칸(mono). 문자열 목록. */
export function GlobField(p: SchemaFormFieldProps) {
  return (
    <ShapedField
      field={p}
      footer={<p className="app-muted wiki-hint">{w.globHint}</p>}
      renderItem={(a: ItemRenderArgs) => (
        <input
          id={a.id}
          className="ac-input wiki-mono"
          spellCheck={false}
          autoComplete="off"
          aria-label={a.label}
          aria-invalid={a.invalid || undefined}
          aria-describedby={a.describedBy}
          placeholder={w.globPlaceholder}
          value={a.value}
          disabled={a.disabled}
          onChange={(e) => a.onChange(e.target.value)}
        />
      )}
    />
  );
}

function TemplateItem({ a, variables }: { a: ItemRenderArgs; variables: readonly { name: string; description?: string }[] }) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const insert = (name: string) => {
    const el = ref.current;
    const token = variableToken(name);
    const from = el?.selectionStart ?? a.value.length;
    const to = el?.selectionEnd ?? a.value.length;
    a.onChange(`${a.value.slice(0, from)}${token}${a.value.slice(to)}`);
    requestAnimationFrame(() => {
      el?.focus();
      el?.setSelectionRange(from + token.length, from + token.length);
    });
  };
  return (
    <>
      <textarea ref={ref} id={a.id} className="ac-input wiki-mono" rows={2} aria-label={a.label} aria-invalid={a.invalid || undefined} aria-describedby={a.describedBy} value={a.value} disabled={a.disabled} onChange={(e) => a.onChange(e.target.value)} />
      {variables.length > 0 ? (
        <div className="wiki-var-chips" role="group" aria-label={w.variablesLabel}>
          {variables.map((v) => (
            <button key={v.name} type="button" className="wiki-var-chip" disabled={a.disabled} title={v.description} aria-label={w.insertVariable(v.name)} onClick={() => insert(v.name)}>{variableToken(v.name)}</button>
          ))}
        </div>
      ) : null}
    </>
  );
}

/** 입력 틀: 여러 줄 칸 + 변수 칩(스키마 `x-ui.variables`; 누르면 커서 위치에 `{이름}`). */
export function WikiTemplateTextField(p: SchemaFormFieldProps) {
  const root = (typeof p.options["$rootSchema"] === "object" && p.options["$rootSchema"] !== null ? p.options["$rootSchema"] : p.schema) as SchemaNode;
  const node = p.schema as SchemaNode;
  const own = xuiVariables(node);
  const variables = own.length > 0 ? own : xuiVariables(unwrapNullable(resolveRef(node, root), root).schema);
  return <ShapedField field={p} renderItem={(a) => <TemplateItem a={a} variables={variables} />} />;
}

/** 위키 규칙 폼이 문서 틀 위젯에 더하는 위젯 표(이름 → 필드). 모르는 이름은 스키마 타입 기본 위젯. */
export const WIKI_RULE_WIDGET_FIELDS: Readonly<Record<string, ComponentType<SchemaFormFieldProps>>> = {
  [KNOWN_UI_WIDGETS.GLOB]: GlobField,
  [KNOWN_UI_WIDGETS.TEMPLATE_TEXT]: WikiTemplateTextField,
};
