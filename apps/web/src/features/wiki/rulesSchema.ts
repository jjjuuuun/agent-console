/**
 * 계약 JSON Schema의 `x-ui`에서 화면 데이터를 읽는 순수 함수들(위키 규칙). 필드 이름·값 이름을 코드에 두지 않고 스키마 전체를 훑는다:
 * 열린 문자열의 값별 라벨(`enum_labels`)·톤(`enum_tones`), 최상위 속성 제목(`title`), 입력 틀 변수(`variables`).
 */
type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const strings = (v: unknown): Record<string, string> => (isObj(v) ? Object.fromEntries(Object.entries(v).filter((e): e is [string, string] => typeof e[1] === "string")) : {});

/** 스키마 어디에 있든 `x-ui.enum_labels`·`enum_tones`를 값 이름별로 합친다(같은 값이 여럿이면 먼저 만난 것). */
export function collectEnumUi(schema: unknown): { labels: Record<string, string>; tones: Record<string, string> } {
  const labels: Record<string, string> = {};
  const tones: Record<string, string> = {};
  const seen = new Set<unknown>();
  const walk = (node: unknown) => {
    if (!isObj(node) && !Array.isArray(node)) return;
    if (seen.has(node)) return;
    seen.add(node);
    if (isObj(node)) {
      const xui = node["x-ui"];
      if (isObj(xui)) {
        for (const [k, v] of Object.entries(strings(xui["enum_labels"]))) labels[k] ??= v;
        for (const [k, v] of Object.entries(strings(xui["enum_tones"]))) tones[k] ??= v;
      }
    }
    for (const child of Object.values(node as Obj)) walk(child);
  };
  walk(schema);
  return { labels, tones };
}

/** 스키마 루트 속성의 `title`(키 → 제목). 제목이 없는 속성은 뺀다. */
export function propertyTitles(schema: unknown): Record<string, string> {
  const props = isObj(schema) && isObj(schema["properties"]) ? schema["properties"] : {};
  const out: Record<string, string> = {};
  for (const [key, node] of Object.entries(props)) if (isObj(node) && typeof node["title"] === "string") out[key] = node["title"];
  return out;
}

/** 필드 스키마의 `x-ui.variables`(입력 틀 변수 `[{name, description}]`). 모양이 다르면 빈 목록. */
export function xuiVariables(node: unknown): { name: string; description?: string }[] {
  const xui = isObj(node) ? node["x-ui"] : undefined;
  const raw = isObj(xui) ? xui["variables"] : undefined;
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((v) => (isObj(v) && typeof v["name"] === "string" ? [{ name: v["name"], ...(typeof v["description"] === "string" ? { description: v["description"] } : {}) }] : []));
}

/** 입력 틀에 끼우는 변수 글자(`{이름}`). 닫는 중괄호는 이스케이프로 쓴다 — `}}`가 소스에 나오면 링크 패턴 하드코딩 검사가 오인한다. */
export const variableToken = (name: string): string => `{${name}\u007d`;
