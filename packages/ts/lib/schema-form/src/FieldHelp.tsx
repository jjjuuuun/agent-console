import type { KeyboardEvent, ReactNode } from "react";
import { readXUi } from "./xui";
import type { SchemaFormMessages } from "./types";

const fill = (t: string, vars: Record<string, string | number>) => t.replace(/\{(\w+)\}/g, (_, k: string) => (k in vars ? String(vars[k]) : `{${k}}`));

function show(v: unknown, m: SchemaFormMessages): string {
  if (typeof v === "boolean") return v ? m.yes : m.no;
  return typeof v === "string" ? v : JSON.stringify(v);
}
const isEmpty = (v: unknown) => v === undefined || v === null || v === "";
/** 값이 한 줄로 보일 만한 기본값인지(객체·배열·빈 문자열은 제외). */
const hintableDefault = (d: unknown) => d !== undefined && d !== null && d !== "" && typeof d !== "object";

/** 스키마에서 팝오버에 넣을 내용(예시·기본값·바꾸는 때)이 있는가. */
export function hasFieldHelp(schema: Record<string, unknown>, readonly = false): boolean {
  const xui = readXUi(schema);
  return xui.example !== undefined || (hintableDefault(schema["default"]) && !readonly) || xui.when !== undefined;
}

/** Alt+I 키 판별. 필드 행의 onKeyDown에서 쓴다. */
export function isHelpKey(e: KeyboardEvent): boolean {
  return e.altKey && !e.ctrlKey && !e.metaKey && (e.code === "KeyI" || e.key.toLowerCase() === "i");
}

/** 값 출처 팝오버를 여는 ⓘ 버튼(`x-ui` 도움말이 없는 출처 전용 폼에서만 쓴다). 열림 상태는 부모가 쥔다. */
export function FieldHelpButton(p: { open: boolean; popoverId: string; label: string; onToggle: () => void }) {
  return (
    <button type="button" className="ac-sf-info" data-ac-sf-help aria-expanded={p.open} aria-controls={p.popoverId} aria-label={p.label} title={p.label} onClick={p.onToggle}>
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
        <path d="M5.9 6.1a2.2 2.2 0 1 1 3.3 1.9c-.8.5-1.2.9-1.2 1.8M8 12.3h.01" />
      </svg>
    </button>
  );
}

/**
 * 라벨에 호버·포커스하면 뜨는 말풍선(CSS만). 예시·기본값·바꾸는 때를 한 줄씩 보인다. 부모는 `.ac-sf-help-host[data-help]`이고
 * 라벨(`.ac-sf-help-target`)에 점선 밑줄이 붙는다. 내용이 없으면 아무것도 그리지 않는다. 자세히·예시 채우기는 `Alt+I` 팝오버.
 * 말풍선은 `<label>` 밖에 두고 장식(`aria-hidden`)이다: 같은 내용을 키보드·스크린 리더는 `Alt+I` 팝오버로 읽는다.
 */
export function FieldHelpTip(p: { schema: Record<string, unknown>; readonly: boolean; messages: SchemaFormMessages }) {
  const { schema, messages: m } = p;
  if (!hasFieldHelp(schema, p.readonly)) return null;
  const xui = readXUi(schema);
  const def = schema["default"];
  return (
    <span className="ac-sf-tip" aria-hidden="true" data-ac-sf-tip>
      {xui.example !== undefined ? <span className="ac-sf-tip-line">{fill(m.exampleHint, { value: show(xui.example, m) })}</span> : null}
      {hintableDefault(def) && !p.readonly ? <span className="ac-sf-tip-line">{fill(m.defaultHint, { value: show(def, m) })}</span> : null}
      {xui.when ? <span className="ac-sf-tip-line">{fill(m.whenHint, { when: xui.when })}</span> : null}
      <span className="ac-sf-tip-key">{m.helpToggle}</span>
    </span>
  );
}

interface PopoverProps {
  id: string;
  schema: Record<string, unknown>;
  formData: unknown;
  readonly: boolean;
  disabled: boolean;
  messages: SchemaFormMessages;
  /** 값 출처 같은 앱·템플릿별 추가 내용 */
  children?: ReactNode;
  onFill: (v: unknown) => void;
}

/**
 * ⓘ 팝오버 본문: 예시(클릭하면 빈 칸을 채움)·기본값·바꾸는 때, 그리고 추가 내용(값 출처).
 * 문구는 모두 `messages`에서 온다.
 */
export function FieldHelpPopover(p: PopoverProps) {
  const { schema, messages: m } = p;
  const xui = readXUi(schema);
  const def = schema["default"];
  const canFill = !p.readonly && !p.disabled && isEmpty(p.formData) && xui.example !== undefined;
  const fillValue = () => {
    const ex = xui.example;
    const t = schema["type"];
    const numeric = t === "number" || t === "integer" || (Array.isArray(t) && (t.includes("number") || t.includes("integer")));
    p.onFill(numeric && typeof ex === "string" && ex.trim() !== "" && !Number.isNaN(Number(ex)) ? Number(ex) : ex);
  };
  const exampleText = xui.example === undefined ? undefined : fill(m.exampleHint, { value: show(xui.example, m) });
  return (
    <div id={p.id} className="ac-sf-popover ac-sf-help" role="group" aria-label={m.helpTitle}>
      {exampleText ? (
        canFill ? (
          <button type="button" className="ac-sf-hintline ac-sf-example" data-ac-sf-example onClick={fillValue}>
            {exampleText}
          </button>
        ) : (
          <p className="ac-sf-hintline ac-sf-example">{exampleText}</p>
        )
      ) : null}
      {hintableDefault(def) && !p.readonly ? <p className="ac-sf-hintline ac-sf-default">{fill(m.defaultHint, { value: show(def, m) })}</p> : null}
      {xui.when ? <p className="ac-sf-hintline ac-sf-when">{fill(m.whenHint, { when: xui.when })}</p> : null}
      {p.children}
    </div>
  );
}

/**
 * 폼 엔진이 라벨을 그리지 않는 필드(배열·`ui:field`)인가. 이런 필드는 템플릿이 라벨 줄에 텍스트 라벨을 직접 그린다.
 * 객체 값은 안쪽 객체 템플릿이 제목을 그리므로 제외한다.
 */
export function needsOwnLabel(p: { schema: unknown; uiSchema?: unknown }): boolean {
  const schema = p.schema as { type?: unknown; properties?: unknown };
  const types = Array.isArray(schema.type) ? schema.type : [schema.type];
  const custom = typeof (p.uiSchema as Record<string, unknown> | undefined)?.["ui:field"] === "string";
  const objectValued = types.includes("object") && typeof schema.properties === "object" && schema.properties !== null;
  return !objectValued && (custom || types.includes("array"));
}
