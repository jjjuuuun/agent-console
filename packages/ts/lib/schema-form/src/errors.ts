import type { RJSFValidationError } from "@rjsf/utils";
import { DEFAULT_MESSAGES } from "./messages";
import type { FormError, SchemaFormMessages } from "./types";

type ErrorNode = { __errors?: string[] } & { [key: string]: ErrorNode | string[] | undefined };

/** JSON Pointer("/a/0/b")를 키 배열로. 루트("")는 빈 배열. */
export function parsePointer(pointer: string): string[] {
  if (pointer === "" || pointer === "/") return [];
  return pointer
    .replace(/^\//, "")
    .split("/")
    .map((s) => s.replace(/~1/g, "/").replace(/~0/g, "~"));
}

/** FormError[]를 폼 엔진의 에러 스키마({a:{b:{__errors:[..]}}})로 변환. 경고는 "▲ ", 오류는 "⚠ " 접두(색 외 단서). */
export function toErrorSchema(errors: FormError[]): ErrorNode {
  const root: ErrorNode = {};
  for (const err of errors) {
    let node = root;
    for (const key of parsePointer(err.path)) {
      const next = (node[key] as ErrorNode | undefined) ?? {};
      node[key] = next;
      node = next;
    }
    const mark = err.severity === "warning" ? "▲ " : "⚠ ";
    node.__errors = [...(node.__errors ?? []), mark + err.message];
  }
  return root;
}

const MESSAGE_KEY: Record<string, keyof SchemaFormMessages> = {
  required: "required",
  minimum: "minimum",
  maximum: "maximum",
  exclusiveMinimum: "exclusiveMinimum",
  exclusiveMaximum: "exclusiveMaximum",
  minLength: "minLength",
  maxLength: "maxLength",
  minItems: "minItems",
  maxItems: "maxItems",
  multipleOf: "multipleOf",
  pattern: "pattern",
  format: "format",
  enum: "enumValue",
  const: "enumValue",
  type: "type",
  uniqueItems: "uniqueItems",
};

/**
 * ajv 검증 오류 메시지를 `messages`의 문구(기본 한국어)로 바꾼다. 템플릿의 `{limit}` 등은 ajv params로 채운다.
 * @param messages 문구(기본 `DEFAULT_MESSAGES`); 호출 측이 `resolveMessages`로 합쳐 넘긴다.
 */
export function translateErrors(
  errors: RJSFValidationError[],
  messages: SchemaFormMessages = DEFAULT_MESSAGES,
): RJSFValidationError[] {
  return errors.map((e) => {
    const key = e.name ? MESSAGE_KEY[e.name] : undefined;
    if (!key) return e;
    const p = (e.params ?? {}) as Record<string, unknown>;
    const message = messages[key].replace(/\{(\w+)\}/g, (_m, name: string) => String(p[name] ?? ""));
    return { ...e, message };
  });
}

/** 오류 스키마(트리)를 경로 키로 병합해 새 트리를 만든다. */
export function mergeErrorSchemas(a: ErrorNode, b: ErrorNode): ErrorNode {
  const out: ErrorNode = { ...a };
  for (const [key, val] of Object.entries(b)) {
    if (key === "__errors") {
      out.__errors = [...(a.__errors ?? []), ...((val as string[] | undefined) ?? [])];
    } else if (val && !Array.isArray(val)) {
      const existing = a[key];
      out[key] = mergeErrorSchemas(existing && !Array.isArray(existing) ? existing : {}, val);
    }
  }
  return out;
}

export type { ErrorNode };
