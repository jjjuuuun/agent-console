type Obj = Record<string, unknown>;

/** `ui:field`로 쓰는 원시 JSON 필드 이름. */
export const RAW_JSON_FIELD = "acRawJson";

function ref(s: Obj, root: Obj): Obj {
  const r = s.$ref;
  if (typeof r !== "string" || !r.startsWith("#/$defs/")) return s;
  const t = (root.$defs as Obj | undefined)?.[r.slice("#/$defs/".length)];
  return typeof t === "object" && t !== null ? { ...(t as Obj), ...Object.fromEntries(Object.entries(s).filter(([k]) => k !== "$ref")) } : s;
}

function includesType(t: unknown, name: string): boolean {
  return t === name || (Array.isArray(t) && t.includes(name));
}

/** 값의 모양을 스키마가 정하지 않는 위치인가(자유 객체 `additionalProperties: true`, 스키마 없는 값 `{}`/`true`). */
function isFreeForm(s: Obj | boolean): boolean {
  if (s === true) return true;
  if (typeof s !== "object") return false;
  const meaningful = Object.keys(s).filter((k) => !["title", "description", "default", "examples", "$comment", "x-ui"].includes(k));
  if (meaningful.length === 0) return true;
  return includesType(s.type, "object") && s.properties === undefined && s.additionalProperties === true && !s.oneOf && !s.anyOf && !s.allOf && s.patternProperties === undefined;
}

function walk(raw: unknown, root: Obj, depth: number, top: boolean): Obj {
  if (raw === true) return top ? {} : { "ui:field": RAW_JSON_FIELD };
  if (typeof raw !== "object" || raw === null || depth > 10) return {};
  const s = ref(raw as Obj, root);
  if (!top && isFreeForm(s)) return { "ui:field": RAW_JSON_FIELD };
  const out: Obj = {};
  if (typeof s.properties === "object" && s.properties !== null) {
    for (const [k, v] of Object.entries(s.properties as Obj)) {
      const child = walk(v, root, depth + 1, false);
      if (Object.keys(child).length > 0) out[k] = child;
    }
  }
  if (includesType(s.type, "array") && s.items !== undefined && !Array.isArray(s.items)) {
    const child = walk(s.items, root, depth + 1, false);
    if (Object.keys(child).length > 0) out.items = child;
  }
  return out;
}

/**
 * 스키마가 값의 모양을 정하지 않는 위치(자유 객체, 스키마 없는 값)에 `ui:field: acRawJson`을 단 uiSchema.
 * 폼 엔진이 그런 값을 못 그리므로 해당 값 전체를 원시 JSON 편집기로 그린다. 최상위는 제외.
 */
export function rawJsonUiSchema(schema: Obj): Obj {
  return walk(schema, schema, 0, true);
}

export function mergeUi(a: Obj | undefined, b: Obj | undefined): Obj | undefined {
  if (!a) return b;
  if (!b) return a;
  const out: Obj = { ...a };
  for (const [k, v] of Object.entries(b)) {
    const av = out[k];
    out[k] =
      typeof v === "object" && v !== null && !Array.isArray(v) && typeof av === "object" && av !== null && !Array.isArray(av)
        ? mergeUi(av as Obj, v as Obj)
        : v;
  }
  return out;
}
