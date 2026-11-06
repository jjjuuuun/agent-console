/**
 * 규칙 탭의 섹션 목록을 스키마에서 만든다(screen-sdd §10.2, S3). 섹션 이름·필드 이름은 코드에 없다:
 * 최상위 속성 중 `x-ui.tier`가 `advanced`가 아닌 것만 보이고, 값이 객체인 속성(예: 규칙)은 그 속성 하나하나가 섹션이 된다.
 * 객체가 아닌 속성(이름·설명·문서 목록)은 각각 섹션이다. 제목은 스키마 `title`, 순서는 `x-ui.order`(없으면 스키마 순서).
 */
import { resolveRef, unwrapNullable, type SchemaNode } from "../../lib/schemaTools";

export interface RuleSection {
  /** 섹션 id(경로 조각의 이어 붙임: `documents`, `rules/gates`) */
  id: string;
  title: string;
  /** 값에서 이 섹션이 다루는 위치(속성 이름 경로, 길이 1 또는 2) */
  path: readonly string[];
  /** 이 섹션 하나를 그리는 JSON Schema(속성 하나를 감싼 객체, `$defs` 포함) */
  schema: SchemaNode;
  /** 오류 점 계산용 JSON Pointer 접두 */
  pointer: string;
}

const isNode = (v: unknown): v is SchemaNode => typeof v === "object" && v !== null && !Array.isArray(v);
const xui = (node: SchemaNode): SchemaNode => (isNode(node["x-ui"]) ? node["x-ui"] : {});
const orderOf = (node: SchemaNode, index: number): number => {
  const { order } = xui(node);
  return typeof order === "number" ? order : 1000 + index;
};

function wrap(root: SchemaNode, key: string, node: SchemaNode): SchemaNode {
  return { type: "object", properties: { [key]: node }, $defs: root["$defs"] };
}

/**
 * `schema`(정의 모델 전체, `$defs` 포함)에서 섹션을 만든다.
 * @param includeAdvanced 고급(`tier: advanced`)이어도 섹션으로 보일 최상위 속성 이름(데이터에서 온다). 기본은 없음.
 */
export function ruleSections(schema: SchemaNode, includeAdvanced: readonly string[] = []): RuleSection[] {
  const props = isNode(schema["properties"]) ? schema["properties"] : {};
  const out: { section: RuleSection; order: number }[] = [];
  Object.entries(props).forEach(([key, raw], index) => {
    if (!isNode(raw)) return;
    const node = resolveRef(raw, schema);
    if (xui(node)["tier"] === "advanced" && !includeAdvanced.includes(key)) return;
    const inner = unwrapNullable(node, schema).schema;
    const innerProps = inner["type"] === "object" && isNode(inner["properties"]) ? inner["properties"] : null;
    if (innerProps === null) {
      out.push({ order: orderOf(node, index), section: { id: key, title: String(node["title"] ?? key), path: [key], schema: wrap(schema, key, raw), pointer: `/${key}` } });
      return;
    }
    Object.entries(innerProps).forEach(([sub, subRaw], subIndex) => {
      if (!isNode(subRaw)) return;
      const subNode = resolveRef(subRaw, schema);
      out.push({ order: orderOf(node, index) * 1000 + orderOf(subNode, subIndex), section: { id: `${key}/${sub}`, title: String(subNode["title"] ?? sub), path: [key, sub], schema: wrap(schema, sub, subRaw), pointer: `/${key}/${sub}` } });
    });
  });
  return out.sort((a, b) => a.order - b.order).map((x) => x.section);
}

/** 값(`{name, rules: {…}}` 모양)에서 섹션이 다루는 조각을 `{속성: 값}`으로 꺼낸다. */
export function sectionValue(value: Readonly<Record<string, unknown>>, section: RuleSection): Record<string, unknown> {
  const [first, second] = section.path;
  if (second === undefined) return first === undefined || value[first] === undefined ? {} : { [first]: value[first] };
  const container = isNode(value[first as string]) ? (value[first as string] as SchemaNode) : {};
  return container[second] === undefined ? {} : { [second]: container[second] };
}

/** 섹션 폼이 낸 `{속성: 값}`을 전체 값에 합친다(값이 없어지면 그 키를 지운다). 새 객체를 돌려준다. */
export function mergeSection(value: Readonly<Record<string, unknown>>, section: RuleSection, next: unknown): Record<string, unknown> {
  const picked = isNode(next) ? next : {};
  const [first, second] = section.path;
  const key = second ?? (first as string);
  const result = { ...value };
  if (second === undefined) {
    if (picked[key] === undefined) delete result[key];
    else result[key] = picked[key];
    return result;
  }
  const container = { ...(isNode(value[first as string]) ? (value[first as string] as SchemaNode) : {}) };
  if (picked[key] === undefined) delete container[key];
  else container[key] = picked[key];
  result[first as string] = container;
  return result;
}

/** 검사 이슈 `path`(JSON Pointer)가 섹션에 속하는가. */
export function issueInSection(path: string | null | undefined, section: RuleSection): boolean {
  return typeof path === "string" && (path === section.pointer || path.startsWith(`${section.pointer}/`));
}
