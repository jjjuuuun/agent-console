import type { MessageCatalog } from "@agent-console/contracts/i18n";

/** A nested message tree: leaves are strings, branches are objects (one namespace). */
export interface MessageTree {
  [key: string]: string | MessageTree;
}

/** Namespace name -> message tree, for one language. */
export type NamespaceBundle = Record<string, MessageTree>;

/** Language code -> namespaces. */
export type BundledCatalogs = Record<string, NamespaceBundle>;

/** Values for placeholders. `count` selects the plural form (`_one`, `_other`, ...). */
export type MessageValues = { count?: number } & Record<string, unknown>;

/** A format used as `{value, name}` in a message. */
export type Formatter = (value: unknown, language: string | undefined, options: Record<string, unknown>) => string;

/** Format name (lower case) -> formatter. */
export type FormatterRegistry = Record<string, Formatter>;

/** Something went missing while rendering a message. */
export interface MissingInfo {
  /** `key`: no message in any language of the fallback chain. `interpolation`: a `{name}` got no value. */
  kind: "key" | "interpolation";
  language: string;
  namespace: string;
  key: string;
}

export type MissingHandler = (info: MissingInfo) => void;

/** Fetches one language's server catalog; `null` means the server has none. Must honor `signal`. */
export type FetchCatalog = (language: string, signal: AbortSignal) => Promise<MessageCatalog | null>;

/** Loads a language's app bundle on demand (lazy chunks); `undefined` means there is none. */
export type LoadBundled = (language: string) => Promise<NamespaceBundle | undefined>;

/** Reserved namespaces that hold the server's `text` and `codes` maps. */
export const SERVER_TEXT_NS = "$server-text";
export const SERVER_CODES_NS = "$server-codes";
