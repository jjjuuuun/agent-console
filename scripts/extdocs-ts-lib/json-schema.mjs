// 작은 JSON Schema 검사기: declaration.schema.json이 쓰는 낱말만 지원한다(새 의존성을 피하려고).
// 지원: $ref(#/$defs/…)·type·enum·anyOf·properties·required·additionalProperties(false|스키마)·items·
// minItems·minLength·pattern·propertyNames. 그 밖의 낱말(title·description·default 등)은 무시한다.

const typeOk = (type, v) => {
  switch (type) {
    case "string": return typeof v === "string";
    case "boolean": return typeof v === "boolean";
    case "number": return typeof v === "number";
    case "integer": return Number.isInteger(v);
    case "null": return v === null;
    case "array": return Array.isArray(v);
    case "object": return v !== null && typeof v === "object" && !Array.isArray(v);
    default: return true;
  }
};

const resolveRef = (root, ref) => {
  if (!ref.startsWith("#/")) throw new Error(`지원하지 않는 $ref: ${ref}`);
  let node = root;
  for (const part of ref.slice(2).split("/")) node = node?.[part];
  if (node === undefined) throw new Error(`$ref를 찾지 못함: ${ref}`);
  return node;
};

/** 값이 스키마에 맞는지 본다. 반환: `{ path, message }[]` (비면 통과). path는 `a.b[0]` 꼴. */
export function validate(schema, value, root = schema, path = "") {
  if (schema.$ref) return validate(resolveRef(root, schema.$ref), value, root, path);
  const here = path === "" ? "(최상위)" : path;
  if (schema.anyOf) {
    const tries = schema.anyOf.map((s) => validate(s, value, root, path));
    if (tries.some((t) => t.length === 0)) return [];
    // 가장 덜 어긋난 갈래의 오류를 보인다(타입이 맞는 갈래 우선).
    const typed = tries.filter((_, i) => schema.anyOf[i].type === undefined || typeOk(schema.anyOf[i].type, value));
    const best = (typed.length > 0 ? typed : tries).reduce((a, b) => (b.length < a.length ? b : a));
    return best;
  }
  const errs = [];
  if (schema.type !== undefined && !typeOk(schema.type, value)) {
    return [{ path: here, message: `${schema.type} 이어야 합니다` }];
  }
  if (schema.enum && !schema.enum.includes(value)) {
    errs.push({ path: here, message: `${schema.enum.map((e) => JSON.stringify(e)).join(" · ")} 중 하나여야 합니다` });
  }
  if (typeof value === "string") {
    if (schema.minLength !== undefined && value.length < schema.minLength) errs.push({ path: here, message: "비어 있으면 안 됩니다" });
    if (schema.pattern && !new RegExp(schema.pattern).test(value)) errs.push({ path: here, message: `형식(${schema.pattern})에 맞지 않습니다` });
  }
  if (Array.isArray(value)) {
    if (schema.minItems !== undefined && value.length < schema.minItems) errs.push({ path: here, message: `항목이 ${schema.minItems}개 이상이어야 합니다` });
    if (schema.items) value.forEach((v, i) => errs.push(...validate(schema.items, v, root, `${path}[${i}]`)));
  }
  if (typeOk("object", value)) {
    const props = schema.properties ?? {};
    for (const key of schema.required ?? []) {
      if (!(key in value)) errs.push({ path: path === "" ? key : `${path}.${key}`, message: "필수 항목입니다" });
    }
    for (const [key, v] of Object.entries(value)) {
      const sub = path === "" ? key : `${path}.${key}`;
      if (schema.propertyNames) {
        for (const e of validate(schema.propertyNames, key, root, sub)) errs.push({ path: sub, message: `이름: ${e.message}` });
      }
      if (key in props) errs.push(...validate(props[key], v, root, sub));
      else if (schema.additionalProperties === false) errs.push({ path: sub, message: "모르는 키입니다" });
      else if (schema.additionalProperties && typeof schema.additionalProperties === "object") {
        errs.push(...validate(schema.additionalProperties, v, root, sub));
      }
    }
  }
  return errs;
}
