# @agent-console/sdd-view

A collection of specs (SDD) presentation components: the spec list, the document list, the document editor (editing plus Markdown preview), the task table (virtual list, phase grouping, status menu),
the plan graph (read-only) and its grouped text, the requirement-to-task trace table, gate notices, and pure functions.
All data and callbacks are props, and the package knows nothing about the API, storage, or `api-client`. Status, document kind, phase, and tone names are not in the code; they are server data (`label` and `tone`).
Its only internal dependencies are `@agent-console/contracts` (types only) and `@agent-console/markdown-doc` (the document editor, chips, and source badge moved there, and this package re-exports them under the same names). React 19 is a peer.

## Minimal usage
This block matches `test/readme.test.ts`, and the test actually runs it (`pnpm pkg-lint` checks that they match).

```ts readme
import { groupByStage, planToFlow, statusTone } from "@agent-console/sdd-view";
import { samplePlan, sampleStatuses, sampleTasks } from "@agent-console/sdd-view/testing";

const statuses = sampleStatuses();
const tasks = sampleTasks();
const groups = groupByStage(tasks, (s) => statuses.some((x) => x.id === s && x.done === true));
const chip = statusTone("s-done", statuses);
const flow = planToFlow(samplePlan(), tasks);
```

## Installation and usage
Inside the repository, `pnpm install` links the package. Outside the repository, install the tarball (`pnpm pack:all` → `dist/npm`) (React 19 is required).
The app loads `@agent-console/ui/tokens.css` (the design tokens) and this package's `styles.css` once each (`styles.css` `@import`s markdown-doc's `styles.css`).

```tsx
import "@agent-console/sdd-view/styles.css";
import { TaskTable, DocumentEditor, PlanGraph, TraceMatrix } from "@agent-console/sdd-view";

<TaskTable tasks={view.index.tasks} statuses={view.task_statuses} onStatusChange={(task, status) => patch(task.key, status, task.line_hash)} />
<DocumentEditor document={doc} value={draft} onChange={setDraft} onSave={save} readOnly={!writable} conflict={changedOutside} />
```

## Components
| Component | Purpose |
| --- | --- |
| `SpecList` | The spec list (virtual). Progress, current phase, and document status chips. Column header sorting (`sortColumns`, `sort`, `onSortChange`, `aria-sort`) and the row menu slot (`renderRowMenu`) come in as props |
| `DocumentNav` / `DocumentStateChip` / `ToneChip` | The document list, and status chips (the shared rule for the five tones) |
| `DocumentEditor` (re-exported from markdown-doc) | text-editor plus a react-markdown preview. Read-only, missing file, conflict, and IME composition. The comparison base `compare` (→ [Compare changes], TextDiff), the `externalChange` banner and `onCopyMine` ([Copy my changes]), the controlled `mode` and `onModeChange`, `initialLine` and `handleRef` (`openGoToLine`, `goToLine`). It takes only data and callbacks; the caller handles the clipboard, confirmation dialogs, and shortcut registration |
| `TaskTable` (`TaskStatusMenu`, `TaskFieldChips`, `TaskRunChips`) | The task table (virtual, phase grouping, inline expansion). No syntax, empty state, and line conflict. Row checkbox selection (`selectable`, `selectedKeys`), phase collapse overrides (`collapsedOverrides`), an inline notice under a row (`renderRowNotice`), a row context menu (`rowMenuItems`), and a handle for shortcut handlers (`ref`: `TaskTableHandle`) |
| `PlanGraph` / `PlanBundles` | A read-only @xyflow/react + elkjs graph / the parallel bundles as text. Optional props: `readableZoom` (the minimum zoom on first display), `minZoom` (the lower limit of the fit scale, default 0.4; a large graph goes lower so that all of it fits), and `onlyCritical`. Touching zoom, pan, or fit stops the automatic fit |
| `TraceMatrix` | The requirement, task, run, and verification table (virtual), with filtering of the gaps |
| `GateNotice` / `RulesSourceBadge` (re-exported from markdown-doc) | The gate-blocked notice / the rule value source badge |

Pure functions: `groupByStage`, `flattenTaskRows`, `statusTone`, `codeDisplay`, `toneAttr`, `planToFlow`, `planBundles`, `applyPositions`, `createElkPlanLayout`, `filterTraceRows`, and `gapLabelKey`.
Text comes from the `messages` prop (partial override) and `defaultMessages`. The subpath `./testing` holds sample data (keep it out of the app bundle).

## Messages and language
The default messages are Korean (`src/locales/ko.json`, `defaultMessages`), and an English bundle ships alongside. There is no dependency on i18next. Placeholders are `{name}` and `formatMessage` fills them.
`ko` and `en` have the same keys and placeholders (`test/locales.test.ts` checks this). In the JSON files, dotted keys are spread into a tree; when one key is the prefix of another, its value sits under `_`. `flattenMessageTree` (from `@agent-console/markdown-doc`) turns a tree back into the dotted keys the components read.
To use English, pass the bundle as `messages`:

```tsx
import en from "@agent-console/sdd-view/locales/en";
import mdEn from "@agent-console/markdown-doc/locales/en";

<TaskTable tasks={tasks} statuses={statuses} messages={en} />
<DocumentEditor document={doc} value={draft} onChange={setDraft} messages={mdEn} />
```
`DocumentEditor`, the chips, and `RulesSourceBadge` come from `@agent-console/markdown-doc`, so their `editor.*` and `source.*` messages are in that package's bundle (`@agent-console/markdown-doc/locales/en`).
The Korean bundle is `@agent-console/sdd-view/locales/ko`. Both files also export `tree` (the JSON as a tree) for code that takes tree bundles. To change only a few messages, spread and override: `messages={{ ...en, "specs.empty.title": "…" }}`. For a new language, build an object with the same keys. The component sources contain no Korean string literals (the same test checks this).

## Dependencies (what / why / alternatives)
- `@xyflow/react` — renders the plan graph. Alternative: plain SVG (pan, zoom, and accessibility built by hand).
- `elkjs` — layered layout. Imported dynamically only when first needed; the engine can be swapped with the `engine` prop. Alternative: a per-layer column layout (already present as the fallback on failure).
- `@tanstack/react-virtual` — virtual scrolling for large tables. Alternative: pagination.
- `react-markdown` + `remark-gfm` — the document preview. `@agent-console/markdown-doc` now owns it.
