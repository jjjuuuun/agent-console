import { useMemo } from "react";
import type { DelegationStrategyDescriptor, EdgeTypeDescriptor, InteractionKindDescriptor, NodeTypeDescriptor } from "@agent-console/contracts";
import { SchemaForm, type FormError, type SchemaFormFieldProps, type SchemaFormWidgetProps, type UiSchema } from "@agent-console/schema-form";
import { Button, Disclosure } from "@agent-console/ui";
import type { ComponentType } from "react";
import { deepMerge, getAt, setAt } from "../../lib/jsonPointer";
import { applyFormEdit } from "../../lib/formEdit";
import { resolveRef, unwrapNullable, type SchemaNode } from "../../lib/schemaTools";
import { CONFIG_FIELDS, CONFIG_WIDGETS, ConfigIssuesProvider, DEFAULT_TEAM_CONVENTIONS, bridgeWidgetUi, type ConfigIssue } from "../delegation";
import { SETTINGS_FIELDS, SETTINGS_WIDGETS, CHOICE_SELECT_WIDGET, buildUserSettingsUi } from "../settings";
import { teamMessages as t } from "./messages";
import { CHOICE_MULTI_FIELD, ChoiceMultiField } from "./widgets/ChoiceMultiWidget";
import { REVIEW_DECISIONS_FIELD, ReviewDecisionsField, nextDecisionId } from "./widgets/ReviewDecisionsField";
import { TEMPLATE_FIELD, TemplateField, parseVariables } from "./widgets/TemplateField";

const WIDGETS: Record<string, ComponentType<SchemaFormWidgetProps>> = { ...SETTINGS_WIDGETS };
const FIELDS: Record<string, ComponentType<SchemaFormFieldProps>> = {
  ...SETTINGS_FIELDS,
  [CHOICE_MULTI_FIELD]: ChoiceMultiField,
  [TEMPLATE_FIELD]: TemplateField,
  [REVIEW_DECISIONS_FIELD]: ReviewDecisionsField,
};

/** 연결 설정 폼의 `ui:field` 표: 팀 위젯 + 앱 위젯 레지스트리(조건 목록 등). */
const EDGE_FIELDS: Record<string, ComponentType<SchemaFormFieldProps>> = { ...FIELDS, ...CONFIG_FIELDS };
const NO_ISSUES: readonly ConfigIssue[] = [];

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);

function put(ui: Obj, pointer: string, spec: Obj): Obj {
  return setAt(ui, pointer, spec) as Obj;
}

/** 스키마에 해당 경로가 있을 때만 지정한다. */
function hasPath(root: SchemaNode, pointer: string): boolean {
  let cur: SchemaNode = root;
  for (const seg of pointer.split("/").slice(1)) {
    const { schema } = unwrapNullable(cur, root);
    const props = schema["properties"];
    const next = isObj(props) ? props[seg] : undefined;
    if (!isObj(next)) return false;
    cur = next;
  }
  return true;
}

// ---------------------------------------------------------------- 노드 config(정의에 묶이지 않은 노드)

/** 최상위 속성을 "객체 섹션"(널 허용 객체 포함)과 나머지로 가른다. 속성 이름이 아니라 스키마 모양으로 가른다. */
export function splitConfigSchema(descriptor: Pick<NodeTypeDescriptor, "config_schema">): { scalars: string[]; sections: { key: string; schema: SchemaNode; title: string; description?: string }[]; root: SchemaNode } {
  const root = (descriptor.config_schema ?? {}) as SchemaNode;
  const props = isObj(root["properties"]) ? (root["properties"] as Record<string, SchemaNode>) : {};
  const scalars: string[] = [];
  const sections: { key: string; schema: SchemaNode; title: string; description?: string }[] = [];
  for (const [key, raw] of Object.entries(props)) {
    const { schema } = unwrapNullable(raw, root);
    if (isObj(schema["properties"])) {
      const merged = { ...schema, ...(root["$defs"] === undefined ? {} : { $defs: root["$defs"] }) } as SchemaNode;
      sections.push({ key, schema: merged, title: typeof raw["title"] === "string" ? (raw["title"] as string) : key, ...(typeof schema["description"] === "string" ? { description: schema["description"] as string } : {}) });
    } else scalars.push(key);
  }
  return { scalars, sections, root };
}

