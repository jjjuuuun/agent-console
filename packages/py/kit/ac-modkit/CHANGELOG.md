# Changelog

## Unreleased

- Settings warnings that also reach the web now carry a code and `details`: new `SettingsNotice` (`code`, `message`,
  `details`) and `SettingsNoticeCodes` (`plugins.unknown_disabled`, `plugins.disabled_distribution`,
  `plugins.disabled_distribution_nothing`, `plugins.disabled_module_id`, `plugins.disabled_module_id_nothing`,
  `secrets.provider_no_settings_hook`, `secrets.provider_unknown`). `HostPlugins.notices` and
  `SecretProviderSetup.notices` hold them; `warnings` is now a read-only property with the same messages (no longer a
  constructor argument). Message catalogs `locales/en.json` and `locales/ko.json` (entry point
  `agent_console.message_catalogs` `ac-modkit`) hold the code texts and the English of the `plugins.*` report
  reasons, which the terminal log line now prints in English. `host.MASKED_LINE_NOTE` (the comment on masked lines of
  the settings YAML snippet) is now English: `<masked value: set it as secret://name>`.
- `KindContribution.open_role` (default `None`): the web route role of the screen that opens an item of the
  contributed kind. The copy dialog kind list (`CopyKindInfo.open_role`, contracts 0.16.0) uses it. Additions only;
  the range `>=0.1,<0.2` stays.
- Terminal text is now English: `Assembly.warnings` (unknown module ids, bindings, options for modules without
  settings), `RemovedSetting.message()` (`The settings key … is no longer read. Move it to …`, `New location: …`,
  `… was removed. Delete it from the settings file`), log-only lines (module start, stop, build, migration, background
  task, event subscriber, WS relay, plugin and database factory loading), the standalone runner (`standalone.run`:
  help, report `warning:` lines, `check:` and settings errors), the `load_host_settings` shape error, and the secret
  provider settings hook error. Warnings that also reach the web (`plugins.disabled` unknown names, `secrets.providers`
  warnings in `HostPlugins.warnings` and `SecretProviderSetup.warnings`) keep their Korean text; only their log line
  is English. `FlagSetting.help` and `RemovedSetting.reason` are documented as English terminal text.
- The `plugins.disabled` unknown name warning of `load_host_plugins` recognizes common mistakes. For an installed
  distribution name it adds the entry point names of that distribution (the names to write); for a server module id
  (an `agent_console.server_modules` name) it adds a pointer to `modules.disabled` (`--disable-module`) and the entry
  point names of the same distribution. Other names get the same sentence as before.
- `WorkGate` and `DEFAULT_WORK_WAIT`: counting of background thread work plus closing (`run`, `close`, `reopen`,
  `wait_idle`, `close_and_wait`). Background task cancel and stop hooks wait for thread work in progress (used by
  `mod-logs` collection and `mod-memory` automatic cleanup).
- `LoopPublisher[T](publish, *, key=None)`: a publisher that moves notifications from other threads onto the bound
  event loop (consecutive notifications with the same key are sent once; after the bound loop closes they are dropped
  and counted in `dropped`). Merges `mod-memory` `LoopPublisher` and `mod-sdd` `ChangePublisher`.
- Definition kind contributions `KindContribution[K]{kind, references?, summary_fields}` and `KindReferences`, with
  the multi-provider port `DEFINITION_KIND_CONTRIBUTIONS` (`definitions.kind_contributions`). The kit does not know
  the type of kind values (a type parameter).
- `host.SpaceQuery` and `SPACE_QUERY` (the storage space query `?project=`, in route parameter form).
- `MigrationBranch.scopes` (default `("app",)`) and `ModuleContext.active_migrations(scope)`. The host upgrades only
  `app`-scope lineages in the app database (existing modules are unchanged).
- Assembly order. When breaking optional port cycles, sorting no longer removes every optional edge between cycle
  members; it keeps all required edges plus only the optional edges that do not create a cycle (single ports first,
  multi-provider ports later). Even when tied into a large optional cycle (strongly connected component), the
  settings provider to consumer order is kept.
