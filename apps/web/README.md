# @agent-console/web

The Agent Console web app (Vite + React 19, PWA). It is **a thin layer that only assembles packages**: presentational components and schema forms come from `packages/ts/lib/*`,
and the app itself owns only (1) boot (server address, token), (2) data hooks (TanStack Query), (3) routing and the shell, and (4) its own UI text bundles (`src/locales`).
Node types, edge types, resource types, interaction types, usage windows, models, log sources, log categories, widget types, dimensions, metric names and server module ids are not in the code (they are server descriptor or settings data; `src/app/moduleIdsNoHardcoding.test.ts` checks module ids).
The filter and column names of the log screens (`src/features/logs`) live in the data file `logsData.json`; periods, time constants and storage keys live in one place, `logsConfig.ts`.
`src/app/noHardcoding.test.ts` scans the sources to check this. The server (API + WS) and the web app are **separate processes**. The server does not know about the web app.

## Run
```bash
pnpm app                                              # root: server + web preview together
uv run agent-console serve                            # server only (default 127.0.0.1:8765)
pnpm --filter @agent-console/web dev                  # web dev server (Vite, HMR)
pnpm --filter @agent-console/web build                # tsc + vite build -> apps/web/dist (includes the PWA)
pnpm --filter @agent-console/web preview              # serve the build locally (check the service worker and install here)
```
The root `pnpm app` uses the `dev`/`preview` script names and `build`, so do not rename them.

### Server address (no port in the code)
At boot the app takes `apiBaseUrl` from `GET /config.json` (a static web file you can edit after deployment), then the build variable `VITE_AGENT_CONSOLE_API_URL`, and otherwise uses the **same origin**.
A missing file or an empty `apiBaseUrl` is not an error.
- Same origin: `dev`/`preview` proxy `/api` and `/ws` to the server. The target is `AGENT_CONSOLE_SERVER_URL` (preferred) or `AGENT_CONSOLE_HOST`/`AGENT_CONSOLE_PORT` (default 127.0.0.1 / 8765).
- Direct calls: put `{ "apiBaseUrl": "http://127.0.0.1:8765" }` in `config.json`. The server must allow the web origin (`serve --allow-origin …` or `security.allowed_origins`). When a connection failure looks like CORS, the screen shows that hint.

### PWA
`vite-plugin-pwa` generates the manifest and the service worker (registered only in build and preview). **The service worker caches static files only**: `/api`, `/ws` and `config.json` are excluded from caching and offline fallback.
A new version does not reload on its own; a toast announces it with a reload button (and asks first when there are unsaved changes). The install prompt is a sidebar button (when the browser fires the event) and Settings › Install app.

