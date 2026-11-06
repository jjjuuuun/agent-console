import type { PortDef } from "@agent-console/contracts";

/** 포트 이름 → 입력 칸의 현재 값. 칸 종류에 따라 값의 모양이 다르다(아래 `portKind`). */
export type InputValues = Readonly<Record<string, unknown>>;

/** 입력 칸 종류: 스키마 없음 = 멀티라인 텍스트, 스키마 있음 = 스키마 폼, 그릴 수 없는 스키마 = JSON 직접 입력. */
export type PortKind = "text" | "schema" | "json";

type Schema = Record<string, unknown>;

const SHAPE_KEYS = ["type", "enum", "const", "properties", "items", "oneOf", "anyOf", "allOf"] as const;

const schemaOf = (port: PortDef): Schema | null => (port.schema != null && typeof port.schema === "object" ? (port.schema as Schema) : null);

/** 폼이 그릴 수 있는 스키마인가: 값의 모양을 알려 주는 키가 하나라도 있는 객체. */
export function isDrawableSchema(schema: Schema | null): schema is Schema {
  return schema !== null && SHAPE_KEYS.some((k) => k in schema);
}

export function portKind(port: PortDef): PortKind {
  const s = schemaOf(port);
  if (s === null) return "text";
  return isDrawableSchema(s) ? "schema" : "json";
}

/** 스키마에 `default`가 있으면 선택 입력, 없으면 필수(포트 하나의 규칙은 여기 한 곳). */
export function portRequired(port: PortDef): boolean {
  const s = schemaOf(port);
  return s === null || !("default" in s);
}

export const portLabel = (port: PortDef): string => (port.label != null && port.label !== "" ? port.label : port.name);

const isEmpty = (v: unknown): boolean => v === undefined || v === null || (typeof v === "string" && v.trim() === "");

/**
 * 구성이 바뀔 때 입력 칸의 시작 값. 같은 이름의 이전 값은 옮기고, 스키마 `default`는 비어 있는 칸에 채운다.
 * @param ports `Graph.inputs`
 * @param prev 이전 구성의 값(같은 이름만 옮긴다)
 */
export function initialInputValues(ports: readonly PortDef[], prev: InputValues = {}): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const port of ports) {
    if (port.name in prev && !isEmpty(prev[port.name])) {
      out[port.name] = prev[port.name];
      continue;
    }
    const s = schemaOf(port);
    if (s !== null && "default" in s) out[port.name] = portKind(port) === "json" ? JSON.stringify(s["default"], null, 2) : s["default"];
  }
  return out;
}

export interface InputIssue {
  kind: "required" | "json";
}

/** 칸마다 문제(필수 누락·JSON 오류). 문제 없는 포트는 키가 없다. */
export function inputIssues(ports: readonly PortDef[], values: InputValues): Record<string, InputIssue> {
  const out: Record<string, InputIssue> = {};
  for (const port of ports) {
    const v = values[port.name];
    const kind = portKind(port);
    if (kind === "json") {
      if (isEmpty(v)) {
        if (portRequired(port)) out[port.name] = { kind: "required" };
      } else {
        try {
          JSON.parse(String(v));
        } catch {
          out[port.name] = { kind: "json" };
        }
      }
    } else if (portRequired(port) && isEmpty(v)) {
      out[port.name] = { kind: "required" };
    }
  }
  return out;
}

/**
 * `CreateRunRequest.input`을 만든다: 포트 이름이 키다. 포트가 없으면 `{}`(입력 키를 지어내지 않는다).
 * 값이 빈 선택 입력은 보내지 않는다.
 */
export function buildRunInput(ports: readonly PortDef[], values: InputValues): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const port of ports) {
    const v = values[port.name];
    if (isEmpty(v)) continue;
    out[port.name] = portKind(port) === "json" ? (JSON.parse(String(v)) as unknown) : v;
  }
  return out;
}

/** 서버 422 입력 오류(`details`)에서 포트 이름별 메시지를 뽑는다. 알아볼 수 있는 항목만(없으면 빈 객체). */
export function serverInputErrors(details: Record<string, unknown>, ports: readonly PortDef[]): Record<string, string> {
  const names = new Set(ports.map((p) => p.name));
  const out: Record<string, string> = {};
  const list = [details["issues"], details["errors"]].find(Array.isArray) as unknown[] | undefined;
  for (const item of list ?? []) {
    if (item === null || typeof item !== "object") continue;
    const rec = item as Record<string, unknown> & { message?: unknown };
    const raw = [rec["port"], rec["name"], rec["field"], rec["path"], rec["pointer"]].find((x) => typeof x === "string") as string | undefined;
    const message = typeof rec.message === "string" ? rec.message : undefined;
    if (raw === undefined || message === undefined) continue;
    const name = raw.replace(/^\/?(input[/.])?/, "").split(/[/.]/)[0] ?? "";
    if (names.has(name)) out[name] = message;
  }
  return out;
}
