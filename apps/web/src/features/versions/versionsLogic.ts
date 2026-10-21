import type { Issue, ContentChange, DefinitionDiff, DefinitionVersion, DiffChange, ResourceFile } from "@agent-console/contracts";
import { DEFAULT_DIFF_LABEL_KEYS, resolveLabelKeys } from "../../lib/itemLabelKeys";
import { parsePointer } from "../../lib/jsonPointer";
import { resolveRef, unwrapNullable, type SchemaNode } from "../../lib/schemaTools";

export { DEFAULT_DIFF_LABEL_KEYS, resolveLabelKeys };

/** 텍스트 비교를 허용하는 파일 크기 상한(바이트). 넘으면 해시만 비교한다. */
export const MAX_TEXT_DIFF_BYTES = 512 * 1024;

/** 값 한 줄 요약의 최대 글자 수. */
export const VALUE_PREVIEW_CHARS = 80;

/** 한 쪽 문서에서 `segment` 자식 하나. 없으면 undefined. */
function child(node: unknown, segment: string): unknown {
  if (Array.isArray(node)) return node[Number(segment)];
  if (typeof node === "object" && node !== null) return (node as Record<string, unknown>)[segment];
  return undefined;
}

function labelOf(value: unknown, keys: readonly string[]): string | undefined {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return undefined;
  const rec = value as Record<string, unknown>;
  for (const key of keys) {
    const v = rec[key];
    if (typeof v === "string" && v !== "") return v;
  }
  return undefined;
}

export interface ReadablePathOptions {
  /** 배열 원소 이름 후보 키(기본 {@link DEFAULT_DIFF_LABEL_KEYS}) */
  labelKeys?: readonly string[];
  /** 세그먼트마다 스키마 title(모르면 undefined). 같은 길이의 배열을 돌려준다 */
  schemaTitles?: (segments: readonly string[]) => readonly (string | undefined)[];
}

/**
 * JSON Pointer를 사람이 읽는 경로로 바꾼다(표시 전용). 배열 인덱스는 그 문서의 원소 이름(`“PL”`)으로,
 * 이름이 없으면 `#3`으로, 객체 키는 스키마 title이 있으면 그것으로 바꾼다. 문서에 없는 위치는 `#인덱스`/원문 키로 남는다.
 * 예: `/nodes/3/config/model` → `노드 “PL” › config › 모델`
 *
 * @param pointer `DiffChange.path`
 * @param doc 이 경로가 속한 쪽 문서(remove·replace = from 문서, add = to 문서). 없으면 undefined
 */
export function readablePath(pointer: string, doc: unknown, options: ReadablePathOptions = {}): string {
  const segments = parsePointer(pointer);
  if (segments.length === 0) return "/";
  const keys = options.labelKeys ?? DEFAULT_DIFF_LABEL_KEYS;
  const titles = options.schemaTitles?.(segments) ?? [];
  const parts: string[] = [];
  let cur: unknown = doc;
  segments.forEach((segment, i) => {
    const parent = cur;
    cur = child(parent, segment);
    if (Array.isArray(parent)) {
      const label = labelOf(cur, keys);
      const mark = label !== undefined ? `“${label}”` : /^\d+$/.test(segment) ? `#${segment}` : segment;
      if (parts.length === 0) parts.push(mark);
      else parts[parts.length - 1] = `${parts[parts.length - 1]} ${mark}`;
    } else {
      parts.push(titles[i] ?? segment);
    }
  });
  return parts.join(" › ");
}

/**
 * 스키마(루트 + `$defs`)를 따라 JSON Pointer 세그먼트마다 `title`을 찾는다. 모르는 곳부터는 모두 undefined.
 * @param root 정의 모델의 JSON Schema(`$defs`를 함께 가진 것)
 */
export function schemaTitleResolver(root: SchemaNode): (segments: readonly string[]) => (string | undefined)[] {
  return (segments) => {
    const out: (string | undefined)[] = [];
    let node: SchemaNode | undefined = root;
    for (const segment of segments) {
      if (node === undefined) {
        out.push(undefined);
        continue;
      }
      const { schema } = unwrapNullable(node, root);
      const items: unknown = schema["items"];
      if (typeof items === "object" && items !== null && /^\d+$/.test(segment)) {
        node = resolveRef(items as SchemaNode, root);
        out.push(undefined);
        continue;
      }
      const props = schema["properties"];
      const next: unknown = typeof props === "object" && props !== null ? (props as Record<string, unknown>)[segment] : undefined;
      if (typeof next === "object" && next !== null) {
        const resolved = resolveRef(next as SchemaNode, root);
        node = resolved;
        const title = (next as SchemaNode)["title"] ?? resolved["title"];
        out.push(typeof title === "string" ? title : undefined);
      } else {
        node = undefined;
        out.push(undefined);
      }
    }
    return out;
  };
}

export interface ValuePreview {
  /** 한 줄 요약(말줄임 적용) */
  text: string;
  /** 전체 값이 text보다 길다(툴팁으로 전체) */
  truncated: boolean;
  /** 객체·배열이라 [값 펼치기]를 보인다 */
  complex: boolean;
  /** 툴팁·펼침에 쓰는 전체 문자열 */
  full: string;
}

