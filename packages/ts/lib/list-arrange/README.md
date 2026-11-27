# @agent-console/list-arrange

A set of pure functions that group, sort, and divide a list into folders. It does not depend on React, the DOM, or storage.
The grouping criteria (`GroupByDef`) and the sort (`SortDef`) are passed in by the caller as data; this package knows no field names or screen kinds.

## Installation
Inside the repository, `pnpm install` links the local package. Outside the repository, install the tarball (`pnpm pack:all` → `dist/npm`).

```sh
npm install ./agent-console-list-arrange-0.1.0.tgz
```

## Minimal usage
```ts readme
import { byText, folderOf, groupItems, sortItems, withFolder, type GroupByDef } from "@agent-console/list-arrange";

interface Doc { name: string; attributes?: Record<string, unknown> }
const byFolder: GroupByDef<Doc> = { id: "folder", titleKey: "group.folder", tree: true, read: (d) => [folderOf(d.attributes) ?? ""] };
const docs: Doc[] = [{ name: "나", attributes: withFolder({}, "개발/백엔드") }, { name: "가" }];
const groups = groupItems(sortItems(docs, byText((d) => d.name)), byFolder);
const summary = groups.map((g) => `${g.key}:${g.count}`);
```

`summary` is `["개발:0", "개발/백엔드:1", "\u0000none:1"]` (the intermediate folder `개발` has no direct items; items with no value go to the "None" group at the bottom, `NONE_KEY`). This block must match `test/readme.test.ts`.

## Public API
| Name | Purpose |
| --- | --- |
| `groupItems(items, def, options?)` | Groups by a `GroupByDef`. Supports `multi` (an item appears in several groups), `tree` (`/` hierarchy), and empty values (a "None" group at the bottom). Returns a flat `GroupNode[]` |
| `visibleGroups(nodes, collapsed)` · `revealGroup` · `groupKeysOf` · `hasNamedGroups` · `uniqueCount` | Collapse handling, flat-list detection, and de-duplicated counts |
| `sortItems(items, sortDef)` · `byText` · `byNumber` · `textCompare` | Stable sort. Pass the display language as `locale` (default `DEFAULT_LOCALE`, `"en"`, so results never depend on the host locale) |
| `resolveGroupBy` · `checkUsable` · `usableUnlessAllDistinct` | Whether a criterion is usable (for example, it is not when every value is different) |
| `resolveSort` · `availableSorts` | Only the sorts that can be used |
| `folderOf(attributes)` · `withFolder(attributes, folder)` | The folder is `attributes.ui.folder` (a string with a `/` hierarchy). Other attributes are preserved |
| `buildFolderTree` · `flattenFolderTree` | A name-ordered tree built from folder paths |
| `loadViewState` · `saveViewState` · `loadCollapsed` · `saveCollapsed` | Store the view and collapsed state in an injected `KeyValueStorage` (usually `localStorage`). A failure falls back to the default |

## Development and standalone reuse
- `pnpm build`, `pnpm typecheck`, `pnpm lint`, and `pnpm test` each run on their own inside this folder.
- The public API is only the paths listed in `exports`. Other packages do not import `src/` or `dist/` directly.
- To check that the package still works when copied out of the repository, run `pnpm portability --package @agent-console/list-arrange`.
- The rendering side is `ListPane groups`, `GroupHeader`, and `ListViewMenu` in `@agent-console/ui`. The two packages do not import each other; the app connects them.
