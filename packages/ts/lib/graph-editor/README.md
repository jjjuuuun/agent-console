# @agent-console/graph-editor

A descriptor-driven graph editor (React component). Node types, edge kinds, and ports are drawn only from data the server provides (descriptors),
so this package does not change when a new node type appears. It includes a read-only mode for run views and a node status overlay.

- Add nodes (double-click a palette item, focus it and press Enter, or drag), delete (with a 5-second undo toast), connect, move, duplicate
- Groups and undo/redo (100 steps) are out of scope for now (unknown fields of the graph such as `groups` are preserved as they are).
- It includes the team composition mode (see "Team composition mode" below): a definition palette, entry/answer/ask shortcuts, edge kind picking, a resource view, and applying issue suggestions.
- No React Flow types appear in the public API. It depends on no other TS package and uses only the types of `@agent-console/contracts`.

## Minimal usage
This block is the same as `test/readme.test.ts`, and the test actually runs it (`pnpm pkg-lint` checks that they match).

```ts readme
import { categoryColorSlot, categoryColorVar } from "@agent-console/graph-editor";

// Node category string -> category color slot. The same string always gets the same color.
const slot = categoryColorSlot("review");
const cssVar = categoryColorVar("review");
```

## Install
Inside the repository, `pnpm install` links it. Outside it, install the tarball (`pnpm pack:all` → `dist/npm`): `npm install ./agent-console-<name>-<version>.tgz`
`react`/`react-dom` (^19) are peer dependencies. The app loads `tokens.css` from `@agent-console/ui` (colors, fonts, the `[data-status]` rules, `.ac-ellipsis`, and so on) and this package's `styles.css`, once each.

```ts
import "@agent-console/ui/tokens.css";
import "@agent-console/graph-editor/styles.css";
```

## Minimal usage example
```tsx
import { GraphEditor } from "@agent-console/graph-editor";
import type { Graph, NodeTypeDescriptor, EdgeTypeDescriptor } from "@agent-console/contracts";

function Editor({ graph, nodeTypes, edgeTypes, setGraph }: {
  graph: Graph; nodeTypes: NodeTypeDescriptor[]; edgeTypes: EdgeTypeDescriptor[]; setGraph(g: Graph): void;
}) {
  return (
    <div style={{ height: 600 }}>
      <GraphEditor
        graph={graph}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onChange={(next, meta) => setGraph(next)}           // meta.reason: add-node | remove | connect | move | ...
        resolvePorts={(typeId, config) => api.resolvePorts(typeId, config)} // called only for dynamic-port types
        renderConfigPanel={(ctx) => <MyForm node={ctx.node} onChange={ctx.onChangeNode} />}
      />
    </div>
  );
}
```
Run view: `<GraphEditor readOnly graph=… nodeTypes=… edgeTypes=… nodeStates={{ n1: { status: "running", summary: "00:03" } }} />`.

