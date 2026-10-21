import type { ComponentType } from "react";
import type { ChipView } from "@agent-console/graph-editor";
import type { SchemaFormFieldProps, UiSchema } from "@agent-console/schema-form";
import { getAt } from "../../lib/jsonPointer";
import { resolveRef, unwrapNullable, type SchemaNode } from "../../lib/schemaTools";

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);

/** 칩 요약을 만들 때 위젯에 건네는 문맥. 위젯이 필요로 하는 것은 서버 데이터(연산자 목록)와 필드의 `ui:options`다. */
export interface WidgetSummaryContext {
  /** 서버 연산자 목록. 없으면(연동 꺼짐·로딩·오류) null */
  operators: readonly { id: string; title: string }[] | null;
  /** 필드의 `ui:options`(예: 경로 → 제목 표) */
  options: Readonly<Record<string, unknown>>;
}

/** 위젯 한 줄: 필드를 그리는 컴포넌트와, 연결 칩을 만드는 선택 `summary`(없으면 칩 없음). */
export interface ConfigWidget {
  Component: ComponentType<SchemaFormFieldProps>;
  /** 필드 값 → 칩. 칩이 필요 없으면 null. `key`는 호출 쪽이 붙인다 */
  summary?(value: unknown, ctx: WidgetSummaryContext): Omit<ChipView, "key"> | null;
}

/** `ui:widget` 이름 → 위젯. 이름은 서버 `ui_schema`(데이터)에서 오고, 앱이 아는 위젯만 한 줄씩 등록한다. */
export type WidgetRegistry = Readonly<Record<string, ConfigWidget>>;

/** `ui_schema`가 레지스트리 위젯을 지정한 필드(JSON Pointer = 설정 값 안의 위치). */
export interface WidgetField {
  pointer: string;
  name: string;
  options: Readonly<Record<string, unknown>>;
}

/** `ui_schema` 노드의 자식 키(`ui:` 접두가 아닌 것 = 속성 이름). */
const childKeys = (node: Obj): string[] => Object.keys(node).filter((k) => !k.startsWith("ui:"));

