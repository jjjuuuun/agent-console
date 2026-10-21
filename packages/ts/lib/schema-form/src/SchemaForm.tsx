import Form from "@rjsf/core";
import { TranslatableString, deepEquals, getDefaultFormState } from "@rjsf/utils";
import type { FieldProps, RJSFSchema, UiSchema as RjsfUiSchema, WidgetProps } from "@rjsf/utils";
import validator from "@rjsf/validator-ajv8";
import { Component, useEffect, useId, useMemo, useRef, useState } from "react";
import type { ComponentType, ReactNode } from "react";
import { mergeErrorSchemas, parsePointer, toErrorSchema, translateErrors } from "./errors";
import type { ErrorNode } from "./errors";
import { resolveMessages } from "./messages";
import { collapseEmptyNullable, normalizeNullable, nullableUiSchema } from "./nullable";
import { buttonTemplates } from "./buttons";
import { ProvenanceContext, ProvenanceFieldTemplate } from "./ProvenanceFieldTemplate";
import type { ProvenanceContextValue } from "./ProvenanceFieldTemplate";
import { applyDeprecated } from "./deprecated";
import type { DeprecatedApplied } from "./deprecated";
import { changedPaths, deepMerge, extractLayerValue, fieldProvenance } from "./provenance";
import { XUiContext, XUiFieldTemplate, XUiObjectFieldTemplate } from "./XUiParts";
import type { XUiContextValue } from "./XUiParts";
import { CheckboxFieldWidget, LabeledRadioWidget, LabeledSelectWidget } from "./fieldWidgets";
import { RawJsonEditor } from "./RawJsonEditor";
import { mergeUi, RAW_JSON_FIELD, rawJsonUiSchema } from "./rawFields";
import type { JsonSchema, SchemaFormFieldProps, SchemaFormMessages, SchemaFormProps, SchemaFormWidgetProps } from "./types";

const SCHEMA_KEYWORDS = ["type", "properties", "$ref", "oneOf", "anyOf", "allOf", "enum", "const", "items", "if"];

/** 폼으로 그릴 수 있는 스키마인지. `true`, `{}`, 빈 type 등은 원시 JSON 편집기로 대체한다. */
function isRenderable(schema: JsonSchema): schema is Record<string, unknown> {
  if (typeof schema !== "object" || schema === null) return false;
  const type = schema.type;
  if (type === "" || (Array.isArray(type) && type.length === 0)) return false;
  return SCHEMA_KEYWORDS.some((k) => k in schema);
}

/**
 * 스키마의 기본값을 채운 초기 값을 만든다. 앱이 처음 값을 만들 때 쓴다.
 * @param schema JSON Schema
 * @param value 이미 있는 값(있으면 빈 곳만 채움)
 */
export function getDefaultValue(rawSchema: JsonSchema, value?: unknown): unknown {
  const schema = normalizeNullable(rawSchema);
  return getDefaultFormState(validator, schema as RJSFSchema, value as never, schema as RJSFSchema);
}

function countArrayItems(v: unknown): number {
  if (Array.isArray(v)) return v.length + v.reduce<number>((n, x) => n + countArrayItems(x), 0);
  if (v && typeof v === "object") return Object.values(v).reduce<number>((n, x) => n + countArrayItems(x), 0);
  return 0;
}

function pointerToId(prefix: string, pointer: string): string {
  return [prefix, ...parsePointer(pointer)].join("_");
}

function messageTranslator(m: SchemaFormMessages) {
  return (str: TranslatableString, params?: string[]): string => {
    switch (str) {
      case TranslatableString.AddItemButton:
      case TranslatableString.AddButton:
        return m.addItem;
      case TranslatableString.RemoveButton:
        return m.removeItem;
      case TranslatableString.MoveUpButton:
        return m.moveUp;
      case TranslatableString.MoveDownButton:
        return m.moveDown;
      case TranslatableString.ArrayItemTitle:
        return m.itemTitle;
      case TranslatableString.EmptyArray:
        return m.emptyArray;
      case TranslatableString.YesLabel:
        return m.yes;
      case TranslatableString.NoLabel:
        return m.no;
      default: {
        // 나머지는 영어 기본 문구를 그대로 쓰되 %1 자리만 치환한다.
        let text = String(str);
        params?.forEach((p, i) => {
          text = text.replace(`%${i + 1}`, p);
        });
        return text;
      }
    }
  };
}

