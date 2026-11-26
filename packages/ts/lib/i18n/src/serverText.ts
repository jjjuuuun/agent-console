import type { i18n as I18nInstance } from "i18next";

import { SERVER_CODES_NS, SERVER_TEXT_NS } from "./types";

/** Looks up server-provided strings. Both lookups follow the language fallback chain. */
export interface ServerText {
  /** Translates a server original string (the string itself is the key). Unknown strings come back unchanged. */
  text(original: string): string;
  /** Renders an error/issue code with its `details`; when the code has no message, returns `fallback`. */
  issue(code: string, details: Record<string, unknown> | null | undefined, fallback: string): string;
}

const RAW = { keySeparator: false, nsSeparator: false } as const;

/** Builds the lookups for one i18next instance. Not React-specific; `useServerText` wraps it. */
export function createServerText(instance: I18nInstance): ServerText {
  const chain = (): readonly string[] => (instance.languages?.length ? instance.languages : [instance.language]);
  return {
    text(original) {
      for (const language of chain()) {
        const hit: unknown = instance.getResource(language, SERVER_TEXT_NS, original, RAW);
        if (typeof hit === "string" && hit !== "") return hit;
      }
      return original;
    },
    issue(code, details, fallback) {
      const exists = instance.exists(code, { ns: SERVER_CODES_NS, ...RAW });
      if (!exists) return fallback;
      const { count, ...rest } = details ?? {};
      const out = instance.t(code, {
        ns: SERVER_CODES_NS,
        ...RAW,
        ...(typeof count === "number" ? { count } : {}),
        replace: { ...rest, ...(typeof count === "number" ? { count } : {}) },
      });
      return typeof out === "string" && out !== "" ? out : fallback;
    },
  };
}
