# @agent-console/memory-view

Presentation components for shared memory: the scope tree, the entry table (virtual list), the content editor, entry info, the version list and comparison, and the cleanup preview,
plus pure functions (`groupScopes`, `scopeLabel`, `formatAuthor`, and `visibleScopes`).
It knows nothing about the API, storage, `api-client`, `log-view`, or `ui`. All data and callbacks are props, and text comes from `messages`.

- **Scope kinds, scope names, and tool names are not in the code.** It draws only from the list of scope kinds the server provides (`label`, the `id` template, and `context_fields`) and the scope summaries.
  Recognizing a project or a team also relies on the kind's `context_fields` and id template, not on the kind's name (`visibleScopes`). Renaming a kind gives the same result.
- The entry table has 6 columns (pinned, key, author, modified, size, and version) that are not hidden as the width shrinks, and it **adds** the tag column only at a width of 720 or more.
  Even with 10,000 rows, it draws only the visible rows plus 8 rows above and below.
- The content editor uses text-editor as it is. During IME composition it defers saving (Ctrl+S, and `requestSave` on the handle) and saves once when the composition ends.
- An unknown contract vocabulary value (`op` or `author.kind`) is shown as its raw text.

## Installation
Inside the repository, `pnpm install` links the local package. Outside the repository, install the tarball (`pnpm pack:all` → `dist/npm`).

```sh
npm install ./agent-console-memory-view-0.2.0.tgz
```

An app that uses it loads the token CSS (the `--ac-*` variables, `@agent-console/ui/tokens.css`) and this package's `@agent-console/memory-view/styles.css` once each.
The only tokens this package uses are the `var(--ac-…)` references in `styles.css`. The pin icon uses `--ac-icon-pin` when it exists, and a built-in default shape otherwise.

| Dependency | Why | Alternatives |
| --- | --- | --- |
| `@agent-console/text-editor` | Content editing (`TextEditor`, the composition state API) and version comparison (`TextDiff`, which uses `@codemirror/merge` inside). No new editing UI is built | Plug in another editor through the editor slot (`renderEditor`) |
| `@tanstack/react-virtual` | The virtual list for the entry table and the cleanup preview (10,000 rows) | Hand-written windowing |
| `@agent-console/contracts` | Types only, such as `MemoryEntrySummary` (`import type`) | — |

`@codemirror/merge` is not a direct dependency (text-editor already uses it, and this package receives it as `TextDiff`). dependency-cruiser (`memory-view-allowed-deps`) limits this package's internal dependencies to contracts (types) and text-editor.

## Minimal usage
```ts readme
import { groupScopes, scopeLabel, visibleScopes } from "@agent-console/memory-view";
import { sampleKinds, sampleScopes } from "@agent-console/memory-view/testing";

const kinds = sampleKinds();
const scopes = sampleScopes();
const { visible, hidden } = visibleScopes(scopes, kinds, "P1", ["g1"]);
const tree = groupScopes(kinds, visible);
const label = scopeLabel({ kind: "desk", id: "g1" }, kinds[1], { graph_id: () => ({ status: "named", name: "개발팀" }) });
```

When you pick project `P1` (team `g1` is visible), `visible` has 4 scopes and `hidden` has 6 (under the tree: "6 scopes of other projects hidden"),
`tree.groups` groups the kinds in the order the server provided, and `label.text` is `"개발팀"`. This block must match `test/readme.test.ts`.

The drawing components:

```tsx
import "@agent-console/memory-view/styles.css";
import { MemoryScopeTree, MemoryEntryTable, MemoryEntryEditor, MemoryEntryMeta, MemoryVersionList, MemoryVersionDiff, RetentionPreview } from "@agent-console/memory-view";

<MemoryScopeTree kinds={kinds} scopes={visible} selected={scope} onSelect={setScope} resolvers={{ graph_id: resolveGraph }} hiddenCount={hidden.length} onShowHidden={showAll} />;
<MemoryEntryTable entries={entries} hasMore={!!cursor} onLoadMore={next} selectedId={id} onSelect={open} query={q} showScope={scope === null} scopeText={label} />;
<MemoryEntryEditor value={body} onChange={setBody} entryKey={entry.key} contentType={entry.content_type} onSave={save} saveState="dirty" maxBytes={limit} handleRef={editorRef} />;
```

