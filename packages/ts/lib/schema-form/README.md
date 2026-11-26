# @agent-console/schema-form

A React component that takes a JSON Schema (plus a uiSchema) and a value and draws an input form. It is a thin wrapper over @rjsf/core v6 and
uses no API, app, graph, or global state (fetch, WebSocket, localStorage). The fields, order, labels, and defaults are decided by the schema it receives.
It does not import other packages such as `@agent-console/ui`. The common look is shared only through the `--ac-*` CSS variables and utility class names.

## Minimal usage
This block matches `test/readme.test.ts`, and the test actually runs it (`pnpm pkg-lint` checks that they match).

```ts readme
import { getDefaultValue } from "@agent-console/schema-form";

const schema = { type: "object", properties: { name: { type: "string", default: "New name" } } };
const value = getDefaultValue(schema);
```

## Installation
Inside the repository, `pnpm install` links the package. Outside the repository, install the tarball (`pnpm pack:all` → `dist/npm`): `npm install ./agent-console-<name>-<version>.tgz`
`react` and `react-dom` (^19) are peer dependencies.

## Another usage example
```tsx
import { SchemaForm, getDefaultValue } from "@agent-console/schema-form";
import "@agent-console/schema-form/styles.css"; // the app provides the --ac-* variables through tokens.css (fallback values otherwise)

const schema = { type: "object", properties: { name: { type: "string", title: "Name" } } };

function Panel() {
  const [value, setValue] = useState(() => getDefaultValue(schema));
  return (
    <SchemaForm
      schema={schema}
      uiSchema={{ name: { "ui:widget": "textarea" } }}
      value={value}
      onChange={setValue}                         // called only for user edits
      errors={[{ path: "/name", message: "Required" }]} // server errors (JSON Pointer)
    />
  );
}
```