function adaptWidget(Custom: ComponentType<SchemaFormWidgetProps>): ComponentType<WidgetProps> {
  function Adapted(p: WidgetProps) {
    return (
      <Custom
        id={p.id}
        value={p.value}
        onChange={(v) => p.onChange(v)}
        onBlur={() => p.onBlur(p.id, p.value)}
        label={p.label}
        required={!!p.required}
        disabled={!!p.disabled}
        readonly={!!p.readonly}
        placeholder={p.placeholder}
        schema={p.schema as Record<string, unknown>}
        options={p.options as Record<string, unknown>}
        errors={(p.rawErrors ?? []).map(String)}
      />
    );
  }
  return Adapted;
}

function adaptFields(custom: Record<string, ComponentType<SchemaFormFieldProps>> | undefined): Record<string, ComponentType<FieldProps>> {
  const out: Record<string, ComponentType<FieldProps>> = {};
  for (const [name, Custom] of Object.entries(custom ?? {})) {
    out[name] = function CustomField(p: FieldProps) {
      const ui = (p.uiSchema ?? {}) as Record<string, unknown>;
      const options = (typeof ui["ui:options"] === "object" && ui["ui:options"] !== null ? ui["ui:options"] : {}) as Record<string, unknown>;
      const id = p.fieldPathId?.$id ?? name;
      return (
        <Custom
          id={id}
          value={p.formData}
          onChange={(v) => p.onChange(v as never, p.fieldPathId.path)}
          onBlur={() => p.onBlur(id, p.formData as never)}
          label={(p.schema.title as string | undefined) ?? p.name ?? ""}
          required={!!p.required}
          disabled={!!p.disabled}
          readonly={!!p.readonly}
          schema={p.schema as Record<string, unknown>}
          options={options}
          errors={(Array.isArray(p.rawErrors) ? p.rawErrors : []).map(String)}
        />
      );
    };
  }
  return out;
}

class FormBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  override state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  override render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

/**
 * JSON Schema(+uiSchema)로 입력 폼을 그린다. 제어형이며 API·앱·전역 상태를 모른다.
 * 스타일은 `@agent-console/schema-form/styles.css`(CSS 변수 `--ac-*` 사용)를 앱이 한 번 로드한다.
 */
