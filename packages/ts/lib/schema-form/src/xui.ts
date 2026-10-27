/**
 * 스키마 확장 `x-ui`(필드 표시 힌트)를 읽는 순수 함수. 필드 이름·종류 id를 모른다.
 * `x-ui` 키: tier(basic|advanced)·when·example·group·group_title·order·unit·enum_labels. 없으면 tier 폴백 규칙을 쓴다.
 */
type Obj = Record<string, unknown>;

export type Tier = "basic" | "advanced";

export interface XUi {
  tier?: Tier;
  /** 언제 바꾸나 */
  when?: string;
  example?: unknown;
  group?: string;
  groupTitle?: string;
  order?: number;
  unit?: string;
  /** enum 값 → 화면 라벨(`oneOf`의 `title`이 없는 단순 `enum`용) */
  enumLabels?: Record<string, string>;
}

const MAX_DEPTH = 8;

function isObj(v: unknown): v is Obj {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/** `$ref`(`#/…` 로컬)와 단일 `allOf` 래퍼를 풀고 형제 키를 덮어 얹는다. 못 풀면 그대로. */
export function resolveNode(node: unknown, root: unknown, depth = 0): Obj {
  if (!isObj(node)) return {};
  if (depth > MAX_DEPTH) return node;
  const { $ref, allOf, ...siblings } = node as Obj;
  let base: Obj = {};
  let touched = false;
  if (typeof $ref === "string" && $ref.startsWith("#/")) {
    let cur: unknown = root;
    for (const seg of $ref.slice(2).split("/")) cur = isObj(cur) ? cur[seg.replace(/~1/g, "/").replace(/~0/g, "~")] : undefined;
    if (isObj(cur)) {
      base = resolveNode(cur, root, depth + 1);
      touched = true;
    }
  }
  if (Array.isArray(allOf) && allOf.length === 1) {
    base = { ...base, ...resolveNode(allOf[0], root, depth + 1) };
    touched = true;
  }
  if (!touched) return node;
  const xui = isObj(base["x-ui"]) || isObj(siblings["x-ui"]) ? { ...(base["x-ui"] as Obj | undefined), ...(siblings["x-ui"] as Obj | undefined) } : undefined;
  return { ...base, ...siblings, ...(xui ? { "x-ui": xui } : {}) };
}

/** 노드의 `x-ui`를 읽는다(타입이 맞지 않는 값은 버린다). */
export function readXUi(node: unknown): XUi {
  const raw = isObj(node) ? node["x-ui"] : undefined;
  if (!isObj(raw)) return {};
  const out: XUi = {};
  if (raw["tier"] === "basic" || raw["tier"] === "advanced") out.tier = raw["tier"];
  if (typeof raw["when"] === "string" && raw["when"]) out.when = raw["when"];
  if (raw["example"] !== undefined && raw["example"] !== null) out.example = raw["example"];
  if (typeof raw["group"] === "string" && raw["group"]) out.group = raw["group"];
  if (typeof raw["group_title"] === "string" && raw["group_title"]) out.groupTitle = raw["group_title"];
  if (typeof raw["order"] === "number") out.order = raw["order"];
  if (typeof raw["unit"] === "string" && raw["unit"]) out.unit = raw["unit"];
  const labels = raw["enum_labels"];
  if (isObj(labels)) {
    const entries = Object.entries(labels).filter((e): e is [string, string] => typeof e[1] === "string" && e[1] !== "");
    if (entries.length > 0) out.enumLabels = Object.fromEntries(entries);
  }
  return out;
}

const escapeRe = (v: string) => v.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/**
 * 안내 문장에 섞인 enum 원시 값을 사람이 읽는 라벨로 바꾼다(`x-ui.enum_labels`가 데이터).
 * `문장(value)`처럼 값을 괄호로 덧붙인 곳은 괄호째 지우고(라벨이 이미 선택지에 보인다), 그 밖의 값 단어는 라벨로 치환한다.
 * 영문·숫자·밑줄로 이어진 단어의 일부는 건드리지 않는다. 라벨이 없으면 문장을 그대로 돌려준다.
 */
export function humanizeEnumText(text: string, labels: Readonly<Record<string, string>> | undefined): string {
  if (labels === undefined) return text;
  const values = Object.keys(labels).sort((a, b) => b.length - a.length);
  let out = text;
  for (const v of values) out = out.replace(new RegExp(`\\s?[(（]${escapeRe(v)}[)）]`, "g"), "");
  for (const v of values) out = out.replace(new RegExp(`(?<![A-Za-z0-9_])${escapeRe(v)}(?![A-Za-z0-9_])`, "g"), labels[v] ?? v);
  return out;
}

/**
 * tier 결정 순서(ux-overhaul §5.3): x-ui.tier 명시 -> required -> 객체는 자식 중 basic이 있으면 basic ->
 * 기본값 있는 선택 필드는 advanced, 없는 선택 필드는 basic.
 */
export function resolveTier(node: unknown, required: boolean, root: unknown, depth = 0): Tier {
  const s = resolveNode(node, root);
  const explicit = readXUi(s).tier;
  if (explicit) return explicit;
  if (required) return "basic";
  const props = s["properties"];
  if (isObj(props) && depth < MAX_DEPTH && Object.keys(props).length > 0) {
    const req = Array.isArray(s["required"]) ? (s["required"] as unknown[]) : [];
    const anyBasic = Object.entries(props).some(([k, child]) => resolveTier(child, req.includes(k), root, depth + 1) === "basic");
    return anyBasic ? "basic" : "advanced";
  }
  return s["default"] !== undefined && s["default"] !== null ? "advanced" : "basic";
}

export interface SplitEntry<T> {
  name: string;
  item: T;
  tier: Tier;
  xui: XUi;
}

/** 이름 목록을 tier·order 기준으로 나눈다. order가 있는 항목이 먼저, 나머지는 원래 순서. */
export function splitByTier<T extends { name: string }>(items: readonly T[], objectSchema: unknown, root: unknown): { basic: SplitEntry<T>[]; advanced: SplitEntry<T>[] } {
  const s = resolveNode(objectSchema, root);
  const props = isObj(s["properties"]) ? s["properties"] : {};
  const req = Array.isArray(s["required"]) ? (s["required"] as unknown[]) : [];
  const entries: SplitEntry<T>[] = items.map((item) => {
    const node = props[item.name];
    return { name: item.name, item, tier: node === undefined ? "basic" : resolveTier(node, req.includes(item.name), root), xui: readXUi(resolveNode(node, root)) };
  });
  const sorted = entries.map((e, i) => ({ e, i })).sort((a, b) => (a.e.xui.order ?? Infinity) - (b.e.xui.order ?? Infinity) || a.i - b.i).map((x) => x.e);
  return { basic: sorted.filter((e) => e.tier === "basic"), advanced: sorted.filter((e) => e.tier === "advanced") };
}

/** errorSchema 가지에 오류가 하나라도 있는가. */
export function hasErrorNode(node: unknown): boolean {
  if (!isObj(node)) return false;
  for (const [k, v] of Object.entries(node)) {
    if (k === "__errors") {
      if (Array.isArray(v) && v.length > 0) return true;
    } else if (hasErrorNode(v)) return true;
  }
  return false;
}