- Settings compatibility cleanup: removed the mechanism that read and moved old keys (`MovedSetting`,
  `SettingsMove`, `migrate_settings`, `SettingsCompat.moved` and `SeedSetting.before_moves`). No declarations used it
  any more, and the policy is to not read old keys and reject them with `RemovedSetting`. Filling defaults is done by
  the new function `seed_settings(data, compats)`. Removed the move declaration from the example
  `ECHO_SETTINGS_COMPAT`. The change is within the unreleased 0.1.0 range, so the version is unchanged.
- Read-only view of module options. Core `read_module_options`, `ModuleOptions`, `mask_values`, `OPTIONS_MASK`,
  `SECRET_SCHEMA_KEY` and `SecretPathFinder`, and `Assembly.module_options(id)` (added the `Assembly.descriptors` and
  `Assembly.options` fields). Host `GET /modules/{id}/options` (`build_module_options_router`,
  `default_module_options_payload`, `create_host_app(options_payload=)`) and the YAML snippet `options_yaml_snippet`
  (masked lines carry the comment `MASKED_LINE_NOTE`, and objects or lists that become empty are `{}` or `[]`). There
  is one mask string, `OPTIONS_MASK` (`host.REDACTED` has the same value), and the host aligns it with the `mask=`
  argument. No writes.
- `RemovedSetting` gained `new` (the new location), a default `reason` and `message()`. Used to turn old keys whose
  read compatibility has ended into errors that point to the new location.

## 0.1.0

- `Assembly.routers(first_kinds=)` and the host `include_routers(app, assembly, prefix=,
  first_kinds=ROUTE_FIRST_KINDS)`: link module routers are attached first, so fixed subpaths (for example
  `/runs/handoffs`) are not shadowed by parameter paths of feature modules (`/runs/{run_id}`). `create_host_app` uses
  this.
- HTTP helpers `host.IfMatchHeader`, `if_match_version`, `etag`, `json_with_etag` and `attachment_response`
  (responses for versioned resources and content files, shared by modules).
- `DatabaseHandle` (protocol) and `MigrationBranch`, `ModuleDescriptor.migrations`; `assemble` runs
  `database.upgrade` for the lineages of enabled modules right before build (on failure only that module is
  `failed`), and `standalone.run(database=)`.
- First release (from the scripts/pkgkit template `kit`).
- Core: `PortKey(multi=)`, `Topic`, `ModuleDescriptor`, `ModuleParts`, `Module`, `ModuleContext`, `assemble`
  (topological sort, five states, bindings, multi lists), `EventBus` (subscriber exception isolation), `Hub`,
  `BaseServices` and `load_installed_modules`.
- Extra `[host]`: the security middleware, tokens, `/health`, WS multiplexing and log masking moved here from
  `apps/server` (same behavior), with `create_host_app` and `HostSettings`.
- `standalone.run(module, argv)`: `--with`, `--config`, `--host`, `--port 0` and `--check`.
- `testing`: `fake_module` and the example `EchoModule`.
- `ModuleDescriptor.contracts` and `ModuleReport.contracts` became a `{contract submodule: version}` mapping, with
  `ModuleReport.to_dict()`, `ModulesConfig.with_overrides(enable=, disable=)` (command-line enable and disable),
  `Assembly.start(fail_fast=)`, and `FeatureUnavailableError`, `FEATURE_UNAVAILABLE` and
  `ModuleContext.unavailable(key)`. Host: `GET /modules` (`build_modules_router`, `default_modules_payload`,
  `create_host_app(modules_payload=)`), `install_feature_unavailable` (409 `{module, port}`), and
  `feature_unavailable` in `DEFAULT_ERROR_STATUS`. The example `EchoModule` has `GET /echo/transformed` (409 without
  the optional port). An import-blocking test checks that the core imports and assembles without fastapi, uvicorn,
  websockets, ruamel or starlette.
- `ErrorReply`, `ErrorMapper`, `ErrorMapping` and `error_reply`: `ModuleParts.error_map` values take a function from
  exception to `ErrorReply` (code, message, `details`, headers) instead of a code string (handled by
  `install_error_map`). `standalone.run(default_with=, error_status=)`: modules to attach when `--with` is absent, and a
  table from error code to HTTP status.
