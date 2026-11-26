# @agent-console/wiki-view

A package of wiki presentation components and pure functions (React 19). All data and callbacks are props, and the package knows nothing about the API or storage (no `api-client` import).
Link patterns, front matter keys, rule ids, and the names of operations, kinds, and severities are not in the code. The package draws from the link ranges and statuses the server provides and the display table (`WikiDisplay`) the app provides; a value that is not in the table is shown as its raw text with a neutral tone.

## Installation
Inside the repository, `pnpm install` links the local package. Outside the repository, install the tarball (`pnpm pack:all` → `dist/npm`).

```sh
npm install ./agent-console-wiki-view-0.1.0.tgz
```

The app loads `tokens.css` and `@agent-console/wiki-view/styles.css` once each (colors and spacing use only `--ac-*` tokens).

## Minimal usage
```ts readme
import { linkifySource } from "@agent-console/wiki-view";

const content = "가나 😀 [[다라]] 끝";
// Link range from the server (UTF-16): content.slice(start, end) === "[[다라]]"
const link = { start: 6, end: 12, raw: "[[다라]]", kind: "wikilink", rule_id: "r", label: "다라", status: "ok", resolved: "da" };
const text = linkifySource(content, [link]);
```

`text` is `"가나 😀 [다라](ac-wiki:6) 끝"`. This block must match `test/readme.test.ts`.

## Components
| Component | Purpose |
| --- | --- |
| `PageTree` | The page tree (virtual list, `role="tree"`, folders first, natural number ordering) |
| `PageView` | The content view. Runs `linkifySource` with the server's link ranges, then `MarkdownPreview` (markdown-doc), with a link style per status |
| `OutlinksPanel` | The list of outgoing links (callbacks to jump to the position in the content and to sync highlighting) |
| `PageHistory` / `HistoryDiff` | The history list (operation and author chips) / the comparison (text-editor `TextDiff`) |
| `LinkGraph` / `LinkList` | The link graph (@xyflow/react + elkjs stress, a cheap layered layout when there are many nodes, read-only) / the same information as text |
| `LintTable` | The check table (virtual grid, filtering, sorting) |
| `SearchResults` | Search results (highlighting from the server's `marks`) |
| `NewPageForm` / `MovePageForm` | A new page (template and variables) / rename (with a preview of link fixes) |
| `RuleListEditor` / `SyntaxValueTree` | Order, remove, and add the rules in use / the effective syntax value tree with source badges |
| `AuthorChip` / `OpChip` | The author chip / the history operation chip |

Pure functions: `linkifySource`, `usableLinks`, and `linkMarks` (link ranges → Markdown links and editor decorations), `splitByMarks`, `buildTree`, `graphToFlow`, `createElkGraphLayout`, `nearestNode`, and `edgeGeometry`, `authorLabel` and `resolveDisplay`.

## Link ranges (UTF-16)
`WikiLink.start` and `end` are UTF-16 code unit offsets. Use them as they are in `content.slice(start, end)`; do not convert them to code points.
Replace in descending order of `start` so that earlier offsets do not shift. Ranges that overlap or fall outside the content are dropped. Search `marks` follow the same rule (a surrogate pair is never split).

## Dependencies
contracts (types plus the constants-only entry point), `markdown-doc` (preview, chips, and source badges), `text-editor` (comparison), @xyflow/react + elkjs (the graph), and @tanstack/react-virtual (the virtual list).
It does not import `sdd-view` or `api-client`.

## Development and standalone reuse
- `pnpm build`, `pnpm typecheck`, `pnpm lint`, and `pnpm test` each run on their own inside this folder.
- The public API is only the paths listed in `exports`. Other packages do not import `src/` or `dist/` directly.
- To check that the package still works when copied out of the repository, run `pnpm portability --package @agent-console/wiki-view`.
