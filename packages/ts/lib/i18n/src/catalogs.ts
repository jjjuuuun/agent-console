import type { MessageTree } from "./types";

const PLURAL_SUFFIX = /_(zero|one|two|few|many|other)$/;
const PLACEHOLDER = /\{\s*([A-Za-z_][\w]*)\s*(?:,\s*([^}]*?))?\s*\}/g;

/** Flattens a tree to `a.b.c` -> string. */
export function flattenMessages(tree: MessageTree, prefix = ""): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(tree)) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === "string") out[path] = value;
    else Object.assign(out, flattenMessages(value, path));
  }
  return out;
}

/** Placeholder names in a message (`{count}`, `{label, particle.object}`), without format names; sorted, unique. */
export function placeholdersOf(message: string): string[] {
  const names = new Set<string>();
  for (const match of message.matchAll(PLACEHOLDER)) names.add(match[1]!);
  return [...names].sort();
}

/** Format names used in a message (`particle.object` from `{label, particle.object}`); options in parentheses dropped. */
export function formatNamesOf(message: string): string[] {
  const names = new Set<string>();
  for (const match of message.matchAll(PLACEHOLDER)) {
    const spec = match[2];
    if (spec) names.add(spec.split("(")[0]!.trim().toLowerCase());
  }
  return [...names].sort();
}

/** Groups plural forms: `issues_one` and `issues_other` become the key `issues`. */
function groupPlurals(flat: Record<string, string>): Map<string, string[]> {
  const groups = new Map<string, string[]>();
  for (const [key, message] of Object.entries(flat)) {
    const base = key.replace(PLURAL_SUFFIX, "");
    groups.set(base, [...(groups.get(base) ?? []), message]);
  }
  return groups;
}

export interface PlaceholderDiff {
  key: string;
  a: string[];
  b: string[];
}

export interface CatalogComparison {
  /** Keys only `a` has. */
  onlyInA: string[];
  /** Keys only `b` has. */
  onlyInB: string[];
  /** Keys both have but with different placeholder sets (plural forms of one key are compared together). */
  placeholderMismatches: PlaceholderDiff[];
  /** True when there is no difference at all. */
  same: boolean;
}

/** Compares two message trees by keys and placeholder names (format names and order do not count). */
export function compareCatalogs(a: MessageTree, b: MessageTree): CatalogComparison {
  const ga = groupPlurals(flattenMessages(a));
  const gb = groupPlurals(flattenMessages(b));
  const onlyInA = [...ga.keys()].filter((k) => !gb.has(k)).sort();
  const onlyInB = [...gb.keys()].filter((k) => !ga.has(k)).sort();
  const placeholderMismatches: PlaceholderDiff[] = [];
  for (const [key, messagesA] of ga) {
    const messagesB = gb.get(key);
    if (!messagesB) continue;
    const union = (messages: string[]) => [...new Set(messages.flatMap(placeholdersOf))].sort();
    const pa = union(messagesA);
    const pb = union(messagesB);
    if (pa.join("|") !== pb.join("|")) placeholderMismatches.push({ key, a: pa, b: pb });
  }
  placeholderMismatches.sort((x, y) => x.key.localeCompare(y.key));
  return { onlyInA, onlyInB, placeholderMismatches, same: !onlyInA.length && !onlyInB.length && !placeholderMismatches.length };
}

/** Keys whose message uses a format starting with `prefix` (for example `particle.` in a non-Korean catalog). */
export function keysUsingFormat(tree: MessageTree, prefix: string): string[] {
  return Object.entries(flattenMessages(tree))
    .filter(([, message]) => formatNamesOf(message).some((name) => name.startsWith(prefix)))
    .map(([key]) => key)
    .sort();
}