export function SchemaForm(props: SchemaFormProps) {
  const {
    uiSchema,
    value,
    onChange,
    errors,
    disabled,
    readonly,
    idPrefix = "root",
    focusPath,
    onFocusReached,
    focusTimeoutMs = 5000,
    customWidgets,
    customFields,
    validateOn = "blur",
    rawJsonToggle = true,
    className,
    xui = true,
    advancedStorageKey,
    compactProvenance = false,
  } = props;
  const messages = useMemo(() => resolveMessages(props.messages), [props.messages]);
  const baseSchema = useMemo(() => normalizeNullable(props.schema), [props.schema]);
  // `deprecated: true` 필드: 값이 없으면 빼고, 있으면 칩·안내를 단다(일반 규칙, 필드 이름 비교 없음).
  const depValue = props.provenance !== undefined && props.effectiveValue !== undefined ? deepMerge(props.effectiveValue, value) : value;
  const nextDep = typeof baseSchema === "object" && baseSchema !== null ? applyDeprecated(baseSchema as Record<string, unknown>, depValue, messages) : undefined;
  // 스키마 identity는 (원본 스키마, 폐기 필드 표시 상태, 문구)가 같으면 유지한다(값이 바뀔 때마다 폼이 다시 만들어지지 않게).
  const [dep, setDep] = useState({ base: baseSchema as unknown, key: nextDep?.key ?? "", messages: messages as unknown, applied: nextDep });
  const depStale = dep.base !== baseSchema || dep.key !== (nextDep?.key ?? "") || dep.messages !== messages;
  if (depStale) setDep({ base: baseSchema, key: nextDep?.key ?? "", messages, applied: nextDep });
  const applied: DeprecatedApplied | undefined = depStale ? nextDep : dep.applied;
  const schema = (applied?.schema ?? baseSchema) as typeof baseSchema;
  const deprecatedUi = applied?.ui;
  const formUiSchema = useMemo(() => {
    if (typeof schema !== "object" || schema === null) return uiSchema;
    // 값의 모양을 스키마가 정하지 않는 위치는 원시 JSON 필드로(호출 측 uiSchema가 우선)
    // 선언된 속성이 있는 루트 객체는 "속성 추가" 단추를 숨긴다(뜻을 알 수 없는 + 버튼). 호출 측 uiSchema가 우선이고, 원시 JSON 보기로 자유 키를 넣을 수 있다.
    const root = schema as Record<string, unknown>;
    const fixedRoot = typeof root["properties"] === "object" && root["properties"] !== null && Object.keys(root["properties"]).length > 0 ? { "ui:options": { expandable: false } } : undefined;
    return nullableUiSchema(schema, mergeUi(mergeUi(mergeUi(fixedRoot, rawJsonUiSchema(root)), deprecatedUi), uiSchema));
  }, [schema, uiSchema, deprecatedUi]);
  const containerRef = useRef<HTMLDivElement>(null);
  const rawId = useId();
  const [raw, setRaw] = useState(false);
  const [touched, setTouched] = useState(false);
  const [announce, setAnnounce] = useState("");
  const prevCount = useRef(countArrayItems(value));

  const renderable = isRenderable(schema);
  const showRaw = raw || !renderable;

  const widgets = useMemo(() => {
    const out: Record<string, ComponentType<WidgetProps>> = { CheckboxWidget: CheckboxFieldWidget, SelectWidget: LabeledSelectWidget, RadioWidget: LabeledRadioWidget };
    for (const [name, W] of Object.entries(customWidgets ?? {})) out[name] = adaptWidget(W);
    return out;
  }, [customWidgets]);

  const { provenance, layers, editLayerId, effectiveValue, layerValues, onOverride, onInherit, disabledPaths, fieldWarnings, mergeNotes, onOpenLayer, renderProvenanceBadge } = props;
  // 출처 표시는 선택 기능: provenance 또는 disabledPaths가 있을 때만 켠다.
  const provEnabled = provenance !== undefined || disabledPaths !== undefined;
  const templates = useMemo(
    () => ({
      ButtonTemplates: buttonTemplates(messages),
      ...(provEnabled ? { FieldTemplate: ProvenanceFieldTemplate } : xui ? { FieldTemplate: XUiFieldTemplate } : {}),
      ...(xui ? { ObjectFieldTemplate: XUiObjectFieldTemplate } : {}),
    }),
    [messages, provEnabled, xui],
  );
  const xuiContext = useMemo<XUiContextValue | null>(
    () =>
      xui
        ? {
            messages,
            value,
            focusPath,
            advancedStorageKey,
            // 행 칩과 같은 판정(fieldProvenance)을 "지정 N"에도 쓴다. 출처 표시가 꺼져 있으면 undefined(템플릿이 값·기본값으로 판단).
            ...(provEnabled
              ? {
                  isFieldSet: (pointer: string, container: boolean) =>
                    fieldProvenance({ pointer, container, provenance: provenance ?? {}, layers: layers ?? [], editLayerId, layerValue: value }).state === "set",
                }
              : {}),
          }
        : null,
    [xui, messages, value, focusPath, advancedStorageKey, provEnabled, provenance, layers, editLayerId],
  );
  const provContext = useMemo<ProvenanceContextValue | null>(
    () =>
      provEnabled
        ? {
            messages,
            layers: layers ?? [],
            provenance: provenance ?? {},
            layerValue: value,
            compact: compactProvenance,
            props: { editLayerId, layerValues, onOverride, onInherit, disabledPaths, fieldWarnings, mergeNotes, onOpenLayer, renderProvenanceBadge },
          }
        : null,
    [provEnabled, compactProvenance, messages, layers, provenance, value, editLayerId, layerValues, onOverride, onInherit, disabledPaths, fieldWarnings, mergeNotes, onOpenLayer, renderProvenanceBadge],
  );
  // 폼 엔진에는 (상속 값 + 이 층 값)을 보여 주고, onChange로는 이 층 값만 돌려준다.
  const formValue = useMemo(
    () => (provenance !== undefined && effectiveValue !== undefined ? deepMerge(effectiveValue, value) : value),
    [provenance, effectiveValue, value],
  );
  const fields = useMemo(
    () => ({
      ...adaptFields(customFields),
      [RAW_JSON_FIELD]: function RawJsonField(p: FieldProps) {
        const id = p.fieldPathId?.$id ?? "raw";
        const label = (p.schema.title as string | undefined) ?? p.name ?? "";
        const extra = Array.isArray(p.rawErrors) ? p.rawErrors.map(String) : [];
        return (
          <RawJsonEditor
            id={id}
            value={p.formData}
            onChange={(v) => p.onChange(v as never, p.fieldPathId.path)}
            label={label}
            invalidMessage={messages.invalidJson}
            disabled={!!p.disabled}
            readonly={!!p.readonly}
            errors={extra}
          />
        );
      },
    }),
    [messages, customFields],
  );

  const translateString = useMemo(() => messageTranslator(messages), [messages]);

  const extraErrors = useMemo(() => {
    let tree: ErrorNode = errors && errors.length > 0 ? toErrorSchema(errors) : {};
    if (renderable && (validateOn === "change" || (validateOn === "blur" && touched))) {
      const result = validator.validateFormData(formValue, schema as RJSFSchema, undefined, (errs) => translateErrors(errs, messages));
      tree = mergeErrorSchemas(result.errorSchema as ErrorNode, tree);
    }
    return tree;
  }, [errors, renderable, validateOn, touched, formValue, schema, messages]);

  useEffect(() => {
    const count = countArrayItems(value);
    if (count > prevCount.current) setAnnounce(messages.itemAdded);
    else if (count < prevCount.current) setAnnounce(messages.itemRemoved);
    prevCount.current = count;
  }, [value, messages]);

  // focusPath 필드는 비동기로 그려질 수 있어(스키마·값 로드 후) 생길 때까지 기다린다.
  // MutationObserver로 요소가 나타나면 포커스하고, 다른 처리가 포커스를 빼앗으면 시간 제한 안에서 다시 가져온다.
  // 사용자가 누르거나 키를 치면 멈춘다. 첫 포커스 성공 때 onFocusReached를 부른다.
  const onFocusReachedRef = useRef(onFocusReached);
  useEffect(() => {
    onFocusReachedRef.current = onFocusReached;
  });
  useEffect(() => {
    const root = containerRef.current;
    if (focusPath == null || !root) return;
    const id = pointerToId(idPrefix, focusPath);
    const doc = root.ownerDocument;
    const find = () =>
      root.querySelector<HTMLElement>(`[id="${CSS.escape(id)}"]`) ?? root.querySelector<HTMLElement>(`[id^="${CSS.escape(id)}"]`);
    let reached = false;
    let held = 0;
    const attempt = () => {
      const el = find();
      if (!el) return;
      if (doc.activeElement === el) {
        held += 1;
        return;
      }
      const active = doc.activeElement;
      if (reached && active && active !== doc.body && !root.contains(active) && active.closest(".react-flow") === null) {
        stop();
        return;
      }
      el.focus();
      held = 0;
      if (!reached) {
        reached = true;
        onFocusReachedRef.current?.(el);
      }
    };
    const timer = setInterval(() => {
      attempt();
      if (held >= 3) stop();
    }, 100);
    const deadline = setTimeout(() => stop(), focusTimeoutMs);
    const observer = typeof MutationObserver === "undefined" ? null : new MutationObserver(attempt);
    observer?.observe(root, { childList: true, subtree: true });
    function stop() {
      clearInterval(timer);
      clearTimeout(deadline);
      observer?.disconnect();
      doc.removeEventListener("pointerdown", stop, true);
      doc.removeEventListener("keydown", stop, true);
    }
    doc.addEventListener("pointerdown", stop, true);
    doc.addEventListener("keydown", stop, true);
    attempt();
    return stop;
  }, [focusPath, idPrefix, focusTimeoutMs]);

  const emptyObject =
    renderable &&
    schema.type === "object" &&
    !schema.properties &&
    schema.additionalProperties === undefined &&
    !schema.oneOf &&
    !schema.anyOf &&
    !schema.allOf;

  const rawEditor = (
    <RawJsonEditor
      id={`${idPrefix}__raw`}
      value={value}
      onChange={onChange}
      label={messages.rawJsonLabel}
      invalidMessage={messages.invalidJson}
      disabled={disabled}
      readonly={readonly}
    />
  );

  const toggle =
    rawJsonToggle && renderable ? (
      <div className="ac-sf-toolbar">
        <button
          type="button"
          className="ac-sf-toggle"
          aria-pressed={raw}
          aria-controls={rawId}
          onClick={() => setRaw((r) => !r)}
        >
          {raw ? messages.formViewToggle : messages.rawJsonToggle}
        </button>
      </div>
    ) : null;

  return (
    <div ref={containerRef} className={["ac-schema-form ac-text", className].filter(Boolean).join(" ")} id={rawId}>
      {toggle}
      {!renderable ? <p className="ac-sf-hint">{messages.schemaUnusable}</p> : null}
      {showRaw ? (
        rawEditor
      ) : (
        <FormBoundary
          key={JSON.stringify(schema)}
          fallback={
            <>
              <p className="ac-sf-error" role="alert">
                ⚠ {messages.schemaUnusable}
              </p>
              {rawEditor}
            </>
          }
        >
          {emptyObject ? <p className="ac-sf-hint">{messages.emptyObject}</p> : null}
          <XUiContext.Provider value={xuiContext}>
          <ProvenanceContext.Provider value={provContext}>
          <Form
            schema={schema as RJSFSchema}
            uiSchema={formUiSchema as RjsfUiSchema | undefined}
            formData={formValue}
            validator={validator}
            idPrefix={idPrefix}
            disabled={disabled}
            readonly={readonly}
            widgets={widgets}
            fields={fields}
            templates={templates}
            extraErrors={extraErrors as never}
            noHtml5Validate
            showErrorList={false}
            liveValidate={false}
            translateString={translateString}
            onBlur={() => setTouched(true)}
            onChange={(e) => {
              // 마운트 시 기본값 채움 등 사용자 편집이 아닌 변경은 통지하지 않는다.
              const shown = getDefaultFormState(validator, schema as RJSFSchema, formValue as never, schema as RJSFSchema);
              if (deepEquals(e.formData, shown)) return;
              const next = collapseEmptyNullable(schema, e.formData);
              const extra = provenance !== undefined && compactProvenance ? changedPaths(collapseEmptyNullable(schema, shown), next) : [];
              onChange?.(provenance !== undefined ? extractLayerValue(next, value, provenance, editLayerId, extra) : next);
            }}
          >
            <></>
          </Form>
          </ProvenanceContext.Provider>
          </XUiContext.Provider>
        </FormBoundary>
      )}
      <div className="ac-sf-sr-only" aria-live="polite" role="status">
        {announce}
      </div>
    </div>
  );
}
