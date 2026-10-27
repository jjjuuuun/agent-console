import { InlineMarkdown, stripInlineMarkdown } from "./InlineMarkdown";
import { getDefaultRegistry } from "@rjsf/core";
import type { FieldTemplateProps, ObjectFieldTemplateProps } from "@rjsf/utils";
import { createContext, useContext, useEffect, useId, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { deepEquals } from "@rjsf/utils";
import { parsePointer } from "./errors";
import type { SchemaFormMessages } from "./types";
import { FieldHelpPopover, FieldHelpTip, hasFieldHelp, isHelpKey, needsOwnLabel } from "./FieldHelp";
import { hasErrorNode, humanizeEnumText, readXUi, resolveNode, resolveTier, splitByTier } from "./xui";
import type { SplitEntry } from "./xui";

/** SchemaForm이 내려 주는 `x-ui` 렌더 설정. 없으면(Provider 밖) 템플릿은 기본 동작으로 돌아간다. */
export interface XUiContextValue {
  messages: SchemaFormMessages;
  /** 이 층(또는 폼) 값. "지정 N" 계산용 */
  value: unknown;
  focusPath: string | null | undefined;
  advancedStorageKey: string | undefined;
  /** 출처 표시 모드면 행 칩과 같은 "이 층에서 지정" 판정. 없으면 값·기본값 비교로 판단한다 */
  isFieldSet?: (pointer: string, container: boolean) => boolean;
}

export const XUiContext = createContext<XUiContextValue | null>(null);

const fill = (t: string, vars: Record<string, string | number>) => t.replace(/\{(\w+)\}/g, (_, k: string) => (k in vars ? String(vars[k]) : `{${k}}`));

function isEmpty(v: unknown): boolean {
  return v === undefined || v === null || v === "";
}

function show(v: unknown, m: SchemaFormMessages): string {
  if (typeof v === "boolean") return v ? m.yes : m.no;
  return typeof v === "string" ? v : JSON.stringify(v);
}

/** 필수 칩(색만으로 구분하지 않고 글자도 둔다). */
export function RequiredChip({ messages }: { messages: SchemaFormMessages }) {
  return <span className="ac-sf-required">{messages.requiredChip}</span>;
}

/** 필드 설명 한 줄(최대 2줄 clamp). */
export function FieldDescription({ text, id }: { text: string | undefined; id?: string }) {
  if (!text) return null;
  return (
    <p className="ac-sf-desc" id={id} title={stripInlineMarkdown(text)}>
      <InlineMarkdown text={text} />
    </p>
  );
}

/** 단위 접미사를 입력 오른쪽에 붙인다. */
export function UnitWrap({ unit, children }: { unit: string | undefined; children: ReactNode }) {
  if (!unit) return <>{children}</>;
  return (
    <div className="ac-sf-unit-wrap">
      {children}
      <span className="ac-sf-unit">{unit}</span>
    </div>
  );
}

/** 읽기 전용 값: 입력이 아닌 텍스트 + 복사 버튼. */
export function ReadOnlyValue({ value, messages: m }: { value: unknown; messages: SchemaFormMessages }) {
  const [copied, setCopied] = useState(false);
  const text = isEmpty(value) ? "" : show(value, m);
  const copy = () => {
    void navigator.clipboard?.writeText(text).then(() => setCopied(true), () => undefined);
  };
  return (
    <div className="ac-sf-readonly">
      <code className="ac-sf-readonly-value">{text === "" ? m.emptyValue : text}</code>
      {text === "" ? null : (
        <button type="button" className="ac-sf-copy" onClick={copy}>
          {copied ? m.copiedValue : m.copyValue}
        </button>
      )}
    </div>
  );
}

/** 이 필드를 `x-ui` 레이아웃으로 그려야 하는가(루트·배열 원소·숨김·객체 컨테이너는 기본 템플릿). */
export function isXUiLeaf(p: FieldTemplateProps): boolean {
  const path = p.fieldPathId.path as (string | number)[];
  if (p.hidden || path.length === 0 || path.some((s) => typeof s === "number")) return false;
  const s = p.schema as { type?: unknown; properties?: unknown };
  const customField = typeof (p.uiSchema as Record<string, unknown> | undefined)?.["ui:field"] === "string";
  return customField || !(s.type === "object" && typeof s.properties === "object" && s.properties !== null);
}

/** 출처 표시가 없는 폼의 필드 행. 라벨 줄(라벨·필수, 도움말 말풍선), 입력(+단위), 한 줄 설명, 오류. 예시·기본값·바꾸는 때는 `Alt+I` 팝오버(라벨 호버·포커스 때는 말풍선). */
export function XUiFieldTemplate(p: FieldTemplateProps) {
  const ctx = useContext(XUiContext);
  const Default = getDefaultRegistry().templates.FieldTemplate;
  const popId = useId();
  const [helpOpen, setHelpOpen] = useState(false);
  if (!ctx || !isXUiLeaf(p)) return <Default {...p} />;
  const m = ctx.messages;
  const schema = p.schema as Record<string, unknown>;
  const root = p.registry.rootSchema;
  const xui = readXUi(schema);
  const rawText = p.rawDescription ?? (typeof schema["description"] === "string" ? schema["description"] : undefined);
  const descriptionText = rawText === undefined ? undefined : humanizeEnumText(rawText, xui.enumLabels);
  const readOnlyValue = schema["readOnly"] === true;
  const helpable = hasFieldHelp(schema, p.readonly);
  const ownLabel = !(p.displayLabel && p.label) && needsOwnLabel(p);
  const labelNode =
    p.displayLabel && p.label ? (
      <label className="control-label ac-sf-help-target" htmlFor={p.id}>
        {p.label}
      </label>
    ) : p.label && ownLabel ? (
      <span className="control-label ac-sf-label-text ac-sf-help-target">{p.label}</span>
    ) : null;
  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!helpable || !isHelpKey(e)) return;
    e.preventDefault();
    e.stopPropagation();
    setHelpOpen((o) => !o);
  };
  return (
    <div className={[p.classNames, "ac-sf-field"].filter(Boolean).join(" ")} style={p.style} data-tier={resolveTier(schema, !!p.required, root)} data-own-label={ownLabel || undefined} onKeyDown={onKeyDown}>
      {labelNode || p.required ? (
        <div className="ac-sf-labelrow ac-sf-help-host" data-help={(helpable && labelNode !== null) || undefined}>
          {labelNode}
          {p.required ? <RequiredChip messages={m} /> : null}
          {helpable && labelNode !== null ? <FieldHelpTip schema={schema} readonly={p.readonly ?? false} messages={m} /> : null}
        </div>
      ) : null}
      {readOnlyValue ? (
        <ReadOnlyValue value={p.formData} messages={m} />
      ) : (
        <UnitWrap unit={xui.unit}>{p.children}</UnitWrap>
      )}
      <FieldDescription text={descriptionText} />
      {p.errors}
      {p.help}
      {helpOpen && helpable ? (
        <FieldHelpPopover id={popId} schema={schema} formData={p.formData} readonly={p.readonly} disabled={p.disabled} messages={m} onFill={(v) => p.onChange(v as never, p.fieldPathId.path)} />
      ) : null}
    </div>
  );
}

