# Server host and modules

The server app does not know feature names. Features come in as server modules, and the basic services (the plugin
registry set, plugin loaders, the DB) come in through host extension entry points. This page covers those points and
the shared points through which a module contributes to other modules (definition kinds, DB migration scopes, run
labels). How to build a module itself is in [Server modules](modules.md) and [Link modules](links.md). This page covers
only what differs per point.

| What you want to do | Point |
| --- | --- |
| Add a new feature (REST, storage, settings section) to the server | [server-module](#server-module) |
| Add a new definition kind to the definition store | [definition-kind-contribution](#definition-kind-contribution) |
| Keep a module's DB tables in project record DBs as well | [migration-scope](#migration-scope) |
| Tag runs to group and filter them | [run-labels](#run-labels) |
| Use the definition library with storage other than files | [definition-store](#definition-store) |
| Change the basic services while embedding the server in another app | [host-registries](#host-registries), [host-plugin-loader](#host-plugin-loader), [host-database](#host-database) |

The last three host points are for people who embed the server in another app or replace a basic service entirely.
You do not need them to build plugins or modules.

## definition-kind-contribution

**When to use**: when a module wants to keep its data as definitions that users edit (YAML files in the workspace,
version history, usage display, export, and project spaces included). These are things users create and edit on
screens and in files, such as document templates, rule sets, and profiles.

**Minimal shape**: put `provides=[DEFINITION_KIND_CONTRIBUTIONS]` (the port `definitions.kind_contributions`,
multi-provider) in the module descriptor, and in `build` call
`ctx.provide(DEFINITION_KIND_CONTRIBUTIONS, KindContribution(kind, references=, summary_fields=))` once per kind.
`kind` is the kind rule of the definition store (`DefinitionKind`: name, folder, validation model, body mode,
`library`, `portable`). The definitions module collects them and registers them in the store.

**Rules**

- Name the kind and its folder with your module prefix. They must not collide with built-in kinds (`agent`, `graph`,
  `resource`, and so on).
- `references` is a pure function that extracts the list of references to other definitions, `(kind, id)`, from one
  document. It is used for usage display and for warnings before deletion. Consumers swallow its exceptions, so
  references silently go missing. Check it with tests.
- Use a contract-side Pydantic model as the validation model. The model decides whether to accept or reject unknown
  keys.
- Your module must start even when the definitions module is off. You **provide** this port, so without a consumer it
  simply goes unused.

**Common mistakes**: storing the kind's documents separately in the module's own DB tables. Then versions, export,
and project spaces do not come with them. Keep what users edit as a definition kind, and what accumulates, such as run
results, in your own tables.

**Data left after removal**: when you turn off or remove the module, the kind is not registered and does not appear
in lists or on screens. The kind's folders and files in the workspace stay, and they show again when you turn the
module back on.

<!-- extdocs:facts definition-kind-contribution -->
- Registration: A server module provides the port `definitions.kind_contributions` (symbol `agent_console_modkit:DEFINITION_KIND_CONTRIBUTIONS`, multiple: yes).
- Interface:
  - `agent_console_modkit:KindContribution` — The contribution for one definition kind.
  - `agent_console_modkit:KindReferences` — The ``(kind, id)`` a contributed-kind document uses (reference closure of the copy plan).
  - `agent_console_modkit:KindDelete` — Delete one item of a contributed kind ``(space, id, expected version)``.
- Built-in implementations: `mod-sdd`, `mod-wiki`
- Examples:
  - package: [examples/extensions/agent-console-example-module](../../examples/extensions/agent-console-example-module/README.md)
- Turning it off or removing it: Turn off the providing module (`modules.<id>.enabled: false`); consumers turn off only the parts that use it.
<!-- /extdocs:facts -->

## definition-store

**When to use**: when you use the definition library (`agent-console-store`) in another script or app without the
server and want to change where it stores data. Examples are a database, remote storage, and in-memory storage for
tests. Inside the server, the definitions module creates a file store, and there is no setting to change that.

**Minimal shape**: subclass `BaseDefinitionStore` and fill in the raw I/O methods `_read`, `_write`, `_remove`, and
`_ids`. To handle kinds with body files (resources and others), also fill in the body hooks (`_read_body`,
`_write_body`, `_remove_body`, `_list_body`, `_body_ids`). The base class handles version history, hashes, optimistic
locking (`expected_version`), and size limits.

**Rules**

- `_read` returns None when the document does not exist and raises `DefinitionCorrupt` when it cannot be read. Do not
  turn these into other exceptions.
- The kind list, the version history store, the clock, and the hash function are injected through the constructor. Do
  not take them from globals.
- If you need a check before writing, pass `write_guard`. When it refuses, nothing changes.

**Common mistakes**: overriding the public methods (`save`, `create`). That breaks the version and locking rules. Fill
in only the raw methods.

**Data left after removal**: this is a library point, so no names remain in server settings or user data.

<!-- extdocs:facts definition-store -->
- Registration: Inject an implementation through a constructor or an argument (an object that follows the interface).
- Interface:
  - `agent_console_store:DefinitionStore` — Definition store (graph, agent, settings, ...). Kinds are registered as `DefinitionKind`.
  - `agent_console_store:BaseDefinitionStore` — Common `DefinitionStore` implementation. Subclasses fill in five raw document I/O methods.
- Built-in implementations: —
- Examples:
  - reference: [packages/py/features/ac-store](../../packages/py/features/ac-store/README.md) — `FileDefinitionStore` (YAML files) and `InMemoryDefinitionStore`
- Turning it off or removing it: Without an injected implementation, the default implementation is used.
<!-- /extdocs:facts -->

## host-database

**When to use**: when you want to move the shared DB the server uses to another engine or location. The built-in
implementation is SQLite.

**Minimal shape**: the entry point points to a function `(Path) -> DatabaseHandle`. The handle has `engine` (an
SQLAlchemy engine), `upgrade(branches)` (upgrade the migration branches of the modules that are on), and `close()`.
Only the first factory in name order is used.

**Rules**

- If the factory cannot open the DB, it raises. That counts as a server startup failure.
- Branch upgrades are called with a module's branches only when that module is on. The handle does not choose
  branches.
- If there is no factory at all, the server starts without a DB, and modules that need storage run in memory, or turn
  that feature off and say so.

**Common mistakes**: installing one more factory under a different name from the built-in one and expecting it to be
used. Only the first in name order is used, so remove the built-in factory or arrange the name order.

**Data left after removal**: DB files are not deleted. When the factory is gone, the server runs without a DB from the
next start.

<!-- extdocs:facts host-database -->
- Registration: Register in the entry point group `agent_console.host_database` (constant `agent_console_modkit:HOST_DATABASE_GROUP`). The registration name is the id.
- Interface:
  - `agent_console_modkit:DatabaseHandle` — Shared DB handle the host creates for modules. Modules never create engines.
- Built-in implementations: `sqlite (agent-console-store)`
- Examples:
  - contract-tests: `agent_console_modkit.testing:open_recording_database`
- Turning it off or removing it: Add the name to the setting `plugins.disabled`, or uninstall the package, then restart the server.
<!-- /extdocs:facts -->

## host-plugin-loader

**When to use**: when a module that defines a new extension point needs to read the plugins of its group into a
registry at server startup. The built-in modules (runs, resources, logs, usage, and so on) each read their own groups
with this loader. Plugin authors do not need it.

**Minimal shape**: the entry point points to a `PluginLoader`, a function
`(PluginLoadContext) -> list of (report group, LoadReport)`. The context holds the registry set, the names to read
(`enabled`: `plugins.enabled` with `plugins.disabled` already removed), the deny list (`disabled`), the host paths,
and the raw administrator module settings. If you read entry points with
`load_entry_points(..., enabled=ctx.enabled)`, both settings apply with the same rules as for other groups. A loader
that uses names that are not entry points decides with `ctx.allows(name)`.

**Rules**

- Attach a validator to your registry with `registries.extension(name, validator=)`, then read the entry points.
  Plugins that come in later through `plugins.modules` go through the same validator.
- Respect the allow list (`ctx.enabled`). When it is None, everything installed is allowed.
- Return failures as reports instead of raising. The reports appear in `plugins` of `GET /api/v1/server-info`.
- Read your own module settings from `ctx.options[module id]` and validate them yourself. If they are wrong, use the
  defaults and log a warning.

**Common mistakes**: the loader creating services that the module's `build` will use. The loader only registers in
registries; services are created in `build`.

**Data left after removal**: the plugins of that group are not read. User data that uses names from that group is
reported with the "unknown name" issue of the point.

<!-- extdocs:facts host-plugin-loader -->
- Registration: Register in the entry point group `agent_console.host_plugin_loaders` (constant `agent_console_modkit:HOST_PLUGIN_LOADERS_GROUP`). The registration name is the id.
- Interface:
  - `agent_console_modkit:PluginLoader` — Plugin loader: loads into the bundle, returns ``(report group, report)``; reports failures.
  - `agent_console_modkit:PluginLoadContext` — What a plugin loader receives.
- Built-in implementations: `architecture (agent-console-mod-architecture)`, `exports (agent-console-mod-exports)`, `i18n (agent-console-mod-i18n)`, `imports (agent-console-mod-imports)`, `logs (agent-console-mod-logs)`, `memory (agent-console-mod-memory)`, `projects (agent-console-mod-projects)`, `resources (agent-console-mod-resources)`, `runs (agent-console-mod-runs)`, `sdd (agent-console-mod-sdd)`, `usage (agent-console-mod-usage)`, `wiki (agent-console-mod-wiki)`
- Examples:
  - contract-tests: `agent_console_modkit.testing:example_plugin_loader`
- Turning it off or removing it: Add the name to the setting `plugins.disabled`, or uninstall the package, then restart the server.
<!-- /extdocs:facts -->

## host-registries

**When to use**: when you embed the server in another app and want to replace the registry set with your own. This
is for a set that needs attributes (typed fields) besides named registries. The built-in implementation is the set the
runs module provides.

**Minimal shape**: the entry point points to a function without arguments that returns a `RegistryBundle`
(`extension(name, *, validator=None)`, `all()`). Only the first factory in name order is used. If there is none, or it
fails, the set is an `ExtensionRegistries` with only named registries.

**Rules**

- `extension(name)` creates the registry when it does not exist, and attaches the validator when one is given. The
  same name returns the same registry.
- Secret providers are looked up in the `secret_providers` registry of the set. Keep this name when you replace the
  set.

**Common mistakes**: assuming the server stops when the factory fails. The failure is recorded as a report and the
server starts with the default set, so check the reports.

**Data left after removal**: none. The default set is used from the next start.

<!-- extdocs:facts host-registries -->
- Registration: Register in the entry point group `agent_console.host_registries` (constant `agent_console_modkit:HOST_REGISTRIES_GROUP`). The registration name is the id.
- Interface:
  - `agent_console_modkit:RegistryBundle` — The minimum shape a registry bundle must have.
  - `agent_console_modkit:ExtensionRegistries` — Default registry bundle (no factory entry point). Holds named registries only.
- Built-in implementations: `runs (agent-console-mod-runs)`
- Examples:
  - reference: [packages/py/modules/ac-mod-runs](../../packages/py/modules/ac-mod-runs/README.md) — `plugins.create_registries`, the run registry set
- Turning it off or removing it: Add the name to the setting `plugins.disabled`, or uninstall the package, then restart the server.
<!-- /extdocs:facts -->

## migration-scope

**When to use**: when a module's tables must not live only in the app DB but also in the record DB that belongs to a
project folder. This is data that must travel with the project, such as run history.

**Minimal shape**: set `scopes` in `MigrationBranch(name, versions, scopes)` of the descriptor `migrations`. The
default `("app",)` means the app DB only. With `("app", "project")`, the integration that opens project record DBs also
upgrades the same branch in those DBs. Scope names are open strings. For the full explanation of migration branches,
see [storage in Server modules](modules.md#storage-migration-branches).

**Rules**

- The same branch is upgraded in two DBs, so each revision must give the same result in both. Do not rely on other
  tables that exist only in the app DB.
- The projects integration opens project record DBs and upgrades the branches. Your module must not assume that DB is
  open.

**Common mistakes**: editing an old revision after adding a scope. Some DBs are already upgraded, so add a new
revision.

**Data left after removal**: when you remove a scope, the branch is not upgraded in project DBs opened from then on.
Tables and data already created stay.

<!-- extdocs:facts migration-scope -->
- Registration: Put a value in the descriptor field `MigrationBranch.scopes`.
- Interface:
  - `agent_console_modkit:MigrationBranch` — Migration branch a module owns (package data folder).
- Built-in implementations: —
- Examples:
  - package: [examples/extensions/agent-console-example-module](../../examples/extensions/agent-console-example-module/README.md)
- Turning it off or removing it: Leave the field empty to use the default.
<!-- /extdocs:facts -->

## run-labels

**When to use**: when another feature or a script wants to group the runs it started and filter them later. Tag a run
with which spec started it or which batch job it belongs to. There is no code registration; it is one field of the
run record.

**Shape**: `labels` (string → string) of the run start request `POST /api/v1/runs`. Labels are attached to the root
run.

```json extdocs:validate=agent_console_contracts:CreateRunRequest
{
  "graph_id": "review-team",
  "input": {"task": "변경 검토"},
  "origin": "acme.nightly",
  "labels": {"acme.batch": "2026-11-07", "acme.ticket": "OPS-142"}
}
```

Filter the list as in `GET /api/v1/runs?label=acme.batch=2026-11-07`. When you give it several times, all must match
(AND). A value may contain `=` (it is split at the first `=`).

To show labels as chips on screen, the module that adds them puts display rules in `ModuleParts.label_display` of its
`build` result. The web collects them from `GET /api/v1/modules`, draws labels with the same key as chips, and turns
them into links when a screen handles `target.role`.

```yaml extdocs:validate=agent_console_contracts:LabelDisplay
key: acme.ticket
title: 티켓
target: {role: acme-tickets, id_from: acme.ticket}
order: 10
```

**Rules**

- Name keys with your own prefix (so they do not collide with other features' labels). It is even better to let the
  prefix be changed through administrator settings.
- Limits: 16 labels, 64 characters per key, 256 characters per value. Beyond these, the start request is a validation
  error (422). Keys must not be empty; values may be empty strings.
- Do not put secrets, personal information, or long content in labels. Labels go out as they are in list responses.

**Common mistakes**: trying to change run behavior with labels. Labels are for grouping, filtering, and display. Pass
values that affect the run as input or settings.

**Data left after removal**: when you remove the feature that adds labels, the labels already added stay in the run
history and can still be used for filtering. When the display rules go away, the chip display for that key goes away
with them.

<!-- extdocs:facts run-labels -->
- Registration: Put a value in the contract field `Run.labels` (an open value, with no code registration).
- Interface:
  - `agent_console_contracts:Run` — One run of a graph. A subgraph runs as a child Run (`parent_run_id`).
- Built-in implementations: —
- Examples:
  - snippet: —
- Turning it off or removing it: Leave the value unset; only the features that use the field stay empty.
<!-- /extdocs:facts -->

## server-module

**When to use**: when you add a new feature with its own REST paths, its own storage (DB tables), and its own
settings section to the server. Adding one more of an existing kind is a plugin, not a module. Connecting two features
is a link module (`kind = "link"`).

**Minimal shape**: register an object with `descriptor` (`ModuleDescriptor`) and `build(ctx) -> ModuleParts` in the
entry point group `agent_console.server_modules`. The name is the module id. Fields, ports, settings, turning on and
off, and standalone runs are all in [Server modules](modules.md).

**Rules**

- Do not import other modules. Connect only by port name. If a required port is missing, only your module is turned
  off as `unsatisfied`.
- Use the same prefix for the module id, issue codes, event `type`, label keys, and definition kind names.
- Add `title`, `description`, and `x-ui` to every field of the administrator option schema. If the options are wrong,
  only that module is `failed`.
- Do not do slow work (file scans, network) in `build`. Defer it to a startup hook or a background task. The server
  readiness signal comes after all startup hooks have finished.

**Common mistakes**: creating new server app settings keys. Keep module settings only under
`modules.options.<module id>`. When you move a key, put a notice for the old key in `settings_compat`.

**Data left after removal**: the paths return 404 and drop out of the web menu. Tables, files, and settings sections
stay (to remove the tables as well, downgrade the migration branch before removing the module). Even if
`modules.options.<id>` is left in the settings file, the server starts and only logs a warning. Links that required
the module's ports become `unsatisfied`.

<!-- extdocs:facts server-module -->
- Registration: Register in the entry point group `agent_console.server_modules` (constant `agent_console_modkit:MODULES_GROUP`). The registration name is the id.
- Interface:
  - `agent_console_modkit:Module` — Server module. Install it via entry point group ``MODULES_GROUP`` or pass it directly.
  - `agent_console_modkit:ModuleDescriptor` — Data a module uses to describe itself: for assembly order, turning on and off, and reports.
  - `agent_console_modkit:ModuleContext` — What ``Module.build`` receives (no globals). The assembler creates one per module.
  - `agent_console_modkit:SettingsCompat` — One module's host settings compatibility declaration.
- Built-in implementations: `link-chat-runs (agent-console-link-chat-runs)`, `link-definitions-resources (agent-console-link-definitions-resources)`, `link-definitions-teams (agent-console-link-definitions-teams)`, `link-exports-teams (agent-console-link-exports-teams)`, `link-logs-architecture (agent-console-link-logs-architecture)`, `link-logs-runs (agent-console-link-logs-runs)`, `link-logs-trace (agent-console-link-logs-trace)`, `link-logs-usage (agent-console-link-logs-usage)`, `link-memory-runs (agent-console-link-memory-runs)`, `link-projects-memory (agent-console-link-projects-memory)`, `link-projects-records (agent-console-link-projects-records)`, `link-projects-runs (agent-console-link-projects-runs)`, `link-projects-sdd (agent-console-link-projects-sdd)`, `link-projects-wiki (agent-console-link-projects-wiki)`, `link-runs-sdd (agent-console-link-runs-sdd)`, `link-runs-teams (agent-console-link-runs-teams)`, `link-runs-trace (agent-console-link-runs-trace)`, `link-runs-usage (agent-console-link-runs-usage)`, `link-wiki-runs (agent-console-link-wiki-runs)`, `mod-architecture (agent-console-mod-architecture)`, `mod-chat (agent-console-mod-chat)`, `mod-definitions (agent-console-mod-definitions)`, `mod-exports (agent-console-mod-exports)`, `mod-i18n (agent-console-mod-i18n)`, `mod-imports (agent-console-mod-imports)`, `mod-logs (agent-console-mod-logs)`, `mod-memory (agent-console-mod-memory)`, `mod-projects (agent-console-mod-projects)`, `mod-resources (agent-console-mod-resources)`, `mod-runs (agent-console-mod-runs)`, `mod-sdd (agent-console-mod-sdd)`, `mod-usage (agent-console-mod-usage)`, `mod-versions (agent-console-mod-versions)`, `mod-wiki (agent-console-mod-wiki)`
- Examples:
  - package: [examples/extensions/agent-console-example-module](../../examples/extensions/agent-console-example-module/README.md)
  - contract-tests: `agent_console_modkit.testing:echo_module`, `agent_console_modkit.testing:fake_module`
- Turning it off or removing it: Add the name to the setting `plugins.disabled`, or uninstall the package, then restart the server.
<!-- /extdocs:facts -->
