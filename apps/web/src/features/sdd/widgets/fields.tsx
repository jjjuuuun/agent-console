/**
 * 규칙 폼 `x-ui.widget` 위젯 8종(screen-sdd §10.2). 위젯 이름은 계약 `KNOWN_UI_WIDGETS` 상수이고 어떤 필드가 어떤 위젯을 쓰는지는 서버 스키마가 정한다.
 * 모든 위젯은 `SchemaFormFieldProps`만 받는다(`customFields`): API·화면 상태는 `SddWidgetEnv`·`ConfigIssuesProvider` 문맥에서 읽는다.
 * 정규식은 웹이 평가하지 않는다 — 서버 검사 이슈를 칸 아래에 보인다.
 */
import { useId, useRef, type ComponentType } from "react";
import { KNOWN_UI_WIDGETS } from "@agent-console/contracts/constants";
import type { SchemaFormFieldProps } from "@agent-console/schema-form";
import { ToneChip } from "@agent-console/sdd-view";
import { ConditionListField, useConfigIssuesUnder } from "../../delegation";
import { TONE_CHOICES } from "../sddConfig";
import { sddMessages as m } from "../messages";
import { pointerOf, rootOf, ShapedField, type ItemRenderArgs } from "./ShapedField";
import { useSddWidgetEnv } from "./SddWidgetEnv";

/** 조건(`ac-conditions`): 팀 구성 연결의 조건 편집 부품을 그대로 쓴다. 이슈 위치는 폼이 알려 준 정확한 위치다. */
export function ConditionField(p: SchemaFormFieldProps) {
  const pointer = pointerOf(p);
  return <ConditionListField {...p} options={{ ...p.options, $rootSchema: rootOf(p), ...(pointer === undefined ? {} : { $pointer: pointer }) }} />;
}

/** 정규식 칸(mono). 문자열 하나 또는 정규식 목록. 검사는 서버가 한다. */
export function RegexField(p: SchemaFormFieldProps) {
  return (
    <ShapedField
      field={p}
      renderItem={(a: ItemRenderArgs) => (
        <input
          id={a.id}
          className="ac-input sdd-w-mono"
          spellCheck={false}
          autoComplete="off"
          aria-label={a.label}
          aria-invalid={a.invalid || undefined}
          aria-describedby={a.describedBy}
          placeholder={m.widgets.regexPlaceholder}
          value={a.value}
          disabled={a.disabled}
          onChange={(e) => a.onChange(e.target.value)}
        />
      )}
    />
  );
}

function TemplateItem({ a, variables }: { a: ItemRenderArgs; variables: readonly string[] }) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const insert = (name: string) => {
    const el = ref.current;
    const token = `{${name}}`;
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
      <textarea ref={ref} id={a.id} className="ac-input sdd-w-mono" rows={3} aria-label={a.label} aria-invalid={a.invalid || undefined} aria-describedby={a.describedBy} value={a.value} disabled={a.disabled} onChange={(e) => a.onChange(e.target.value)} />
      {variables.length > 0 ? (
        <div className="sdd-w-chips" role="group" aria-label={m.widgets.variables}>
          {variables.map((v) => (
            <button key={v} type="button" className="sdd-w-chip" disabled={a.disabled} aria-label={m.widgets.insertVariable(v)} onClick={() => insert(v)}>{`{${v}}`}</button>
          ))}
        </div>
      ) : null}
    </>
  );
}

/** 실행 입력 틀: 여러 줄 칸 + 변수 칩(누르면 커서 위치에 `{이름}`). 모르는 변수는 서버 경고가 칸 아래에 나온다. */
export function TemplateTextField(p: SchemaFormFieldProps) {
  const env = useSddWidgetEnv();
  return <ShapedField field={p} renderItem={(a) => <TemplateItem a={a} variables={env.variables} />} />;
}

/** 값 고르기(목록 + 직접 입력): 목록은 위젯 이름으로 `SddWidgetEnv`에서 온다. 목록에 없는 값은 칸 아래 경고. */
export function createRefField(widgetName: string, missing: (id: string) => string = m.widgets.refMissing): ComponentType<SchemaFormFieldProps> {
  function RefField(p: SchemaFormFieldProps) {
    const env = useSddWidgetEnv();
    const options = env.refs[widgetName] ?? null;
    const listId = useId();
    const issues = useConfigIssuesUnder(pointerOf(p));
    return (
      <ShapedField
        field={p}
        renderItem={(a) => (
          <>
            <input
              id={a.id}
              className="ac-input"
              list={options === null ? undefined : listId}
              autoComplete="off"
              aria-label={a.label}
              aria-invalid={a.invalid || undefined}
              aria-describedby={a.describedBy}
              value={a.value}
              disabled={a.disabled}
              onChange={(e) => a.onChange(e.target.value)}
            />
            {options === null ? null : (
              <datalist id={listId}>
                {options.map((o) => <option key={o.id} value={o.id}>{o.label ?? ""}</option>)}
              </datalist>
            )}
          </>
        )}
        itemNote={(value) => (options !== null && value !== "" && !options.some((o) => o.id === value) && issues.length === 0 ? <p className="sdd-w-note" data-tone="warning" data-testid="sdd-w-missing">{missing(value)}</p> : null)}
      />
    );
  }
  return RefField;
}

/** 톤: 제안 칩(미리보기) + 직접 입력. 값은 열린 문자열이다. */
export function ToneField(p: SchemaFormFieldProps) {
  return (
    <ShapedField
      field={p}
      renderItem={(a) => (
        <>
          <div className="sdd-w-tones" role="group" aria-label={m.widgets.toneGroup}>
            {TONE_CHOICES.map((c) => {
              const label = m.widgets.tones[c.labelKey] ?? c.tone;
              return (
                <button key={c.tone} type="button" className="sdd-w-tone" aria-pressed={a.value === c.tone} aria-label={label} disabled={a.disabled} onClick={() => a.onChange(a.value === c.tone ? "" : c.tone)}>
                  <ToneChip label={label} tone={c.tone} />
                </button>
              );
            })}
          </div>
          <input id={a.id} className="ac-input" autoComplete="off" aria-label={m.widgets.toneDirect} value={a.value} disabled={a.disabled} onChange={(e) => a.onChange(e.target.value)} />
        </>
      )}
    />
  );
}

/** 계약 위젯 이름 → 필드 컴포넌트. 모르는 이름은 표에 없어 스키마 타입 기본 위젯으로 그려진다. */
export const SDD_WIDGET_FIELDS: Readonly<Record<string, ComponentType<SchemaFormFieldProps>>> = {
  [KNOWN_UI_WIDGETS.CONDITION]: ConditionField,
  [KNOWN_UI_WIDGETS.REGEX]: RegexField,
  [KNOWN_UI_WIDGETS.TEMPLATE_TEXT]: TemplateTextField,
  [KNOWN_UI_WIDGETS.GRAPH_REF]: createRefField(KNOWN_UI_WIDGETS.GRAPH_REF, m.widgets.refMissingGraph),
  [KNOWN_UI_WIDGETS.PROFILE_REF]: createRefField(KNOWN_UI_WIDGETS.PROFILE_REF),
  [KNOWN_UI_WIDGETS.STATE_REF]: createRefField(KNOWN_UI_WIDGETS.STATE_REF),
  [KNOWN_UI_WIDGETS.STATUS_REF]: createRefField(KNOWN_UI_WIDGETS.STATUS_REF),
  [KNOWN_UI_WIDGETS.TONE]: ToneField,
};