function storageKey(key: string): string {
  return `ac.form.advanced.${key}`;
}
function readOpen(key: string | undefined): boolean {
  if (!key) return false;
  try {
    return globalThis.localStorage?.getItem(storageKey(key)) === "1";
  } catch {
    return false;
  }
}
function writeOpen(key: string | undefined, open: boolean): void {
  if (!key) return;
  try {
    globalThis.localStorage?.setItem(storageKey(key), open ? "1" : "0");
  } catch {
    /* 저장 불가 환경은 기억하지 않는다 */
  }
}

type Prop = ObjectFieldTemplateProps["properties"][number];

function AdvancedDisclosure(props: { entries: SplitEntry<Prop>[]; setCount: number; errorCount: number; focusTarget: string | undefined; ctx: XUiContextValue; groupTitles: Map<string, string> }) {
  const { entries, ctx, errorCount, focusTarget } = props;
  const m = ctx.messages;
  const key = ctx.advancedStorageKey;
  // 열림은 `open` 하나다. 사용자 클릭이 항상 이기고, 자동 열기는 이벤트(오류 증가·focusPath 변경)로만 하며 자동 접기는 없다.
  const [state, setState] = useState(() => ({ key, open: readOpen(key) }));
  let open = state.open;
  if (state.key !== key) {
    // 폼 종류(키)가 바뀌면 새 키의 저장값으로 다시 맞춘다(토글 전에는 쓰지 않는다).
    open = readOpen(key);
    setState({ key, open });
  }
  const panelId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const prevErrors = useRef(0);
  const prevFocus = useRef<string | undefined>(undefined);
  const scrollToError = () => {
    panelRef.current?.querySelector<HTMLElement>("[aria-invalid='true'], .has-error, .text-danger, .ac-sf-error")?.scrollIntoView?.({ block: "nearest" });
  };
  useEffect(() => {
    if (errorCount > prevErrors.current) {
      setState((st) => ({ ...st, open: true }));
      scrollToError();
    }
    prevErrors.current = errorCount;
  }, [errorCount]);
  useEffect(() => {
    if (focusTarget !== undefined && focusTarget !== prevFocus.current) setState((st) => ({ ...st, open: true }));
    prevFocus.current = focusTarget;
  }, [focusTarget]);
  const toggle = () => {
    const next = !open;
    setState({ key, open: next });
    writeOpen(key, next);
  };
  // 그룹: 그룹 없는 필드가 먼저, 그다음 그룹을 처음 나온 순서대로
  const groups: { id: string | undefined; items: SplitEntry<Prop>[] }[] = [];
  for (const e of entries) {
    const id = e.xui.group;
    let g = groups.find((x) => x.id === id);
    if (!g) {
      g = { id, items: [] };
      groups.push(g);
    }
    g.items.push(e);
  }
  groups.sort((a, b) => Number(a.id !== undefined) - Number(b.id !== undefined));
  return (
    <div className="ac-sf-advanced" data-open={open || undefined}>
      <div className="ac-sf-adv-bar">
        <button type="button" className="ac-sf-adv-toggle" aria-expanded={open} aria-controls={panelId} onClick={toggle}>
          <svg className="ac-sf-adv-chevron" viewBox="0 0 16 16" width="12" height="12" aria-hidden="true" focusable="false">
            <path d="M6 3l5 5-5 5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          {fill(m.advancedTitle, { count: entries.length })}
        </button>
        {props.setCount > 0 ? <span className="ac-sf-chip ac-sf-adv-set">{fill(m.advancedSetCount, { count: props.setCount })}</span> : null}
        {errorCount > 0 ? (
          <span className="ac-sf-chip ac-sf-adv-error" role="status">
            <span aria-hidden="true">✕ </span>
            {fill(m.advancedErrorCount, { count: errorCount })}
          </span>
        ) : null}
      </div>
      <div id={panelId} ref={panelRef} className="ac-sf-adv-panel" hidden={!open}>
        {groups.map((g) => (
          <section key={g.id ?? "_"} className="ac-sf-adv-group">
            {g.id !== undefined ? <h4 className="ac-sf-adv-group-title">{props.groupTitles.get(g.id) ?? g.id}</h4> : null}
            {g.items.map((e) => (
              <div key={e.name} className="ac-sf-adv-item">
                {e.item.content}
              </div>
            ))}
          </section>
        ))}
      </div>
    </div>
  );
}