/** 속성 이름을 JSON Pointer 조각으로. */
const seg = (key: string) => "/" + key.replace(/~/g, "~0").replace(/\//g, "~1");

/**
 * `ui_schema`를 훑어 레지스트리 위젯이 지정된 필드를 모두 찾는다. 위젯 이름만 보고 속성 이름은 보지 않는다.
 * `summary`를 가진 위젯만 고르려면 `withSummary`를 켠다(연결 칩 계산용).
 */
export function widgetFieldsOf(uiSchema: unknown, registry: WidgetRegistry, withSummary = false): WidgetField[] {
  const out: WidgetField[] = [];
  const walk = (node: unknown, pointer: string) => {
    if (!isObj(node)) return;
    const name = node["ui:widget"];
    if (typeof name === "string" && registry[name] !== undefined && (!withSummary || registry[name]!.summary !== undefined)) {
      const options = isObj(node["ui:options"]) ? node["ui:options"] : {};
      out.push({ pointer, name, options });
    }
    for (const key of childKeys(node)) walk(node[key], pointer + seg(key));
  };
  walk(uiSchema, "");
  return out;
}

/** `kind.ui_schema`와 값에서 위젯 `summary` 칩을 모은다. 값이 없는 필드는 `summary(undefined)`로 부른다(빈 조건 경고 칩 등). */
export function chipsFromWidgets(
  uiSchema: unknown,
  value: unknown,
  registry: WidgetRegistry,
  ctxFor: (field: WidgetField) => WidgetSummaryContext,
): ChipView[] {
  const chips: ChipView[] = [];
  for (const field of widgetFieldsOf(uiSchema, registry, true)) {
    const widget = registry[field.name]!;
    const chip = widget.summary?.(getAt(value, field.pointer), ctxFor(field));
    if (chip !== null && chip !== undefined) chips.push({ key: `w:${field.pointer}`, ...chip });
  }
  return chips;
}

/** 이름을 모르는 위젯을 그릴 때 쓰는 `ui:field` 이름. 컴포넌트는 앱이 따로 등록한다. */
export const UNKNOWN_WIDGET_FIELD = "unknown-widget";

/** 스키마 노드가 객체·배열처럼 폼 엔진의 단일 위젯으로 그릴 수 없는 값인가(널 허용 포함). */
function isStructured(node: SchemaNode, root: SchemaNode): boolean {
  const { schema } = unwrapNullable(node, root);
  const type = Array.isArray(schema["type"]) ? schema["type"].find((t) => t !== "null") : schema["type"];
  return type === "object" || type === "array" || isObj(schema["properties"]) || Array.isArray(schema["anyOf"]) || Array.isArray(schema["oneOf"]);
}

export interface BridgedUi {
  uiSchema: UiSchema;
  /** 이름을 몰라 JSON 폴백으로 바꾼 필드(안내 표시용) */
  unknown: { pointer: string; name: string }[];
}

/**
 * 서버 `ui_schema`의 `ui:widget` 이름을 폼 엔진이 쓸 수 있게 바꾼다.
 *  - 레지스트리에 있는 이름: 객체·배열 값을 통째로 그리는 `ui:field`로 옮기고 `ui:options.$rootSchema`(위젯이 `$defs`를 읽도록)와 `$pointer`(설정 값 안의 위치, 서버 이슈 매핑용)를 더한다.
 *  - 값이 구조화(객체·배열)인데 이름을 모르는 위젯(`extraKnown`에도 없음): `UNKNOWN_WIDGET_FIELD`로 바꿔 JSON으로 보이고 안내한다.
 *  - 그 밖(단순 값의 위젯 이름)은 손대지 않는다.
 * 입력은 바꾸지 않는다.
 */
export function bridgeWidgetUi(uiSchema: unknown, schema: SchemaNode | undefined, registry: WidgetRegistry, extraKnown: readonly string[] = []): BridgedUi {
  const unknown: { pointer: string; name: string }[] = [];
  const root = schema ?? {};
  const walk = (node: unknown, pointer: string, fieldSchema: SchemaNode | undefined): unknown => {
    if (!isObj(node)) return node;
    const next: Obj = {};
    for (const [key, value] of Object.entries(node)) {
      if (key.startsWith("ui:")) next[key] = value;
      else {
        const parent = fieldSchema === undefined ? undefined : unwrapNullable(fieldSchema, root).schema;
        const props = parent?.["properties"];
        const child = isObj(props) && isObj(props[key]) ? (props[key] as SchemaNode) : undefined;
        next[key] = walk(value, pointer + seg(key), child);
      }
    }
    const name = node["ui:widget"];
    if (typeof name === "string") {
      if (registry[name] !== undefined) {
        const { ["ui:widget"]: _w, ...rest } = next;
        void _w;
        const options = isObj(next["ui:options"]) ? next["ui:options"] : {};
        return { ...rest, "ui:field": name, "ui:options": { ...options, $rootSchema: root, $pointer: pointer } };
      }
      if (!extraKnown.includes(name) && fieldSchema !== undefined && isStructured(fieldSchema, root)) {
        unknown.push({ pointer, name });
        const { ["ui:widget"]: _w, ...rest } = next;
        void _w;
        const options = isObj(next["ui:options"]) ? next["ui:options"] : {};
        return { ...rest, "ui:field": UNKNOWN_WIDGET_FIELD, "ui:options": { ...options, widgetName: name } };
      }
    }
    return next;
  };
  return { uiSchema: walk(uiSchema, "", root) as UiSchema, unknown };
}

/** 위젯이 읽는 필드 스키마 풀이: `$ref`를 풀고 널 허용 분기를 벗긴다. */
export function resolveFieldSchema(schema: SchemaNode, root: SchemaNode): SchemaNode {
  return unwrapNullable(resolveRef(schema, root), root).schema;
}
