# @agent-console/i18n

i18next setup for web UIs: `{name}` placeholders, a language fallback chain, language resolution, a format registry (lists, numbers, dates, relative time, Korean particles), React hooks, and Vitest helpers.

It does not know about any server. A message source is a function you pass in (`fetchCatalog`), so it works with an app bundle alone. The server's catalog shape (`MessageCatalog`, `I18nInfo`) comes from `@agent-console/contracts` as types only.

## Install
Inside the repository, `pnpm install` links the local package. Outside it, install the tarball (`pnpm pack:all` -> `dist/npm`).

```sh
npm install ./agent-console-i18n-0.1.0.tgz
```

Dependencies (exact versions, both MIT): `i18next` 27.2.9 (bundles, fallback chain, plural forms, formats; alternatives: FormatJS `intl-messageformat`, Lingui) and `react-i18next` 18.0.3 (React re-rendering and hooks; alternative: your own context). `react` is a peer dependency.

## Minimal use
```ts readme
import { createI18n, resolveLanguage } from "@agent-console/i18n";

const language = resolveLanguage({ browser: ["ko-KR"], available: ["en", "ko"] });
const i18n = createI18n({
  language,
  bundled: {
    en: { app: { greeting: "Open {label}" } },
    ko: { app: { greeting: "{label, particle.object} 엽니다" } },
  },
});
const text = i18n.t("greeting", { ns: "app", replace: { label: "팀" } });
```

`text` is `"팀을 엽니다"`. This block must match `test/readme.test.ts`.

## Messages
- A bundle is `language -> namespace -> nested object`; leaves are strings. Placeholders are `{name}`. Plurals use i18next suffixes (`issues_one`, `issues_other`) with `count`. A format is written `{value, name}`.
- Missing keys fall back along `language -> primary language (en-US -> en) -> fallbackLanguage -> en`.
- The server catalog (`applyServerCatalog`) is merged over the app bundle: its `ns` entries override the same keys, `text` (original string -> translation) and `codes` (issue code -> template) are read by `createServerText`/`useServerText`.

Server strings made of values ("20 seconds ...") come with their sentence templates: `render(field, templates)` translates every template and fills the values, or returns `field` unchanged when any template has no translation. Tell the lookups the server's original-string language with `createI18n({ sourceLanguage })` or `setLanguage(i18n, code, { sourceLanguage })`: `text` and `render` then stop at that language instead of reading translations of other languages over the original.

## Language
```ts
resolveLanguage({ preference, browser: navigator.languages, available, serverDefault }); // saved -> browser -> server default -> "en"
await setLanguage(i18n, "ko", { fetchCatalog, timeoutMs: 5000 }); // app bundle, then server catalog, then one language switch
```
`setLanguage` never throws for a server failure: the app bundle still applies and the result says `server: "failed"` (or `"missing"`, `"skipped"`, `"loaded"`).

## React
```tsx
<I18nProvider i18n={i18n}>
  <App />
</I18nProvider>

const t = useT("app");                          // t("greeting", { label, count })
const messages = useLibMessages("graph-editor", defaultMessages); // pass to a library component's `messages` prop
const { text, issue, render } = useServerText(); // text("Original server string"), issue(code, details, fallback), render(value, parts)
```
`useLibMessages` overlays the current language on your defaults and leaves `{name}` for the library to fill.

## Formats
`defaultFormatters` registers: `time`, `datetime`, `datetime-full`, `date`, `time-local`, `relative`, `duration`, `number`, `number-compact`, `percent`, `bytes`, `currency`, `list`, and Korean `particle.object|subject|topic|and|direction`. Each also has a `.only` form that prints just the particle, for values inside quotes: `‘{label}’{label, particle.object.only}`. The particle table is data (`koreanParticles`); add or replace formats with `createI18n({ formatters })`.

## Tests
`@agent-console/i18n/testing` exports `createTestI18n` (Korean by default, missing keys throw), `throwOnMissing`, and `assertCatalogsMatch(ko, en)` (same keys and placeholders; English must not use `particle.*`). `compareCatalogs` returns the differences as data.

## Development
- `pnpm build` · `pnpm typecheck` · `pnpm lint` · `pnpm test` run inside this folder on their own.
- The public API is only the paths in `exports`. Other packages do not import `src/` or `dist/`.
- Check that it works outside the repository with `pnpm portability --package @agent-console/i18n`.