/**
 * 최상위 객체의 속성을 기본/고급으로 나눈다. 고급이 없거나 기본이 없으면 기본 템플릿 그대로.
 * 기본 필드는 기본 템플릿 안에(제목·설명 유지), 고급은 그 아래 접는 영역에 둔다.
 */
export function XUiObjectFieldTemplate(p: ObjectFieldTemplateProps) {
  const ctx = useContext(XUiContext);
  const Default = getDefaultRegistry().templates.ObjectFieldTemplate;
  const isRoot = (p.fieldPathId.path as unknown[]).length === 0;
  if (!ctx || !isRoot) return <Default {...p} />;
  const root = p.registry.rootSchema;
  const visible = p.properties.filter((x) => !x.hidden);
  const { basic, advanced } = splitByTier(visible, p.schema, root);
  const hiddenProps = p.properties.filter((x) => x.hidden);
  // 접는 영역이 없는 폼은 의도다: 고급이 없으면 그대로, 기본이 없으면 전부 펼쳐 두고 이유를 한 줄로 알린다.
  if (advanced.length === 0) return <Default {...p} />;
  if (basic.length === 0) {
    return (
      <>
        <p className="ac-sf-adv-allhint">{ctx.messages.advancedAllHint}</p>
        <Default {...p} />
      </>
    );
  }
  const props = resolveNode(p.schema, root);
  const propSchemas = (props["properties"] ?? {}) as Record<string, unknown>;
  const groupTitles = new Map<string, string>();
  for (const e of advanced) if (e.xui.group && e.xui.groupTitle) groupTitles.set(e.xui.group, e.xui.groupTitle);
  const values = typeof ctx.value === "object" && ctx.value !== null ? (ctx.value as Record<string, unknown>) : {};
  const setCount = advanced.filter((e) => {
    const v = values[e.name];
    if (v === undefined || v === null) return false; // 명시적 null = "지정 안 함"
    const node = resolveNode(propSchemas[e.name], root);
    if (ctx.isFieldSet) {
      const container = node["type"] === "object" && typeof node["properties"] === "object" && node["properties"] !== null;
      return ctx.isFieldSet(`/${e.name}`, container);
    }
    return !deepEquals(v, node["default"]);
  }).length;
  const errorCount = advanced.filter((e) => hasErrorNode((e.item.content.props as { errorSchema?: unknown }).errorSchema)).length;
  const focusFirst = ctx.focusPath != null ? parsePointer(ctx.focusPath)[0] : undefined;
  const focusTarget = focusFirst !== undefined && advanced.some((e) => e.name === focusFirst) ? String(ctx.focusPath) : undefined;
  return (
    <>
      <Default {...p} properties={[...hiddenProps, ...basic.map((e) => e.item)]} />
      <AdvancedDisclosure entries={advanced} setCount={setCount} errorCount={errorCount} focusTarget={focusTarget} ctx={ctx} groupTitles={groupTitles} />
    </>
  );
}

