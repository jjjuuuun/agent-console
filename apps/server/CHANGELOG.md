# Changelog

## Unreleased

## [1.1.0] - 2026-11-29

- Raised the display version to 1.1.0 (`project.version`). `server_version` in `/health`, `/bootstrap` and
  `/server-info` and the OpenAPI `info.version` still come from the installed metadata.
- Moved to contracts 0.16 (`agent-console-contracts>=0.16,<0.17`); `/bootstrap` reports `contracts_version` 0.16.1.
  A workspace `settings.yaml` that still has the removed key `default_backend` starts as before: the value is not
  used, and `/server-info` reports the info issue `settings.ignored_key` (`details.key = "default_backend"`,
  `details.replacement = "agent_defaults.backend"`).
- The server now bundles the language module `mod-i18n` (dependency `agent-console-mod-i18n`), which serves the merged
  message catalogs (`GET /api/v1/i18n`, `GET /api/v1/i18n/{lang}`). Turn it off with `--disable-module mod-i18n`; the
  routes then return 404, the web app uses only its own catalogs and server text stays as the original.
- Raised the dependency ranges to 0.2 for `agent-console-backend-claude-sdk`, `agent-console-backend-fake-agent`,
  `agent-console-mod-runs`, `agent-console-link-runs-teams`, `agent-console-link-logs-runs`, `agent-console-mod-sdd`
  and `agent-console-mod-wiki`. These bring the model lookup (`GET /api/v1/backends/{id}/model-catalog`), text
  templates on backend and log sentences, template version comparison and the wiki freshness window.
- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `server`, so the web app can show the `plugin_load_failed`, `plugins.config` and
  `settings.removed_key` codes in English (data only, no API change).
- Settings warnings in `GET /server-info` `warnings` keep the code and `details` of the modkit `SettingsNotice` (for
  example `plugins.unknown_disabled` with `details.name`), so the web app picks the text in the current language.
  Warnings that come as plain text still use `plugins.config`.
- Terminal text is now English: the `serve` help (module option help gets a `(module <id>)` suffix), startup and ready
  log lines, and `ConfigError` messages (`Invalid settings (settings.removed_key): …`, `Invalid settings: …`, settings
  file read and shape errors, non-loopback bind, unknown module option). Error codes (`ConfigError.code`, `removed`)
  are unchanged. Responses to the web app (error bodies, `/server-info` warnings, schema text) keep their Korean
  original text; the web app translates them by code.

## 1.0.0

- Raised the display version to 1.0.0 (`project.version`). `server_version` in `/health`, `/bootstrap` and
  `/server-info` and the OpenAPI `info.version` are read from the installed metadata (no code change; added a test
  that keeps the values aligned). The contract version stays at 0.15.0. The README public API table lists
  `server_version()`.
- README update (no code change): moved the history sentences of the README here and kept only descriptions of the
  current behavior. Moved history: the router (`ac-routing`), terminal console (`ac-console`) and `ac-client` packages
  and the WS `console.*` messages were removed in an earlier version. The WS `graph:` topic and the monolithic module
  were removed later. The chat queue has been stored in the server database (`chat_queue`) since the chat split
  (before that, in server memory). The default of `mod-imports.project_dir` is the settings file folder. The default of
  claude-agent-sdk `allow_subscription_auth` is `true`. The README module table was rebuilt from the installed entry
  points (10 feature modules and 11 link modules), and a backend sign-in (`backend_login`) section was added.
- Removed the presets feature: dropped the dependency `agent-console-mod-presets`. The route `/presets`,
  `serve --apply-preset` and the environment variables `AGENT_CONSOLE_PRESET_DIRS` and `AGENT_CONSOLE_APPLY_PRESETS`
  are gone. When `presets` or `modules.options.mod-presets` remains in the settings, the server refuses to start with a
  "The presets feature was removed" settings error (`settings.removed_key`, declared by `mod-definitions`).
- Settings compatibility cleanup: removed the host table of removed keys `REMOVED_KEYS` (`console` and
  `default_manual_route_pattern` from an early version). A leftover `console:` and similar keys are general settings
  errors (`extra="forbid"`). Removed the read compatibility mechanism `MovedKey`, `SETTINGS_MOVED_KEY`,
  `ServerSettings.moved_keys` and `migrate_moved_keys`, and the `settings.moved_key` warning of `/server-info`.
  Rejection of removed keys (`RemovedKey`, `SETTINGS_REMOVED_KEY`) and default filling (`SeedSetting`, modkit
  `seed_settings`) are unchanged. Fixed history comments in `_ws.py` and `testing.py`.
- Command-line option parsing is merged into `main` (`agent-console serve` calls it too). Moved
  `--allow-origin ORIGIN` (repeatable) and the public function `merge_origins` from apps/cli, and added `-c` for
  `--config`. `main(argv, *, prog="agent-console-server", modules=None)`: `prog` is the command name in help and error
  lines, and `modules` is the modules to read options from and assemble (None means the installed modules).
  `serve(..., modules=None)` passes them to `create_app(modules=)`. Settings error lines go to standard error instead
  of standard output (exit code 2 is unchanged).
