/** 페이지 목록 → 트리 행. 폴더 먼저, 그 안은 이름 오름차순(한국어·숫자 정렬). 경로 구분은 `/`. */
import type { WikiPageSummary } from "@agent-console/contracts/wiki";
import { lastSegment } from "./format";

export type TreeTitleMode = "title" | "path";

export interface TreeRow {
  kind: "folder" | "page";
  /** 폴더는 폴더 경로, 페이지는 페이지 경로(고유) */
  key: string;
  /** 보이는 이름 */
  name: string;
  depth: number;
  expanded?: boolean;
  /** 폴더가 가진 페이지 수(하위 포함) */
  count?: number;
  page?: WikiPageSummary;
}

export interface BuildTreeOptions {
  expanded: ReadonlySet<string>;
  filter?: string;
  titleMode?: TreeTitleMode;
  /** 이 페이지의 상위 폴더는 항상 펼친다. */
  revealPath?: string | null;
}

interface FolderNode {
  path: string;
  name: string;
  folders: Map<string, FolderNode>;
  pages: WikiPageSummary[];
}

const collator = new Intl.Collator("ko", { numeric: true, sensitivity: "base" });

/** 페이지의 트리 이름. */
export function pageName(page: WikiPageSummary, mode: TreeTitleMode): string {
  const seg = lastSegment(page.path);
  return mode === "title" && page.title && page.title !== "" ? page.title : seg;
}

/** 경로의 상위 폴더 경로들(바깥부터). `a/b/c` → `["a", "a/b"]` */
export function ancestorFolders(path: string): string[] {
  const parts = path.split("/");
  const out: string[] = [];
  for (let i = 1; i < parts.length; i += 1) out.push(parts.slice(0, i).join("/"));
  return out;
}

function matches(page: WikiPageSummary, needle: string): boolean {
  return page.path.toLowerCase().includes(needle) || (page.title ?? "").toLowerCase().includes(needle);
}

function countPages(f: FolderNode): number {
  let n = f.pages.length;
  for (const c of f.folders.values()) n += countPages(c);
  return n;
}

/** 목록 전체의 모든 폴더 경로(모두 펼치기용). */
export function allFolders(pages: readonly WikiPageSummary[]): string[] {
  const set = new Set<string>();
  for (const p of pages) for (const f of ancestorFolders(p.path)) set.add(f);
  return [...set];
}

/** 보이는 행(펼침 상태 반영)을 만든다. `filter`가 있으면 맞는 페이지와 그 상위 폴더만 남기고 모두 펼친다. */
export function buildTree(pages: readonly WikiPageSummary[], opts: BuildTreeOptions): TreeRow[] {
  const mode = opts.titleMode ?? "title";
  const needle = (opts.filter ?? "").trim().toLowerCase();
  const filtering = needle !== "";
  const root: FolderNode = { path: "", name: "", folders: new Map(), pages: [] };
  for (const page of pages) {
    if (filtering && !matches(page, needle)) continue;
    const parts = page.path.split("/");
    let node = root;
    for (let i = 0; i < parts.length - 1; i += 1) {
      const p = parts.slice(0, i + 1).join("/");
      let next = node.folders.get(p);
      if (!next) {
        next = { path: p, name: parts[i]!, folders: new Map(), pages: [] };
        node.folders.set(p, next);
      }
      node = next;
    }
    node.pages.push(page);
  }
  const forced = new Set(opts.revealPath ? ancestorFolders(opts.revealPath) : []);
  const rows: TreeRow[] = [];
  const walk = (node: FolderNode, depth: number): void => {
    const folders = [...node.folders.values()].sort((a, b) => collator.compare(a.name, b.name));
    for (const f of folders) {
      const open = filtering || forced.has(f.path) || opts.expanded.has(f.path);
      rows.push({ kind: "folder", key: f.path, name: f.name, depth, expanded: open, count: countPages(f) });
      if (open) walk(f, depth + 1);
    }
    const sorted = [...node.pages].sort((a, b) => collator.compare(pageName(a, mode), pageName(b, mode)) || collator.compare(a.path, b.path));
    for (const page of sorted) rows.push({ kind: "page", key: page.path, name: pageName(page, mode), depth, page });
  };
  walk(root, 0);
  return rows;
}
