import type { i18n as I18nInstance } from "i18next";
import { useMemo, useSyncExternalStore, type ReactNode } from "react";
import { I18nextProvider, useTranslation } from "react-i18next";

import { createServerText, type ServerText } from "./serverText";
import type { MessageTree, MessageValues } from "./types";

/** Makes `instance` the one the hooks below read. Wrap the app once. */
export function I18nProvider({ i18n, children }: { i18n: I18nInstance; children: ReactNode }): ReactNode {
  return <I18nextProvider i18n={i18n}>{children}</I18nextProvider>;
}

/** Translates a key of the hook's namespace. `count` picks the plural form; other values fill `{name}`. */
export type Translate = (key: string, values?: MessageValues) => string;

/** The translate function and current language of a namespace; re-renders when the language or messages change. */
export function useT(namespace: string): Translate & { language: string } {
  const { i18n } = useTranslation(namespace, { bindI18nStore: "added removed" });
  const language = i18n.language;
  return useMemo(() => {
    const t: Translate = (key, values) => {
      const { count, ...rest } = values ?? {};
      return i18n.t(key, {
        ns: namespace,
        ...(typeof count === "number" ? { count } : {}),
        replace: { ...rest, ...(typeof count === "number" ? { count } : {}) },
      });
    };
    return Object.assign(t, { language });
    // `language` changes with the instance language; resource changes re-render through the subscription above.
  }, [i18n, namespace, language]);
}

const versions = new WeakMap<I18nInstance, number>();

function subscribeVersion(i18n: I18nInstance, onChange: () => void): () => void {
  const bump = () => {
    versions.set(i18n, (versions.get(i18n) ?? 0) + 1);
    onChange();
  };
  // Resource events come from the store (the same source react-i18next binds to).
  i18n.store.on("added", bump);
  i18n.store.on("removed", bump);
  i18n.on("languageChanged", bump);
  return () => {
    i18n.store.off("added", bump);
    i18n.store.off("removed", bump);
    i18n.off("languageChanged", bump);
  };
}

/** A number that changes whenever the language or any resource changes (for memo keys). */
function useCatalogVersion(i18n: I18nInstance): number {
  return useSyncExternalStore(
    (onChange) => subscribeVersion(i18n, onChange),
    () => versions.get(i18n) ?? 0,
  );
}

/**
 * Overlays the current language's messages of `namespace` on `defaults` and returns an object of the same shape,
 * ready to pass as a library component's `messages` prop. Placeholders (`{name}`) stay as they are: the library
 * fills them itself. Keys missing in the language use the fallback chain, then `defaults`.
 */
export function overlayMessages<T extends MessageTree>(i18n: I18nInstance, namespace: string, defaults: T): T {
  const languages = i18n.languages?.length ? i18n.languages : [i18n.language];
  const walk = (base: MessageTree, path: string[]): MessageTree => {
    const out: MessageTree = {};
    for (const [key, value] of Object.entries(base)) {
      if (typeof value === "string") {
        let found = value;
        for (const language of languages) {
          const hit: unknown = i18n.getResource(language, namespace, [...path, key].join("."));
          if (typeof hit === "string") {
            found = hit;
            break;
          }
        }
        out[key] = found;
      } else {
        out[key] = walk(value, [...path, key]);
      }
    }
    return out;
  };
  return walk(defaults, []) as T;
}

/**
 * The messages object for a library package: `useLibMessages("graph-editor", defaultMessages)`. The result keeps the
 * same identity until the language or the catalog changes. Pass a stable `defaults` (a module constant).
 */
export function useLibMessages<T extends MessageTree>(namespace: string, defaults: T): T {
  const { i18n } = useTranslation(namespace);
  const version = useCatalogVersion(i18n);
  // eslint-disable-next-line react-hooks/exhaustive-deps -- `version` is the change signal for resources.
  return useMemo(() => overlayMessages(i18n, namespace, defaults), [i18n, namespace, defaults, version, i18n.language]);
}

/** Lookups for server strings and codes; re-renders when the language or the server catalog changes. */
export function useServerText(): ServerText {
  const { i18n } = useTranslation(undefined, { bindI18nStore: "added removed" });
  const language = i18n.language;
  // eslint-disable-next-line react-hooks/exhaustive-deps -- `language` is the change signal; resources re-render via the subscription.
  return useMemo(() => createServerText(i18n), [i18n, language]);
}
