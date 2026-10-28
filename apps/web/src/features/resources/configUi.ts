import type { UiSchema } from "@agent-console/schema-form";
import { STRING_TAGS_FIELD } from "../settings";
import { resolveRef, unwrapNullable } from "../../lib/schemaTools";
import { resourceMessages as t } from "./messages";

type Obj = Record<string, unknown>;

const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);

function typeIs(schema: Obj, name: string): boolean {
  return schema["type"] === name || (Array.isArray(schema["type"]) && schema["type"].includes(name));
}

function strings(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
}

/** 노드(또는 그 `$ref`·널 허용 풀이) 어디서든 `x-ui.widget` 이름을 찾는다. */
function widgetNameOf(node: Obj, root: Obj): string | undefined {
  const own = isObj(node["x-ui"]) ? node["x-ui"]["widget"] : undefined;
  if (typeof own === "string") return own;
  const inner = unwrapNullable(node, root).schema;
  const w = isObj(inner["x-ui"]) ? inner["x-ui"]["widget"] : undefined;
  return typeof w === "string" ? w : undefined;
}

/** 항목이 enum인 중복 없는 배열은 체크박스 묶음으로 그린다(폼 엔진 기본 위젯 이름). 5.7R.19부터 모든 리소스 종류에 적용되며, 라벨은 `x-ui.enum_labels`를 쓴다. */
const CHECKBOXES_WIDGET = "checkboxes";
function enumArrayWidget(resolved: Obj): string | undefined {
  return typeIs(resolved, "array") && isObj(resolved["items"]) && Array.isArray((resolved["items"] as Obj)["enum"]) && resolved["uniqueItems"] === true ? CHECKBOXES_WIDGET : undefined;
}

/**
 * 스키마 어디에 있든(중첩 객체·배열 항목 포함) `x-ui.widget` 이름이 `names`에 있는 필드를 `ui:widget`으로 잇는 uiSchema 조각을 만든다.
 * 속성 이름·종류 이름을 보지 않고 위젯 이름만 본다. 해당 필드가 없으면 undefined.
 */
export function namedWidgetUi(node: Obj, root: Obj, names: ReadonlySet<string>, depth = 0, implicit?: (resolved: Obj) => string | undefined): Obj | undefined {
  if (depth > 8) return undefined;
  const name = widgetNameOf(node, root);
  if (name !== undefined && names.has(name)) return { "ui:widget": name };
  const resolved = unwrapNullable(node, root).schema;
  const byShape = implicit?.(resolved);
  if (byShape !== undefined) return { "ui:widget": byShape };
  const out: Obj = {};
  if (isObj(resolved["properties"])) {
    for (const [key, raw] of Object.entries(resolved["properties"])) {
      const child = isObj(raw) ? namedWidgetUi(raw, root, names, depth + 1, implicit) : undefined;
      if (child !== undefined) out[key] = child;
    }
  }
  if (isObj(resolved["items"])) {
    const child = namedWidgetUi(resolved["items"], root, names, depth + 1, implicit);
    if (child !== undefined) out["items"] = child;
  }
  return Object.keys(out).length === 0 ? undefined : out;
}

/**
 * 종류 `config_schema` 모양만 보고 만드는 입력 보강(필드 이름·종류 이름을 모른다). 서버가 준 `ui_schema`가 먼저다.
 * - 문자열 배열 -> 태그 입력(제안 = 항목 스키마 `examples`, placeholder = 첫 예시).
 * - `examples`가 있는 문자열 -> 입력 위 제안 목록(브라우저 datalist, 목록에 없는 값도 입력 가능)과 한 줄 안내.
 */
export function buildConfigUi(schema: Obj | undefined, serverUi: Obj | undefined, widgetNames: ReadonlySet<string> = new Set()): UiSchema {
  const out: Obj = { ...(serverUi ?? {}) };
  const props = schema?.["properties"];
  if (!isObj(props)) return out as UiSchema;
  // 앱이 아는 이름의 위젯(`x-ui.widget`)을 중첩 위치까지 이어 준다. 서버 ui_schema가 먼저다.
  if (schema !== undefined) {
    for (const [key, raw] of Object.entries(props)) {
      if (!isObj(raw) || (isObj(out[key]) && Object.keys(out[key] as Obj).length > 0)) continue;
      const ui = namedWidgetUi(resolveRef(raw, schema), schema, widgetNames, 0, enumArrayWidget);
      if (ui !== undefined) out[key] = ui;
    }
  }
  for (const [key, raw] of Object.entries(props)) {
    if (!isObj(raw) || isObj(out[key]) && Object.keys(out[key] as Obj).length > 0) continue;
    if (typeIs(raw, "array") && isObj(raw["items"]) && typeIs(raw["items"], "string")) {
      const examples = strings((raw["items"] as Obj)["examples"]);
      out[key] = {
        "ui:field": STRING_TAGS_FIELD,
        "ui:options": {
          suggestions: examples,
          addLabel: examples[0] === undefined ? t.config.tagAdd : t.config.tagAddExample(examples[0]),
          addButtonLabel: t.config.tagAddButton,
          removeLabel: t.config.tagRemove,
        },
      };
    } else if (typeIs(raw, "string") && strings(raw["examples"]).length > 0 && raw["enum"] === undefined) {
      out[key] = { "ui:help": t.config.freeInputNote };
    }
  }
  return out as UiSchema;
}

/**
 * 항목이 enum인 배열은 중복 없는 다중 선택(체크박스)으로 그린다: 스키마 어디에 있든 `type: array` + `items.enum` 모양이면 `uniqueItems`를 켠 사본을 돌려준다.
 * 필드 이름·종류 이름을 보지 않는다. 입력은 바꾸지 않는다.
 */
export function withEnumArraysUnique<T>(node: T): T {
  if (Array.isArray(node)) return node.map(withEnumArraysUnique) as T;
  if (!isObj(node)) return node;
  const out: Obj = {};
  for (const [k, v] of Object.entries(node)) out[k] = withEnumArraysUnique(v);
  if (typeIs(out, "array") && isObj(out["items"]) && Array.isArray((out["items"] as Obj)["enum"]) && out["uniqueItems"] === undefined) out["uniqueItems"] = true;
  return out as T;
}
