import { resolveRef, schemaAt, unwrapNullable, type SchemaNode } from "../../lib/schemaTools";

/** 섹션 검색 한 줄의 입력(섹션 정의에서 뽑은 글자). 섹션 id·이름을 모르는 순수 데이터다. */
export interface SearchableSection {
  id: string;
  group: string;
  /** 검색 대상 글자(제목·설명·필드 라벨·필드 설명 …) */
  texts: readonly string[];
}

const isNode = (v: unknown): v is SchemaNode => typeof v === "object" && v !== null && !Array.isArray(v);

/** 검색용 정규화: 앞뒤 공백 제거·소문자. */
export function normalizeQuery(q: string): string {
  return q.trim().toLocaleLowerCase();
}

/** 스키마 노드 하나의 글자(`title`·`description`). */
function nodeTexts(node: SchemaNode): string[] {
  const out: string[] = [];
  for (const k of ["title", "description"]) {
    const v = node[k];
    if (typeof v === "string" && v.trim() !== "") out.push(v);
  }
  return out;
}

/**
 * 설정 문서 스키마에서 `keys`(`a/b` 경로)가 가리키는 속성 아래 모든 필드의 라벨·설명을 모은다.
 * 라벨이 스키마에 없으면 속성 이름을 라벨로 쓴다(폼이 그리는 것과 같다). 깊이는 `maxDepth`까지.
 */
export function fieldTexts(root: SchemaNode, keys: readonly string[], maxDepth = 4): string[] {
  const out: string[] = [];
  const walk = (node: SchemaNode, name: string, depth: number) => {
    const { schema } = unwrapNullable(node, root);
    const texts = nodeTexts(schema);
    out.push(...(texts.length > 0 ? texts : [name]));
    const props = schema["properties"];
    if (depth >= maxDepth || !isNode(props)) return;
    for (const [k, v] of Object.entries(props)) if (isNode(v)) walk(resolveRef(v, root), k, depth + 1);
  };
  for (const key of keys) {
    const node = schemaAt(root, `/${key}`);
    if (node === undefined) continue;
    const { schema } = unwrapNullable(node, root);
    const props = schema["properties"];
    // 섹션 키 자체의 제목·설명은 섹션 글자로 이미 있으므로 하위 필드만 모은다.
    if (isNode(props)) for (const [k, v] of Object.entries(props)) if (isNode(v)) walk(resolveRef(v, root), k, 1);
  }
  return out;
}

/** 검색어가 글자 중 하나에 부분 일치하는가(빈 검색어는 모두 일치). */
export function matchesQuery(texts: readonly string[], query: string): boolean {
  const q = normalizeQuery(query);
  return q === "" || texts.some((t) => t.toLocaleLowerCase().includes(q));
}

/** 검색어로 섹션을 거른다. 빈 검색어면 전부. 원래 순서를 유지한다. */
export function filterSections<T extends SearchableSection>(items: readonly T[], query: string): T[] {
  return normalizeQuery(query) === "" ? [...items] : items.filter((s) => matchesQuery(s.texts, query));
}
