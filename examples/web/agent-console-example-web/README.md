# @agent-console/example-web

An example that adds **one dashboard widget, one architecture map cell drawing, and one settings form widget** to the web screens.
The web has no runtime plugins. This example is presentation code built as a library; it shows up only after you register it in the web app with one line each and rebuild the app.
It does not change the server or contract code. If you do not register it in the app, nothing changes.

| Point | What this example provides | Key (data) |
| --- | --- | --- |
| Dashboard widget | `gaugeWidget` (one metric as a bar against its maximum) | Widget kind `example.gauge` |
| Architecture map cell drawing | `cellRenderers` (adds a `count` badge to a cell) | The cell's `view` value `example-badge` |
| Settings form widget | `configWidgets` (a comma-separated tag list input) | The settings schema's `ui:widget` name `example.tags` |

All three are harmless for values they do not know. If a widget kind is not registered, the grid draws an "Unknown widget" placeholder and the settings are preserved.
A cell whose `view` key does not match gets the default look. When the value is `null` (not collected), it shows "–" rather than 0, or no badge is attached.

## Minimal code

All three pieces are split into presentational components and a registration object, and there are no server calls. Data and callbacks come in as props.

```ts readme
import { builtinWidgets, createWidgetRegistry } from "@agent-console/log-view";
import { cellRenderers, configWidgets, gaugeWidget } from "@agent-console/example-web";

const registry = createWidgetRegistry(builtinWidgets, [gaugeWidget]);
const gaugeRegistered = registry.has("example.gauge");
const cellViews = Object.keys(cellRenderers);
const widgetNames = Object.keys(configWidgets);
```

`gaugeRegistered` is `true`, `cellViews` is `["example-badge"]`, and `widgetNames` is `["example.tags"]`. This block must match `test/readme.test.ts`.

The real implementation is in `src/GaugeWidget.tsx`, `src/BadgeCell.tsx`, and `src/TagsField.tsx`.

## Registration

In the web app (`apps/web`), it is one line per point. The prop names the library accepts are the same as the `interface` in each point's declaration.

```tsx
// 1) Dashboard widget: add the list to the registry that DashboardGrid and WidgetEditor use
const registry = createWidgetRegistry(builtinWidgets, [gaugeWidget]);
<DashboardGrid registry={registry} /* … */ />;

// 2) Architecture map cell: pass the table to the cellRenderers prop. A cell's view value is decided by the server's architecture profile data
<ArchitectureDiagram cellRenderers={cellRenderers} /* … */ />;

// 3) Settings form widget: spread it into the app's widget registry. The name is the ui:widget in the server settings schema
export const CONFIG_WIDGETS = { /* existing widgets */ ...configWidgets };
```

The app takes this example in as a `package.json` dependency and then **rebuilds the web app** (`pnpm --filter @agent-console/web build`).
This example's folder is set up so that the app does not import it (the repository enforces this with a dependency check). To use it, copy the folder and rename it, or move it into your own package.

## Install and remove

- Install: keep this folder as a pnpm workspace member (`examples/web/*` in `pnpm-workspace.yaml`). To use it in the app, add the registration code above to the app and add the dependency.
- Remove: delete the app's registration line and the dependency, then rebuild. Saved dashboard widgets are not deleted; they remain as "Unknown widget" and their settings are preserved.
- Outside the repository, install the tarball (`pnpm pack:all` → `dist/npm`).

## Test

```sh
pnpm --filter @agent-console/example-web test
pnpm --filter @agent-console/example-web typecheck
```

The widget is registered in and drawn by `DashboardGrid`, the cell drawing by `ArchitectureDiagram`, and the settings form widget by `SchemaForm`.
The tests also check unknown values (null, options that do not match, `view` keys, and non-array values) and accessibility (0 axe violations).
The copy-out-of-repository check (from the repository root): `pnpm portability --package @agent-console/example-web`.
If the internal dependency tarballs (`dist/npm`) are missing, the tool runs `pnpm pack:all` first. After changing the source of an internal package, add `--pack`.
