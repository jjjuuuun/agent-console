# Changelog

All notable changes to Agent Console are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The app version (server, CLI and
web) follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html). Internal packages and the API contracts have
their own versions and changelogs, listed at the end of each release.

## [Unreleased]

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

[Unreleased]: https://github.com/jjjuuuun/agent-console/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/jjjuuuun/agent-console/releases/tag/v1.0.0
