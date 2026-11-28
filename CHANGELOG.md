# Changelog

All notable changes to Agent Console are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The app version (server, CLI and
web) follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Internal packages and the API contracts have
their own versions and changelogs, listed at the end of each release.

## [Unreleased]

## [1.1.1] - 2026-11-28

A patch release with two fixes. The server, the `agent-console` command and the web app all report version 1.1.1. The
API contracts are unchanged (0.16.1).

### Fixed

- **Korean marked as partly translated**: *Settings › Appearance › Language* and the **Change language…** list marked
  Korean as **Partly translated**, with thousands of missing texts shown in English. Korean is the language of the
  server source text (`modules.options.mod-i18n.source_language`), so its source text no longer counts as missing. Codes
  and namespaced text are still counted, and other languages are counted as before
  ([agent-console-mod-i18n](packages/py/modules/ac-mod-i18n/CHANGELOG.md) 0.1.1).
- **Missing Korean development guide**: the public repository now includes
  [docs/DEVELOPMENT.ko.md](docs/DEVELOPMENT.ko.md), so its links from the Korean README, the Korean user guide and this
  changelog work. The link in the 1.1.0 release notes points to the `v1.1.0` tag, which does not have the file; use
  this release instead.

### Package changelogs

- Languages: [agent-console-mod-i18n](packages/py/modules/ac-mod-i18n/CHANGELOG.md)
- Apps: [server](apps/server/CHANGELOG.md), [CLI](apps/cli/CHANGELOG.md)

## [1.1.0] - 2026-11-28

The app now runs in English or Korean, the model field fills itself with the models your account can use, and the
backend sign-in and connection test are one click away from any screen. The server, the `agent-console` command and
the web app all report version 1.1.0. The API contracts are at 0.16.1.

### Added

- **Screen language**: choose the language in *Settings › Appearance › Language*, or open **Quick navigation**
  (`Ctrl+K`) and choose **Change language…**. The default is **Automatic (browser language)**: the first browser
  language the app has, otherwise the server default language (English unless the administrator changes it). The
  choice is saved in the workspace settings (`ui.language`) and applies at once, without a reload. Dates, numbers and
  sorting follow the chosen language. Text that comes from the server (setting titles and descriptions, kind and module
  names, error and issue messages, backend status sentences, log event titles) is translated as well. English and
  Korean ship with the app.
- **Message catalogs, a new extension point**: screen text is per-language JSON data. Every built-in package ships
  `locales/en.json` and `locales/ko.json`; plugins ship their own catalogs the same way (entry point group
  `agent_console.message_catalogs`, see [docs/extending/i18n.md](docs/extending/i18n.md)). To change wording or add a
  language without changing code, put your own `<language>.json` files in a folder and list it in
  `modules.options.mod-i18n.catalog_dirs`. A language with missing text is marked **Partly translated** and shows the
  missing text in the fallback language. The new server module `mod-i18n` serves the merged catalogs
  (`GET /api/v1/i18n`, `GET /api/v1/i18n/{lang}`) and has the options `default_language`, `fallback_language`,
  `source_language`, `catalog_dirs` and `disabled_catalogs`. New packages: `agent-console-i18n`,
  `agent-console-mod-i18n` and `@agent-console/i18n`. The web libraries export their messages as `./locales/ko` and
  `./locales/en`.
- **Server sentences with values**: sentences that mix in values (backend status details and check notes, connection
  test, sign-in and sign-out messages, log event titles and summaries) also carry their source template and values
  (`text_templates`), so the web translates the sentence and keeps the values. `I18nInfo.source_language` tells the
  web which language the server source text is in.
