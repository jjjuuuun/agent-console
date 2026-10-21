import type { SchemaFormMessages } from "./types";

type Obj = Record<string, unknown>;

const MAX_DEPTH = 12;

function isObj(v: unknown): v is Obj {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/** `#/$defs/<이름>`(또는 `#/definitions/<이름>`) 참조를 풀어 형제 키를 덮어 얹는다. 못 풀면 그대로. */
function resolve(s: Obj, root: Obj): Obj {
  const r = s["$ref"];
  if (typeof r !== "string") return s;
  const m = /^#\/(\$defs|definitions)\/(.+)$/.exec(r);
  const target = m ? (root[m[1]!] as Obj | undefined)?.[m[2]!] : undefined;
  if (!isObj(target)) return s;
  const siblings = { ...s };
  delete siblings["$ref"];
  return { ...target, ...siblings };
}

interface Walked {
  schema: Obj;
  ui: Obj;
  /** 깊은 곳에서 바뀐 것이 있는가 */
  changed: boolean;
  /** 숨김·표시 상태를 나타내는 키 조각(스키마·값이 바뀌지 않았는지 비교용) */
  marks: string[];
}

function walk(raw: Obj, value: unknown, root: Obj, messages: Pick<SchemaFormMessages, "deprecatedChip" | "deprecatedNote">, path: string, depth: number): Walked {
  const s = resolve(raw, root);
  const props = s["properties"];
  if (!isObj(props) || depth > MAX_DEPTH) return { schema: raw, ui: {}, changed: false, marks: [] };
  const values = isObj(value) ? value : {};
  const nextProps: Obj = {};
  const ui: Obj = {};
  const marks: string[] = [];
  const hidden = new Set<string>();
  let changed = false;
  for (const [name, rawChild] of Object.entries(props)) {
    if (!isObj(rawChild)) {
      nextProps[name] = rawChild;
      continue;
    }
    const child = resolve(rawChild, root);
    const childPath = `${path}/${name}`;
    const has = values[name] !== undefined && values[name] !== null;
    if (child["deprecated"] === true) {
      if (!has) {
        hidden.add(name);
        changed = true;
        marks.push(`${childPath}:hidden`);
        continue;
      }
      marks.push(`${childPath}:shown`);
      const title = typeof child["title"] === "string" ? child["title"] : name;
      const description = typeof child["description"] === "string" ? `${child["description"]} ` : "";
      ui[name] = { "ui:title": `${title} · ${messages.deprecatedChip}`, "ui:description": `${description}${messages.deprecatedNote}` };
    }
    // 객체 속성이면 안쪽의 폐기 예정 필드도 같은 규칙으로
    const inner = walk(rawChild, values[name], root, messages, childPath, depth + 1);
    marks.push(...inner.marks);
    if (inner.changed) {
      nextProps[name] = inner.schema;
      changed = true;
    } else {
      nextProps[name] = rawChild;
    }
    if (Object.keys(inner.ui).length > 0) ui[name] = { ...(isObj(ui[name]) ? (ui[name] as Obj) : {}), ...inner.ui };
  }
  if (!changed) return { schema: raw, ui, changed: false, marks };
  const out: Obj = { ...s, properties: Object.fromEntries(Object.entries(nextProps).filter(([k]) => !hidden.has(k))) };
  if (Array.isArray(s["required"])) out["required"] = (s["required"] as unknown[]).filter((r) => typeof r !== "string" || !hidden.has(r));
  return { schema: out, ui, changed: true, marks };
}

export interface DeprecatedApplied {
  /** 값이 없는 폐기 예정 필드를 뺀 스키마(바뀐 것이 없으면 입력 그대로) */
  schema: Obj;
  /** 값이 있는 폐기 예정 필드에 칩·안내를 다는 uiSchema 조각 */
  ui: Obj | undefined;
  /** 상태가 같으면 같은 문자열(스키마 identity를 안정시키는 데 쓴다) */
  key: string;
}

/**
 * JSON Schema의 `deprecated: true` 필드 일반 규칙(필드 이름을 모른다).
 * - 값이 없으면 폼에서 뺀다(스키마에서 제거, `required`에서도).
 * - 값이 있으면 그리되 라벨에 칩 문구, 설명에 안내 문구를 단다. 값은 그대로 편집·삭제할 수 있다.
 * `$defs` 참조는 풀어서 따라간다. 배열 안 항목은 보지 않는다.
 */
export function applyDeprecated(schema: Obj, value: unknown, messages: Pick<SchemaFormMessages, "deprecatedChip" | "deprecatedNote">): DeprecatedApplied {
  const walked = walk(schema, value, schema, messages, "", 0);
  return { schema: walked.schema, ui: Object.keys(walked.ui).length > 0 ? walked.ui : undefined, key: walked.marks.join("|") };
}
