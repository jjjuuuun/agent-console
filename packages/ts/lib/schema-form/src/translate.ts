import type { JsonSchema, UiSchema } from "./types";

/** 서버·앱이 준 문구를 현재 언어로 바꾸는 함수. 모르는 문구는 그대로 돌려준다. */
export type TranslateText = (text: string) => string;

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);

/** 값이 데이터라서 안으로 들어가지 않는 스키마 키(기본값·허용 값·예시). */
const DATA_KEYS = new Set(["default", "const", "enum", "examples"]);
/** 값이 `이름 → 스키마` 표라서 키 이름은 건드리지 않고 값만 스키마로 보는 키. */
const SCHEMA_MAPS = new Set(["properties", "patternProperties", "$defs", "definitions", "dependentSchemas", "dependencies"]);

function translateXUi(raw: unknown, t: TranslateText): unknown {
  if (!isObj(raw)) return raw;
  const out: Obj = { ...raw };
  for (const key of ["when", "group_title", "unit"]) if (typeof out[key] === "string") out[key] = t(out[key] as string);
  if (isObj(out["enum_labels"])) {
    out["enum_labels"] = Object.fromEntries(Object.entries(out["enum_labels"]).map(([k, v]) => [k, typeof v === "string" ? t(v) : v]));
  }
  return out;
}

function translateNode(node: unknown, t: TranslateText): unknown {
  if (Array.isArray(node)) return node.map((n) => translateNode(n, t));
  if (!isObj(node)) return node;
  const out: Obj = {};
  for (const [key, value] of Object.entries(node)) {
    if ((key === "title" || key === "description") && typeof value === "string") out[key] = t(value);
    else if (key === "x-ui") out[key] = translateXUi(value, t);
    else if (DATA_KEYS.has(key)) out[key] = value;
    else if (SCHEMA_MAPS.has(key) && isObj(value)) out[key] = Object.fromEntries(Object.entries(value).map(([k, v]) => [k, translateNode(v, t)]));
    else out[key] = translateNode(value, t);
  }
  return out;
}

/**
 * 스키마의 보이는 문구(`title`·`description`·`x-ui`의 `when`·`group_title`·`unit`·`enum_labels` 값, `oneOf` 가지 이름)를 `t`로 바꾼 복사본을 돌려준다.
 * 기본값·`enum`·`const`·`examples`와 속성 이름은 데이터라서 그대로 둔다. 원본은 바꾸지 않는다.
 */
export function translateSchema<T extends JsonSchema>(schema: T, t: TranslateText): T {
  return translateNode(schema, t) as T;
}

const UI_TEXT_KEYS = new Set(["ui:title", "ui:description", "ui:placeholder", "ui:help"]);

function translateUiNode(node: unknown, t: TranslateText): unknown {
  if (!isObj(node)) return node;
  return Object.fromEntries(Object.entries(node).map(([k, v]) => [k, UI_TEXT_KEYS.has(k) && typeof v === "string" ? t(v) : translateUiNode(v, t)]));
}

/** `uiSchema`의 `ui:title`·`ui:description`·`ui:placeholder`·`ui:help` 문자열을 `t`로 바꾼 복사본. */
export function translateUiSchema<T extends UiSchema | undefined>(ui: T, t: TranslateText): T {
  return translateUiNode(ui, t) as T;
}