/** 섹션 안 필드의 위젯 지정(설정 키 -> 위젯 이름 데이터). 스키마에 그 경로가 있을 때만 적용한다. */
function sectionUi(section: SchemaNode, kinds: readonly InteractionKindDescriptor[]): UiSchema {
  let ui = buildUserSettingsUi(section) as Obj;
  if (hasPath(section, "/decisions")) {
    const idSchema = (() => {
      const items = getAt(section, "/properties/decisions/items") as SchemaNode | undefined;
      const resolved = items === undefined ? undefined : resolveRef(items, section);
      const idProp = (resolved?.["properties"] as Record<string, SchemaNode> | undefined)?.["id"];
      return typeof idProp?.["pattern"] === "string" ? (idProp["pattern"] as string) : undefined;
    })();
    ui = put(ui, "/decisions", { "ui:field": REVIEW_DECISIONS_FIELD, "ui:options": idSchema === undefined ? {} : { idPattern: idSchema } });
  }
  if (hasPath(section, "/output_template")) {
    const desc = (getAt(section, "/properties/output_template") as SchemaNode | undefined)?.["description"];
    ui = put(ui, "/output_template", { "ui:field": TEMPLATE_FIELD, "ui:options": { variables: parseVariables(typeof desc === "string" ? desc : undefined) } });
  }
  if (hasPath(section, "/kind") && kinds.length > 0) {
    ui = put(ui, "/kind", { "ui:widget": CHOICE_SELECT_WIDGET, "ui:options": { choices: kinds.map((k) => ({ value: k.id, label: k.title })), emptyLabel: t.review.kindDefault } });
  }
  return ui as UiSchema;
}

/** 섹션을 켤 때 채울 시작 값: 필수 목록(최소 1개)이 있으면 항목 하나를 만든다. */
export function starterSection(section: SchemaNode): Obj {
  const props = isObj(section["properties"]) ? (section["properties"] as Record<string, SchemaNode>) : {};
  const required = Array.isArray(section["required"]) ? (section["required"] as string[]) : [];
  const out: Obj = {};
  for (const key of required) {
    const raw = props[key];
    if (raw === undefined) continue;
    const { schema } = unwrapNullable(raw, section);
    if (schema["type"] === "array" && typeof schema["minItems"] === "number" && schema["minItems"] > 0) {
      const item = isObj(schema["items"]) ? resolveRef(schema["items"] as SchemaNode, section) : {};
      const itemRequired = Array.isArray(item["required"]) ? (item["required"] as string[]) : [];
      const entry: Obj = {};
      for (const k of itemRequired) entry[k] = k === "id" ? nextDecisionId([]) : "";
      out[key] = [entry];
    }
  }
  return out;
}

export interface NodeConfigFormProps {
  descriptor: NodeTypeDescriptor;
  config: Obj;
  onChange: (next: Obj) => void;
  interactionKinds?: readonly InteractionKindDescriptor[];
  errors?: FormError[];
  disabled?: boolean;
}

function pickKeys(source: Obj, keys: readonly string[]): Obj {
  return Object.fromEntries(Object.entries(source).filter(([k]) => keys.includes(k)));
}

/**
 * 정의에 묶이지 않은 노드(사용자 노드 등)의 `config` 폼. 노드 타입의 `config_schema`가 그린다:
 * 단순 값은 한 폼으로, 객체 섹션(예: 중간 검토)은 접힘 블록 + 켜기/끄기로. 속성 이름·타입 이름은 코드에 없다.
 */