## Messages and language
The default messages are Korean (`src/locales/ko.json`, `defaultMessages`), and an English bundle ships alongside. There is no dependency on i18next. Placeholders are `{name}` and pure functions in this package fill them.
`ko` and `en` have the same keys and placeholders (`test/locales.test.ts` checks this). In the JSON files, dotted keys are spread into a tree; when one key is the prefix of another, its value sits under `_`. `flattenMessageTree` turns a tree back into the dotted keys the components read.
To use English, pass the bundle as `messages` (to the components and to functions such as `scopeLabel`, `formatRelativeTime`, and `orderText`).

```tsx
import en from "@agent-console/memory-view/locales/en";

<MemoryScopeTree kinds={kinds} scopes={scopes} messages={en} locale="en" /* … */ />
```
The Korean bundle is `@agent-console/memory-view/locales/ko`. Both files also export `tree` (the JSON as a tree) for code that takes tree bundles. To change only a few messages, spread and override: `messages={{ ...en, "table.empty": "…" }}`. For a new language, build an object with the same keys. The component sources contain no Korean string literals (the same test checks this).

## Public API
| Name | Role |
| --- | --- |
| `MemoryScopeTree` | The tree of all scopes → kind → scope. A group of unusable scopes (unknown or turned-off kinds), a hidden row, a `⋯` menu, and keyboard navigation |
| `MemoryEntryTable` | The entry table (virtual list, `role="grid"`). Rows of 32/52, 6 pinned columns plus a conditional tag column, roving tabindex, and a next-page request 5 rows before the end |
| `MemoryEntryEditor` | text-editor plus a status line (line and column / bytes and limit / format / save state). Saving is deferred during composition, and blocked when over the limit |
| `MemoryEntryMeta` | The info grid: scope, version, size, hash, creator, last editor, tag input, format, pinned, and archived |
| `MemoryVersionList` | The version list (newest first, with operation chips, author, time, and size change) |
| `MemoryVersionDiff` | Previous/current comparison, side by side or inline, a text description for an operation with no content, and [Revert to this version] |
| `RetentionPreview` | A cleanup plan summary + a virtual table (up to 200 rows) + [Apply now]. The call and the confirmation window belong to the app |
| `groupScopes(kinds, scopes, { locale? })` | Groups by kind (server order, scopes by label in `locale`, default `"en"`), the entry totals, `selfScope`, and separation of unusable scopes |
| `scopeLabel(scope, kind, resolvers)` | The scope label. Resolves names per context field, and marks deleted or unknown kinds |
| `visibleScopes(scopes, kinds, project, graphs)` | Filtering for the project switcher (decided only from `context_fields` and the id template) |
| `formatAuthor(author, options)` | Author display (an agent avatar and name, chips for user, cleanup, and import, and the raw text for an unknown kind) |
| `validateKey`, `languageForContentType`, `formatBytes`, `formatRelativeTime`, `utf8Bytes` | The key character rules, content format → editor language, and size and time formatting |
| `defaultMessages`, `resolveMessages`, `flattenMessageTree` | The Korean text table (the names of the `memory.*` keys with the prefix removed), the merge with custom messages, and tree → dotted keys |
| `@agent-console/memory-view/locales/ko`, `…/locales/en` | The message bundles (`default` = the table, `tree` = the JSON tree) |
| `@agent-console/memory-view/testing` | Sample data (`sampleKinds`, `sampleScopes`, `makeEntries`, `sampleVersions`, `samplePlan`, and `renameKinds`) |

## Development and standalone reuse
- `pnpm build`, `pnpm typecheck`, `pnpm lint`, and `pnpm test` each run on their own inside this folder.
- The public API is only the paths listed in `exports`. Other packages do not import `src/` or `dist/` directly.
- To check that the package still works when copied out of the repository, run `pnpm portability --package @agent-console/memory-view`.
