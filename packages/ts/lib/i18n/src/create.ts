import type { MessageCatalog } from "@agent-console/contracts/i18n";
import { createInstance, type i18n as I18nInstance } from "i18next";

import { defaultFormatters } from "./formatters";
import { SERVER_CODES_NS, SERVER_TEXT_NS } from "./types";
import type {
  BundledCatalogs,
  FetchCatalog,
  FormatterRegistry,
  LoadBundled,
  MissingHandler,
  NamespaceBundle,
} from "./types";

export interface CreateI18nOptions {
  /** The language to start with. Default: `fallbackLanguage`. */
  language?: string;
  /** Used when a message is missing in the current language. Default `en`. */
  fallbackLanguage?: string;
  /** App bundles that are already loaded (language -> namespace -> messages). */
  bundled?: BundledCatalogs;
  /** Loads an app bundle that is not in `bundled` yet (lazy chunks); used by `setLanguage`. */
  loadBundled?: LoadBundled;
  /** Namespaces that exist; default: every namespace found in `bundled`. */
  namespaces?: readonly string[];
  /** Extra formats, merged over `defaultFormatters` (same name = yours wins). */
  formatters?: FormatterRegistry;
  /** Called for a missing key or placeholder value. Tests pass `throwOnMissing`. */
  onMissing?: MissingHandler;
}

/** A created instance. The extra fields are what `setLanguage` needs. */
export interface Console18n extends I18nInstance {
  /** The app-bundle loader given to `createI18n`. */
  loadBundled?: LoadBundled;
}

/**
 * Builds an i18next instance with `{name}` placeholders, the fallback chain `language -> primary -> fallbackLanguage
 * -> en`, and the format registry. Initialization is synchronous when `bundled` carries the resources.
 */
export function createI18n(options: CreateI18nOptions = {}): Console18n {
  const { fallbackLanguage = "en", bundled = {}, formatters = {}, onMissing } = options;
  const instance = createInstance() as Console18n;
  const namespaces = new Set<string>(options.namespaces ?? []);
  const resources: Record<string, Record<string, object>> = {};
  for (const [language, bundle] of Object.entries(bundled)) {
    // i18next mutates the objects it stores, so keep the caller's bundles untouched.
    resources[language] = structuredClone(bundle);
    for (const ns of Object.keys(bundle)) namespaces.add(ns);
  }
  const fallbacks = [...new Set([fallbackLanguage, "en"])];

  void instance.init({
    lng: options.language ?? fallbackLanguage,
    fallbackLng: fallbacks,
    resources,
    ns: [...namespaces],
    defaultNS: [...namespaces][0],
    initAsync: false,
    interpolation: { prefix: "{", suffix: "}", escapeValue: false },
    returnNull: false,
    saveMissing: onMissing !== undefined,
    missingKeyHandler: (languages: readonly string[], ns: string, key: string) => {
      if (ns === SERVER_TEXT_NS || ns === SERVER_CODES_NS) return;
      onMissing?.({ kind: "key", language: languages[0] ?? instance.language, namespace: ns, key });
    },
    // Returning the text keeps an unfilled `{name}` visible instead of blank.
    missingInterpolationHandler: (text: string, _value: unknown, opts: { ns?: string | readonly string[] } | undefined) => {
      const ns = typeof opts?.ns === "string" ? opts.ns : opts?.ns?.[0];
      onMissing?.({ kind: "interpolation", language: instance.language, namespace: ns ?? "", key: text });
      return text;
    },
  });
  for (const [name, format] of Object.entries({ ...defaultFormatters, ...formatters })) {
    instance.services.formatter?.add(name, (value: unknown, lng: string | undefined, opts: Record<string, unknown>) =>
      format(value, lng, opts),
    );
  }
  if (options.loadBundled) instance.loadBundled = options.loadBundled;
  return instance;
}

/** Adds an app bundle for a language. `overwrite` replaces existing keys (default true). */
export function addBundle(instance: I18nInstance, language: string, bundle: NamespaceBundle, overwrite = true): void {
  for (const [ns, tree] of Object.entries(bundle)) instance.addResourceBundle(language, ns, structuredClone(tree), true, overwrite);
}

/**
 * Merges a server catalog over the app bundle: `ns` entries override same-named app namespaces (deep), `text` and
 * `codes` go to the reserved server namespaces (read by `createServerText`).
 */
export function applyServerCatalog(instance: I18nInstance, catalog: MessageCatalog): void {
  const language = catalog.language;
  instance.addResourceBundle(language, SERVER_TEXT_NS, { ...catalog.text }, true, true);
  instance.addResourceBundle(language, SERVER_CODES_NS, { ...catalog.codes }, true, true);
  addBundle(instance, language, catalog.ns as NamespaceBundle, true);
}

export interface SetLanguageOptions {
  /** Fetches the server catalog. Omit when there is no server (app bundles only). */
  fetchCatalog?: FetchCatalog;
  /** Give up on the server catalog after this many ms (the app bundle still applies). Default 5000. */
  timeoutMs?: number;
}

/** What `setLanguage` did. `server`: `loaded`, `failed` (error or timeout), `missing` (server has none), `skipped` (no fetch given). */
export interface SetLanguageResult {
  language: string;
  server: "loaded" | "failed" | "missing" | "skipped";
}

/**
 * Switches the language: loads the app bundle (if lazy), then the server catalog (so the server overrides), then
 * changes the language once, so a screen never shows a half-loaded state. A failed server fetch is not an error;
 * the app bundle alone applies and the result says `failed`.
 */
export async function setLanguage(
  instance: Console18n,
  language: string,
  options: SetLanguageOptions = {},
): Promise<SetLanguageResult> {
  const { fetchCatalog, timeoutMs = 5000 } = options;
  if (instance.loadBundled && !instance.hasResourceBundle(language, "")) {
    const bundle = await instance.loadBundled(language).catch(() => undefined);
    if (bundle) addBundle(instance, language, bundle, false);
  }
  let server: SetLanguageResult["server"] = "skipped";
  if (fetchCatalog) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const catalog = await Promise.race([
        fetchCatalog(language, controller.signal),
        new Promise<never>((_, reject) => controller.signal.addEventListener("abort", () => reject(new Error("timeout")))),
      ]);
      if (catalog) {
        applyServerCatalog(instance, { ...catalog, language });
        server = "loaded";
      } else {
        server = "missing";
      }
    } catch {
      server = "failed";
    } finally {
      clearTimeout(timer);
    }
  }
  await instance.changeLanguage(language);
  return { language, server };
}
