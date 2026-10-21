import { parsePointer } from "./jsonPointer";

/** JSON Schema 조각(느슨한 형태). */
export type SchemaNode = Record<string, unknown>;

function isNode(v: unknown): v is SchemaNode {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/** `#/$defs/Name` 참조를 푼다(형제 키가 우선). 풀 수 없으면 그대로. */
export function resolveRef(node: SchemaNode, root: SchemaNode): SchemaNode {
  const ref = node["$ref"];
  if (typeof ref !== "string" || !ref.startsWith("#/$defs/")) return node;
  const defs = root["$defs"];
  const target = isNode(defs) ? defs[ref.slice("#/$defs/".length)] : undefined;
  if (!isNode(target)) return node;
  const { $ref: _ref, ...siblings } = node;
  void _ref;
  return { ...target, ...siblings };
}

/** `anyOf: [X, {type:"null"}]`에서 X(널 분기 제외)와 널 허용 여부. 해당 형태가 아니면 노드 그대로. */
export function unwrapNullable(node: SchemaNode, root: SchemaNode): { schema: SchemaNode; nullable: boolean } {
  const resolved = resolveRef(node, root);
  const any = resolved["anyOf"];
  if (Array.isArray(any)) {
    const branches = any.filter(isNode);
    const nonNull = branches.filter((b) => b["type"] !== "null");
    if (nonNull.length === 1 && nonNull.length < branches.length) {
      const { anyOf: _drop, ...rest } = resolved;
      void _drop;
      return { schema: resolveRef({ ...nonNull[0]!, ...rest }, root), nullable: true };
    }
  }
  const type = resolved["type"];
  return { schema: resolved, nullable: Array.isArray(type) && type.includes("null") };
}

/** 문자열 enum 값 목록(없으면 빈 배열). */
export function enumValues(node: SchemaNode, root: SchemaNode): string[] {
  const { schema } = unwrapNullable(node, root);
  const values = schema["enum"];
  return Array.isArray(values) ? values.filter((v): v is string => typeof v === "string") : [];
}

/** 숫자(정수 포함) 또는 널 허용 숫자인가. */
export function isNullableNumber(node: SchemaNode, root: SchemaNode): boolean {
  const { schema, nullable } = unwrapNullable(node, root);
  const type = schema["type"];
  const base = Array.isArray(type) ? type.find((t) => t !== "null") : type;
  return nullable && (base === "number" || base === "integer");
}

/**
 * 설명 문장에서 enum 값별 설명을 뽑는다. 서버 스키마가 `"queue: …, reject: …"` 형태로 쓴다.
 * 값 이름 + `": "`가 나오는 위치를 경계로 자르며, 못 찾은 값은 결과에서 빠진다.
 */
export function parseEnumDescriptions(description: string | undefined, values: readonly string[]): Record<string, string> {
  if (description === undefined || description === "") return {};
  const marks = values
    .map((v) => ({ v, at: description.indexOf(`${v}: `) }))
    .filter((m) => m.at >= 0)
    .sort((a, b) => a.at - b.at);
  const out: Record<string, string> = {};
  marks.forEach((m, i) => {
    const start = m.at + m.v.length + 2;
    const end = i + 1 < marks.length ? marks[i + 1]!.at : description.length;
    const text = description.slice(start, end).trim().replace(/[,，、]\s*$/, "").replace(/[.。]\s*$/, "");
    if (text !== "") out[m.v] = text;
  });
  return out;
}

/** 루트 스키마(`$defs` 포함)에서 최상위 속성 일부만 가진 object 스키마를 만든다. 없는 키는 건너뛴다. */
export function pickProperties(root: SchemaNode, keys: readonly string[]): SchemaNode {
  const props = isNode(root["properties"]) ? root["properties"] : {};
  const picked: SchemaNode = {};
  for (const key of keys) if (key in props) picked[key] = props[key];
  const out: SchemaNode = { type: "object", properties: picked };
  if (root["$defs"] !== undefined) out["$defs"] = root["$defs"];
  return out;
}

/** 스키마 속성 경로(JSON Pointer) 목록. `maxDepth`까지(자동완성용). */
export function schemaPointers(root: SchemaNode, maxDepth = 2): string[] {
  const out: string[] = [];
  const walk = (node: SchemaNode, prefix: string, depth: number) => {
    const { schema } = unwrapNullable(node, root);
    const props = schema["properties"];
    if (!isNode(props) || depth > maxDepth) return;
    for (const [key, child] of Object.entries(props)) {
      const pointer = `${prefix}/${key.replace(/~/g, "~0").replace(/\//g, "~1")}`;
      out.push(pointer);
      if (isNode(child)) walk(child, pointer, depth + 1);
    }
  };
  walk(root, "", 1);
  return out;
}

/** 포인터가 가리키는 속성 스키마. 못 찾으면 undefined. */
export function schemaAt(root: SchemaNode, pointer: string): SchemaNode | undefined {
  let cur: SchemaNode = root;
  for (const seg of parsePointer(pointer)) {
    const { schema } = unwrapNullable(cur, root);
    const props = schema["properties"];
    const next = isNode(props) ? props[seg] : undefined;
    if (!isNode(next)) return undefined;
    cur = next;
  }
  return cur;
}

/** 포인터가 가리키는 속성의 확장 키워드(예: `x-merge`). 없으면 undefined. */
export function keywordAt(root: SchemaNode, pointer: string, keyword: string): unknown {
  return schemaAt(root, pointer)?.[keyword];
}