## Layout (`src/`)
| Folder | Role |
| --- | --- |
| `app/` | Boot (`config`, `boot`, `AppRoot`), API and query contexts (`ApiContext`, `queries`), message hooks (`appMessages`, `shellMessages`, `moduleMessages`, `settingsUiMessages`), hint banners (`hints`), storage (`storage`) |
| `i18n/` | Screen language assembly (the domain logic is in `@agent-console/i18n`): app bundles (`import.meta.glob('../locales/*/*.json')`; language and namespace names come from the file names, and only `boot` loads synchronously in the first chunk), lazy loaders for library package bundles (`libLocales.ts`), the first-screen language (`agent-console.language` → browser language → `en`), the language switch sequence (`languageController`: merges rapid switches within 250 ms, swaps everything at once after the bundles are ready, saves the single `ui.language` field), the language picker in Settings › Appearance (`LanguageSelect`, `LanguageSetting`), and `AppSchemaForm`/`AppShortcutProvider` (pass current-language text to the libraries) |
| `locales/<language>/<namespace>.json` | App text bundles. Adding a language = adding a folder (merged with the languages from the server's `GET /i18n` to form the choices). |
| `definition/` | Shared definition editing: `useDefinitionEditor` (draft, If-Match save, 412 conflict), `ConflictBanner`, `SaveStatus`, `UnsavedGuard` (leave protection) — also used by the team, agent and resource screens |
| `shell/` | App shell: route settings data (`routeConfig`), page table (`routes.tsx`), sidebar, quick navigation, help, keyboard shortcuts, waiting-for-you subscription, Esc stack |
| `pwa/` | Install prompt state (`installPrompt`), update notice adapter (`registerSw` is imported only by `main.tsx`) |
| `features/settings/` | Settings screen and sections, `UserSettingsForm` (the team screen reuses it), `LayerForm` (form wrapper that shows where each value comes from) |
| `lib/` | Pure functions (JSON Pointer, schema tools, shortcut validation, layer editing, formatting) |
| `testing/` | Test-only fakes and helpers (do not import from app code) |

Adding a screen: (1) add one entry to `DEFAULT_ROUTES` in `shell/routeConfig.ts` (the sidebar, the `g` shortcut, quick navigation and the document title follow automatically; also set the `serves` roles that other screens look up when they link here — feature code finds a route with `routePath(ROUTE_ROLES.*)`, not by route id), (2) add `routeId → child routes` to `DEFAULT_PAGES` in `shell/routes.tsx`.
The shell owns the default shortcut table, and the `ui.keybindings` setting overrides it (duplicate-key warnings appear only in development mode).

## Dependencies (what / why / alternative)
| Dependency | Why | Alternative |
| --- | --- | --- |
| `@agent-console/i18n` (the app imports only this; i18next and react-i18next stay inside that package) | Screen text in several languages (language resolution, bundle overlay, hooks, formatters) | Use i18next directly |
| `react` 19 · `react-dom` | Rendering | — |
| `react-router` ^7 | Routing, leave protection (`useBlocker`), memory-router tests | TanStack Router |
| `@tanstack/react-query` ^5 | Server state cache shared across screens, invalidation, refresh on window focus | The hand-written `useAsync` (the previous approach) |
| `pretendard` ^1.3.9 | Self-hosted default font (`src/styles/fonts.css` points at the woff2 files). Same font offline, no CDN | System fonts only |
| `vite-plugin-pwa` ^2 + `workbox-window` (dev) | Generates the manifest and the service worker (Workbox), installable app | Hand-written manifest and service worker |
| `yaml` ^2 | Reads and writes architecture map profile YAML in Settings (with line-numbered errors) | `js-yaml` (weaker error positions and comment preservation) |
| `@agent-console/contracts` | Server contract types and JSON Schema (generated from Pydantic) | — |
| `@agent-console/api-client` | REST and WebSocket client | — |
| `@agent-console/ui` | Tokens and base components (dialog, tabs, popover, …) | — |
| `@agent-console/schema-form` | JSON Schema settings forms (`x-ui` hints) | — |
| `@agent-console/graph-editor` | Team graph editing and display | — |
| `@agent-console/chat` | Conversation message list, composer, interaction cards | — |
| `@agent-console/log-view` | Log analysis tables, filters, session list, dashboards | — |
| `@agent-console/trace-view` | Run trace timeline | — |
| `@agent-console/text-editor` | Text, Markdown and JSON editors and diff | — |
| `@agent-console/list-arrange` | List sorting, grouping, collapsing | — |
| `@agent-console/projects` | Project status, space and copy plan helpers | — |

Package dependencies use `^x.y.z` ranges plus pnpm `linkWorkspacePackages` (no `workspace:` protocol).

## Tests
- Unit and screen tests (Vitest, happy-dom): from the repository root, `npx vitest run --project web [path] --maxWorkers=2`. The full TS check is `pnpm check` (ESLint, tsc, Vitest, dependency-cruiser). Under heavy load use `pnpm check -- --testTimeout=60000`. Tests pin the screen language to `ko` (`src/testing/setup.ts` sets the browser language to ko, and Playwright uses `locale: "ko-KR"`).
- Static checks: `src/app/noHardcoding.test.ts` and `moduleIdsNoHardcoding.test.ts` (hard-coding checks), `src/app/tokenConsumers.test.ts` (token definitions match their uses; the allowlist is `tokenAllowlist.json`). The scan for Korean string literals in the sources uses `src/testing/i18nScan.ts`; its allowlist (permanent exemptions such as example data, plus files still waiting for conversion) is `src/testing/i18nPending.json`.
- E2E (Playwright, fake backend): from the root, `pnpm e2e [part of a file name | -g title]`. It builds the web app and starts it with the server. Scenarios are in `apps/web/e2e/*.spec.ts`.
