import type { I18nInfo } from "@agent-console/contracts/i18n";

/** Normalizes a BCP 47 code: `_` becomes `-`, language lower case, region upper case, script title case. */
export function normalizeLanguage(code: string): string {
  const parts = code.trim().replace(/_/g, "-").split("-").filter(Boolean);
  return parts
    .map((part, index) => {
      if (index === 0) return part.toLowerCase();
      if (part.length === 4) return part[0]!.toUpperCase() + part.slice(1).toLowerCase();
      if (part.length === 2 || part.length === 3) return part.toUpperCase();
      return part;
    })
    .join("-");
}

/** Picks the available code for a requested one: exact match first, then the primary language (`en-US` -> `en`). */
export function matchLanguage(code: string, available: readonly string[]): string | undefined {
  const wanted = normalizeLanguage(code);
  if (!wanted) return undefined;
  const normalized = available.map((a) => [a, normalizeLanguage(a)] as const);
  const exact = normalized.find(([, n]) => n === wanted);
  if (exact) return exact[0];
  const primary = wanted.split("-")[0]!;
  return normalized.find(([, n]) => n === primary)?.[0];
}

export interface ResolveLanguageInput {
  /** The saved setting (`ui.language`); `null`/`undefined`/empty means automatic. */
  preference?: string | null;
  /** Browser languages in priority order (`navigator.languages`). */
  browser?: readonly string[];
  /** Languages that can be shown (app bundles plus server languages). */
  available: readonly string[];
  /** The server's `default_language`, when connected. */
  serverDefault?: string | null;
  /** Last resort. Default `en`. */
  fallback?: string;
}

/**
 * Decides the language to show: saved setting, then browser languages, then the server default, then `fallback`.
 * A saved setting that is not available is skipped (the caller can show "unavailable" from the raw value).
 */
export function resolveLanguage(input: ResolveLanguageInput): string {
  const { preference, browser = [], available, serverDefault, fallback = "en" } = input;
  if (preference) {
    const hit = matchLanguage(preference, available);
    if (hit) return hit;
  }
  for (const code of browser) {
    const hit = matchLanguage(code, available);
    if (hit) return hit;
  }
  if (serverDefault) {
    const hit = matchLanguage(serverDefault, available);
    if (hit) return hit;
  }
  return fallback;
}

/** Union of app-bundle languages and server languages, in first-seen order. */
export function availableLanguages(bundled: readonly string[], info?: Pick<I18nInfo, "languages"> | null): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const code of [...bundled, ...(info?.languages.map((l) => l.code) ?? [])]) {
    if (!seen.has(code)) {
      seen.add(code);
      out.push(code);
    }
  }
  return out;
}

/** The name of a language written in `inLanguage` (default: the language itself); falls back to the code. */
export function languageName(code: string, inLanguage: string = code): string {
  try {
    const name = new Intl.DisplayNames([inLanguage], { type: "language" }).of(code);
    return name && name !== code ? name : code;
  } catch {
    return code;
  }
}
