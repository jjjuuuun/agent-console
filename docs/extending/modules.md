# Server modules

Each server feature (chat, runs, usage, logs, definitions, wiki, and so on) is a server module. The server does not
know feature names. It collects the installed modules through entry points, assembles them, and exposes them over
HTTP and WebSocket. To add a new feature to the server, create one module package. You do not change server, web, or
other module code.

If a plugin (one more of the same kind) can do the job, do not create a module. Use a module for a "feature" that has
its own REST paths, storage, and settings section.

Full example: [agent-console-example-module](../../examples/extensions/agent-console-example-module/README.md)
(it shows the descriptor, REST, administrator options, command-line options, a user settings section, a definition
kind contribution, a migration branch, ports, and a standalone run). Installed modules:
[server module table](reference.md#server-modules).

## Shape

A module is an object with two things: `descriptor` (data) and `build(ctx) -> ModuleParts` (assembly). It uses only
the public API of the module kit (`agent-console-modkit`). The code that writes the descriptor, `build`, and the port
declarations is in [How to build a module](../../examples/extensions/agent-console-example-module/README.md#how-to-build-a-module)
in the example README.

```toml
[project.entry-points."agent_console.server_modules"]
mod-notes = "my_console_notes.module:module"       # name = module id
```

### Descriptor `ModuleDescriptor`

| Field | Meaning |
| --- | --- |
| `id` | Module id. The key in the `modules.*` settings and the entry point name |
| `version`, `title`, `description` | For reports. `description` is one line the app user reads (do not use internal names) |
| `kind` | `feature` (feature module) or `link` (link module, see [Link modules](links.md)) |
| `provides` | Ports it provides. Put them in with `ctx.provide(port, implementation)` in `build` |
| `requires` | Required ports. If any is missing, this module is turned off as `unsatisfied` |
| `optional` | Optional ports. When one is missing, `ctx.port(port)` is None (an empty list for multi-provider ports) and only that behavior is turned off |
| `settings_schema` | A Pydantic model that validates the administrator options `modules.options.<id>` |
| `settings_compat` | Command-line options, environment variables, and notices for removed settings keys (below) |
| `migrations` | The migration branches this module owns (`MigrationBranch`) |
| `contracts` | The contract submodules it uses and their versions (for reports) |
| `web_roles` | Web screen entry roles. Only the roles of modules that are on appear in the web menu |

### `build`

- Create services and stores inside `build`. Do not keep global state. Get the DB, clock, environment, and other
  modules from `ctx`.
- The result, `ModuleParts`, holds REST routers, WS topic handlers, exception-to-error-code mappings, and startup and
  shutdown hooks.
- The host checks tokens, Host, and Origin, and limits request size. Modules do not contain security code.
- For error response codes, use the known codes of the contract (`not_found`, `validation_failed`, and so on). Use your
  own prefix for your own issue codes.

## Ports

Modules do not import each other. They connect **only by port name**. The consuming side declares a `PortKey` with the
same name in its own package.

| Port kind | Providers | When several provide it |
| --- | --- | --- |
| Single (`PortKey("name")`) | One | Both are `conflict`. Choose one with the setting `modules.bindings` |
| Multi-provider (`PortKey("name", multi=True)`) | Several | All are collected and received as a list (extra checks, extra scopes, and so on) |

If a missing optional port means a request cannot be handled, use `raise ctx.unavailable(port)`. The host turns it
into 409 `feature_unavailable{module, port}`. Existing ports (who provides and who uses them) are in the
[port table](reference.md#ports).

The example below shows the assembly rules with the module kit's test modules. When you turn off the module that
provides the notes port, only the module that requires it is turned off, and the module that uses it as optional stays
on.

```python
>>> from agent_console_modkit import ModulesConfig, PortKey, assemble
>>> from agent_console_modkit.testing import fake_module
>>> NOTES = PortKey("notes.reader")
>>> notes = fake_module("mod-notes", provides=[NOTES])
>>> viewer = fake_module("mod-viewer", optional=[NOTES])
>>> board = fake_module("link-notes-board", kind="link", requires=[NOTES])
>>> on = assemble([notes, viewer, board])
>>> [(r.id, r.state.value) for r in on.report]
[('link-notes-board', 'active'), ('mod-notes', 'active'), ('mod-viewer', 'active')]
>>> off = assemble([notes, viewer, board], ModulesConfig(disabled=["mod-notes"]))
>>> [(r.id, r.state.value, r.missing) for r in off.report]
[('link-notes-board', 'unsatisfied', ('notes.reader',)), ('mod-notes', 'disabled', ()), ('mod-viewer', 'active', ())]

```

## Settings

| Layer | Where | Who changes it | In the module |
| --- | --- | --- | --- |
| Administrator options | Server settings file `modules.options.<id>` | The person who installs and runs the server. A change needs a restart | `ctx.settings` (validated by `settings_schema`) |
| Command line and environment variables | `agent-console serve --<option>`, `AGENT_CONSOLE_<NAME>` | Same. They take precedence over the settings file | `FlagSetting` and `EnvSetting` in `settings_compat` |
| User settings section | The module's own section in the workspace `settings.yaml` | App users. Applies from the next request, without a restart | Read through the common settings port |

- Add `title`, `description`, and `x-ui` to the administrator option fields ([Plugin basics](plugins.md#settings-schema)).
  The settings screen shows them as a read-only table and masks secret fields.
- If the options do not match the schema, only that module is `failed` (reason: settings validation failed), and the
  server and the other modules start.
- Command-line options a module declares appear in `agent-console serve --help` automatically.
- If you move or remove a key, put `RemovedSetting(old key, new=new location, reason=reason)` in `settings_compat`. If
  the settings still contain the old key, the server refuses to start and reports the reason and the new location
  (`settings.removed_key`). It does not silently read and move the old value.

## Storage (migration branches)

- The shape of the tables is defined by the migration branch the module owns (an Alembic revision folder). Announce it
  in the descriptor `migrations` as `MigrationBranch(name, versions, scopes)`.
- The host upgrades a branch **only when its module is on**. It does not touch the tables of modules that are off.
- `scopes` are the DB scopes to upgrade the branch in. The default `("app",)` means the app DB only. With
  `("app", "project")`, the integration that opens project record DBs also upgrades the same branch in those DBs. Scope
  names are open strings.
- Do not create a DB engine yourself. Use `ctx.database`. If the host has no DB, run in memory, or turn that feature
  off and say so.

## Turning on and off

```yaml
modules:
  enabled: null                 # null = all installed modules
  disabled: [mod-notes]         # turn off. Same as the command-line --disable-module mod-notes
  options:
    mod-notes: {max_notes: 200}
```

- A module that is off returns 404 for its REST paths, has no WS topics, and drops out of the web menu. Its branches
  are not upgraded. Its data (tables, files) stays.
- Modules that require its ports are turned off together as `unsatisfied`. Modules that use them as optional return
  409 only for that behavior. Everything else keeps working.
- Status is in `GET /api/v1/modules` (`active`, `disabled`, `unsatisfied`, `conflict`, `failed`, with the reason and
  the missing ports).
- `GET /api/v1/health` returns 200 only after the startup hooks of all modules have finished.

Below is the result of attaching one test module to the host and turning it on and off.

```python
>>> from fastapi.testclient import TestClient
>>> from agent_console_modkit.host import SecurityPolicy, create_host_app
>>> from agent_console_modkit.testing import echo_module
>>> policy = SecurityPolicy.for_bind("127.0.0.1", 0, token="t" * 32, allowed_hosts=["testserver"])
>>> def status_codes(config):
...     app = create_host_app(assemble([echo_module], config), policy=policy)
...     with TestClient(app) as client:
...         return (
...             client.get("/api/v1/echo", params={"text": "hi"}).status_code,
...             client.get("/api/v1/health").status_code,
...         )
>>> status_codes(ModulesConfig()), status_codes(ModulesConfig(disabled=["echo"]))
((200, 200), (404, 200))
>>> bad = assemble([echo_module], ModulesConfig(options={"echo": {"prefix": [1]}}))
>>> bad.report[0].state.value, bad.report[0].reason
('failed', '설정 검증 실패: prefix')

```

## Standalone runs

You can start one module without the combined server. It uses the same host code and security rules. The module
package's `__main__.py` is a few lines that call `agent_console_modkit.standalone.run`.

```bash
python -m my_console_notes --config standalone.yaml --port 0            # start
python -m my_console_notes --with mod-definitions --port 0              # together with another installed module
python -m my_console_notes --check                                      # check that /health returns 200, then exit
```

`--with` does not pull in required ports automatically. The user chooses the modules to start together. When a module
runs standalone, you can attach that feature to another app or test it on its own.

## Testing

The module kit's `assemble` is the test host. Assemble without a server to check ports, status, and settings, and use
`create_host_app` to test REST as well. If you need other modules, use the doubles that their packages provide in
their `testing` modules. See [Testing](testing.md#4-assembly-tests).
