const SEP = "/";
const UI = "ui";
const FOLDER = "folder";

type Attrs = Readonly<Record<string, unknown>>;

/** 폴더 경로 정리: 조각을 다듬고 빈 조각을 없앤다. 비면 undefined. */
export function normalizeFolder(value: string | undefined | null): string | undefined {
  if (typeof value !== "string") return undefined;
  const parts = value.split(SEP).map((p) => p.trim()).filter((p) => p !== "");
  return parts.length === 0 ? undefined : parts.join(SEP);
}

/** `attributes.ui.folder`를 읽는다(없거나 문자열이 아니면 undefined). */
export function folderOf(attributes: Attrs | undefined | null): string | undefined {
  const ui = attributes?.[UI];
  if (ui === null || typeof ui !== "object") return undefined;
  return normalizeFolder((ui as Record<string, unknown>)[FOLDER] as string | undefined);
}

/**
 * `attributes.ui.folder`만 바꾼 새 attributes를 돌려준다(다른 속성·`ui`의 다른 키는 보존, 입력은 바꾸지 않음).
 * `folder`가 비면 키를 지우고, `ui`가 비면 `ui`도 지운다.
 */
export function withFolder(attributes: Attrs | undefined | null, folder: string | undefined | null): Record<string, unknown> {
  const next: Record<string, unknown> = { ...(attributes ?? {}) };
  const prevUi = next[UI];
  const ui: Record<string, unknown> = prevUi !== null && typeof prevUi === "object" ? { ...(prevUi as Record<string, unknown>) } : {};
  const value = normalizeFolder(folder);
  if (value === undefined) delete ui[FOLDER];
  else ui[FOLDER] = value;
  if (Object.keys(ui).length === 0) delete next[UI];
  else next[UI] = ui;
  return next;
}

export interface FolderNode {
  name: string;
  /** 전체 경로. */
  path: string;
  children: FolderNode[];
}

/** 폴더 경로들(중복 허용)로 이름순 트리를 만든다. 중간 단계도 노드가 된다. */
export function buildFolderTree(paths: readonly (string | undefined)[], locale = "ko"): FolderNode[] {
  const collator = new Intl.Collator(locale, { numeric: true, sensitivity: "base" });
  const root: FolderNode = { name: "", path: "", children: [] };
  for (const raw of paths) {
    const norm = normalizeFolder(raw);
    if (norm === undefined) continue;
    let cur = root;
    let acc = "";
    for (const part of norm.split(SEP)) {
      acc = acc === "" ? part : `${acc}${SEP}${part}`;
      let child = cur.children.find((c) => c.name === part);
      if (child === undefined) {
        child = { name: part, path: acc, children: [] };
        cur.children.push(child);
      }
      cur = child;
    }
  }
  const sort = (node: FolderNode) => {
    node.children.sort((a, b) => collator.compare(a.name, b.name));
    node.children.forEach(sort);
  };
  sort(root);
  return root.children;
}

/** 트리를 깊이 우선 경로 목록으로 편다("폴더로 이동" 후보). */
export function flattenFolderTree(tree: readonly FolderNode[]): string[] {
  return tree.flatMap((n) => [n.path, ...flattenFolderTree(n.children)]);
}
