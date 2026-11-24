import type { JsonSchema, SchemaFormMessages } from "./types";

type Obj = Record<string, unknown>;

/** 선택지 가지 하나가 값 종류로 이름을 붙일 수 있는 단순 스키마인가(`$ref`·중첩 선택지는 제외) */
function kindOf(branch: unknown): "kindString" | "kindNumber" | "kindBoolean" | "kindArray" | "kindObject" | undefined {
  if (typeof branch !== "object" || branch === null) return undefined;
  const b = branch as Obj;
  if (typeof b.title === "string" && b.title !== "") return undefined;
  switch (b.type) {
    case "string":
      return "kindString";
    case "number":
    case "integer":
      return "kindNumber";
    case "boolean":
      return "kindBoolean";
    case "array":
      return "kindArray";
    case "object":
      return "kindObject";
    default:
      return undefined;
  }
}

function walk(node: unknown, m: SchemaFormMessages): unknown {
  if (Array.isArray(node)) return node.map((n) => walk(n, m));
  if (typeof node !== "object" || node === null) return node;
  const out: Obj = {};
  for (const [k, v] of Object.entries(node as Obj)) {
    if ((k === "anyOf" || k === "oneOf") && Array.isArray(v)) {
      const kinds = v.map(kindOf);
      const seen = new Map<string, number>();
      out[k] = v.map((branch, i) => {
        const kind = kinds[i];
        const walked = walk(branch, m);
        if (kind === undefined) return walked;
        const name = m[kind];
        const n = (seen.get(name) ?? 0) + 1;
        seen.set(name, n);
        const same = kinds.filter((x) => x !== undefined && m[x] === name).length;
        return { ...(walked as Obj), title: same > 1 ? `${name} ${n}` : name };
      });
    } else out[k] = walk(v, m);
  }
  return out;
}

/**
 * 제목 없는 `anyOf`/`oneOf` 가지에 값 종류 이름(`글자`·`목록`…)을 단다. 폼 엔진의 기본 이름 `option N` 대신 쓰려는 것이다.
 * 스키마가 `title`을 준 가지·`$ref` 가지는 건드리지 않는다. 필드 이름을 보지 않는 일반 규칙이다.
 */
export function titleUntitledBranches<T extends JsonSchema>(schema: T, messages: SchemaFormMessages): T {
  return walk(schema, messages) as T;
}
