# @agent-console/log-view

A log analysis **presentation** package: the event table (virtual scrolling), the filter bar, category chips, event detail, the session list, the playback bar, the lane ribbon,
the handoff matrix, the dashboard grid (a widget registry plus a chart adapter), the widget editor, and the template picker. All data and callbacks are props.
The app handles server calls, routing, and storage. Source, category, widget, dimension, and metric names are not in the code; everything is drawn from the data it receives.

Its only internal dependency is `@agent-console/contracts` (types only). It does not import the shared UI (`ui`), the delegation flow drawing (`trace-view`), the schema form (`schema-form`),
or the JSON view (`text-editor`); it takes them through slot props (`renderCodeBlock`, `renderLinks`, `renderOptionsForm`, `filterBar`, `preview`).
Without a slot, it draws plain HTML or hides that area. The app injects the color slot hash as `slotFor(key) => 0..7` (the hash is not copied).

## Installation
Inside the repository, `pnpm install` links the local package. Outside the repository, install the tarball (`pnpm pack:all` → `dist/npm`).

```sh
npm install ./agent-console-log-view-0.1.0.tgz
```

## Minimal usage
This block matches `test/readme.test.ts`, and the test actually runs it (`pnpm pkg-lint` checks that they match).

```ts readme
import { isErrorEvent, sortEvents, splitSearchParams, toTaxonomyView } from "@agent-console/log-view";

// An error is decided only by the taxonomy entries with tone="danger" (no name comparison).
const taxonomy = toTaxonomyView({ categories: { "x-fail": { tone: "danger" } } });
const failing = isErrorEvent({ category: "x-fail" }, taxonomy);
// Playback order is ascending by (time, seq).
const order = sortEvents([{ seq: 2, time: 5 }, { seq: 1, time: 9 }]).map((e) => e.seq);
// Screen-only URL parameters (through, lane, view, range, tab) are left out of the server filter.
const { filter, screen } = splitSearchParams("q=abc&through=7");
```

`failing` is `true`, `order` is `[2, 1]`, `filter` is `{ q: "abc" }`, and `screen` is `{ through: ["7"] }`.

## Text and language
The default text is Korean (`src/locales/ko.json`), and an English bundle ships alongside it. There is no dependency such as i18next. Placeholders are `{name}`, filled by `fmt()`.
The bundle is split into `messages` (the components' `messages` prop) and `builtinWidgets` (the titles and descriptions of the four built-in widgets). `ko` and `en` have the same keys and placeholders (`test/locales.test.ts` checks this).

```tsx
import en from "@agent-console/log-view/locales/en";
import { createBuiltinWidgets, createWidgetRegistry, DashboardGrid } from "@agent-console/log-view";

const registry = createWidgetRegistry(createBuiltinWidgets(en.builtinWidgets));
<DashboardGrid registry={registry} messages={en.messages} /* … */ />;
```
The Korean bundle is `@agent-console/log-view/locales/ko` (`defaultLogViewMessages` and `builtinWidgets` stay Korean). To change only part of a bundle, override it as in `messages={{ ...en.messages, empty: "…" }}` (`mergeMessages` also merges nested keys). For a new language, build an object with the same keys (the `LogViewLocale` type) and pass it in.
The component source contains no Korean strings (the same test checks this). The default units of `formatDurationMs` also come from the ko bundle. Data the server provides, such as category and column names, is not translated.

## Styles
```ts
import "@agent-console/ui/tokens.css";
import "@agent-console/log-view/styles.css";
```
If the `--ac-log-*` and `--ac-dash-*` tokens (tokens.md 5.9) are defined, they are used; otherwise the defaults in `styles.css` apply.

## Public API summary
| Area | Names |
| --- | --- |
| Components | `LogEventTable` `LogFilterBar` `CategoryChips` `LogEventDetail` `SessionList` `PlaybackBar` `LaneRibbon` `HandoffMatrixView` `DashboardGrid` `WidgetEditor` `TemplatePicker` `ColorSlotPicker` `UnknownWidget` `AggregateTable` |
| Appearance options | `savedPlacement` on `LogFilterBar` (`menu` by default: favorite filters sit in the bottom section of the [+ Filter] menu / `button`: a [★ ▾] button), `settingsPlacement` on `PlaybackBar` (`popover` by default: speed and gap skipping are inside [Playback settings ▾] / `inline`), and `maxInline` on `CategoryChips` (selected chips stay visible even when collapsed) |
| Empty table | Turning on `emptyBelowHeader` on `LogEventTable` draws the table header even with 0 rows and places the `renderEmpty` message under the header |
| Imperative API | `LogEventTable` and `LogEventDetail` expose `LogEventTableHandle` (`scrollToUid`, `focus`) and `LogEventDetailHandle` (`selectTabAt`, `focusTab`, `visibleTabs`) through `ref`. With `onActivate` (Enter in the table), `activeTab` and `onActiveTabChange` (the detail), and `onActiveChange` (`SessionList`), the app does not read or click the DOM |
| Widget registry | `WidgetDescriptor` `createWidgetRegistry` `builtinWidgets` (metric, bar, line, table) `validateQuery` |
| Playback | `sortEvents` `visibleThrough` `indexOfSeq` `seqAtIndex` `usePlayback` (inject a fake `clock`) `playbackDelay` `nextSpeed` `clipTraceAt` |
| Filter and URL | `reservedParams` `splitSearchParams` `buildFilterQuery` `buildScreenSearch` `findReservedConflicts` `createLocalStorageSavedFilters` |
| Taxonomy | `toTaxonomyView` `isErrorEvent` (the decision lives in one place) `isHiddenEvent` `colorFor` `orderCategories` `groupByMessage` |
| Dashboard layout | `layoutFlow` `moveWidget` `resizeWidget` `updateWidget` `removeWidget` `duplicateWidget` `preserveUnknown` `preserveUnknownDashboards` |
| Formatting | `defaultFormatters` `formatRelativeTime` `formatDurationMs` `formatTokensShort` (the app can override them through the `formatters` prop) |

- To add a widget kind, build a `WidgetDescriptor` and pass it to `createWidgetRegistry(builtinWidgets, mine)`. The list has no `switch`, and a `kind` that is not in the registry is drawn as `UnknownWidget` (its settings are preserved).
- Charts use recharts only inside the `charts/` adapter and are loaded lazily. If loading fails, the widget falls back to a table. Recharts types never appear in the public API.
- Formatting functions: the repository's existing formatters (`apps/web/src/lib/format.ts` and `features/runs/runsLib.ts`) live inside the app, so the package cannot borrow them; it ships its own built-in implementation of the same rules. If the app already has formatters, inject them through the `formatters` prop.

## New dependencies
| What | Version and license | Why | Alternatives |
| --- | --- | --- | --- |
| `@tanstack/react-virtual` | 3.14.x, MIT, peer `react ^16.8 \|\| ... \|\| ^19` | Virtual scrolling for the event table, the session table, and related lists (headless) | react-window (MIT) |
| `recharts` | 3.10.x, MIT, peers `react`, `react-dom`, and `react-is` `^16.8 \|\| ... \|\| ^19` | Line charts (declarative React). Used only inside the `charts/` adapter and loaded lazily | ECharts (Apache-2.0, heavy), uPlot (MIT, imperative) |
| `react-is` | 19.x, MIT | A peer dependency of recharts | — |

## Testing
`pnpm test` — renders with arbitrary taxonomies (0 entries, 100-character names, unknown colors), arbitrary widget descriptors, and arbitrary filter fields, and runs playback on a fake clock.
