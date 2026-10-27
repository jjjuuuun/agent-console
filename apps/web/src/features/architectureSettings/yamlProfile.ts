/** 프로필 본문 <-> YAML 글. 프로필 필드를 모른다. */
import { parse, stringify, YAMLParseError } from "yaml";
import { getContractSchema } from "@agent-console/contracts";

export type ParsedProfile = { ok: true; value: Record<string, unknown> } | { ok: false; message: string; line: number | null };

/** 본문 객체를 YAML 글로. */
export function profileToYaml(body: unknown): string {
  return stringify(body ?? {}, { indent: 2, lineWidth: 0 });
}

/** YAML 글을 객체로. 최상위가 객체(맵)가 아니면 오류로 본다. 빈 글은 빈 객체다. */
export function parseProfileYaml(text: string): ParsedProfile {
  try {
    const v: unknown = parse(text);
    if (v === null || v === undefined) return { ok: true, value: {} };
    if (typeof v !== "object" || Array.isArray(v)) return { ok: false, message: "", line: null };
    return { ok: true, value: v as Record<string, unknown> };
  } catch (e) {
    if (e instanceof YAMLParseError) return { ok: false, message: e.message.split("\n")[0] ?? e.message, line: e.linePos?.[0].line ?? null };
    return { ok: false, message: e instanceof Error ? e.message : String(e), line: null };
  }
}

/** 문제 경로(`cells.foo`·`edges[3].when`)가 가리키는 YAML 줄(1부터). 못 찾으면 null. */
export function lineOfPath(text: string, path: string): number | null {
  const parts = path.split(/[.[\]]+/).filter((p) => p !== "");
  if (parts.length === 0) return null;
  const lines = text.split("\n");
  let from = 0;
  let found: number | null = null;
  for (const part of parts) {
    const isIndex = /^\d+$/.test(part);
    if (isIndex) continue; // 배열 순번은 줄로 옮기기 어려워 앞 키 위치를 쓴다
    const re = new RegExp(`^\\s*(?:-\\s+)?["']?${part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}["']?\\s*:`);
    let hit = -1;
    for (let i = from; i < lines.length; i++) if (re.test(lines[i] ?? "")) { hit = i; break; }
    if (hit < 0) break;
    found = hit + 1;
    from = hit + 1;
  }
  return found;
}

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => v !== null && typeof v === "object" && !Array.isArray(v);

function resolve(schema: Obj, root: Obj): Obj {
  const ref = schema["$ref"];
  if (typeof ref === "string") return resolve(isObj(root["$defs"]) && isObj((root["$defs"] as Obj)[ref.split("/").pop() ?? ""]) ? ((root["$defs"] as Obj)[ref.split("/").pop() ?? ""] as Obj) : {}, root);
  const any = schema["anyOf"];
  if (Array.isArray(any)) {
    const first = any.find((x) => isObj(x) && x["type"] !== "null");
    if (isObj(first)) return { ...schema, ...resolve(first, root) };
  }
  return schema;
}

function sample(schemaIn: Obj, root: Obj, depth: number): unknown {
  const schema = resolve(schemaIn, root);
  const ui = isObj(schema["x-ui"]) ? (schema["x-ui"] as Obj) : {};
  if (ui["example"] !== undefined) return ui["example"];
  const props = isObj(schema["properties"]) ? (schema["properties"] as Obj) : {};
  const required = Array.isArray(schema["required"]) ? (schema["required"] as string[]) : [];
  if (schema["type"] === "object" && Object.keys(props).length > 0) {
    const out: Obj = {};
    for (const [k, v] of Object.entries(props)) if (required.includes(k) && isObj(v)) out[k] = sample(v, root, depth + 1);
    return out;
  }
  return undefined;
}

/**
 * 새 프로필 골격. 어떤 필드를 넣을지는 계약 스키마의 `x-ui.tier: basic` 속성에서 얻는다(필드명을 코드에 두지 않는다).
 * 문자열 속성은 `title`로 채우고, 객체는 필수 속성을 예시값으로 채우며, 이름표가 붙는 맵은 항목 하나(`mapKey`)를 넣는다. 배열은 비워 둔다.
 */
export function newProfileSkeleton(title: string, mapKey: string, model = "ArchitectureProfile"): Record<string, unknown> {
  const root = getContractSchema(model) as unknown as Obj;
  const props = isObj(root["properties"]) ? (root["properties"] as Obj) : {};
  const out: Obj = {};
  let titled = false;
  for (const [k, raw] of Object.entries(props)) {
    if (!isObj(raw)) continue;
    const sch = resolve(raw, root);
    const ui = isObj(sch["x-ui"]) ? (sch["x-ui"] as Obj) : isObj(raw["x-ui"]) ? (raw["x-ui"] as Obj) : {};
    if (ui["tier"] !== "basic") continue;
    if (sch["type"] === "string" && !titled) {
      out[k] = title;
      titled = true;
    } else if (sch["type"] === "object" && isObj(sch["additionalProperties"])) {
      out[k] = { [mapKey]: sample(sch["additionalProperties"] as Obj, root, 1) ?? {} };
    } else if (sch["type"] === "object") {
      const v = sample(sch, root, 0);
      if (v !== undefined) out[k] = v;
    }
  }
  return out;
}
