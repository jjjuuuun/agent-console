import { textCompare } from "./sort";
import type { GroupByDef, GroupNode, GroupOptions } from "./types";

/** "없음" 묶음의 키. 실제 값과 겹치지 않는 제어 문자. */
export const NONE_KEY = "\u0000none";
const SEP = "/";

function clean(values: readonly string[]): string[] {
  const out: string[] = [];
  for (const v of values) {
    const t = v.trim();
    if (t !== "" && !out.includes(t)) out.push(t);
  }
  return out;
}

/** `a/b/c`를 조각으로 나눈다(빈 조각 제거). 깊이 `maxDepth` 아래는 한 이름으로 합친다. */
function segments(value: string, maxDepth: number): string[] {
  const parts = value.split(SEP).map((p) => p.trim()).filter((p) => p !== "");
  return parts.length > maxDepth + 1 ? [...parts.slice(0, maxDepth), parts.slice(maxDepth).join(SEP)] : parts;
}

/**
 * 항목을 묶는다. 순수 함수. 반환은 화면 순서의 평평한 목록(트리는 깊이 우선, 같은 형제끼리 이름순,
 * "없음" 묶음은 항상 맨 아래). 항목이 없는 묶음은 만들지 않는다(트리의 중간 단계는 하위에 항목이 있으면 둔다).
 */
export function groupItems<T>(items: readonly T[], def: GroupByDef<T>, options: GroupOptions<T> = {}): GroupNode<T>[] {
  const { locale = "ko", compare, maxDepth = 3 } = options;
  const text = textCompare(locale);
  const tree = def.tree === true;
  const nodes = new Map<string, GroupNode<T>>();
  const none: T[] = [];

  const ensure = (path: string[]): GroupNode<T> => {
    const key = path.join(SEP);
    let node = nodes.get(key);
    if (node === undefined) {
      node = { key, name: path[path.length - 1]!, depth: path.length - 1, parentKey: path.length > 1 ? path.slice(0, -1).join(SEP) : undefined, items: [], count: 0, none: false };
      nodes.set(key, node);
    }
    return node;
  };

  for (const item of items) {
    const values = clean(def.read(item));
    const used = def.multi === true ? values : values.slice(0, 1);
    if (used.length === 0) {
      none.push(item);
      continue;
    }
    const placed = new Set<string>();
    for (const value of used) {
      const path = tree ? segments(value, maxDepth) : [value];
      if (path.length === 0) continue;
      for (let i = 1; i < path.length; i++) ensure(path.slice(0, i));
      const node = ensure(path);
      if (placed.has(node.key)) continue;
      placed.add(node.key);
      node.items.push(item);
    }
    if (placed.size === 0) none.push(item);
  }

  const sortedItems = (list: T[]): T[] => (compare === undefined ? list : list.map((item, i) => ({ item, i })).sort((a, b) => compare(a.item, b.item) || a.i - b.i).map((e) => e.item));
  const children = new Map<string | undefined, GroupNode<T>[]>();
  for (const node of nodes.values()) {
    node.items = sortedItems(node.items);
    node.count = node.items.length;
    const list = children.get(node.parentKey) ?? [];
    list.push(node);
    children.set(node.parentKey, list);
  }
  const out: GroupNode<T>[] = [];
  const walk = (parent: string | undefined) => {
    for (const node of (children.get(parent) ?? []).sort((a, b) => text(a.name, b.name))) {
      out.push(node);
      walk(node.key);
    }
  };
  walk(undefined);
  if (none.length > 0) out.push({ key: NONE_KEY, name: "", depth: 0, parentKey: undefined, items: sortedItems(none), count: none.length, none: true });
  return out;
}

/** 이름 있는 묶음이 하나라도 있는지. false면 평면 목록으로 그린다(머리 없음). */
export function hasNamedGroups<T>(nodes: readonly GroupNode<T>[]): boolean {
  return nodes.some((n) => !n.none);
}

/** 접힌 묶음의 하위 묶음을 뺀 목록(접힌 묶음 자신은 남는다). */
export function visibleGroups<T>(nodes: readonly GroupNode<T>[], collapsed: ReadonlySet<string>): GroupNode<T>[] {
  const byKey = new Map(nodes.map((n) => [n.key, n]));
  const hidden = (n: GroupNode<T>): boolean => {
    for (let p = n.parentKey; p !== undefined; p = byKey.get(p)?.parentKey) if (collapsed.has(p)) return true;
    return false;
  };
  return nodes.filter((n) => !hidden(n));
}

/** 키 하나와 그 조상을 접힘 집합에서 뺀다(선택 항목이 든 묶음을 펼칠 때). 새 집합을 돌려준다. */
export function revealGroup(collapsed: ReadonlySet<string>, key: string): Set<string> {
  const next = new Set(collapsed);
  const parts = key.split(SEP);
  for (let i = 1; i <= parts.length; i++) next.delete(parts.slice(0, i).join(SEP));
  return next;
}

/** 항목이 속한 묶음의 키들(선택 항목 펼치기용). */
export function groupKeysOf<T>(nodes: readonly GroupNode<T>[], match: (item: T) => boolean): string[] {
  return nodes.filter((n) => n.items.some(match)).map((n) => n.key);
}

/** 중복 없는 항목 수(다중 값 기준에서 같은 항목이 여러 묶음에 있어도 한 번). */
export function uniqueCount<T>(nodes: readonly GroupNode<T>[]): number {
  return new Set(nodes.flatMap((n) => n.items)).size;
}