Props: `schema`, `uiSchema`, `value`, `onChange`, `errors`, `disabled`, `readonly`, `idPrefix`, `focusPath`,
`customWidgets` (a `ui:widget` name → a component, with props `SchemaFormWidgetProps`), `customFields` (a `ui:field` name → a component, with props `SchemaFormFieldProps`; `pointer` = this field's JSON Pointer inside the form value (including array indexes) — for when one component draws a whole object or array value, such as a key-value map or an attachment list. It also works inside a provenance row), `validateOn` (`blur` | `change` | `submit`),
`rawJsonToggle`, `messages` (a partial override of the Korean defaults), and `className`.
A schema that cannot be interpreted (`true`, `{}`) or a render exception is replaced by a raw JSON editor.

## Provenance display (optional)
Use it when editing values that overlap across settings layers (common, team, agent, node, and so on). Passing `provenance` or `disabledPaths` turns it on; without them, everything behaves as above.
Layer ids and names are not in the code; they come only as `layers` data (lower priority first). Every path is a JSON Pointer.

| Prop | Description |
| --- | --- |
| `layers` `{id,label}[]` / `editLayerId` | The layer list and the layer being edited. The badge color slot = the layer index mod 6 (`--ac-layer-1..6`) |
| `provenance` `{pointer: layerId}` | The source of each leaf value (the server's `Resolved.provenance`). An object row gathers its descendants' sources into a "Mixed N layers" badge |
| `effectiveValue` | The effective value, used to show inherited values. `value` holds only this layer's values |
| `layerValues` `{layerId: value}` | The popover "How this value is decided", opened by clicking the badge (a row becomes a button when `onOpenLayer` is given) |
| `onOverride(path)` / `onInherit(path)` | [Override or set in this layer] / [↺ Revert to inherited]. The app changes `value`. Clearing an input does not call `onInherit` |
| `disabledPaths` `{pointer: reason}` | Fields that do not apply (including descendants): grayed out with a lock and the reason, with inputs and buttons disabled |
| `fieldWarnings` / `mergeNotes` | A warning text under a field / a chip text next to a label (the app decides the text) |
| `renderProvenanceBadge(info)` | Injects the badge renderer (for example, `ProvenanceBadge` from `@agent-console/ui`). This package imports no other `@agent-console/*`, so the built-in badge is the default |

- `onChange` returns **only this layer's values** (inherited values are not included). When cleared, a string stays `""` and anything else stays `null`, and the key is kept.
- States: `set` (editable + ↺), `inherited` (read-only style + override), and `default` (read-only + set). Read-only is implemented with the row's `<fieldset disabled>`.
- `Alt+Enter`: toggles override and revert for the focused field. When it becomes editable after an override, focus moves to the input.
- An enum array (`items.enum`) drawn with `ui:widget: "checkboxes"` also uses `x-ui.enum_labels` (on the array or on the `items` side) as labels. The web resource form draws every enum array with this widget.
- An array is one value as a whole (replace merge), so it has one badge, and the sources of its elements (`/tags/0`) are viewed together.

## Rendering the schema's `x-ui`
The form reads and draws the schema's `x-ui` (`tier`, `when`, `example`, `group`, `group_title`, `order`, `unit`, and `enum_labels` (an enum value → a screen label)). Field names and kind ids are not in the code.
- `hideRootTitle`: hides the top-level object title (such as a schema class name). Nested object titles stay.
- Basic fields come first, and advanced fields go in a collapsed "Advanced settings (N)" area (the expanded state is remembered through `advancedStorageKey`, it opens automatically when there is an error or a `focusPath`, and there is a "N set" chip).
- Each field gets a required chip, a one-line description, a unit suffix, an example (click to fill when empty), the default, and "When to change" (always shown for advanced fields, an i button for basic ones). `readOnly: true` shows text plus a copy button.
- Without `x-ui.tier`, the fallback is: `required` → basic, an object is basic if any child is basic, an optional field with a default → advanced, and an optional field without one → basic. A form with only advanced fields is not collapsed.
- With `xui={false}`, the form keeps the existing rjsf look. When `compactProvenance` is on together with provenance display, only fields that are set show the badge and the revert icon, and the rest are edited directly (touching one sets it in this layer).
- The pure functions `readXUi`, `resolveTier`, and `splitByTier` are in `src/xui.ts` (not a public export).

## Deprecated fields (`deprecated: true`)
- When a schema property has `deprecated: true`, it is handled by a general rule **without knowing the field name** (including inside `$defs` references, but excluding inside array items).
- With no value, the field is left out of the form (removed from the schema and from `required`, and no "N hidden" notice is shown either). With a value, it is drawn with `messages.deprecatedChip` on the label and `messages.deprecatedNote` in the description. The value can still be edited or deleted as it is.

## Text and language
The form's own default text (`DEFAULT_MESSAGES`) is Korean (`src/locales/ko.json`), and an English bundle ships alongside it. There is no dependency such as i18next. Placeholders are `{name}`.
`ko` and `en` have the same keys and placeholders (`test/locales.test.ts` checks this). To use English, pass one bundle as `messages`.

```tsx
import en from "@agent-console/schema-form/locales/en";

<SchemaForm schema={schema} value={value} onChange={setValue} messages={en} />
```
The Korean bundle is `@agent-console/schema-form/locales/ko`. To change only part of a bundle, spread it and override, as in `messages={{ ...en, addItem: "Add" }}`. For a new language, build an object with the same keys and pass it in.

Text that comes from the schema (titles, descriptions, `x-ui`'s `when`, `group_title`, `unit`, the `enum_labels` values, the names of `oneOf` branches, and the uiSchema's `ui:title`, `ui:description`, `ui:placeholder`, and `ui:help`) is changed through the `translate` prop. By default it is shown as it is. The function can return unknown text as it is, and should be passed as a stable reference (a module constant or `useCallback`). Defaults, `enum`, `const`, and property names are data, so they are not changed.

```tsx
const translate = (text: string) => table[text] ?? text; // table is the app's text table

<SchemaForm schema={schema} value={value} onChange={setValue} messages={en} translate={translate} />
```
To use the same conversion outside the form, use `translateSchema(schema, translate)` and `translateUiSchema(uiSchema, translate)`. The component source contains no Korean strings (the same test checks this).

## Dependencies (what / why / alternatives)
| Package | Version (npm latest at install time) | Why | Alternatives |
| --- | --- | --- | --- |
| @rjsf/core | 6.11.0 (peer react >=18, verified to work on React 19.3) | Generates forms from JSON Schema (handles arrays, nesting, oneOf, and $ref) | JSON Forms, a custom implementation (costly) |
| @rjsf/utils | 6.11.0 | Utilities such as default value calculation and deepEquals | - |
| @rjsf/validator-ajv8 | 6.11.0 | Client-side validation (ajv8) | validator-ajv6 (an older version) |

rjsf types are not exposed in the public API. To swap the engine, change only this package's internals.

## Testing
`pnpm test` (from the package folder or the repository root; Vitest + happy-dom). The tests run without tokens.css.

## Additional behavior
- The buttons for adding, deleting, moving, and duplicating array items use the package's own template (a character icon plus an `aria-label` and `title`, changeable through `messages`), so no icon font (glyphicon) is needed.
- Where the schema does not decide the shape of a value (a free object with `additionalProperties: true`, or a value with no schema such as `{}` or `true`), the whole value is drawn with a raw JSON editor (invalid JSON is shown as a field error, and applied only when valid).