/** 값을 표 한 칸에 넣을 요약으로. 스칼라는 한 줄, 객체·배열은 `{…}`/`[…]`. */
export function previewValue(value: unknown, max: number = VALUE_PREVIEW_CHARS): ValuePreview {
  if (value === undefined) return { text: "", truncated: false, complex: false, full: "" };
  if (typeof value === "object" && value !== null) {
    const full = JSON.stringify(value, null, 2) ?? "";
    const size = Array.isArray(value) ? value.length : Object.keys(value).length;
    return { text: Array.isArray(value) ? `[… ${size}]` : `{… ${size}}`, truncated: false, complex: true, full };
  }
  const full = typeof value === "string" ? value : JSON.stringify(value) ?? String(value);
  const oneLine = full.replace(/\s+/g, " ");
  return oneLine.length > max
    ? { text: `${oneLine.slice(0, max)}…`, truncated: true, complex: false, full }
    : { text: oneLine, truncated: full !== oneLine, complex: false, full };
}

export type DiffOpName = DiffChange["op"];

export interface OpCounts {
  add: number;
  remove: number;
  replace: number;
}

export function countOps(changes: readonly DiffChange[]): OpCounts {
  const counts: OpCounts = { add: 0, remove: 0, replace: 0 };
  for (const c of changes) counts[c.op] += 1;
  return counts;
}

/** 변경 행이 검색어와 맞는가(원문 경로·읽는 경로·값). 비밀 값은 값 비교를 하지 않는다. */
export function matchesQuery(change: DiffChange, readable: string, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (q === "") return true;
  if (change.path.toLowerCase().includes(q) || readable.toLowerCase().includes(q)) return true;
  if (change.secret === true) return false;
  return [change.before, change.after].some((v) => v !== undefined && previewValue(v, Number.MAX_SAFE_INTEGER).full.toLowerCase().includes(q));
}

export type ContentStatus = "added" | "removed" | "changed";

/** 본문 변경 상태: 이전 해시가 없으면 추가, 이후가 없으면 삭제, 둘 다 있으면 변경. */
export function contentStatus(change: ContentChange): ContentStatus {
  if (change.before_hash == null) return "added";
  if (change.after_hash == null) return "removed";
  return "changed";
}

/** 파일 확장자 -> 구문 강조 언어 이름(텍스트 편집 패키지가 아는 이름). 데이터. 모르면 `text`. */
export const LANGUAGE_BY_EXTENSION: Readonly<Record<string, string>> = {
  md: "markdown",
  markdown: "markdown",
  json: "json",
  html: "html",
  htm: "html",
};

export function languageOfPath(path: string, table: Readonly<Record<string, string>> = LANGUAGE_BY_EXTENSION): string {
  const dot = path.lastIndexOf(".");
  const ext = dot < 0 ? "" : path.slice(dot + 1).toLowerCase();
  return Object.hasOwn(table, ext) ? (table[ext] ?? "text") : "text";
}

/** 파일 목록에서 경로 하나의 크기(없으면 undefined). */
export function sizeOfFile(files: readonly ResourceFile[] | undefined, path: string): number | undefined {
  return files?.find((f) => f.path === path)?.size;
}

/** 텍스트 비교가 불가능한 이유(크기). 가능하면 undefined. */
export function textDiffBlocked(sizes: readonly (number | undefined)[], max: number = MAX_TEXT_DIFF_BYTES): "too_large" | undefined {
  return sizes.some((s) => s !== undefined && s > max) ? "too_large" : undefined;
}

export type CompareMode = "current" | "pair";

export interface CompareTarget {
  /** 이전(왼쪽) 버전 해시 */
  from: string;
  /** 이후(오른쪽) 버전 해시. undefined = 현재(서버가 현재와 비교) */
  to: string | undefined;
}

/**
 * 비교 대상을 정한다. 목록은 최신순(0번 = 현재).
 * - `current`: 체크한 버전 1개 vs 현재(체크 없으면 직전 버전). 비교할 이전 버전이 없으면 undefined.
 * - `pair`: 체크 2개 -> 오래된 것이 앞. 2개가 아니면 undefined.
 */
export function compareTarget(versions: readonly Pick<DefinitionVersion, "version_hash">[], checked: readonly string[], mode: CompareMode): CompareTarget | undefined {
  const index = (hash: string) => versions.findIndex((v) => v.version_hash === hash);
  if (mode === "pair") {
    if (checked.length !== 2) return undefined;
    const [x, y] = checked as [string, string];
    const older = index(x) > index(y) ? x : y;
    const newer = older === x ? y : x;
    return { from: older, to: index(newer) === 0 ? undefined : newer };
  }
  const first = checked.find((h) => index(h) > 0);
  const from = first ?? versions[1]?.version_hash;
  return from === undefined ? undefined : { from, to: undefined };
}

/** 비교 결과에서 바뀐 필드 수·본문 수. */
export function diffTotals(diff: Pick<DefinitionDiff, "changes" | "content_changes"> | undefined): { fields: number; content: number } {
  return { fields: diff?.changes?.length ?? 0, content: diff?.content_changes?.length ?? 0 };
}

/** 두 버전이 같은가(변경 0). */
export function isSameDiff(diff: Pick<DefinitionDiff, "changes" | "content_changes">): boolean {
  const { fields, content } = diffTotals(diff);
  return fields === 0 && content === 0;
}

/** 서버 422 `details.issues`에서 `{path, message}`만 읽는다. 모양이 다르면 빈 목록. */
export function readIssues(raw: unknown): { path: string; message: string; code?: string }[] {
  if (!Array.isArray(raw)) return [];
  const out: { path: string; message: string; code?: string }[] = [];
  for (const item of raw as (Partial<Issue> | null)[]) {
    if (typeof item !== "object" || item === null || typeof item.message !== "string") continue;
    out.push({
      path: typeof item.path === "string" ? item.path : "",
      message: item.message,
      ...(typeof item.code === "string" ? { code: item.code } : {}),
    });
  }
  return out;
}
