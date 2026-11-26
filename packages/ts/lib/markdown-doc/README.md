# @agent-console/markdown-doc

A Markdown document editor (`DocumentEditor`: text-editor + preview + change comparison + banners for conflict, external change, missing file, and read-only + go to line),
a preview (`MarkdownPreview`: react-markdown + GFM, raw HTML not allowed, with link and source hooks), and the small presentational parts the specs and wiki screens share
(the `ToneChip` and `DocumentStateChip` status chips, and the `RulesSourceBadge` value source badge).
All data and callbacks are props, and the package knows nothing about the API, storage, or `api-client`. Status, tone, and source names are not in the code; they are data the caller provides.
Its only internal dependencies are `@agent-console/contracts` (types only) and `@agent-console/text-editor`. React 19 is a peer.

Where the shared parts live: the chips and badge go here, not in `ui`. `sdd-view` does not use `ui` (it does not import it),
and `sdd-view` and `wiki-view` both already depend on this package, so no new dependency edge appears. `sdd-view` re-exports them under the same names.

## Installation
Inside the repository, `pnpm install` links the local package. Outside the repository, install the tarball (`pnpm pack:all` → `dist/npm`) (React 19 is required).
The app loads `@agent-console/ui/tokens.css` (the design tokens) and this package's `styles.css` once each.

## Minimal usage
This block matches `test/readme.test.ts`, and the test actually runs it (`pnpm pkg-lint` checks that they match).

```ts readme
import { formatMessage, resolveMessages, statusTone } from "@agent-console/markdown-doc";

const chip = statusTone("s2", [{ id: "s2", label: "검토", tone: "info" }]);
const text = resolveMessages({ "editor.save": "올리기" });
const line = formatMessage(text["editor.issue.line"], { line: 7 });
```

```tsx
import "@agent-console/markdown-doc/styles.css";
import { DocumentEditor, MarkdownPreview } from "@agent-console/markdown-doc";

<DocumentEditor document={doc} value={draft} onChange={setDraft} onSave={save} compare={{ before: saved }} previewHooks={{ renderLink }} />
<MarkdownPreview source={text} transformSource={linkify} renderLink={(href, children) => <a href={href}>{children}</a>} />
```

## Messages and language
The default messages are Korean (`src/locales/ko.json`, `defaultMessages`), and an English bundle ships alongside. There is no dependency on i18next. Placeholders are `{name}` and `formatMessage` fills them.
`ko` and `en` have the same keys and placeholders (`test/locales.test.ts` checks this). In the JSON files, dotted keys are spread into a tree; when one key is the prefix of another, its value sits under `_`. `flattenMessageTree` turns a tree back into the dotted keys the components read.
To use English, pass the bundle as `messages`:

```tsx
import en from "@agent-console/markdown-doc/locales/en";

<DocumentEditor document={doc} value={draft} onChange={setDraft} messages={en} />
```
The Korean bundle is `@agent-console/markdown-doc/locales/ko`. Both files also export `tree` (the JSON as a tree) for code that takes tree bundles. To change only a few messages, spread and override: `messages={{ ...en, "editor.save": "…" }}`. For a new language, build an object with the same keys. The component sources contain no Korean string literals (the same test checks this).

## Public API
| Name | Purpose |
| --- | --- |
| `DocumentEditor` | Editor plus preview. `mode` and `onModeChange`, `compare` and `defaultCompareOpen`, `conflict`, `externalChange`, `missing`, and `readOnly`, `issues` (`DocumentIssue`), `initialLine` and `handleRef` (`openGoToLine`, `goToLine`), `toolbarExtra`, and `previewHooks` |
| `MarkdownPreview` | `source`, `renderLink(href, children)`, `transformSource(text)`, and `urlTransform(url)` |
| `ToneChip` / `DocumentStateChip` | Status chips (they set only `data-tone`; CSS decides the color) |
| `RulesSourceBadge` | The source badge for rule and syntax values (the `source.<value>` text key, or the raw text if there is none) |
| `toneAttr`, `statusTone`, `NEUTRAL_TONE` | Tone name normalization, and status id → chip value |
| `defaultMessages`, `resolveMessages`, `formatMessage`, `messageOr`, `flattenMessageTree` | The Korean text table (partially overridden through the `messages` prop), and tree → dotted keys |
| `@agent-console/markdown-doc/locales/ko`, `…/locales/en` | The message bundles (`default` = the table, `tree` = the JSON tree) |

## Dependencies (what / why / alternatives)
- `@agent-console/text-editor` — the editor and comparison (CodeMirror 6). Alternative: wire up CodeMirror directly.
- `react-markdown` + `remark-gfm` — the preview (raw HTML not allowed). Alternative: marked plus your own sanitizing.

## Development and standalone reuse
- `pnpm build`, `pnpm typecheck`, `pnpm lint`, and `pnpm test` each run on their own inside this folder.
- The public API is only the paths listed in `exports` (`.` and `./styles.css`). Other packages do not import `src/` or `dist/` directly.
- To check that the package still works when copied out of the repository, run `pnpm portability --package markdown-doc`.
