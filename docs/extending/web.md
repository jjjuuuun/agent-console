# Web

There are three levels for changing the web screens. Ask from the top, and do not go further down if an earlier level
is enough.

1. **No web code needed**: change only server-side data (settings schemas, `x-ui`, module `web_roles`), and the
   screens follow.
2. **Register one line in the web app and rebuild**: when you need a new piece of screen, such as a new widget, cell
   renderer, or form widget.
3. **Use the presentation libraries in another React app**: take the `@agent-console/*` presentation packages and put
   them in your own screens.

The example for levels 2 and 3 is [@agent-console/example-web](../../examples/web/agent-console-example-web/README.md).
It builds one widget, one architecture map cell renderer, and one settings form widget, and registers them in the real
components to draw them.

## The web has no runtime plugins

A server plugin turns on when you install it and restart the server. The web does not work that way. The web app is
assembled at build time, and there is no mechanism to receive and run JavaScript from the server. There are three
reasons.

- Running code from the server in the browser creates supply chain and permission problems, even with a local server.
- Screen pieces must use the same React and contract types as the app, and matching them at runtime would need a
  separate mechanism for module sharing and version negotiation.
- Thanks to level 1, most server plugin authors do not need to change the web at all.

So when you really need a screen piece, change the web app and rebuild it. The "Level 1" table below shows how the
screens avoid breaking when the server sends names the web does not know.

## Level 1: what works without web code

- The settings schema of a server plugin (JSON Schema and `x-ui`) is drawn by the schema form. Descriptions, examples,
  defaults, required chips, and collapsed advanced fields all come from the schema data.
- Screen entries are defined by the server modules' `web_roles` (data). Only the roles of modules that are on appear
  in the sidebar.
- When a name the web does not know arrives, it is drawn in a reduced form as below. Values are never removed.

| What the server sends | When the web does not know it | Test that shows it |
| --- | --- | --- |
| The `ui:widget` name in a settings schema | For structured values (objects, arrays), switches to JSON editing with a note. For simple values, keeps the name as it is | [Passing widget names on](../../apps/web/src/features/delegation/delegationLib.test.ts) |
| A schema with no or partial `x-ui` | Draws the form from the schema alone (required status and so on follow fallback rules) | [x-ui fallback](../../packages/ts/lib/schema-form/src/xui.test.tsx) |
| An interaction renderer name | Draws a form from the response schema. The built-in fallback shows only the request content | [Interaction card](../../packages/ts/lib/chat/src/interaction/InteractionCard.test.tsx) |
| A dashboard widget kind | Draws an "unknown widget" placeholder and keeps the settings (JSON) | [Dashboard grid](../../packages/ts/lib/log-view/test/dashboard.test.tsx) |
| A log event category | Shows the raw id in a neutral tone | [Log components](../../packages/ts/lib/log-view/test/components.test.tsx) |
| `tone`, `style`, `view` of an architecture map cell | Neutral color, default line, default cell body | [Architecture map](../../packages/ts/lib/arch-view/src/ArchitectureDiagram.test.tsx) |
| A graph node status | Shows the raw status | [Graph editor](../../packages/ts/lib/graph-editor/src/GraphEditor.test.tsx) |
| Module `web_roles` | Only the role screens of modules that are on appear in the sidebar | [App shell](../../apps/web/src/app/App.test.tsx) |

## dashboard-widget

<!-- extdocs:facts dashboard-widget -->
- Registration: Pass it in the props of the component `@agent-console/log-view#DashboardGridProps` (registered at build time).
- Interface:
  - `@agent-console/log-view#WidgetDescriptor`
  - `@agent-console/log-view#WidgetRenderProps`
  - `@agent-console/log-view#WidgetRegistry`
  - `@agent-console/log-view#createWidgetRegistry`
- Built-in implementations: —
- Examples:
  - package: [examples/web/agent-console-example-web](../../examples/web/agent-console-example-web/README.md)
- Turning it off or removing it: Remove it from the props and rebuild.
<!-- /extdocs:facts -->

