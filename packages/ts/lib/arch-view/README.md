# @agent-console/arch-view

Presentation components for the observability architecture map. They draw an `ArchitectureView`, whose coordinates, labels, and metrics the server has already filled in, as **zones, cells, edges (polylines), and label chips**.
The package knows nothing about the API, storage, `ui`, `log-view`, or `api-client`. All data and callbacks are props.

- Cell kinds, edge types, and colors are not in the code. Every name is data, and an unknown `tone` or `style` is drawn with a neutral look.
- `value: null` means "–" or "Not collected" everywhere. It never becomes 0 in totals, sorting, or accessible names.
- Below a scale of 0.45 the display switches to a summary (only a number per cell). It includes the [Diagram | List] switch, the legend, the selection info bar, and keyboard navigation.

## Installation
Inside the repository, `pnpm install` links the local package. Outside the repository, install the tarball (`pnpm pack:all` → `dist/npm`).

```sh
npm install ./agent-console-arch-view-0.2.0.tgz
```

An app that uses it loads the token CSS (the `--ac-*` variables, `@agent-console/ui/tokens.css`) and this package's `@agent-console/arch-view/styles.css` once each.
The only tokens this package uses are the `var(--ac-…)` references in `styles.css`.

| Dependency | Why | Alternatives |
| --- | --- | --- |
| `@xyflow/react` | Zoom, pan, and custom nodes (cells and zones). Edges are polylines decided by `points`, so they are drawn directly over a `ViewportPortal` | Hand-written SVG (the fallback) |
| `@agent-console/contracts` | Types only, such as `ArchitectureView` (`import type`) | — |

## Minimal usage
```ts readme
import { checkLayout, edgePath, formatMetric, gridLayout } from "@agent-console/arch-view";
import { defaultProfileView } from "@agent-console/arch-view/testing";

const view = defaultProfileView();
const problems = checkLayout(view);
const rects = gridLayout(view);
const llm = formatMetric({ status: "not_collected", value: null });
const line = edgePath(null, rects["input"], rects["sdk"]);
```

