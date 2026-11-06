/**
 * 스키마의 `x-ui.widget`을 폼 엔진의 `ui:field` 힌트로 옮긴다. 스키마를 훑어 레지스트리에 있는 위젯 이름이 붙은 필드만 지정하고,
 * 레지스트리에 없는 이름은 건드리지 않아(= 스키마 타입 기본 위젯) 새 위젯 이름이 서버에 생겨도 화면이 깨지지 않는다. 입력은 바꾸지 않는다.
 */
import { resolveRef, unwrapNullable, type SchemaNode } from "../../../lib/schemaTools";

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);

/** `x-ui.widget` 이름. 없으면 undefined. */
export function widgetNameOf(node: unknown): string | undefined {
  if (!isObj(node)) return undefined;
  const xui = node["x-ui"];
  const name = isObj(xui) ? xui["widget"] : undefined;
  return typeof name === "string" ? name : undefined;
}

/** `schema`(루트, `$defs` 포함) 전체에서 `known`에 든 위젯을 `ui:field`로 지정한 uiSchema. `$rootSchema`를 옵션에 실어 위젯이 `$defs`를 읽게 한다. */
export function widgetUiSchema(schema: SchemaNode, known: ReadonlySet<string>): Record<string, unknown> {
  const walk = (node: unknown, trail: readonly string[]): Obj | undefined => {
    if (!isObj(node)) return undefined;
    const name = widgetNameOf(resolveRef(node, schema));
    if (name !== undefined && known.has(name)) return { "ui:field": name, "ui:options": { $rootSchema: schema } };
    const ref = typeof node["$ref"] === "string" ? node["$ref"] : undefined;
    if (ref !== undefined && trail.includes(ref)) return undefined;
    const inner = unwrapNullable(resolveRef(node, schema), schema).schema;
    const next = ref === undefined ? trail : [...trail, ref];
    const out: Obj = {};
    const props = inner["properties"];
    if (isObj(props)) {
      for (const [key, child] of Object.entries(props)) {
        const ui = walk(child, next);
        if (ui !== undefined) out[key] = ui;
      }
    }
    const items = inner["items"];
    if (isObj(items)) {
      const ui = walk(items, next);
      if (ui !== undefined) out["items"] = ui;
    }
    return Object.keys(out).length === 0 ? undefined : out;
  };
  return walk(schema, []) ?? {};
}