## Props summary
| prop | Description |
| --- | --- |
| `graph` | Controlled graph. Fields the editor does not know pass through `onChange` unchanged |
| `nodeTypes`, `edgeTypes` | Descriptor arrays (the only source of the palette, shapes, ports, and edge kinds) |
| `nodeStates`, `edgeStates` | Status overlay. A status only sets the `data-status` attribute (styling lives in tokens.css). Labels come from `messages.statusLabels` |
| `resolvePorts(typeId, config)` | Port calculation for `dynamic_ports` types. 300ms debounce, a (type + config) cache, and only the last request's response is accepted (`PortResolver`) |
| `onChange(next, {reason, previous})` | The single exit for every edit. A drag fires once, on drop |
| `renderConfigPanel(ctx)` | Slot for the right-hand panel (when something is selected). The app fills in the settings form |
| `readOnly` | No palette, delete, connect, or move. Selection, panning, zoom, and the panel slot still work |
| `issues` | The contract `Issue[]` as is. It only draws the node badge (error ✕, warning ▲ + count, with the accessible name "N validation errors, M warnings") and the invalid edge style |
| `focusRequest` | `{ nodeId, token }`. Each time the token changes, that node is selected and fitted into view (for jumping from an issue row click). Pressing the same node again works if only the token (a counter, for example) changes; the same token is ignored |
| `defaultEdgeKind` | The edge kind of a new connection. If absent, `edgeTypes[0]` (with two or more, a picker with the first item preselected) |
| `canvasActions` | Slot for the toolbar at the top left of the canvas (a button like the app's [+ Add ▾]). Not drawn when read-only |
| `showMinimap`, `onShowMinimapChange` | Minimap (140x96, bottom right). Passing `onShowMinimapChange` adds a toggle icon at the bottom right (controlled; the app decides the default on or off) |
| `paletteOverlay`, `paletteOpen`, `onPaletteClose` | Overlay palette for narrow screens: it takes no canvas width and floats above only while `paletteOpen`. Esc calls `onPaletteClose` |
| `locale` | Locale (BCP 47, normally the display language) for palette sorting and search; defaults to `"en"` (`DEFAULT_PALETTE_LOCALE`) |
| `categoryLabel` | `(category) => string` that renames palette groups for display (for example, translating a server category). Grouping and the group color still use the original category, so they do not change with the language |
| `idFactory`, `snapToGrid`, `showPalette`, `palette`, `undoWindowMs`, `messages` | Other settings and text |

Connect from anywhere on a node: selecting a node shows an edge band, and dragging from the band (or a port handle) and dropping on the other node's body connects them. Ports are chosen by `inferKindPorts` (a pure function) in the order `default_ports` -> the first compatible port; when several kinds are candidates, you choose in the picker's port column (`EdgeKindCandidateInfo.portsText`).

`GraphEditorHandle.addNodeAtCenter(typeId, definition?)`: places a node at the **center of the visible area** with the same selection, auto-connect, and `onChange` as the palette [Add] (if it overlaps, it moves diagonally by grid steps, `centerFreePosition`) and returns the new node id.

Lower-level public components and pure functions: `NodeCard`, `NodePalette`, `EdgeKindDialog`, `categoryColorSlot`, `measureNodeSize`, `addNode/removeSelection/duplicateNodes/moveNodes/checkConnection/decideEdgeKind`, `PortResolver`.

**Division of roles:** the issue panel (the list and the jump on row click) is the app's job, while the `issues` prop handles the node and edge display. On a row click, the app requests selection and a jump with `focusRequest={{ nodeId, token: ++n }}`.
The canvas shows only errors (✕) and warnings (▲). Other severities such as info are not shown on the canvas; showing them in lists and panels is the app's job.

## Team composition mode
The editor **does not know node type ids or edge kind ids.** Everything below is decided only from descriptor properties (the tests use descriptors with arbitrary names from `src/testing.ts`).

| Feature | Property it relies on |
| --- | --- |
| Palette "Nodes made from definitions" | Node type `binds{kind,field}` × `definitionLists[binds.kind]`. Adding sets `config[binds.field] = definition id` and the label = the definition name |
| Palette "Basic nodes" | Types without `binds`. Types with `ui_hints.hidden` appear nowhere (they are still drawn if already in the graph) |
| Chip card | `ui_hints.shape` (`chip`/`card`) first, otherwise `executable === false` |
| Kind candidates on connect | `connects.source/target` × node type `role` (`candidateEdgeKinds`). 0 candidates = reject, 1 = connect right away, 2 or more = picker (preselected = the kind chosen last → `defaultEdgeKind` → the first candidate) |
| Cycle rejection | Only when the new kind's `scheduling` is `flow` (the default), checked along existing `flow` edges only. `none/entry/exit` are excluded |
| Entry / answer / ask toggles | The kinds are those with `scheduling = entry` / `exit` / `interaction`. The user node is found by the counterpart role in that kind's `connects`. The port is `default_ports`, or else the first port in the node type's port order |
| Status badge | The same properties (entry = arrival of entry, answer = departure of exit, ask = departure of interaction) |
| Edge kind secondary badge | Computed from `scheduling`/`invocation`/`interaction` (`edgeKindBadge`) |
| Issue suggestions | `Issue.suggestions[].patch` is applied as is (`applyGraphPatch`). Issue codes are not interpreted |
| Dynamic ports (ports decided by the user node) | `dynamic_ports` + `resolvePorts` (same as Phase 1) |

Additional props: `definitionLists`, `definitionKindTitles`, `mode` (`edit`|`readonly-run`), `showResources`/`onShowResourcesChange`, `onOpenResources`, `teamShared`, `onRoleToggle`, `onApplySuggestion`, `onConnectRejected`, `waitingNodes`, `edgeOrder`, `edgeCounts`, `nodeBadgesOverride`, `portLabels` (`auto`|`always`), `nowMs`, `ref`, `palette.onCreateDefinition`.

```tsx
const ref = useRef<GraphEditorHandle>(null);
<GraphEditor ref={ref} graph={g} nodeTypes={nt} edgeTypes={et}
  definitionLists={{ [binds_kind]: [{ id: "a1", name: "PL", usageCount: 2 }] }}
  defaultEdgeKind={settings.editor.default_edge_kind}
  onChange={(next, meta) => setDraft(next)}        // meta.reason: ... | 'role-toggle' | 'apply-suggestion'
  onConnectRejected={(info) => toast(info.reason)}   // when given, the app writes the message instead of the built-in toast
  renderConfigPanel={(ctx) => (
    <RoleToggleRow info={ctx.roleToggles!.entry} label="Entry" onToggle={(on, opt) => ctx.onToggleRole?.("entry", on, opt)} />
  )} />;
// Issue list: <IssueSuggestionButtons issue={issue} onApply={(i, s) => ref.current?.applySuggestion(i, s)} />
```
- `GraphEditorHandle` (ref): `getRoleToggleInfo(nodeId)`, `toggleRole(nodeId, toggle, on, options?)`, `applySuggestion(issue, suggestion)`, `canHaveResources(nodeId)`. When read-only, none of them changes anything and they return `false`.
- Pure functions (usable without UI): `candidateEdgeKinds`, `deriveNodeBadges`, `getRoleToggleInfo`, `applyRoleToggle`, `applyGraphPatch`, `canHaveResources`, `deriveResourceChips`, `buildTeamPalette`, `checkConnection(g, c, portsOf?, {edgeTypes, kind}?)`, `decideEdgeKind(candidate ids[], default?)`.
- Sub-components: `TeamPalette`, `PaletteItem`, `RoleToggleRow`, `ResourceChips`, `IssueSuggestionButtons`, `TeamSharedBar`, `EdgeKindDialog` (candidates + line preview + number keys).
- Resource view: when turned off, it hides `executable=false` nodes and the edges that end at them, and shows a row of resource chips (an icon per type + a count) on the destination card. Shortcut `V`. A checkbox at the bottom center of the canvas (only when resource types exist).
- Known limits: edge label chips keep the Phase 1 rule (shown only when selected, invalid, or when there is a badge or chip). Zoom LOD and placing the edge kind popover at the drop point do not exist yet (it is a modal dialog).

### Declarative badges and chips
It interprets `ui_hints.badges` / `ui_hints.chips` = `[{label_key?, label?, when?}]` on node and edge type descriptors (format and condition vocabulary: design.md "Declarative badges and chips").
Conditions: `config_path` (exists) + `equals`/`not_equals`/`in`/`exists`, and `incoming_scheduling`/`outgoing_scheduling` for nodes only. An object = AND, an array = OR. Text order: `messages.hintLabels[label_key]` → `label` → the key. Pure functions: `declaredLabels`, `evaluateWhen`, `evaluateCondition`.
- When there are several toggle candidates (edge kind × counterpart user node), the editor does not pick the first one: the toolbar opens a choice menu, and without an option `applyRoleToggle` returns with `reason: "ambiguous"` and no change (`toggleChoices(info)` gives the list of combinations).
  - Candidate menu keyboard: on open, focus goes to the first item; ↑↓ and Home/End move; Enter/Space selects (items are buttons); Escape closes and returns focus to the toggle button. It closes automatically when the selected node changes.
- `applySuggestion` calls `onApplySuggestion` only after it was actually applied (when the graph changed).
- Port labels `auto`: all port labels are shown while a connection is being dragged.

## Display rules
- Icon/color: if the descriptor has `ui_hints.icon` (1-2 characters) and `color` (a safe CSS color), they are used; if absent or unresolvable, a hash of the category string (`--ac-cat-1..8`) + the first letter of the title.
- Unknown node types are drawn too (neutral color, dotted danger border, ports restored from the edges). An edge whose port disappeared is not deleted but shown as invalid (dotted + "!").
- Connect: self-connections and flow cycles (`scheduling = flow`) are rejected with a guidance toast, and if a connection with the same (port, kind) already exists, the existing edge is selected.
- The arrowhead ends 6px outside the target node's boundary. Long text uses `.ac-clamp-2`/`.ac-ellipsis` (tokens.css) + the full value in `title`.
- Shortcuts: `Delete`/`Backspace` delete, `Ctrl/⌘+D` duplicate, Shift/Ctrl+click multi-select, arrow keys move (canvas library default).

## Dependencies (what / why / alternatives)
| Dependency | Why | Alternatives |
| --- | --- | --- |
| `@xyflow/react` ^12.12 (MIT) | Node/edge canvas with panning, zoom, handle connections, minimap, and accessibility built in. Kept inside this package only (`components/flow.tsx`, `GraphEditor.tsx`) | A hand-written SVG canvas (costly), Rete.js, Cytoscape.js (unsuited to node UIs) |
| `elkjs` ~0.12.0 (**EPL-2.0 chosen** from `EPL-2.0 OR GPL-3.0-or-later`, decision E-5) | Auto layout [Arrange ▾]: port side constraints in layered layout, four directions, crossing minimization, cycle handling. Used only through dynamic import + a Web Worker, and no types leave `layout/elkEngine.ts`. It is bundled unmodified; if we ever ship a modified source, the license needs another look | `dagre` (no port side support), a custom implementation (quality and maintenance cost), `libavoid-js` (cannot lay out, LGPL, WASM) |
| `react`, `react-dom` ^19 (peer + dev) | Components | — |
| `@testing-library/react` (dev) | Component tests | — |

## Test
`pnpm test` (package folder or root, Vitest, happy-dom). `src/logic/*` has unit tests of pure logic that run without UI, and `GraphEditor.test.tsx` tests rendering and editing with three arbitrarily named descriptors plus an unknown type.
happy-dom has no layout, so node sizes measure as 0; drag moves and handle connection gestures are verified by unit tests (pure functions) and checked in browser E2E (Playwright).

## Placement and display notes
- A node added without a position is placed to the right of the selected node (or the rightmost node if none), and below if it overlaps (`nextFreePosition(g, grid, anchorId)`).
- Edge label chips are shown only on selected or invalid edges (to avoid overlap at narrow spacing). The minimap uses the `--ac-*` tokens.

## Edge shape and path editing

Selecting an edge shows control points on the canvas (hidden when read-only or below zoom 0.5). One operation = one `onChange` with `meta.reason === "layout"`.
`layout` is display data unrelated to run and version hashes, so saving it does not create a new version.

| Operation | How |
| --- | --- |
| Create a waypoint | Drag the midpoint `◇` (3px threshold) / double-click the line / in path edit mode, Enter·Space·W on the midpoint |
| Move a waypoint | Drag `■` (grid snap, Alt turns it off, Shift locks the axis) / ←↑↓→ 8px (Shift 32, Alt 1) / the x·y inputs in the edge panel |
| Delete a waypoint | Double-click / Delete·Backspace / dropping it in line with its neighbors (6px on screen) deletes it automatically |
| Move a label | Drag the chip to move along the path (`label_t`, in steps of 0.05); with Shift, a free position (`label_offset`); double-click resets |
| Reset shape / path | `S`·`Shift+S` (registry order; after the last comes inherit) / `X` |
| Path edit mode | `Enter` on an edge -> Tab visits waypoints, midpoints, and the label chip in order -> `Esc` ends. Results are announced through `aria-live` |

The "Shape and path" section of the edge panel is drawn by passing on `ctx.edgeLayout`, which `renderConfigPanel` receives. The shape list comes from the `edgeShapes` registry,
and inputs whose `supportsRadius`·`supportsBend`·`supportsWaypoints` is false are hidden.

```tsx
<GraphEditor
  graph={graph}
  nodeTypes={nodeTypes}
  edgeTypes={edgeTypes}
  onChange={(next, meta) => save(next, meta.reason)}
  renderConfigPanel={(ctx) => (ctx.edgeLayout ? <EdgeLayoutPanel {...ctx.edgeLayout} /> : null)}
/>
```

`EdgeLayoutPanel` and `EdgeWaypointLayer` are presentational components that do not depend on React Flow, and the pure functions that edit `layout` (`patchEdgeLayout`, `normalizeEdgeLayout`,
`cycleShape`, `insertWaypoint`, `isRedundantWaypoint`, and so on) live in `logic/edgeLayoutOps.ts`. Save normalization: key order `shape, radius, bend, waypoints, label_t, label_offset`,
empty values are deleted along with their key, coordinates and radius use 1 decimal place (label position 2, since it moves in steps of 0.05), and unknown keys pass through. Change the text through `messages` (`waypoint*`, `edgeLayout*`).

## Node placement

Selecting a node lets you change its direction and port sides. One operation = one `onChange` (`reason === "layout"`).

- `R` / `Shift+R`: cycle the direction (the vocabulary is the `directions` props table, by default lr → tb → rl → bt → inherit). The toolbar has the same button.
- Holding a handle for 400ms, or dragging it with `Alt` held, enters move mode, and dropping on the nearest side saves that port's side (`Esc` cancels). Off when read-only.
- `Ctrl+Z` / `Ctrl+Shift+Z` (`Ctrl+Y`): undoes only layout changes (`layout`·`move`·`auto-layout`), 30 steps. If another edit comes in between and the graph differs, the stack is cleared.
- When two nodes move together, the waypoints of the edge between them move by the same displacement (if only one moves, they stay).
- Node direction `auto`: if `auto` is used as the direction value (the first valid layer among node, graph, settings, and hint), the side of every port without a per-port setting is chosen toward the connected counterpart node. It is a derived value and is not saved (only the string `"auto"` is saved), and it is refreshed only on drop and connection change. The `R` cycle goes direction table → auto → inherit.
- Handle order on the same side: handles on the top and bottom sides (and on left and right sides mixing inputs and outputs) line up in the order of the counterpart node's horizontal (vertical) position, so input and output lines do not cross. A port with no counterpart stays in place. The default setup without layout is unchanged.
- Multi-select: selecting two or more edges only gives `ctx.multiLayout` (= `<MultiLayoutPanel>` props) for a bulk [Shape ▾] and [Reset path] (with a confirm step); selecting two or more nodes only gives [Direction]. It arrives as `panels.multi` in `onLayoutPanelsChange`. One operation = one `onChange` (reason `layout`).
- Edge context menu: right-click, or select and press `Shift+F10`/the ContextMenu key. Shape (the registry list), edit path, reset path, delete. If you open it on one of several selected edges, it applies to the whole selection, and [Reset path] goes through a confirm step. Arrow keys, `Home`/`End`, and `Esc` (closing returns focus to the edge).
- Panels: draw `ctx.nodeLayout` / `ctx.edgeLayout` of `renderConfigPanel` with `<NodeLayoutPanel>` / `<EdgeLayoutPanel>`, or, if the app uses its own panel, receive the selected item's values through `onLayoutPanelsChange(panels)` and draw them (called only when values change).
- For `Graph.ui`, `patchGraphUiLayout` merges only `ui.layout` (other keys such as viewport are preserved).

## Arrange and auto layout

When you give `layoutEngines` one or more `LayoutEngineDescriptor`s, the toolbar under the canvas gets [Arrange ▾] (the `L` key) and the "tangled edges" hint chip turns on. Without them, only this feature is off.
The engine list and options (`OptionDecl`: enum/number/boolean) are drawn from declarations, so a new engine needs just one descriptor. The built-in adapter `createElkEngine()` loads elkjs dynamically only on the first calculation and runs it in a Web Worker.

- Popover: layout direction, scope (all / selected nodes), engine options, edge shape (default / per kind), rebuild paths, align node directions, and the edge kinds used for layout. [Preview] draws only a translucent outline and emits no `onChange`. [Apply] emits node coordinates (8px grid) + the chosen cleanup + the `Graph.ui.layout` (direction, shape) record as **one `onChange` (reason `auto-layout`)**. Both the toast [Undo] and `Ctrl+Z` undo it in one step (`ui.layout` is restored too; the other keys of `ui` keep their current values).
- Cancel (`Esc`, [Cancel]) terminates the worker and changes nothing. A failure (engine load, calculation error, over 10 seconds) shows an error line in the popover + [Try again]. The last-used options are remembered only in `storage` (`localStorage` by default), and graph data is not touched.
- "Auto routes for edges too": if an engine descriptor declares `edgeShapeOption: { shapeId, default, title? }`, the popover gets a checkbox. When on, the "default shape" becomes that shape and is recorded in `ui.layout.edge_shape` on apply (this prevents curves from crossing nodes when only the direction changes). The initial value is the declaration's `default`, and afterwards the last choice is remembered in `storage`. `createElkEngine()` recommends `auto` from the start; change it with `edgeShapeOption` or turn it off with `null`. An edge's own `layout.shape` still takes priority.
- [Reset all edge paths]: after confirmation, removes all waypoints, bends, and label positions (the shape stays, reason `layout`).
- Tangled edges: `detectEdgeTrouble` (pure) finds edges that cross nodes or whose handles face away. Once the graph has been stable for 800ms after opening, the chip shows once, and closing it is remembered per graph id. It does not change data.

```tsx
import { GraphEditor, createElkEngine } from "@agent-console/graph-editor";

const engines = [createElkEngine()]; // create it once, outside the component (or in useMemo)
<GraphEditor graph={graph} nodeTypes={nodeTypes} edgeTypes={edgeTypes} onChange={setGraph} layoutEngines={engines} />;
```

Bundler note: the default worker is `new Worker(new URL("elkjs/lib/elk-worker.min.js", import.meta.url))` (Vite emits it as `assets/elk-worker.min-<hash>.js`). With another bundler, pass the ELK instance yourself through `createElkEngine({ workerFactory })` or `{ load }`.

### Edge label spacing (`labelSpacing`)

Labels of edges that fan out from the same node are moved along their paths so they do not overlap (a user-set `label_t` or `label_offset` stays). Change the spacing and margins through an optional prop. Missing values use the defaults.

| Key | Default | Meaning |
| --- | --- | --- |
| `gap` | 8 | Target gap between labels (screen px). Flow gap = `gap` ÷ zoom |
| `minGap` | 4 | Smallest gap allowed when space runs short (screen px) |
| `nodeTolerance` | 8 | How deep a label may go into a node body when space runs short (flow px, 0 = not tolerated) |
| `portClearance` | 4 | Margin outside the port circle (flow px). The port circle + margin is the obstacle labels avoid |
| `minZoom`·`maxZoom` | 0.5·1 | Zoom range used to convert screen px to flow px (values outside are clamped) |
| `settleMs` | 200 | Time to wait after a zoom gesture ends before solving again (ms) |
| `fold` | true | Whether chips fold into an icon and `+N` when space runs short (off means no folding) |
| `foldedWidth`·`foldedHeight` | 44·26 | Size used for a folded chip before its size could be measured (flow px). A chip that was folded once uses the measured size |

Order of giving way: gap `gap`→`minGap` → covering the node body 0→`nodeTolerance` → fold chips (icon and `+N`) → protect ports even if more of the body is covered → allow covering ports (last). Zero overlap between labels is kept at any value.
As in `createElkEngine({ optionDefaults: { layerGap: 160 } })`, the app can pass defaults for the auto layout options as data (the library default `layerGap` is 80).
Apps that use a PWA should keep the elk asset (about 1.4MB) out of the precache and serve it with runtime CacheFirst (for example `apps/web/pwa-workbox.ts`).

## Edge shape and path (pure logic)

`resolveEdgeShape`, `resolveDirection`, and `resolvePortSide` decide display layout values by layer order (edge > graph > user settings > descriptor hint > built-in).
Unknown values are skipped and the next layer is used. Shapes are registered in an `EdgeShapeDescriptor` registry (`createEdgeShapeRegistry`, the five built-ins `BUILTIN_EDGE_SHAPES`),
and `buildEdgePath` applies the gap along the outward normal of the side (`ARROW_GAP`) and then calls the shape's `build`. It does not depend on React Flow.

```ts
import { buildEdgePath, createEdgeShapeRegistry, resolveEdgeShape } from "@agent-console/graph-editor";

const shapes = createEdgeShapeRegistry();
const { value } = resolveEdgeShape({ edge: { shape: "step" }, isKnown: shapes.has });
const path = buildEdgePath({
  source: { x: 0, y: 0, side: "right" },
  target: { x: 200, y: 100, side: "left" },
  shape: shapes.get(value)!,
});
console.log(value, path.d.startsWith("M"));
```

### Auto path router (`shape: "auto"`)

`createAStarRouter(options?)` computes orthogonal paths that avoid node rectangles (padding 16), in edge id order (`logic/route.ts`, a pure function, no dependencies).
The costs (straight 1, bend +4, crossing +8), padding, grid, stub, and search limits (20,000 expansions / 8ms per edge) are all injected through `RouteOptions`.
If a limit is exceeded or no path exists, it falls back to a `smoothstep` path without waypoints and turns on `RoutedEdge.fallback` (the renderer attaches `data-route-fallback="true"` through `routeFallbackAttrs`).
There is a per-edge memo (a hash of the obstacles + the edge input + the inputs of earlier edges), so only moving a node triggers a recalculation. You can swap in another router through the `EdgeRouter` interface.
The search lines are the inflated node boundaries, endpoints, waypoints, and midlines (snapped to the 8px grid). This choice gets the same optimal path without expanding every 8px cell.
The router adds no new external dependency (what: our own A* / why: it fits the side and stub rules exactly and, as a synchronous pure function, is easy to test / alternatives: `libavoid-js` (LGPL), ELK edge routing).

```ts
import { createAStarRouter } from "@agent-console/graph-editor";

const a = { id: "a", x: 0, y: 0, width: 160, height: 64 };
const b = { id: "b", x: 400, y: 0, width: 160, height: 64 };
const router = createAStarRouter();
const routed = router.route(
  [{ id: "e1", source: { x: 160, y: 32, side: "right" }, target: { x: 400, y: 32, side: "left" }, sourceNodeId: "a", targetNodeId: "b" }],
  [a, b],
);
console.log(routed.get("e1")?.fallback, routed.get("e1")?.path.d.startsWith("M"));
```

#### On the canvas

Edges whose shape has `route` (the built-in `auto`) are drawn by `GraphEditor` through the router. There is **one router per editor instance** (pass one through the `edgeRouter` prop, or `createAStarRouter()` is created when first needed. Its working memory is large, so if one screen shows several canvases, you can share the same router among them).
All visible auto-path edges are computed in **one `route()` call** (the crossing cost depends on earlier edges), and endpoints are read from the handle boxes React Flow measured. While dragging a node, it is throttled to 50ms, and fallback edges get `data-route-fallback="true"`.
`selfAvoiding` in `troubleOfModel` means edges drawn by the router (not fallbacks), and the center line of the [Arrange] preview is the same router path. An edge without `layout` keeps the default curve, so no router is created.
Obstacle sizes for auto paths use, in order, the card as actually drawn (`offsetWidth/Height`) → the React Flow measurement → the estimate (`actualNodeSize`). Cards in the run detail are larger than the editor's estimate because of the status and summary lines, and using the estimate made paths graze the card edges.
`mode="readonly-run"` has [Edges ▾] (`viewOverrides`, default auto path and curve). It is only browser-local state and emits no `onChange`, and a temporary view does not use saved waypoints, bends, or label positions.

## Independent delegation, loops, conditions, and nested teams
**No edge kind or node kind names appear in code.** Everything below works only from descriptor properties (`cycle`·`handles_failure`·`invocation`·`scheduling`·`binds`·`ui_hints`) and data the app passes in (`test/noHardcoding.test.ts`).

| Feature | How |
| --- | --- |
| `resolveEdgeStyle(edgeType, strategies, hints?)` | Pure. Decides color, `stroke-dasharray` (referencing the token `--ac-edge-pattern-N`), icon, and default shape. Priority: `ui_hints` → property defaults (failure handling > loop > delegation, the first match) → built-in. The delegation pattern is the sort order of the strategy id % 4 |
| `loopRegion(graph, edgeTypes, edgeId)` | Pure. The node ids of the loop region of a cycle edge. Same definition as the server's `loop_regions` (flow edges only, removes **all** cycle edges from the path, a self loop is that one node) |
| `closesFlowLoop(graph, newEdge, edgeTypes)` | Pure. Whether the new edge closes a flow cycle (only `scheduling = flow` is checked) |
| Creating a connection | If it closes a cycle, a kind with `cycle` is preselected and the other flow kinds are disabled rows (with a reason). If there is no loop candidate, `onConnectRejected` gets reason `cycle`. The `info` prop of `EdgeKindDialog` (`disabledReason`·`preferred`·`iconName`) and the pure `planConnection` |
| Edge chips | `edgeExtraChips` (condition summary, round limit, and strategy chips the app computed), combined with declarative chips up to 4 + `+N`, with accessible names. `edgeBadges` are run detail badges. Below zoom 0.6, icons only. Icon names are drawn by `renderIcon`, and if it cannot, a short character or the first letter of the title |
| Lead chips and node marks | `edgeLeadChips` (key = edge id): the edge label stacks into 2 rows and this chip goes at the start of row 2 (up to 3 chips, `+N` from the 4th, icon only if `iconOnly`, and all icon-only below zoom 0.6). `nodeAnnotations` (key = node id): a 3px band on the left (`stripColor`), header marks (`lead`·`tags`, click and pulse), a one-line chip at the bottom of the card (`foot`), and `emphasis` (highlight/dim). The editor does not know what the values mean and only draws data the app built. The line pattern of a delegation edge is decided by `delegationStrategies[].session` (separate = solid, `same` = long dotted, unknown value = `8 3 2 3`, and with no value, a fallback by strategy id order) |
| Loop region highlight | Selecting a cycle edge outlines the region nodes (`--ac-loop-region`) with an aria-live announcement (also when read-only) |
| Definition-bound card | `bindSummaries` (subtitle, one body line, badge, `missing`, `open`). Node `Alt+Enter` and [Open ↗]. The editor does not read config keys |
| `ui_hints.shape: "stacked"` | Stacked card (two cards behind). Unknown values are a normal card. +8px for auto-path obstacles |
| `nodeRunBadges` | Run detail round and call badges (`#3`, `×4`). `picked`·`onClick` |
| Palette | `DefinitionItem.meta` (subtitle) and `disabledReason` (disabled: adding and dragging are ignored). Item order is exactly as the app gave it (sorting by name is the app's job) |
| Auto arrange (ELK) | Descriptor `cycle` edges are treated as back edges (`LayoutEdgeInput.back`). Nodes are given in topological order excluding the back edges, and `cycleBreaking` (an engine option, default `MODEL_ORDER`) is used. If the destination node is not in an earlier layer than the source node, that edge is removed and the calculation is redone |
| Changing the edge kind | Select one edge and press `T` → the same `EdgeKindDialog` as creating a new edge (the current kind preselected; flow kinds that close a cycle are disabled). Confirming changes only the kind with `onChange` reason `edit-edge`, and the old kind's `config` is cleared |
| Moving the view to a new node | For an add without a set position (the palette), if the new node is outside the viewport, the view moves to it (immediately under reduced motion) |

For graphs without layout values, the render and the `onChange` result are the same as before (without the new props, the DOM is the same too).

A folded chip (`data-folded="true"`) shows only the icon and `+N`, and hovering or keyboard focus brings the expanded body up on top. The chip's `title` and `aria-label` contain the full label and chip text. A selected edge and an edge whose position the user set are not folded. The pure function `spreadLabelLayout` returns the positions together with the list of folded edges (`spreadLabels` returns positions only).

### Text bundles (ko·en)

The default text is Korean (`src/locales/ko.json`), and an English bundle ships alongside it. There is no dependency such as i18next. Pass `messages` to the `messages` prop of `GraphEditor`, `shapes` to shape names and descriptions through `localizeEdgeShapes`, and `layout` to `title` and `optionTitles` of `createElkEngine`. `ko` and `en` have the same keys and placeholders (`test/locales.test.ts` checks this).

```ts
import { BUILTIN_EDGE_SHAPES, createElkEngine, localizeEdgeShapes } from "@agent-console/graph-editor";
import en from "@agent-console/graph-editor/locales/en";

const messages = en.messages; // <GraphEditor messages={messages} ... />
const edgeShapes = localizeEdgeShapes(BUILTIN_EDGE_SHAPES, en.shapes); // <GraphEditor edgeShapes={edgeShapes} ... />
const engine = createElkEngine({ title: en.layout.engineTitle, optionTitles: en.layout.options });
```

The Korean bundle is `@agent-console/graph-editor/locales/ko` (`defaultMessages` stays ko). To change only some entries, override them as in `messages={{ ...en.messages, undo: "…" }}`. For a new language, make an object with the same keys (the `GraphEditorLocale` type) and pass it in.