export function NodeConfigForm({ descriptor, config, onChange, interactionKinds = [], errors = [], disabled }: NodeConfigFormProps) {
  const { scalars, sections, root } = useMemo(() => splitConfigSchema(descriptor), [descriptor]);
  const scalarSchema = useMemo(() => {
    const props = (root["properties"] ?? {}) as Record<string, SchemaNode>;
    return { type: "object", properties: Object.fromEntries(scalars.map((k) => [k, props[k]])), ...(root["$defs"] === undefined ? {} : { $defs: root["$defs"] }) } as SchemaNode;
  }, [root, scalars]);
  if (scalars.length === 0 && sections.length === 0) return <p className="app-muted">{t.settings.noSchema}</p>;
  return (
    <div className="lib-form">
      {scalars.length > 0 ? (
        <SchemaForm
          schema={scalarSchema}
          {...(descriptor.ui_schema ? { uiSchema: descriptor.ui_schema as UiSchema } : {})}
          value={pickKeys(config, scalars)}
          onChange={(next) => onChange({ ...Object.fromEntries(Object.entries(config).filter(([k]) => !scalars.includes(k))), ...applyFormEdit(scalarSchema, pickKeys(config, scalars), next, { unsetOnDefault: true }) })}
          customWidgets={WIDGETS}
          customFields={FIELDS}
          rawJsonToggle={false}
          errors={errors.filter((e) => scalars.some((k) => e.path === `/${k}` || e.path.startsWith(`/${k}/`)))}
          {...(disabled === undefined ? {} : { disabled })}
          idPrefix="node-config"
          advancedStorageKey={`node-config:${descriptor.id}`}
        />
      ) : null}
      {sections.map((s) => {
        const current = config[s.key];
        const enabled = isObj(current);
        const sub = errors.filter((e) => e.path.startsWith(`/${s.key}`)).map((e) => ({ ...e, path: e.path.slice(s.key.length + 1) }));
        return (
          <Disclosure key={s.key} defaultOpen summary={<strong>{s.title}</strong>}>
            <div className="lib-form">
              {s.description ? <p className="app-muted lib-field-note">{s.description}</p> : null}
              {enabled ? (
                <>
                  <SchemaForm
                    schema={{ ...s.schema, title: undefined, description: undefined }}
                    uiSchema={sectionUi(s.schema, interactionKinds)}
                    value={current}
                    onChange={(next) => onChange({ ...config, [s.key]: applyFormEdit(s.schema, current as Obj, next, { unsetOnDefault: true }) })}
                    customWidgets={WIDGETS}
                    customFields={FIELDS}
                    rawJsonToggle={false}
                    errors={sub}
                    {...(disabled === undefined ? {} : { disabled })}
                    idPrefix={`node-config-${s.key}`}
                    advancedStorageKey={`node-section:${s.key}`}
                  />
                  <Button size="sm" variant="ghost" disabled={disabled === true} onClick={() => { const { [s.key]: _gone, ...rest } = config; void _gone; onChange(rest); }}>
                    {t.review.disable}
                  </Button>
                </>
              ) : (
                <>
                  <p className="app-muted">{t.review.empty}</p>
                  <Button size="sm" disabled={disabled === true} onClick={() => onChange({ ...config, [s.key]: starterSection(s.schema) })}>
                    {t.review.enable}
                  </Button>
                </>
              )}
            </div>
          </Disclosure>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------- 연결 config

export interface EdgeConfigFormProps {
  kind: EdgeTypeDescriptor;
  config: Obj;
  onChange: (next: Obj) => void;
  interactionKinds?: readonly InteractionKindDescriptor[];
  strategies?: readonly DelegationStrategyDescriptor[];
  errors?: FormError[];
  /** 서버 이슈(연결 config 기준 경로). 조건 목록처럼 중첩 값을 직접 그리는 위젯이 자기 행에 매단다 */
  issues?: readonly ConfigIssue[];
  disabled?: boolean;
}

/** 연결 종류의 `config_schema`를 그대로 그리는 폼(종류별 전용 화면 없음). 종류가 말하는 선택지는 디스크립터 데이터로 채운다. */
export function EdgeConfigForm({ kind, config, onChange, interactionKinds = [], strategies = [], errors, issues = NO_ISSUES, disabled }: EdgeConfigFormProps) {
  const schema = kind.config_schema as SchemaNode | undefined;
  const bridged = useMemo(() => {
    if (schema === undefined) return undefined;
    let out = buildUserSettingsUi(schema) as Obj;
    const allowed = kind.interaction?.["kinds"];
    if (Array.isArray(allowed) && hasPath(schema, "/kinds")) {
      const titles = new Map(interactionKinds.map((k) => [k.id, k]));
      out = put(out, "/kinds", {
        "ui:field": CHOICE_MULTI_FIELD,
        "ui:options": { choices: (allowed as string[]).map((id) => ({ value: id, label: titles.get(id)?.title ?? id, ...(titles.get(id)?.description ? { hint: titles.get(id)?.description } : {}) })), emptyNote: t.edge.kindsEmpty },
      });
    }
    if (kind.invocation != null && hasPath(schema, DEFAULT_TEAM_CONVENTIONS.edgeStrategy) && strategies.length > 0) {
      out = put(out, DEFAULT_TEAM_CONVENTIONS.edgeStrategy, { "ui:widget": CHOICE_SELECT_WIDGET, "ui:options": { choices: strategies.map((s) => ({ value: s.id, label: s.title })), emptyLabel: t.review.kindDefault } });
    }
    // 서버 `ui_schema`의 위젯 이름(예: 조건 목록)을 앱이 아는 필드로 잇는다. 모르는 이름이 구조화 필드에 있으면 JSON 폴백
    return bridgeWidgetUi(deepMerge(kind.ui_schema ?? {}, out), schema, CONFIG_WIDGETS, Object.keys(WIDGETS));
  }, [schema, kind, interactionKinds, strategies]);
  const ui = bridged?.uiSchema;
  const props = isObj(schema?.["properties"]) ? Object.keys(schema!["properties"] as Obj) : [];
  if (schema === undefined || props.length === 0) return <p className="app-muted">{t.edge.noSettings}</p>;
  return (
    <ConfigIssuesProvider issues={issues}>
      <SchemaForm
        schema={schema}
        {...(ui ? { uiSchema: ui } : {})}
        value={config}
        onChange={(next) => onChange(applyFormEdit(schema, config, next, { unsetOnDefault: true }))}
        customWidgets={WIDGETS}
        customFields={EDGE_FIELDS}
        rawJsonToggle={false}
        {...(errors ? { errors } : {})}
        {...(disabled === undefined ? {} : { disabled })}
        idPrefix="edge-config"
        advancedStorageKey="edge-config"
      />
    </ConfigIssuesProvider>
  );
}
