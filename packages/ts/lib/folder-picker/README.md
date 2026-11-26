# @agent-console/folder-picker

Folder selection: a primary [Select folder…] button (the OS picker window or in-app browsing), a box for the selected folder, a collapsed manual entry, the check result, a browse panel (virtual list), and a middle-ellipsis path display. It knows nothing about the server (api-client).
It takes `check`, `list`, `createFolder`, and `onPickNative` as callback props, so it can attach to any backend.

## Installation
Inside the repository, `pnpm install` links the local package. Outside the repository, install the tarball (`pnpm pack:all` → `dist/npm`).

```sh
npm install ./agent-console-folder-picker-0.1.0.tgz
```

Peers: `react` and `react-dom` 19. Dependency: `@tanstack/react-virtual` (the virtual list for browsing; alternative: custom windowing — we use a proven library).
The app loads `tokens.css` (the `--ac-*` variables) from `@agent-console/ui` and this package's `@agent-console/folder-picker/styles.css` once each.

## Minimal usage
```ts readme
import { deriveCheckState, middleEllipsis } from "@agent-console/folder-picker";

const short = middleEllipsis("/data/work/payments/services/api", 27);
const state = deriveCheckState("/srv/app", {
  kind: "checked",
  check: { input: "/srv/app", path: "/srv/app", exists: true, is_dir: true, readable: true, writable: true, can_create: false },
});
```

`short` is `"/data/work…/services/api"`, and `state.id` is `"ok"` (can be submitted). This block must match `test/readme.test.ts`.

The screen is used as a single container.

```tsx
<FolderPicker
  id="add-folder"
  value={path}
  onValueChange={setPath}
  check={(req, signal) => api.checkFolder(req, signal)}   // returns a FolderCheckOutcome
  list={(req, signal) => api.listFolders(req, signal)}    // FolderListingData
  createFolder={(req, signal) => api.createFolder(req, signal)}
  roots={roots}
  capabilities={caps}                                      // { browse, native_dialog } or null (still loading)
  onPickNative={(initial, signal) => api.pickFolder({ initial }, signal)}   // FolderPickOutcome
  configDir=".my-config"                                   // optional: the "Creates the {dir} folder" line and text
  autoFocus
  onStateChange={(s) => setCanSubmit(s.submittable)}
  onSelectPhaseChange={(p) => setPicking(p === "waiting")}
  onSubmit={submit}
/>
```

- **Selection first**: the first focus goes to [Select folder…]. When `capabilities.native_dialog === true` (or is not yet known, which is null) and `onPickNative` is given, it opens the OS picker window; otherwise the same button opens the in-app browse panel. With `browse: false`, the button is disabled and manual entry opens automatically.
- **Selection flow**: waiting (`waiting`: [Cancel selection], the "If you don't see the window" hint, and after 30 seconds [Browse in the app]) → `picked`, `cancelled`, `unavailable`, `busy`, `timeout`, or `failed`. `unavailable` and `failed` (including a reject, and unknown values) open the panel automatically, and after `unavailable` the same button opens the panel directly. Esc while waiting cancels the selection (it is not passed up to the parent dialog). `onPickNative` must cut the request when `signal` is aborted.
- **Check timing**: a selected path (from the picker window, browsing, a paste, blur, or Enter) is checked immediately; only a value typed in the collapsed "Enter the path manually" is debounced by 300 ms. When the `onPickNative` result carries a `check` (or an `outcome` that includes the conflict), no new request is made. Stale responses are discarded.
- `check` returns a 409 (already registered or overlapping) and a 403 (remote blocked) as `taken`, `overlap`, and `remote_disabled` in `FolderCheckOutcome`. Any other failure is a reject, which shows "Couldn't check".
- Existing configuration notice: if `FolderCheckData.manifest` (an optional field) is present, the notice is `manifest_found` (info, with name and count), and if `valid: false`, `manifest_invalid` (warning). Without it, no notice is drawn. A folder that cannot be written to is `ok_readonly` (with the `{dir}` text when `configDir` is given).
- Changing a path: pass `excludeProjectId` (sent with the request) and `currentFolder` (same-path detection; the start location of the picker window and browsing before a selection is made).
- Text comes from `messages` (partial override), and colors are tokens. No module, feature, or folder names are in the code (`configDir` comes from the app).

## Text and language
The default text is Korean (`src/locales/ko.json`, `defaultMessages`), and an English bundle ships alongside it. There is no dependency such as i18next. Placeholders are `{name}`, filled by `formatMessage`.
`ko` and `en` have the same keys and placeholders (`test/locales.test.ts` checks this). To use English, pass one bundle as `messages`.

```tsx
import en from "@agent-console/folder-picker/locales/en";

<FolderPicker id="add-folder" value={path} onValueChange={setPath} check={check} list={list} roots={roots} messages={en} />
```
The Korean bundle is `@agent-console/folder-picker/locales/ko`. To change only part of a bundle, spread it and override, as in `messages={{ ...en, "folder.pick.action": "Browse…" }}`. For a new language, build an object with the same keys and pass it in. The component source contains no Korean strings (the same test checks this).

## Contents
| Name | Role |
| --- | --- |
| `FolderPicker` | The container that combines the selection button, the selected folder box, the status line, the collapsed manual entry, the result, and browsing |
| `SelectedFolder` / `FolderPickStatusLine` | The selected folder box and the selection flow status line (presentational parts) |
| `FolderPathInput` / `FolderCheckResult` / `FolderBrowser` | Presentational parts (each usable on its own) |
| `useFolderCheck` | A hook for debouncing, immediate checks, and discarding stale responses |
| `deriveCheckState` / `browseStartPath` | Check result → screen state, and the browse start location (pure functions) |
| `middleEllipsis` / `MiddleEllipsisPath` | Middle-ellipsis for paths (a pure function plus a ResizeObserver component) |

## Development and standalone reuse
- `pnpm build`, `pnpm typecheck`, `pnpm lint`, and `pnpm test` each run on their own inside this folder.
- The public API is only the paths listed in `exports`. Other packages do not import `src/` or `dist/` directly.
- To check that the package still works when copied out of the repository, run `pnpm portability --package folder-picker`.
