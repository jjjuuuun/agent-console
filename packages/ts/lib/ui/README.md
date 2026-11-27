# @agent-console/ui

The design tokens (`tokens.css`) and basic components that know nothing about the domain. It knows no node types, graphs, or APIs.
It imports no other TS package (react is a peer). graph-editor and schema-form do not depend on this package;
they rely only on **the `--ac-*` CSS variables, the utility class names, and the `data-status` rule** as a convention.

## Minimal usage
This block matches `test/readme.test.ts`, and the test actually runs it (`pnpm pkg-lint` checks that they match).

```ts readme
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Button, formatBadgeCount } from "@agent-console/ui";

const html = renderToStaticMarkup(createElement(Button, null, "Save"));
const badge = formatBadgeCount(120);
```

## Installation and import
Inside the repository, `pnpm install` links the package. Outside the repository, install the tarball (`pnpm pack:all` → `dist/npm`): `npm install ./agent-console-<name>-<version>.tgz` (React 19 is required)

The app loads it **once**, at the entry point, **before** the other packages' `styles.css`.
```ts
import "@agent-console/ui/tokens.css";
import "@agent-console/graph-editor/styles.css";
```

## What tokens.css contains
- Color: by default it follows the system (without a `data-theme` attribute it uses `prefers-color-scheme`; unless light is preferred, the dark values in `:root` apply), and `[data-theme="dark|light"]` pins it. `--ac-bg`, `--ac-surface-1..3`, `--ac-text*`, `--ac-accent*`, the semantic colors (`--ac-danger/warning/success/info` + `-bg`), the category colors `--ac-cat-1..8` and `--ac-cat-neutral`, edges and canvas, and the status colors `--ac-status-<state>` (+`-bg`).
- Type: `--ac-font-sans` (Pretendard → Noto Sans KR → Malgun Gothic → Apple SD Gothic Neo → system-ui), `--ac-font-mono`, `--ac-text-xs..xl/code` (12px or more), and `--ac-lh-*`.
- Spacing `--ac-space-0..7`, radii `--ac-radius-*`, control heights, layout constants, z-index, motion, and shadows.
- Utilities: `.ac-text`, `.ac-ellipsis`, `.ac-clamp-2/3`, `.ac-mono-wrap`, `.ac-pre`, `.ac-num`, and `.ac-sr-only`.
- Status: `[data-status="pending|queued|running|succeeded|failed|skipped|waiting|cancelled"]` supplies the color, border pattern, and icon mask through CSS variables. Run statuses add `completed|paused|interrupted` under `data-status-kind="run"`. Any other value falls back to a dashed outline plus a question mark. Icons are inline SVG data URIs (no external files). With reduced motion, animation stops.

## Status display rule
Put only `data-status="<the server's status string>"` on an element, and place an empty `<span class="ac-status-icon">` inside it, and the icon appears. To give a box (such as a node card) the border pattern and header tint as well, add the generic hook classes below. The caller passes labels through `messages`, with no JS table.

### Generic hook classes
| Class | Where to put it | Effect |
| --- | --- | --- |
| `ac-status-box` | A box that has `data-status` | The border color, pattern, and thickness per status, hatching and dimming for skipped, and an outer ring for waiting |
| `ac-status-header` | The box's direct child header | The status tint, and a progress bar for running |
| `ac-status-keep` | A direct child of a skipped box that should not be dimmed (such as the category color bar) | Excluded from the 0.7 opacity |
| `ac-status-icon` | An empty `<span>` (it uses the nearest `data-status` ancestor) | The status icon (a mask), rotation for running, and blinking for waiting |

## Usage example
```tsx
import { Button, IconButton, StatusChip, StatusIcon, Banner, ThemeProvider } from "@agent-console/ui";

<ThemeProvider theme={theme} onThemeChange={setTheme /* the app saves it */}>
  <StatusChip status="running" label="Running" />
  <StatusChip status="interrupted" kind="run" label="Interrupted" />
  <StatusChip status="a-status-added-later" />{/* without a label it shows the raw text, with the fallback style */}
  <Button variant="primary" loading={saving} onClick={save}>Save</Button>
  <IconButton label="Delete" icon={<TrashSvg />} />
  <Banner tone="danger" title="Couldn't save">The version conflicted.</Banner>
</ThemeProvider>
```