- Added `agent-console-link-projects-runs` to the install dependencies (fixes a defect: installing only the server left
  out the project run scope link module).
- Removed read compatibility for old top-level settings keys. When they remain,
  `ConfigError(code="settings.removed_key", removed=[RemovedKey])` points to the new location (`SETTINGS_REMOVED_KEY`
  and `RemovedKey` are public). All removed keys are reported at once. Added `testing.make_settings(options=)` and
  documented the httpx requirement of `testing`.
- Added `agent-console-mod-logs`, `agent-console-logs-claude` and `agent-console-hook-probe` to the install dependencies
  (the logs feature module and the default log source plugins, loaded through entry points). The server code did not
  change.

## 0.1.0

- Set up as a standalone project: internal dependencies are declared by name and version range, with per-package
  pytest, mypy and ruff settings, a `dev` dependency group, LICENSE and CHANGELOG. No behavior changes.
- The server became a host: `create_app` assembles modules with the modkit `assemble`. All current features were
  wrapped in a temporary monolithic module `server-monolith` (`MonolithModule`, same behavior). Added the host route
  `GET /modules` (`ModuleInfo[]`), and moved `GET /bootstrap` to a host route (same path and response). Server
  administrator setting `modules`, `python -m agent_console_server --enable-module/--disable-module`,
  `create_app(modules=)`, `apply_module_flags`, `module_info` and `installed_modules`. `FeatureUnavailableError` gives
  409 `feature_unavailable` `{module, port}`. Feature routers are built without a prefix, and the app mounts them under
  `/api/v1`.
- Split usage, imports, exports, presets and versions into feature modules (`agent-console-mod-*`, entry points). The
  monolithic module provides the ports these modules use (`definitions.store`, `definitions.lookup`,
  `definitions.checks`, `secrets.rules`, `workspace.settings`, `exports.dependencies`, `usage.*`) and publishes the
  module event `definitions.saved` on every definition save. The web roles `usage`, `imports`, `exports`, `presets` and
  `versions` moved to their modules. The plugin registries are loaded once in `create_app` and passed as the base
  service `registries` (`_plugins.load_plugins`). The settings `presets`, `usage`, `imports`, `exports` and `versions`
  moved to `modules.options.<module id>` (with read compatibility for the old keys and a `settings.moved_key` warning in
  the startup log and `/server-info` `warnings`). Removed `apply_presets`, `list_presets` and `PresetNotFoundError` from
  the public API (moved to `agent-console-mod-presets`), removed `ServerSettings.preset_paths` and the `usage`,
  `imports`, `exports` and `apply_presets` of `ServerContext`, and added `build_context(plugins=, on_saved=)`. Removed
  presets and settings from the dependencies.
- Definitions and resources split: the definition store, agent, team and common settings CRUD, secret rules and
  plain-text checks moved to `mod-definitions`; resource routes, `/resource-types` and `/merge-strategies` to
  `mod-resources`; the pre-save checks (`DefinitionChecker`) to `link-definitions-resources`; usage, effective
  settings, run plans and bundle previews to `link-definitions-teams`; and export dependencies to `link-exports-teams`
  (removed `_checks.py`, `_secret_rules.py`, `_rest_graph_views.py`, `_rest_resources.py` and
  `_rest_resource_files.py`). The monolithic module takes `definitions.store`, `workspace.settings` and
  `secrets.rules` (required) and provides `graphs.validation` and `secrets.redact`. Only the web roles `runs` and
  `conversations` remained. The plain-text check cache is invalidated on `definitions.saved` (plus deletes) instead of
  by the write request middleware. The settings `resources.*` moved to `modules.options.mod-definitions` (with old key
  reads and a warning). `build_context` takes the definition store, settings and secret rule ports as arguments (the
  public name `definition_kinds` is removed and moved to mod-definitions).
- Chat split: the conversation, turn, message and queue routes and WS `conversation:` moved to `mod-chat`; starting
  and resuming conversation turns (`runs.resume_handlers`), notifications from the `runs.event` subscription, the
  restart queue policy and the shutdown order moved to `link-chat-runs` (removed `_context.py`, `_rest_chat.py`,
  `_rest_queue.py` and `_rest.py`). The monolithic module is a shell with only WS `graph:` left
  (`MonolithModule(server_version=)`, no ports, hooks or web roles, only the contract `modules`). Removed
  `ServerContext`, `build_context` and `RuntimeTurnLauncher` from the public API (moved to
  `agent-console-link-chat-runs.RuntimeTurnLauncher`); there is no `app.state.ctx`; removed the app-level `ChatError`
  handler (module error maps instead); removed `agent-console-chat` from the dependencies and added
  `agent-console-mod-chat` and `agent-console-link-chat-runs`. The conversation store uses the host database handle
  (it does not open its own).