Use this to add a new widget kind to the log dashboard. A widget kind is one `WidgetDescriptor` object with `kind`
(the kind name), `title`, the query shape (`queryShape`), the options schema (`optionsSchema`), a default size, and
`render(props)`. A widget saved on a dashboard holds only the `kind` name, so it is drawn when a kind with the same
name is registered.

```tsx
import { builtinWidgets, createWidgetRegistry, DashboardGrid } from "@agent-console/log-view";

const registry = createWidgetRegistry(builtinWidgets, [myWidget]);   // later lists override the same kind
<DashboardGrid registry={registry} widgets={widgets} results={results} slotFor={slotFor} />
```

- `render` does not call the server. Aggregate results (`rows`), loading, and errors come in through props. When a
  value is `null`, show "–" instead of turning it into 0.
- The editor form for the options is drawn from `optionsSchema` (JSON Schema). For option values it does not
  understand, the widget must fall back to the defaults.
- When the kind is not registered, a placeholder shows and the settings are kept. Removing the registration does not
  delete saved widgets.

Common mistakes: using the same kind name as a built-in widget, which overrides the built-in one, and not giving the
gauge body an accessible name (`aria-label`). Full code: [the gauge widget in the example](../../examples/web/agent-console-example-web/README.md).

## architecture-cell-renderer

<!-- extdocs:facts architecture-cell-renderer -->
- Registration: Pass it in the props of the component `@agent-console/arch-view#ArchitectureDiagramProps` (registered at build time).
- Interface:
  - `@agent-console/arch-view#CellRenderer`
  - `@agent-console/arch-view#CellRenderProps`
  - `@agent-console/arch-view#EdgeStyleSpec`
- Built-in implementations: —
- Examples:
  - package: [examples/web/agent-console-example-web](../../examples/web/agent-console-example-web/README.md)
- Turning it off or removing it: Remove it from the props and rebuild.
<!-- /extdocs:facts -->

Use this to change the inside of architecture map cells or the shape of edges. A cell in the architecture map data
(the profile the server built) can have a `view` string, and `ArchitectureDiagram` looks up the matching function in
its `cellRenderers` table (`view` value → render function) and hands it the inside of the cell. The library draws the
cell shell (button, status marks, keyboard navigation), so the render function is responsible only for the inside.

```tsx
const cellRenderers = {
  "my-badge": ({ cell, defaultBody }) => <>{defaultBody}<Badge count={cell.metrics?.count?.value} /></>,
};
<ArchitectureDiagram view={view} cellRenderers={cellRenderers} />
```

- The render function receives `defaultBody` (the default body). Wrap it or add to it, and the default look is not
  lost.
- When the `view` key is not in the table, the default cell is drawn. When a metric value is `null`, do not add a
  badge (do not show "not collected" as 0).
- Change edge shapes with the `edgeStyles` table (style name → token variable). Colors accept only token variable
  names, and arbitrary colors are reduced to neutral.

Example: [drawing a cell badge](../../examples/web/agent-console-example-web/README.md).

## config-form-widget

<!-- extdocs:facts config-form-widget -->
- Registration: Add an entry to the web app registry `@agent-console/web/src/features/delegation/configWidgets.ts#CONFIG_WIDGETS` (registered at build time).
- Interface:
  - `@agent-console/web/src/features/delegation/widgetRegistry#WidgetRegistry`
  - `@agent-console/web/src/features/delegation/widgetRegistry#ConfigWidget`
- Built-in implementations: —
- Examples:
  - package: [examples/web/agent-console-example-web](../../examples/web/agent-console-example-web/README.md)
- Turning it off or removing it: Remove the entry and rebuild.
<!-- /extdocs:facts -->

Use this to connect a screen component to a `ui:widget` name in a server settings schema. The name is data the server
defines. When you register one line in the app's widget registry (`name → { Component, summary? }`), fields with that
name are drawn with the component. `Component` receives only the schema form's field props
(`SchemaFormFieldProps`: value, `onChange`, `label`, `errors`, and so on).

