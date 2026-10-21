import type { JsonSchema } from "./types";

const FOLDABLE_TYPES = new Set(["string", "number", "integer", "boolean", "object", "array"]);

type Obj = Record<string, unknown>;

function isNullBranch(b: unknown): boolean {
  return typeof b === "object" && b !== null && Object.keys(b).length === 1 && (b as { type?: unknown }).type === "null";
}

function walk(node: unknown, root: Obj, stack: readonly string[]): unknown {
  if (Array.isArray(node)) return node.map((n) => walk(n, root, stack));
  if (typeof node !== "object" || node === null) return node;
  const obj = node as Obj;
  const any = obj.anyOf;
  if (Array.isArray(any) && any.length === 2) {
    const nullIdx = any.findIndex(isNullBranch);
    let other = nullIdx === -1 ? undefined : (any[1 - nullIdx] as Obj | undefined);
    let nextStack = stack;
    if (other && typeof other.$ref === "string") {
      // $ref는 해석한 스키마로 인라인한다(순환 참조는 접지 않는다).
      const target = refTarget(other.$ref, root);
      if (!target || stack.includes(other.$ref)) other = undefined;
      else {
        nextStack = [...stack, other.$ref];
        const { $ref: _r, ...siblings } = other;
        void _r;
        other = { ...target, ...siblings };
      }
    }
    const otherType = other?.type;
    if (other && typeof otherType === "string" && FOLDABLE_TYPES.has(otherType)) {
      const { anyOf: _drop, ...rest } = obj;
      void _drop;
      const merged: Obj = { ...other, ...rest, type: [otherType, "null"] };
      // enum/const가 있으면 null도 허용 값에 넣어야 null이 검증을 통과한다.
      if (Array.isArray(merged.enum)) merged.enum = [...merged.enum, null];
      if ("const" in merged) {
        merged.enum = [merged.const, null];
        delete merged.const;
      }
      return walk(merged, root, nextStack);
    }
  }
  return Object.fromEntries(Object.entries(obj).map(([k, v]) => [k, walk(v, root, stack)]));
}

/**
 * `anyOf: [<X>, {type: "null"}]`(Pydantic의 `X | None`)를 `X` + `type: [<X의 type>, "null"]`로 접는다.
 * X는 스칼라·object·array이거나, 위 형태의 `$ref`(해석한 스키마로 인라인; 순환 참조는 제외).
 * 폼 엔진이 "option 1/2" 선택기 대신 일반 필드로 그리게 하기 위함이며, 값 `null`도 유효하다.
 * `oneOf`, 3분기 이상, null이 없는 anyOf는 그대로 둔다. `$defs` 안쪽까지 훑는다.
 */
export function normalizeNullable<T extends JsonSchema>(schema: T): T {
  if (typeof schema !== "object" || schema === null) return schema;
  return walk(schema, schema as Obj, []) as T;
}

function refTarget(ref: unknown, root: Record<string, unknown>): Record<string, unknown> | null {
  if (typeof ref !== "string" || !ref.startsWith("#/$defs/")) return null;
  const defs = root.$defs as Record<string, unknown> | undefined;
  const t = defs?.[ref.slice("#/$defs/".length)];
  return typeof t === "object" && t !== null ? (t as Record<string, unknown>) : null;
}

function isNullableType(t: unknown): boolean {
  return Array.isArray(t) && t.includes("null");
}

function build(schema: Record<string, unknown>, root: Record<string, unknown>, depth: number): Record<string, unknown> {
  const target = refTarget(schema.$ref, root) ?? schema;
  const out: Record<string, unknown> = {};
  const props = target.properties;
  if (depth < 8 && typeof props === "object" && props !== null) {
    for (const [k, v] of Object.entries(props)) {
      if (typeof v !== "object" || v === null) continue;
      const sub = v as Record<string, unknown>;
      const own = isNullableType(sub.type) ? { "ui:options": { emptyValue: null } } : {};
      const child = { ...build(sub, root, depth + 1), ...own };
      if (Object.keys(child).length > 0) out[k] = child;
    }
  }
  return out;
}

/**
 * nullable로 접힌 필드(`type: [x, "null"]`)는 입력을 비우면 `null`로 돌아오게 하는 uiSchema(`emptyValue: null`)를 만든다.
 * 호출 측 uiSchema가 있으면 그것이 우선한다(깊은 병합).
 */
export function nullableUiSchema(
  schema: Record<string, unknown>,
  userUi: Record<string, unknown> | undefined,
): Record<string, unknown> | undefined {
  const generated = build(schema, schema, 0);
  if (Object.keys(generated).length === 0) return userUi;
  return deepMerge(generated, userUi ?? {});
}

function deepMerge(a: Record<string, unknown>, b: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = { ...a };
  for (const [k, v] of Object.entries(b)) {
    const av = out[k];
    out[k] =
      typeof v === "object" && v !== null && !Array.isArray(v) && typeof av === "object" && av !== null && !Array.isArray(av)
        ? deepMerge(av as Record<string, unknown>, v as Record<string, unknown>)
        : v;
  }
  return out;
}

function resolveNode(s: unknown, root: Obj): Obj | null {
  if (typeof s !== "object" || s === null) return null;
  const o = s as Obj;
  return refTarget(o.$ref, root) ?? o;
}

function isEmptyDeep(v: unknown): boolean {
  if (v === undefined || v === null || v === "") return true;
  if (Array.isArray(v)) return v.length === 0;
  if (typeof v === "object") return Object.values(v as Obj).every(isEmptyDeep);
  return false;
}

function collapse(schema: unknown, data: unknown, root: Obj): unknown {
  const s = resolveNode(schema, root);
  if (!s) return data;
  let out = data;
  if (Array.isArray(data) && s.items) {
    out = data.map((d) => collapse(s.items, d, root));
  } else if (typeof data === "object" && data !== null && !Array.isArray(data) && typeof s.properties === "object" && s.properties !== null) {
    const props = s.properties as Obj;
    out = Object.fromEntries(Object.entries(data as Obj).map(([k, v]) => [k, k in props ? collapse(props[k], v, root) : v]));
  }
  const t = s.type;
  if (isNullableType(t) && ((t as unknown[]).includes("object") || (t as unknown[]).includes("array")) && isEmptyDeep(out)) return null;
  return out;
}

/**
 * nullable로 접힌 object/array 필드의 내용이 모두 비면 `null`로 되돌린다(최상위 값은 제외).
 * `normalizeNullable`을 거친 스키마와 함께 쓴다.
 */
export function collapseEmptyNullable(schema: JsonSchema, data: unknown): unknown {
  if (typeof schema !== "object" || schema === null) return data;
  const root = schema as Obj;
  const s = resolveNode(root, root);
  if (!s) return data;
  // 최상위는 null로 만들지 않고 자식만 처리한다.
  const nullableTop = s.type;
  const probe = isNullableType(nullableTop) ? { ...s, type: (nullableTop as unknown[]).filter((x) => x !== "null") } : s;
  return collapse(probe, data, root);
}
