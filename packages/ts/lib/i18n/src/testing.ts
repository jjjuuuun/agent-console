import { compareCatalogs, keysUsingFormat } from "./catalogs";
import { createI18n, type Console18n, type CreateI18nOptions } from "./create";
import type { MessageTree, MissingHandler } from "./types";

/** A `MissingHandler` that throws, so a test fails on a missing key or placeholder value. */
export const throwOnMissing: MissingHandler = (info) => {
  throw new Error(`i18n ${info.kind} missing: [${info.language}] ${info.namespace}:${info.key}`);
};

/** `createI18n` for tests: Korean by default (existing Korean assertions keep working) and missing keys fail. */
export function createTestI18n(options: CreateI18nOptions = {}): Console18n {
  return createI18n({ language: "ko", onMissing: throwOnMissing, ...options });
}

export interface AssertCatalogsOptions {
  /** Format-name prefixes that `b` must not use (default: `particle.`, which only Korean uses). */
  forbidFormatsInB?: readonly string[];
}

/**
 * Throws with a readable report when two catalogs (usually ko and en of one namespace) differ in keys or
 * placeholders. Also fails when `b` uses a Korean particle format.
 */
export function assertCatalogsMatch(a: MessageTree, b: MessageTree, options: AssertCatalogsOptions = {}): void {
  const diff = compareCatalogs(a, b);
  const problems: string[] = [];
  if (diff.onlyInA.length) problems.push(`only in first: ${diff.onlyInA.join(", ")}`);
  if (diff.onlyInB.length) problems.push(`only in second: ${diff.onlyInB.join(", ")}`);
  for (const m of diff.placeholderMismatches) problems.push(`placeholders differ at ${m.key}: {${m.a.join(",")}} vs {${m.b.join(",")}}`);
  for (const prefix of options.forbidFormatsInB ?? ["particle."]) {
    const keys = keysUsingFormat(b, prefix);
    if (keys.length) problems.push(`second uses format "${prefix}*": ${keys.join(", ")}`);
  }
  if (problems.length) throw new Error(`Catalogs differ:\n${problems.join("\n")}`);
}

export { compareCatalogs };