```ts
export const CONFIG_WIDGETS: WidgetRegistry = {
  /* existing widgets */
  "my.tags": { Component: TagsField },
};
```

- Names in the registry are passed on as `ui:field`, so one component draws the whole field value. When an unknown
  name is on a structured value, it is reduced to JSON editing with a note.
- Show values of an unexpected shape (a tags field whose value is not an array, and so on) as an empty input, but do
  not change the value until the user edits it.
- With `summary`, a summary shows as a chip on the edge. Leave it out if you do not need it.
- Connect the label (`label`) and errors (`errors`) so the widget works with the keyboard and screen readers.

Example: [the tag input widget](../../examples/web/agent-console-example-web/README.md).

## screen-entry

<!-- extdocs:facts screen-entry -->
- Registration: Add an entry to the web app registry `@agent-console/web/src/shell/routeConfig.ts#DEFAULT_ROUTES` (registered at build time).
- Interface:
  - `@agent-console/web/src/shell/routeConfig.ts#RouteDef`
  - `@agent-console/web/src/shell/routes.tsx#PageTable`
  - `@agent-console/web/src/shell/routes.tsx#DEFAULT_PAGES`
- Built-in implementations: —
- Examples:
  - reference: [apps/web](../../apps/web/README.md)
- Turning it off or removing it: Remove the entry and rebuild.
<!-- /extdocs:facts -->

Use this to put a new screen in the sidebar. You need two things: one line of route data (`RouteDef`: path, title
message key, icon, group, role) and one line in the `routeId → screen component` table. The sidebar, quick open, and
the keyboard shortcut help table are all built from this data. If a server module declares the same role in
`web_roles`, the entry disappears when that module is off.

- Screen code finds other screens by `serves` (role), not by route id. Changing an id does not break links.
- Make API calls in a container, and split the screen component so it receives data and callbacks through props.
- Reference: the shell and routes of the [web app](../../apps/web/README.md).

## interaction-renderer

<!-- extdocs:facts interaction-renderer -->
- Registration: Pass it in the props of the component `@agent-console/chat#defaultRenderers` (registered at build time).
- Interface:
  - `@agent-console/chat#RendererComponent`
  - `@agent-console/chat#RendererProps`
- Built-in implementations: —
- Examples:
  - reference: [packages/ts/lib/chat](../../packages/ts/lib/chat/README.md)
- Turning it off or removing it: Remove it from the props and rebuild.
<!-- /extdocs:facts -->

Use this to change the response screen of requests an agent makes to the user (interactions). When the server's
request description has a renderer name, `InteractionCard` looks it up in its `renderers` table (name → component).
The built-in renderers are three, for choices, permissions, and review (`defaultRenderers`), and you add or replace
them with the `renderers` prop.

- An unknown renderer name is reduced to a response schema form (or the built-in fallback). The user is never left
  unable to answer.
- The response value follows the request's response schema. A renderer changes only how it looks.
- Reference: the interaction components of the [chat package](../../packages/ts/lib/chat/README.md).

## Reusing the libraries

The `@agent-console/*` presentation packages (`log-view`, `arch-view`, `schema-form`, `chat`, and others) receive data
and callbacks through props and do not know the server API client. You can use them in other React apps.

- When the bundler supports the `development` condition, the sources are read; otherwise `dist` is read. Add
  `development` to `resolve.conditions` in the app's bundler settings to read the sources.
- Write in-house package dependencies as `^x.y.z` ranges. Outside the repository, install the tarballs
  (`pnpm pack:all` → `dist/npm`).
- Import each package's `styles.css` and the shared token CSS once each.
- Import contract types (`@agent-console/contracts`) as types only (`import type`).
- Check that it works outside the repository with `pnpm portability --package <name>` (the same goes for the
  `examples/web/` examples). If the tarballs it needs are missing, the tool runs `pnpm pack:all` first, and after you
  change sources, rebuild them with `--pack`. For details, see [Creating packages](packages.md).

## Examples are not used by the app

The example packages are samples to copy from. The apps and packages in the repository do not import the examples
(the dependency check prevents it). The examples are not part of the app bundle.