## Text and language
v2 components such as `Sidebar` and `ListPane` take their text through their own `messages` props. The other text that components use by default ("More" in `Tabs` and `PageHeader`, "N more" in `ChipRow`, and the duplicate warning and the outside-provider error in `ShortcutProvider`) is gathered in `UiMessages` (`defaultUiMessages`). The default is Korean (`src/locales/ko.json`), and an English bundle ships alongside it. There is no dependency such as i18next. Placeholders are `{name}`, filled by `formatUiMessage`.
`ko` and `en` have the same keys and placeholders (`test/locales.test.ts` checks this). To use English, pass one bundle as `messages`.

```tsx
import en from "@agent-console/ui/locales/en";

<Tabs tabs={tabs} ariaLabel="Sections" messages={en} />
<ShortcutProvider defaults={defaults} messages={en} />
```
An individual prop such as `moreLabel` takes priority. The Korean bundle is `@agent-console/ui/locales/ko`. For a new language, build an object with the same keys and pass it in. The component source contains no Korean strings (the same test checks this).

## Public API
- Basic: `Button`, `IconButton`, `Spinner`, `StatusIcon`, `StatusChip`, `Badge`, `Tag`, `Banner`, and `ThemeProvider` / `useTheme`.
- v2 (all controlled, with text in props): `Sidebar` (`items`, `activeId`, `onNavigate`, `collapsed`, `messages`; arrow-key roving and a `99+` badge; `groups` plus an item's `group` give group titles and collapse dividers, and a group with no items is not drawn (`groupSidebarItems`); items with `position:'bottom'` and the `tools` slot go in the bottom toolbar as icons, and the collapse button sits at the right end of the toolbar (`messages.toggle` = a fixed name plus `aria-expanded`)), `Dialog` / `ConfirmDialog` (focus trap, Esc, inert background, and focus return; `danger` focuses Cancel by default), `ToastProvider` / `useToast` (errors are assertive, one action button, `regionLabel`; `text` and the action `label` accept a ReactNode, so a language-aware element changes an open toast when the language switches), `FileTree` (`locale` sets the name sort language, default `en`), `Tabs` (`←→ Home End`, `lazy`, controlled or uncontrolled), `ProvenanceBadge` (color slot = `layer.index mod 6`, a text label is required), `Gauge` (a no-value state, and `role=meter` only when there is a value), and `EmptyState` (`steps` and `secondaryAction`).
- `Drawer({open,title,onClose,closeLabel,description?,actions?,width?=560,initialFocus?,testId?})`: a modal drawer on the right. Three rows: a header (title and close), a scrolling body, and a bottom-fixed `actions`. It has Esc, Tab cycling, an inert background, and focus return (the same modal hooks as `Dialog`). It is controlled, so the caller's editing state stays as it is even after it closes. All text comes in as props.
- Modal hooks: `useModalBackdrop(open, backdropRef, { inert? })` (an inert background plus focus return; `inert:false` is for a non-modal panel), `trapTabKey(event, root)` (`Tab` cycling), and `FOCUSABLE_SELECTOR`. `Dialog` and the app's drawers share them.
- Controlled, with text in props and no kind names:
  - `PageHeader` (`title`, `breadcrumb`, `status`, and `actions`; the title is an h1, and the last breadcrumb is `aria-current`).
  - `CommandPalette` (`open`, `onClose`, `groups: {id,title,items:{id,label,hint?,keywords?,icon?,badge?,shortcut?,disabled?,run}[]}[]`, `query`, `onQueryChange`, `loading`, and `messages`). `role=combobox` + `listbox`, `↑↓` cycling (skipping disabled items), `Enter` to run, `Esc` to close, **Enter and arrow keys are ignored during Korean IME composition**, and opening makes the background inert and closing returns focus. Filtering is the caller's job, and the helper `filterCommandGroups(groups, query, maxPerGroup?)` is provided. `keywords` is an alias string used only for matching (not shown). An item's `run` is called after the palette closes.
  - Shortcuts: `useKeyCombo(combo, handler, {platform})`, `matchKeyCombo`, `parseKeyCombo`, and `formatKeyCombo`. Combination strings (`"Mod+K"`, `"Alt+J"`) come in as **data** (the web's default table plus the user setting `ui.keybindings` overrides). Modifier keys must match exactly, and input is ignored during IME composition. The global shortcut handler is covered in the shortcut management item below.
  - `ListPane<T>` (`items`, `getItemId?`, `selectedId`, `onSelect`, `renderItem`, `rowHeight?`, `loading/error/empty` slots (error > loading > empty), `searchValue/onSearchChange`, `toolbar`, and `messages`). `role=listbox`, focus moves with `↑↓ Home End`, `Enter/Space` or a click selects, and `↓` in the search box enters the list.
  - `ListPane`'s `groups` (`ListPaneGroup[]`: key, label, title, count, depth, collapsed, and items) and `onToggleGroup(key, collapsed)`: the group header (`GroupHeader`, sticky, with `aria-expanded`) and `role=group` items. A header is also a `↑↓` target, and on a header `←` collapses, `→` expands, and `Enter/Space` toggles. Hiding and computing sub-groups is the caller's job (for example, `@agent-console/list-arrange`). `ListViewMenu`: a "View" menu that takes the grouping and sorting choices as `ListViewOption[]` (`menuitemradio`, it stays open after a choice, the `G` shortcut connects through `open/onOpenChange`, and collapse all / expand all).
  - `AttachmentList` (`groups: {layer,items:Attachment[],editable}[]`, `modeOptions` (data), `renderRow`, `onReorder(layerId, orderedKeys)`, `onRemove`, `onModeChange`, `onAdd`, and `messages`). Reordering uses up and down buttons (keyboard accessible), and a layer that cannot be edited is read-only.
  - `Disclosure` (based on `<details>`, controlled or uncontrolled, and the summary responds to Enter and Space).
  - `FileTree` (`items: {path, trailing?, leading?}[]`, `view` tree or flat, `selected`, and `onSelect`). `role=tree`, `↑↓ ←→ Home End Enter`, and folders are built from paths (domain-independent).
  - `TrustBadge` (`trust: string`, an open value, and `label`). A level the style knows changes the color, icon, and border shape, and an unknown value gets a neutral badge plus the raw text (the code has no list of levels, only the CSS `[data-trust]`).
  - Icons: `iconRegistry` (the app's fixed names `defaultIcons`: entry/exit/ask/override/inherit/lock/external-link/copy/eye/eye-off), `createIconRegistry`, `registerIcons(icons, base?)` (immutable; it returns a new registry), `IconRegistryProvider` (`registry` or `icons`; when nested, it adds to the parent), and `Icon({name,size,label,fallbackText})`. An unknown name becomes an avatar with the first letter of `fallbackText`.

- Overflow prevention and the icon button foundation (all controlled, with text in props, `min-width:0`, ellipsis, and a tooltip):
  - `Dialog({open,title,onClose,children,actions?,size?: "sm"|"md"|"lg"|"xl",initialFocus?})`: a three-row grid of title / **scrolling body** / **bottom-fixed `actions`** (the maximum height is `--ac-dialog-max-h`, the width is at most `--ac-dialog-w-*` and 94vw, and below a width of 480 the buttons stack vertically at full width). Buttons must go in `actions` (no button row inside the body: the dashboard template dialog broke because it drew a button row inside the body without `actions`, and the row was clipped inside `overflow:auto`). A `fieldset` in the body has no border, and a one-line radio or checkbox is `<label class="ac-choice"><input/><span>Label</span></label>`. `wide` is an alias of `size="lg"` (deprecated).
  - `Tabs` (+`moreLabel?`, `TabItem.title?`): a single line, with a width in `[--ac-tab-min-w, --ac-tab-max-w]`, and an overflow goes to a "More ▾" menu on the right. **The active tab is always visible**, and keyboard ←→ moves through hidden tabs too and promotes them.
  - `ChipRow({chips: {id,label,title?,icon?,tone?,active?,onSelect?}[], ariaLabel, moreLabel?(n)})`: a single line, chips at most `--ac-chip-max-w`, and an overflow becomes a `+N` button and a popover. An `active` chip is always visible.
  - `MiddleEllipsis({value, head?, tail?, copyLabel?})` / `middleEllipsis(value, head=8, tail=4)`: shortens a long id or hash to `abcdefgh…wxyz` and keeps the full value in a tooltip. Giving `copyLabel` adds a copy button.
  - `ActionButton({icon?: a registry name, label, shortcut?, display?: "icon"|"icon-label"|"label", variant?, size?, loading?, pressed?, platform?, ...button})`: `label` = `aria-label` = the tooltip (+`Ctrl+…`), and while loading it shows a spinner and `aria-busy`. `ActionDef = {id, icon?, label, shortcut?}` is the shape of one line in a screen settings table.
  - `Tooltip({content, placement?, align?})` (CSS only, 400 ms on hover and immediate on focus, and `aria-hidden` because it is decorative), `Popover({open,onOpenChange,renderTrigger,panelRole,panelLabel,align})` (non-modal, Esc and an outside click, no portal), and `Menu({items: MenuItemDef[], onClose})` (`role=menu`, `↑↓ Home End`).
  - `PageHeader` (+`secondaryActions: MenuItemDef[]`, `moreLabel?`): the title is at most `--ac-header-title-max` with an ellipsis and a tooltip. When the header (container) width is below 640, the secondary actions fold into a `more` menu (a container query, not the viewport).
  - Hooks and pure functions: `useOverflowFit` and `computeVisible(widths,gap,available,moreWidth,priority)`.
  - Added icons: `refresh close more plus undo check trash send stop panel-left-close panel-left-open filter columns table chevron-left/right/down expand play pencil pin`, and `plug`. If the app registers the same name, the app's wins.
  - Default labels (such as `moreLabel` "More") are Korean defaults. For another language, pass them as props.
  - ESLint: `agent-console/button-name` in `@agent-console/eslint-config/react` blocks a `<button>` that has only an icon.

- Shortcut management (domain-independent — action ids, handlers, and title keys are data):
  - `ShortcutProvider({defaults: ShortcutDef[], overrides?: Record<id, keys>, platform?, enabled?, onWarn?, target?})`, with `ShortcutDef = {id, scope, keys, titleKey, modifierRequired?, run}`.
  - `useShortcuts(defs)` (a screen registers and unregisters; for the same id the screen's definition wins, and the latest handler is called), `useEffectiveShortcuts()` (the help and settings table, updated on change), `useShortcutRegistry().getEffectiveKeys()` → `{id, scope, titleKey, keys, isDefault, conflict?}[]`, and the pure function `computeEffectiveKeys`.
  - Key notation: `"Mod+K"`, `"?"`, and a sequence is separated by a space (`"g c"`). An empty string in `overrides` = disabled.
  - Rules: a single-letter key without a modifier (Ctrl, Meta, or Alt) does nothing inside input, textarea, select, contenteditable, or `[data-ac-editable]` (modifier combinations still work). A sequence needs the second key within 1 second (otherwise, or with a different key, it is canceled). Input is ignored during IME composition. A duplicate key in the same scope (global overlaps every scope) is marked as `conflict` and warned through `onWarn` (default console.warn; `null` turns it off).
  - The Esc layer stack belongs to the app, not this package.

```tsx
<Sidebar items={routes} activeId={active} onNavigate={go} collapsed={c} onCollapsedChange={setC}
  messages={{ navLabel: "Main menu", collapse: "Collapse", expand: "Expand" }} />
<Gauge value={usage /* undefined when there is none */} label="5-hour window" noValueLabel="No usage information" />
<ProvenanceBadge layer={{ id, label, index }} variant="set" />
```

## Dependencies (what / why / alternatives)
No added runtime dependencies (only the react peer). Icons are passed by the caller as a ReactNode, and the dialog and toast are our own implementations (small and domain-independent). Alternatives: Radix UI or React Aria (to be swapped in behind an adapter if guaranteed focus and accessibility handling becomes necessary).

## Testing
`pnpm test` (from the package folder or the repository root; Vitest). `tokens.test.ts` parses tokens.css as text and checks that every `--ac-*` variable, utility class, and the rules for the 8 statuses that other packages read are defined. When testing another package on its own, load `tokens.css` in the test setup as well.