- **Models from your account**: the model field (in *Settings › Agent defaults*, the agent editor and node settings)
  now lists the models the backend account can use, even when the administrator list `backends.<id>.models` is empty.
  The two lists are merged: configured models come first and win on the same id, and each option shows where it came
  from (**Config**, **Account** or both). Claude Agent SDK asks Claude Code for its start-up information when you use
  the subscription, and the Anthropic Models API when you use an API key. Neither calls a model, so the lookup costs
  nothing. The result is kept in server memory (one hour, failures one minute) and cleared when you sign in or out from
  the app. A line under the field shows the state, with **[Refresh]** and **[Check connection…]**; a failed lookup never
  blocks the field, and **Enter manually** still takes any model id. Turn the lookup off with
  `modules.options.mod-runs.model_discovery.enabled: false` (or per backend with `disabled_backends`), and tune the
  Claude Agent SDK lookup under `backends.claude-agent-sdk.model_discovery`. New route
  `GET /api/v1/backends/{id}/model-catalog?refresh=`; `GET /api/v1/backends/{id}/models` returns the merged list in
  the same shape as before. Backends opt in with the optional capability `discover_models` and
  `capabilities.model_discovery` ([docs/extending/backends.md](docs/extending/backends.md#backend-model-discovery)); the
  `fake-agent` backend and the example backend implement it.
- **Backend connection shortcut**: a **Backend connection** button (plug icon) is the first button in the icon row at
  the bottom of the sidebar. Its badge shows the state of the default backend. The same dialog opens from the
  **Backend · {state}** chip in the **Usage** header and from **Quick navigation** (`Ctrl+K`) → **Backend connection…**.
  The dialog has the backend status cards with sign-in, **[Test connection]**, **[Check again]** and the model line, and
  **More in Settings** goes to *Settings › Agent defaults*. The button, chip and command are left out when the server
  has no backend status feature.
- **Template version comparison**: the **Versions** tab of the template editor compares a saved version with the
  current one, or two versions with each other (`GET /api/v1/sdd/templates/{id}/versions/{a}/diff` and
  `…/diff/{b}`, returning `DefinitionDiff`). Connected to a 1.0.0 server, the web hides the comparison.
- **Wiki freshness window**: the administrator option `modules.options.mod-wiki.freshness_seconds` (default 2, `0`
  checks on every request).
- **Reserved ids right away**: new-name fields (for example in the copy dialog) say as you type when an id is a word
  that kind reserves. The server provides the words (`CopyKindInfo.reserved_ids`, `SddInfo.reserved_template_ids`);
  the web has no list of its own.
- The copy dialog and the project configuration rows offer **Open** for every kind that has a screen
  (`CopyKindInfo.open_role`, supplied by the kind data or the module that contributes the kind).
- A `plugins.disabled` entry that matches no plugin now gets a hint: for an installed distribution name, the entry
  point names to write; for a server module id, a pointer to `modules.disabled` (`--disable-module`).
- Contracts 0.16.1 (additions): `ModelInfo.sources`, `BackendCapabilities.model_discovery`, `BackendModelCatalog`,
  `ModelDiscoveryInfo`, the issue code `backend.model_discovery_failed`, `TextTemplate` with `render_text_template`,
  `text_templates` on the backend readiness, connection test, sign-in and sign-out responses and on `LogEvent`, and
  `I18nInfo.source_language`.

### Changed

- **Documentation is in English** by default: README, user guide, changelogs, the extension guide, the server and CLI
  READMEs and every package README. Korean copies: [README.ko.md](README.ko.md), [USAGE.ko.md](USAGE.ko.md) and
  [docs/DEVELOPMENT.ko.md](docs/DEVELOPMENT.ko.md).
- **Terminal output is in English**: the help and output of every `agent-console` command, `serve --help` (module
  options end with `(module <id>)`), server start and ready messages, log lines and settings errors. Error codes are
  unchanged, and the web shows the same errors in the chosen language by code.
- **The screen language follows the browser.** 1.0.0 always showed Korean. To keep Korean, choose it in
  *Settings › Appearance › Language*, or set the server default with `modules.options.mod-i18n.default_language`.
- **Wiki freshness check**: inside the freshness window (2 seconds by default), wiki reads reuse the last check of the
  wiki definition, rules, settings and page listing instead of checking on every request. Changes made through this
  server show at once; files edited in another editor can show up to one window later. **Rescan** checks right away.
- Settings warnings in `GET /api/v1/server-info` keep their code and `details`, so the web shows them in the chosen
  language.
- Page header actions fold by measured width, so longer English labels do not overflow.

### Removed

- `WorkspaceSettings.default_backend` (contracts 0.16.0). The server no longer reads it; use `agent_defaults.backend`.
  See Breaking changes.
- `@agent-console/projects` 0.3.0: the log filter helpers `applyLogFilter` and `logFilterFor` and the types
  `LogProjectRef` and `ProjectLogFilter`.

### Fixed

- Team graph edge labels: label chips keep a minimum gap from each other, no longer cover node ports, and fold into an
  icon with a count when there is no room (hover or focus shows the full chip). The spacing is a graph editor prop with
  a default value. A team opens at the same zoom whether or not the web font has arrived, and nodes in read-only run
  graphs no longer overlap by a few pixels.
- Usage screen: chips in the table note column and in the header status line no longer touch each other.
- Runs: a page left open refreshes the start of its period, so runs that fall out of the period leave the list. Runs
  started without a chat show their input summary in the list.
- Projects: the delete confirmation says when the items that use a configuration cannot be checked, instead of showing
  an empty list. The import guide no longer repeats the word "folder".
- Folder picker: the primary button keeps enough text contrast on hover.
- Team editor: an edge classification value the editor does not know is shown as written.

### Breaking changes

#### Upgrading from 1.0.0

- **No data migration is needed.** A workspace `settings.yaml` or export bundle that still has `default_backend` is
  read as before (the key is kept as an unknown key) and the server starts. The value is no longer used: the server
  reports an info issue `settings.ignored_key` (`details.key = "default_backend"`,
  `details.replacement = "agent_defaults.backend"`). Set the backend in *Settings › Agent defaults*
  (`agent_defaults.backend`). If no layer sets a backend, the pre-run check reports `backend.unresolved` with a fix
  button.
- Plugins and other API clients must move to contracts 0.16: `agent-console-contracts>=0.16,<0.17` (Python) and
  `@agent-console/contracts@^0.16.0` (TypeScript). Clients that read the 0.16.1 fields need `>=0.16.1` / `^0.16.1`.
  0.x contract minors are not compatible with each other; a 0.16 web app connected to a 0.15 server, or the reverse,
  shows the contract version warning.

#### Contracts 0.16.0

| Removed | Use instead |
| --- | --- |
| `WorkspaceSettings.default_backend` | `WorkspaceSettings.agent_defaults.backend` |

Also in 0.16.0 (additive): the `i18n` submodule (`I18nInfo`, `LanguageInfo`, `MessageCatalog`),
`UiPreferences.language`, the error code `i18n.unknown_language` (404), the catalog issue codes `i18n.*`, the widget
name `language`, `CopyKindInfo.reserved_ids`, `CopyKindInfo.open_role` and `SddInfo.reserved_template_ids`.

#### Package APIs

- `agent-console-teams` 0.2.0 and `agent-console-link-runs-teams` 0.2.0: the common layer and `TeamRules` no longer
  read `WorkspaceSettings.default_backend`. The node service key `DEFAULT_BACKEND` and the `default_backend` argument
  (the last fallback a host injects) remain.
- `@agent-console/projects` 0.3.0: removed `applyLogFilter`, `logFilterFor`, `LogProjectRef` and `ProjectLogFilter`,
  which had no web consumers. Build the log query filter `project=<id>` directly (from `LogSessionSummary.project_id`).

### Known limitations

- Automated tests run on the fake backend. Real Claude Agent SDK runs (session resume, subscription sign-in in a
  terminal, spec task runs, wiki tools handed to agents), model lookups against a real account, and some platform
  setups (Windows file system details such as junctions, case-insensitive and network drives; the native folder picker;
  IME input; SQLite builds without FTS5; very large wikis; binding to non-loopback addresses; performance on an idle
  machine; installed third-party usage sources) are outside the automated checks. Check these combinations in your own
  environment.
- The model list follows the authentication that the backend status card checks (`readiness.auth`, the subscription
  by default); agents with a different `backend_options.auth` do not get a list of their own, so type their model id.
  The subscription list is what the installed Claude Code CLI reports, so a CLI version that reports no models shows
  only configured models. Without a sign-in (or without the API key for `readiness.auth`) the lookup does not start and
  the field shows `auth_missing`.
- Whether the terms of service allow subscription credentials with the Agent SDK has not been confirmed (Anthropic's
  documentation recommends API keys for apps built on the Agent SDK). Check the terms yourself and use it at your own
  risk.
- Only app text is translated. Names, descriptions, instructions and prompts you write, text written by agents, and
  log contents are never translated. Text from an extension that ships no message catalog, and default text an
  administrator changed in settings, appear as written unless a catalog in `catalog_dirs` covers them. Code comments,
  docstrings and the source text of the contract schema descriptions are mostly in Korean (the screen shows the
  descriptions through the message catalogs).
- Packages are not published to PyPI or npm. Install from source.

### Package changelogs

- Contracts: [Python](packages/py/base/ac-contracts/CHANGELOG.md),
  [TypeScript](packages/ts/lib/contracts/CHANGELOG.md)
- Languages: [agent-console-i18n](packages/py/features/ac-i18n/CHANGELOG.md),
  [agent-console-mod-i18n](packages/py/modules/ac-mod-i18n/CHANGELOG.md),
  [@agent-console/i18n](packages/ts/lib/i18n/CHANGELOG.md)
- Model lookup: [agent-console-runtime](packages/py/features/ac-runtime/CHANGELOG.md),
  [agent-console-backend-claude-sdk](packages/py/features/ac-backend-claude-sdk/CHANGELOG.md),
  [agent-console-mod-runs](packages/py/modules/ac-mod-runs/CHANGELOG.md),
  [@agent-console/api-client](packages/ts/lib/api-client/CHANGELOG.md)
- Default backend removal: [agent-console-teams](packages/py/features/ac-teams/CHANGELOG.md),
  [agent-console-link-runs-teams](packages/py/links/ac-link-runs-teams/CHANGELOG.md)
- Log filter helpers: [@agent-console/projects](packages/ts/lib/projects/CHANGELOG.md)
- Templates and wiki: [agent-console-mod-sdd](packages/py/modules/ac-mod-sdd/CHANGELOG.md),
  [agent-console-mod-wiki](packages/py/modules/ac-mod-wiki/CHANGELOG.md)
- Apps: [server](apps/server/CHANGELOG.md), [CLI](apps/cli/CHANGELOG.md)
- Every other package under `packages/` keeps a `CHANGELOG.md` next to its README.

## [1.0.0] - 2026-11-26

First stable release. The server, the `agent-console` command and the web app all report version 1.0.0. The API
contracts are at 0.15.0.

### Highlights

- **Team graphs and execution engine**: build teams of agents on a visual graph editor with conditions, loops,
  parallel branches, delegation between agents, sub-teams, and questions or approvals that come back to you during a
  run. Node types, edge types and execution backends are plugins, and nothing is pre-installed: the server starts
  with an empty workspace.
- **Chat**: pick a team, send it a task, and answer the agents' questions while the run is going.
- **Projects**: register local folders. The app only works inside registered folders and its own workspace. Chats,
  runs, logs, memory, wiki and specs are kept per project, and each project copies what it needs from a shared
  configuration library.
- **Observability**: run history and run detail with the delegation flow, hook events, MCP tool calls, timing and
  errors; an architecture map of agents, hooks and MCP servers; Claude Code session logs with search, timelines and
  dashboards; usage windows and token totals from runs, session logs and the status line bridge.
- **Wiki, memory and specs**: a project wiki with a link graph and rule checks, shared memory that agents can read and
  write, and spec documents with task tracking. Templates, rules and classifiers are your data.
- **Extension points and plugins**: node types, edge types, condition operators, backends, log sources, classifiers,
  usage sources, import and export formats, resource types, secret providers, wiki checks and whole server modules
  are added as plugin packages. Each backend feature is a module you can turn on or off, and an extension guide with
  one example plugin per extension point is included.
- **Import, export and versions**: import agents and settings from a project's `.claude/` folder (originals are only
  read), export to a zip file or a Claude Code folder layout, and restore any earlier version of a definition.

### Breaking changes

#### Upgrading from 0.x

- **No data migration is needed.** Old keys in workspace `settings.yaml`, `project.yaml` and export bundles are still
  read (kept as unknown keys) and never stop the server from starting.
- Plugins and other API clients must move to contracts 0.15: `agent-console-contracts>=0.15,<0.16` (Python) and
  `@agent-console/contracts@^0.15.0` (TypeScript). 0.x contract minors are not compatible with each other; a 0.15 web
  app connected to a 0.14 server, or the reverse, shows the contract version warning.
- If you call the three removed REST endpoints below, or use the removed package APIs, switch to the replacements in
  the tables.

#### Contracts 0.15.0

Contracts 0.15.0 removes the project-scope APIs that were deprecated in 0.11–0.12.

| Removed | Use instead |
| --- | --- |
| `MovePlan`, `MovePlanRequest`, `DefinitionMove` | Definitions no longer belong to a project. To clean up old definitions that still have a `project` field, use the copy plan: `POST /api/v1/projects/{id}/legacy/plan`, then `POST /api/v1/projects/copy/apply`. |
| `DeletePlan`, `ProjectDeleteMode` | `DELETE /api/v1/projects/{id}` unregisters (archives) a project. It never deletes definitions and takes no `mode`. |
| `WorkspaceSettings.projects` (`ProjectPreferences`, `DefinitionScope`) | Nothing. A new definition is saved in the space where you create it (the shared library or a project). |
| `LogSettings.projects` (`LogProjectSettings`, `LogProjectGroup`) | Nothing. A log session belongs to the registered project whose folder contains its working directory. |
| `LogSessionSummary.project` (`LogProjectRef`) | `LogSessionSummary.project_id`. Get the display name from `GET /api/v1/projects`. |
| `KnownIssueCodes.PROJECT_MEMORY_NETWORK_FS` (`project.memory_network_fs`) | `KnownIssueCodes.PROJECT_NETWORK_FS` (`project.network_fs`). Servers have sent only the new code since 0.12.1. |
| `KnownIssueCodes.PROJECT_SHARED_USES_PROJECT`, `PROJECT_CROSS_PROJECT`, `PROJECT_DEFINITIONS_UNAVAILABLE`, `KnownSuggestionIds.PROJECT_MOVE_TO_SHARED` | Nothing. No server sends them. `KnownSuggestionIds` stays and is currently empty. |
| Python: `Project.working_directory`, `Project.log_projects` | `Project.folder`; `log_projects` was always empty. Files that still use `working_directory` are read as `folder`. |

Also in 0.15.0 (additive): `MemoryChanged.space`; error and issue code `project.memory_unavailable` (409, replaces
`feature_unavailable` when a project's memory database cannot be opened); `WikiInfo.wiki_kind` and
`WikiInfo.reserved_page_names`; wiki graph `depth=all` (constant `WIKI_GRAPH_DEPTH_ALL`) and `WikiGraph.depth`;
`WikiRuleEntry.severity` narrowed to `"error" | "warning" | "info" | null`. `LOG_PROJECT_UNGROUPED` (`~ungrouped`) is
no longer deprecated.

#### Removed REST endpoints

`POST /api/v1/projects/move-plan`, `POST /api/v1/projects/move` and `POST /api/v1/projects/scope-issues` are gone.
They now answer `405 Method Not Allowed` because the path matches `/api/v1/projects/{id}`.

#### Settings that are read and ignored

If your workspace `settings.yaml` still has `projects` (for example `projects.new_definition_scope`) or
`logs.projects`, the server starts, ignores the key, and reports an info issue `settings.ignored_key` with
`details.key`. Remove the key when convenient. Old project-file keys keep their behavior: `working_directory` is read
as `folder`; `log_projects`, `uses` and `import_mode` are dropped on save. The `mod-projects` option
`snapshot_ttl_seconds` is still accepted but no longer read.

#### Package APIs

- `@agent-console/projects` 0.2.0: removed the scope, badge and move-plan helpers, `createProjectsClient`,
  `configDirLabel`, and the `projects.dir_fallback` message. Use `@agent-console/api-client` for project REST calls.
- `agent-console-projects` 0.3.0: removed the old definition-scope rules `visible`, `scope_issues`, `move_plan`,
  `delete_plan` and their constants. Use `legacy_items`, `legacy_counts` and `copy_plan`.
- `agent-console-mod-projects` 0.3.0: removed `ScopeService` and `DefinitionSnapshot` together with the three REST
  endpoints above.
- `agent-console-exports`: the `ExportCatalog` protocol has a new method `content(kind, id)` that reads a definition
  whose body is a single file. If you build your own catalog, add this method (return `None` when there is no body).

### Known limitations

- Automated tests run on the fake backend. Real Claude Agent SDK runs and some platform setups (Windows file system
  details, the native folder picker, IME input, SQLite builds without FTS5, very large wikis, binding to non-loopback
  addresses) are outside the automated checks. Check these combinations in your own environment.
- The web UI and most documentation, including the package changelogs, are in Korean for now.
- Packages are not published to PyPI or npm. Install from source.

### Package changelogs

- Contracts: [Python](packages/py/base/ac-contracts/CHANGELOG.md),
  [TypeScript](packages/ts/lib/contracts/CHANGELOG.md)
- Projects: [agent-console-projects](packages/py/features/ac-projects/CHANGELOG.md),
  [agent-console-mod-projects](packages/py/modules/ac-mod-projects/CHANGELOG.md),
  [@agent-console/projects](packages/ts/lib/projects/CHANGELOG.md)
- Exports: [agent-console-exports](packages/py/features/ac-exports/CHANGELOG.md),
  [agent-console-mod-exports](packages/py/modules/ac-mod-exports/CHANGELOG.md)
- Apps: [server](apps/server/CHANGELOG.md), [CLI](apps/cli/CHANGELOG.md)
- Every other package under `packages/` keeps a `CHANGELOG.md` next to its README.

[Unreleased]: https://github.com/jjjuuuun/agent-console/compare/v1.1.1...HEAD
[1.1.1]: https://github.com/jjjuuuun/agent-console/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/jjjuuuun/agent-console/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/jjjuuuun/agent-console/releases/tag/v1.0.0