`problems` is `[]` (the default profile's coordinates have no overlaps or crossings), `llm.text` is `"–"` (not collected is not 0), and `line` is two points joining the two cells 6 px outside their borders.
This block must match `test/readme.test.ts`.

The diagram component:

```tsx
import "@agent-console/arch-view/styles.css";
import { ArchitectureDiagram } from "@agent-console/arch-view";

<ArchitectureDiagram
  view={view}                       // ArchitectureView (undefined while loading)
  selection={selection}             // the target currently filtered on {kind, id, group?} | null
  highlight={membership}            // the cells, edges, and groups the selected event hit
  onSelect={setSelection}           // pressing the same target again gives null
  onBlocked={(target, reason) => toast(reason)}  // a not-collected cell or a structural edge: no events to filter by
  onDrill={(cellId, group) => drillInto(cellId, group)}
  messages={{ /* text overrides */ }}
/>;
```

## Public API
| Name | Role |
| --- | --- |
| `ArchitectureDiagram` | The toolbar (zoom, fit, diagram/list, legend) + the canvas + the selection info bar. `scale`, `fitMode`, and `viewMode` work both controlled and uncontrolled |
| `ArchitectureCellList` | The list of cells and edges (the same selection state and callbacks as the diagram) |
| `ArchitectureInfoBar` | A line that spells out the selected or focused target (the full metric values, group chips, and a button for the child architecture map) |
| `ArchitectureLegend` | The legend samples (the same classes as the real cells and edges). The zone samples come from the prop `zoneLegend` (default `defaultZoneLegend`; none for `[]`) |
| `hasBatchim`, `josa`, `withJosa` | Pure functions that pick the Korean particle by final consonant. In a text template, write it as `{to\|으로/로}` (with a final consonant / without one). The default template for an edge's accessible name uses it, and `messages.ariaEdgeFlow` overrides it |
| `gridLayout(view)` | A table of cell rectangles that places cells without coordinates on a grid in declaration order |
| `edgePath(points, from, to)` | Uses `points` as they are when present; otherwise a straight line between the two cell borders (6 px outside) |
| `formatMetric(metric, messages, opts)` | A metric → the cell text, the accessible name, and the spelled-out text. Not collected is "–" |
| `checkLayout(view)` | A list of overlaps and crossings between cell and cell, edge and cell, edge and edge, and chip and chip (a pure function; it can also be used in a settings preview) |
| Fit `auto` (default) | `autoFit`, `AUTO_CONTAIN_MIN`, and the prop `autoContainMin`: if a width fit works, it uses the width; otherwise it fits everything when the whole-fit scale is at or above the threshold (0.55), and below that it fits the width and shows a clipping indicator (a bottom gradient, a "N more cells below ↓" chip, and a scroll indicator). It is recalculated whenever the canvas size changes |
| `fitViewport`, `zoomAround`, `ensureVisible`, `nearestInDirection` | Pure functions for fit, zoom, minimal scrolling, and arrow-key movement |
| `@agent-console/arch-view/testing` | A sample `ArchitectureView` (the default profile's coordinates, with placeholder metric values) |

## Extension points
The `tone`, `style`, `view`, and metric names used in data are open strings. The code knows no names and changes them only through the mapping tables below.
A value accepts **only a token variable name** (`--ac-…`), not a CSS color; any other value (such as `#ff0000`) is drawn with a neutral look.

```tsx
<ArchitectureDiagram
  view={view}
  tones={{ ...defaultTones, mint: "--ac-cat-2" }}                       // tone → cell band and border color
  edgeStyles={{ ...defaultEdgeStyles, slow: { stroke: "--ac-cat-3", dash: "--ac-edge-pattern-3" } }}  // style → line look
  edgeLegend={{ slow: "Slow call" }}                                     // the legend text for the new style
  metricKinds={{ ...defaultMetricKinds, bytes: { kind: "number" } }}    // metric name → display kind
  cellRenderers={{ gauge: ({ cell, defaultBody }) => <>{defaultBody}<Gauge cell={cell} /></> }}  // a cell's view key → its inner drawing
/>
```

## Accessibility
Cells and edge chips are a `button` (`aria-pressed`), and the accessible name is "name, metric part, status part". `Tab` goes through the cells (in declaration order) and then the edges, the arrow keys move to the nearest cell, `Home` and `End` work, `Shift+Enter` opens the child architecture map, `Esc` clears the selection, `+`, `-`, and `0` zoom in, zoom out, and fit, and `Backspace` goes up one level (`onBack`).
State is never conveyed by color alone (hatching, dashes, text, and icons are used too).

## Development and standalone reuse
- `pnpm build`, `pnpm typecheck`, `pnpm lint`, and `pnpm test` each run on their own inside this folder.
- The public API is only the paths listed in `exports`. Other packages do not import `src/` or `dist/` directly.
- To check that the package still works when copied out of the repository, run `pnpm portability --package @agent-console/arch-view`.

## Text and language
The default text is Korean (`src/locales/ko.json`, `defaultMessages`), and an English bundle ships alongside it. There is no dependency such as i18next. Placeholders such as `{n}` and `{title}` are filled by `formatMessage`.
`ko` and `en` have the same keys and placeholders (`test/locales.test.ts` checks this). To use English, pass one bundle as `messages`.

```tsx
import en from "@agent-console/arch-view/locales/en";

<ArchitectureDiagram view={view} selection={selection} onSelect={setSelection} messages={en} />
```
The Korean bundle is `@agent-console/arch-view/locales/ko`. To change only part of a bundle, spread it and override, as in `messages={{ ...en, empty: "…" }}`. For a new language, build an object with the same keys and pass it in.
The particle template (`josa`) such as `{to|으로/로}` is used only in the ko bundle. The component source contains no Korean strings (the same test checks this; only the sample data `testing.ts` is excluded). `checkLayout` takes a new option, `errorsPlaceholder` (the error text used to estimate the chip width).
