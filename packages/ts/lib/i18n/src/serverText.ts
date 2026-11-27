import type { i18n as I18nInstance } from "i18next";

import { SERVER_CODES_NS, SERVER_TEXT_NS } from "./types";

/** A nested value of a text template: a JSON scalar or another template (a fixed word to translate). */
export type TextParamValue = string | number | boolean | null | TextTemplateLike;

/**
 * Structural shape of the server's `TextTemplate` (`@agent-console/contracts`): an original template with `{name}`
 * placeholders and its values. Structural on purpose, so this package takes no runtime dependency on the contracts.
 */
export interface TextTemplateLike {
  template: string;
  params?: Record<string, TextParamValue> | null | undefined;
}

/** Looks up server-provided strings. Both lookups follow the language fallback chain. */
export interface ServerText {
  /**
   * Translates a server original string (the string itself is the key). Unknown strings come back unchanged.
   * The lookup stops at the server's source language when `setSourceLanguage` was given one (design I-18).
   */
  text(original: string): string;
  /** Renders an error/issue code with its `details`; when the code has no message, returns `fallback`. */
  issue(code: string, details: Record<string, unknown> | null | undefined, fallback: string): string;
  /**
   * Renders a field made of sentence templates (design I-15). `value` is the server-rendered field value; `parts`
   * is the field's `text_templates` entry. When every template (nested ones included) is found in the server
   * catalog, the translated templates are filled with the values and joined with one space; otherwise (or when
   * `parts` is empty or missing) the result is `text(value)`.
   */
  render(value: string, parts?: readonly TextTemplateLike[] | null): string;
}

const RAW = { keySeparator: false, nsSeparator: false } as const;

/** Where the source language lives on the instance. A global symbol, so duplicate copies of this package agree. */
const SOURCE_KEY = Symbol.for("@agent-console/i18n:sourceLanguage");
type WithSource = { [SOURCE_KEY]?: string };

/**
 * Tells the lookups which language the server's original strings are written in (`I18nInfo.source_language`).
 * `text` and `render` stop their fallback chain there (that language included); `null` clears it (unknown).
 */
export function setSourceLanguage(instance: I18nInstance, language: string | null | undefined): void {
  const holder = instance as WithSource;
  if (language) holder[SOURCE_KEY] = language;
  else delete holder[SOURCE_KEY];
}

/** The language set by `setSourceLanguage`, if any. */
export function getSourceLanguage(instance: I18nInstance): string | undefined {
  return (instance as WithSource)[SOURCE_KEY];
}

/** Cuts a fallback chain after the source language (the source language's own catalog still counts). */
export function chainUntilSource(chain: readonly string[], source: string | undefined): readonly string[] {
  if (!source) return chain;
  const at = chain.findIndex((language) => language === source);
  return at < 0 ? chain : chain.slice(0, at + 1);
}

const IDENTIFIER = /^[A-Za-z_]\w*$/;

function plainValue(value: Exclude<TextParamValue, TextTemplateLike>): string {
  if (value === null) return "";
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

/**
 * Fills one template with its values (design I-16, same rules as the server's `render_text_template`): `{name}`
 * only; a missing name, dotted access, positional or format-spec placeholder stays as written; `{{`/`}}` are braces;
 * a template with unbalanced braces comes back unchanged.
 */
export function fillTemplate(template: string, values: Readonly<Record<string, string>>): string {
  let out = "";
  let i = 0;
  while (i < template.length) {
    const ch = template[i]!;
    if (ch === "{") {
      if (template[i + 1] === "{") {
        out += "{";
        i += 2;
        continue;
      }
      const end = template.indexOf("}", i + 1);
      if (end < 0 || template.slice(i + 1, end).includes("{")) return template;
      const name = template.slice(i + 1, end);
      out += IDENTIFIER.test(name) && Object.hasOwn(values, name) ? values[name]! : `{${name}}`;
      i = end + 1;
    } else if (ch === "}") {
      if (template[i + 1] !== "}") return template;
      out += "}";
      i += 2;
    } else {
      out += ch;
      i += 1;
    }
  }
  return out;
}

/** Builds the lookups for one i18next instance. Not React-specific; `useServerText` wraps it. */
export function createServerText(instance: I18nInstance): ServerText {
  const fullChain = (): readonly string[] => (instance.languages?.length ? instance.languages : [instance.language]);
  const textChain = (): readonly string[] => chainUntilSource(fullChain(), getSourceLanguage(instance));
  const find = (original: string): string | undefined => {
    for (const language of textChain()) {
      const hit: unknown = instance.getResource(language, SERVER_TEXT_NS, original, RAW);
      if (typeof hit === "string" && hit !== "") return hit;
    }
    return undefined;
  };
  /** The filled sentence, or `undefined` when this template or a nested one has no translation. */
  const fill = (part: TextTemplateLike): string | undefined => {
    const translated = find(part.template);
    if (translated === undefined) return undefined;
    const values: Record<string, string> = {};
    for (const [name, value] of Object.entries(part.params ?? {})) {
      if (typeof value === "object" && value !== null) {
        const inner = fill(value);
        if (inner === undefined) return undefined;
        values[name] = inner;
      } else {
        values[name] = plainValue(value);
      }
    }
    return fillTemplate(translated, values);
  };
  const text = (original: string): string => find(original) ?? original;
  return {
    text,
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
    render(value, parts) {
      if (!parts || parts.length === 0) return text(value);
      const sentences: string[] = [];
      for (const part of parts) {
        const sentence = fill(part);
        if (sentence === undefined) return value;
        sentences.push(sentence);
      }
      return sentences.join(" ");
    },
  };
}
