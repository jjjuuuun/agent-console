# agent-console-modkit

The server module kit. It holds the interfaces and the assembler that feature modules and link modules follow,
and the HTTP host shared by the integrated server and standalone runs.

- **It knows no feature, module, or link names.** Ports and topics are matched only by name strings (`PortKey("definitions.store")`).
- **No global state.** The event bus, WS hub, clock, environment, and paths are injected through `BaseServices`.
- **It does not depend on the contracts package.** Reports (`ModuleReport`) and error bodies are its own types, and converting them to contract models
  (`ModuleInfo` and others) is done by the integrated server. Dependencies: `agent-console-registry`, `pydantic`.
- The core (`agent_console_modkit`) is used without FastAPI. The HTTP host (`agent_console_modkit.host`) and standalone
  runs (`agent_console_modkit.standalone`) need the extra `[host]` (fastapi, uvicorn, websockets, ruamel-yaml).

## Installation

```bash
pip install agent-console-modkit            # core (assembly, events)
pip install "agent-console-modkit[host]"    # + host and standalone runs
# outside the repository, with internal dependencies: pip install --find-links <wheelhouse> "agent-console-modkit[host]"
```

## Minimal usage

Assemble a set of modules. `mod-chat` requires `definitions.store`, and `chat.turn_launcher` is optional.

```python
>>> from agent_console_modkit import ModulesConfig, PortKey, assemble
>>> from agent_console_modkit.testing import fake_module
>>> STORE = PortKey("definitions.store")
>>> LAUNCHER = PortKey("chat.turn_launcher")
>>> definitions = fake_module("mod-definitions", provides=[STORE])
>>> chat = fake_module("mod-chat", requires=[STORE], optional=[LAUNCHER])
>>> link = fake_module("link-chat-runs", kind="link", provides=[LAUNCHER], requires=[STORE])
>>> assembly = assemble([chat, link, definitions])
>>> assembly.order
['mod-definitions', 'link-chat-runs', 'mod-chat']
>>> chat.contexts[0].port(LAUNCHER)
'link-chat-runs/chat.turn_launcher'

```

When the definitions module is turned off, the modules that require it are turned off with a reason (no automatic correction).

```python
>>> off = assemble([chat, link, definitions], ModulesConfig(disabled=["mod-definitions"]))
>>> for r in off.report:
...     print(r.id, r.state.value, r.missing)
link-chat-runs unsatisfied ('definitions.store',)
mod-chat unsatisfied ('definitions.store',)
mod-definitions disabled ()

```

When two modules provide the same single port, both are `conflict`, and you choose with `bindings`. `PortKey(multi=True)` receives a list.

```python
>>> a = fake_module("mod-a", provides=[STORE])
>>> b = fake_module("mod-b", provides=[STORE])
>>> [r.state.value for r in assemble([a, b]).report]
['conflict', 'conflict']
>>> assemble([a, b], ModulesConfig(bindings={"definitions.store": "mod-b"})).port(STORE)
'mod-b/definitions.store'

```

The module event bus isolates subscriber exceptions.

```python
>>> from agent_console_modkit import EventBus, Topic
>>> bus = EventBus()
>>> SAVED = Topic("definitions.saved")
>>> got = []
>>> def broken(item):
...     raise ValueError(item)
>>> _ = bus.subscribe(SAVED, broken)
>>> _ = bus.subscribe(SAVED, got.append)
>>> bus.publish(SAVED, "agent:planner")
>>> got, bus.errors
(['agent:planner'], 1)

```

The host (extra `[host]`) attaches the routers, WS topics, and error maps of enabled modules and applies the security rules (Host, Origin, token, size).

```python
>>> from fastapi.testclient import TestClient
>>> from agent_console_modkit.host import SecurityPolicy, create_host_app
>>> from agent_console_modkit.testing import echo_module
>>> policy = SecurityPolicy.for_bind("127.0.0.1", 0, token="t" * 32, allowed_hosts=["testserver"])
>>> app = create_host_app(assemble([echo_module]), policy=policy)
>>> with TestClient(app) as client:
...     print(client.get("/api/v1/health").json())
...     print(client.get("/api/v1/echo", params={"text": "hi"}).json())
...     print(client.post("/api/v1/echo/room", json={"text": "x"}).status_code)
{'status': 'ok', 'modules': {'echo': 'active'}}
{'text': 'hi'}
401

```

The host also attaches `GET /modules` (module reports). Behavior inside an enabled module that is off because an optional port is missing is reported with
`raise ctx.unavailable(PORT)`, and the host turns it into 409 `feature_unavailable{module, port}`.

```python
>>> with TestClient(app) as client:
...     print([(m["id"], m["state"]) for m in client.get("/api/v1/modules").json()])
...     error = client.get("/api/v1/echo/transformed", params={"text": "hi"}).json()["error"]
...     print(error["code"], error["details"])
[('echo', 'active')]
feature_unavailable {'module': 'echo', 'port': 'echo.transform'}

```

`/health` is 200 only after the module startup hooks finish (503 `not_ready` before that and after shutdown, `Assembly.running`).

The host's base services are also built without feature names. Installed packages announce a registry bundle
factory (`agent_console.host_registries`), plugin loaders (`agent_console.host_plugin_loaders`), and a database factory
(`agent_console.host_database`) through entry points, and the host uses them with `load_host_plugins` and `open_host_database`.

```python
>>> from importlib.metadata import EntryPoint
>>> from agent_console_modkit import HOST_PLUGIN_LOADERS_GROUP, load_host_plugins
>>> loader = EntryPoint("ex", "agent_console_modkit.testing:example_plugin_loader", HOST_PLUGIN_LOADERS_GROUP)
>>> plugins = load_host_plugins(entry_points=[loader], options={"example": {"a": 1}})
>>> plugins.registries.extension("examples").get("example")
{'workspace': None, 'options': {'a': 1}}
>>> off = load_host_plugins(entry_points=[loader], disabled=["example"])  # settings plugins.disabled
>>> [(r.status, r.reason) for _, r in off.reports]
[('skipped', '설정 plugins.disabled에 있음')]

```

`enabled` (allow list) and `disabled` (exclude list) follow the same rule in every group: the exclude list is subtracted within the allow list. Loaders
receive the combined result as `PluginLoadContext.enabled` (for keys that are not entry points, `ctx.allows(name)`), and excluded names that appear in no report
are kept in `HostPlugins.warnings`.

Removed settings keys, environment variables, command-line aliases, and defaults are announced by modules through `ModuleDescriptor.settings_compat` (`SettingsCompat`).
Old keys are not read and migrated. A module that moved or removed a key declares `RemovedSetting(old, new=..., reason=...)`,
and if that key remains, the host refuses with an error that gives the reason and the new location (server code `settings.removed_key`).
This message is printed in the terminal on a refused start, so its source text is English.

```python
>>> from agent_console_modkit import removed_settings, seed_settings
>>> from agent_console_modkit.testing import ECHO_SETTINGS_COMPAT
>>> seed_settings({"host": "127.0.0.1"}, {"mod-echo": ECHO_SETTINGS_COMPAT})["modules"]
{'options': {'mod-echo': {'host': '127.0.0.1'}}}
>>> [r.message() for r in removed_settings({"echo_old": {}}, {"mod-echo": ECHO_SETTINGS_COMPAT})]
['The settings key echo_old is no longer read. Move it to modules.options.mod-echo']

```

WS notifications can come from store threads, but `Hub` is touched only on the loop thread. `LoopPublisher` moves them to the loop
bound in the startup hook, and the same change notified twice is emitted once (`key`).

```python
>>> import asyncio, threading
>>> from agent_console_modkit import LoopPublisher
>>> seen = []
>>> pub = LoopPublisher(lambda p: seen.append((p, threading.current_thread().name)), key=lambda p: p)
>>> async def scenario():
...     pub.bind(asyncio.get_running_loop())
...     for payload in ("a", "a", "b"):
...         worker = threading.Thread(target=pub, args=(payload,), name="worker")
...         worker.start()
...         worker.join()
...     await asyncio.sleep(0)
>>> asyncio.run(scenario())
>>> seen
[('a', 'MainThread'), ('b', 'MainThread')]

```

<!-- doctest: keep a blank line after the expected output (so the closing ``` line is not read as output). -->

### Read-only view of module options

Module options (`modules.options.<id>`) are changed only in the settings file. `Assembly.module_options(id)` only **shows** the value
together with the schema (even for disabled modules). Fields the schema says are secret (`SecretStr`, `x-secret`) are
always masked, and plain-text secret suspicion is injected through `secret_paths` (for example the locations from
`find_suspected` of `agent_console_secret_rules`). The host publishes it at `GET /modules/{id}/options`, together with a YAML
snippet to paste into the settings file (`host.options_yaml_snippet`). There is no write path. Masked lines in the snippet are **comments**, so
pasting it as is (or in part) never turns the secret text or the mask string into a settings value (those keys drop out and become defaults,
and objects and lists left with only masked lines are closed as `{}` and `[]`). The mask string is the single `OPTIONS_MASK` within modkit
(`host.REDACTED` is the same value). Hosts that use the secret rules package pass that package's mask string as `mask=` to match.

```python
>>> from pydantic import BaseModel, SecretStr
>>> class EchoOptions(BaseModel):
...     limit: int = 3
...     token: SecretStr | None = None
>>> opts = fake_module("mod-opts", settings_schema=EchoOptions)
>>> assembly = assemble([opts], ModulesConfig(options={"mod-opts": {"token": "abc"}}))
>>> view = assembly.module_options("mod-opts")
>>> view.values, view.masked
({'limit': 3, 'token': '[REDACTED]'}, ('/token',))
>>> assembly.module_options("mod-chat") is None   # unknown module
True
>>> from agent_console_modkit.host import options_yaml_snippet
>>> print(options_yaml_snippet("mod-opts", view.values, masked=view.masked), end="")
modules:
  options:
    mod-opts:
      limit: 3
      # token: <가린 값 — secret://이름으로 넣으세요>

```


## Writing a module

```python
from agent_console_modkit import ModuleContext, ModuleDescriptor, ModuleParts, PortKey

# the same name means the same port (no need to import other modules)
STORE = PortKey("definitions.store")


class _Module:
    descriptor = ModuleDescriptor(
        id="mod-x",
        version="0.1.0",
        kind="feature",
        title="X",
        requires=(STORE,),
        settings_schema=None,
        web_roles=("x",),
    )

    def build(self, ctx: ModuleContext) -> ModuleParts:
        store = ctx.port(STORE)  # required ports are always present; optional ports can be None
        router = make_router(store)  # fastapi.APIRouter
        return ModuleParts(
            routers=[router], ws_topics={"x:": handler}, error_map={XError: "not_found"}
        )


module = _Module()
```

### When to read optional ports (convention)

- **Read optional ports when calling.** Do not take values out in `build` and keep them; call `ctx.port(KEY)` and `ctx.ports(KEY)` in functions that hold `ctx`
  when handling requests (for example `lambda: ctx.port(SETTINGS)`).
- The assembly order is "all required edges + optional edges that do not create cycles". When optional ports create a cycle, edges of multi-provider ports
  (`PortKey(multi=True)`) are removed first, so **providers of multi optional ports can be built later than their consumers**.
  So `ctx.ports(...)` at `build` time can be an empty list or hold only some providers.
- What may be read at `build` time is only required ports and single optional ports. Single optional ports can also be dropped when single ports alone form
  a cycle (dropped optional edges are not reported or warned separately), so unless you are sure there is no such combination, read them
  when calling.

Install through the entry point group `agent_console.server_modules` (`MODULES_GROUP`).
`poe new-package --kind module|link` creates `module.py` and `__main__.py` for you.

## Standalone runs (development and reuse)

A module package's `__main__.py` is a few lines that call `standalone.run`.

```bash
python -m agent_console_mod_x [--with ID] [--config PATH] [--host 127.0.0.1] [--port 0] [--check]
```

- `--with ID`: modules to start together (found in installed entry points). Required ports are not pulled in automatically. If none is given,
  the modules the module package set with `run(default_with=[...])` are attached (for example the local definition store in the same package's `testing`).
- `--config PATH`: the same keys as the integrated server settings (`host`, `port`, `security`, `modules`), `.json`, `.toml`, YAML.
- `--check`: start → check `GET /api/v1/health` returns 200 → exit (for portability checks). Exit codes 0/1/2.
- The default binding is 127.0.0.1. For non-loopback addresses, `security.allow_remote: true` is required.
  The token is never printed. To make change requests, set `security.token` in the settings.

## Public API

| Name | Description |
| --- | --- |
| `PortKey[T](name, description="", multi=False)` | A port name (equality = name). With `multi`, several providers are not a conflict |
| `Topic[T](name)` | A module event topic |
| `KindContribution[K](kind, references=None, summary_fields=(), title=None, delete=None)` / `KindReferences` / `KindDelete` / `DEFINITION_KIND_CONTRIBUTIONS` | Definition kind contributions. With `delete` (optional, `(space, id, expected version) -> None`), the common delete path for kinds can delete items of that kind (None = cannot be deleted). The multi-provider port `definitions.kind_contributions` lives in the kit so that supplying modules (for example SDD) and consuming modules (definitions, projects) do not import each other. The kit does not know the type of kind values (the definitions module accepts only `agent_console_store.DefinitionKind`) |
| `ModuleDescriptor` | `id`, `version`, `kind` (`feature`/`link`, an open string), `title`, `description`, `provides`, `requires`, `optional`, `settings_schema`, `contracts` (`{contract submodule: version}`), `web_roles`, `migrations`, `settings_compat` |
| `ModuleParts` | `routers`, `ws_topics` (a key ending in `:` is a prefix), `error_map` (exception → a code string or an `ErrorMapper`), `startup`, `shutdown` (reverse order), `background` |
| `ErrorReply(code, message=None, details={}, headers={}, fix=None)` / `ErrorMapper` / `ErrorMapping` / `error_reply` | `error_map` values: a string when only a code is needed; when details, headers (for example `ETag`), or a fix button (`fix`, which appears in the body `error.fix` only when given) are needed, an exception → `ErrorReply` function |
| `Module` | `descriptor` + `build(ctx) -> ModuleParts` (runtime_checkable) |
| `ModuleContext` | `port(key)`·`ports(key)`·`provide(key, impl)`·`unavailable(key)`·`publish`·`subscribe`, `settings`, `clock`·`environ`·`paths`·`database`·`registries`·`ws_hub`·`events`·`secret_resolver` |
| `FeatureUnavailableError(module, port)` / `FEATURE_UNAVAILABLE` | Behavior that is off because an optional port is missing (the host returns 409, `details = {module, port}`) |
| `assemble(modules, config=None, *, base=None) -> Assembly` | Topological sort → build. Failures go into the report |
| `Assembly` | `parts`·`report`·`order`·`warnings`·`port`·`ports`·`provided_ports`·`routers(first_kinds=())`·`ws_topics`·`error_map`·`start(fail_fast=False)`·`stop()` |
| `ModulesConfig` | `enabled`, `disabled`, `bindings`, `options`, `with_overrides(enable=, disable=)` (command-line on and off; for the same id, off wins) |
| `ModuleState` / `ModuleReport` | The 5 states (`active`, `disabled`, `unsatisfied`, `failed`, `conflict`) and reports (`reason`, `missing`, `conflicts`…, `to_dict()`) |
| `EventBus` | `subscribe` (returns an unsubscribe function), `publish` (non-blocking), `deliver` (waits), `drain`, `errors` |
| `Hub[T]` | Fan-out of WS topic strings (slow subscribers are dropped, `dropped`) |
| `LoopPublisher[T](publish, *, key=None)` | Moves notifications from other threads to the event loop thread bound with `bind(loop)` and calls `publish`. Consecutive notifications with the same `key` are emitted once (key None = that notification is not checked); before binding and after `bind(None)` it calls directly; if the bound loop is closed, they are dropped (`dropped`) |
| `WorkGate` / `DEFAULT_WORK_WAIT` | Counting background thread work + closing. `run(fn, stopped=None)` (`stopped()` after closing), `close()`, `reopen()`, `closed`, `busy`, `wait_idle(timeout)`, `await close_and_wait(timeout)`. Waits for running thread work before background tasks are cancelled or shutdown hooks close resources |
| `BaseServices` / `Paths` | Host base services |
| `DatabaseHandle` (protocol) / `MigrationBranch(name, versions, scopes=("app",))` | The shared database handle and the migration lineages modules declare in `ModuleDescriptor.migrations`. `assemble` upgrades, right before build, only the lineages of enabled modules whose `scopes` include `"app"` with `database.upgrade` (other scopes, for example `"project"` for project records databases, are read with `ModuleContext.active_migrations(scope)` and upgraded by the module that opens that database) (on failure only that module is `failed`, with a masked message). The implementation is in the storage layer (`agent_console_store.SqliteDatabase`) |
| `load_installed_modules(group=MODULES_GROUP)` | Reads modules from entry points (the ac-registry loader) |
| `load_host_plugins(*, enabled, disabled, paths, modules, options, entry_points)` → `HostPlugins` (`registries`, `reports`, `warnings`) / `PluginLoadContext` (`enabled`, `disabled`, `allows(name)`) / `PluginLoader` / `ExtensionRegistries` / `RegistryBundle` / `REASON_PLUGINS_DISABLED`, `REASON_PLUGINS_NOT_ENABLED` | Host plugin registries: bundle factory (`HOST_REGISTRIES_GROUP`, the first by name, otherwise `ExtensionRegistries`) → loaders (`HOST_PLUGIN_LOADERS_GROUP`, by name) → `register(registries)` plugins. Failures are reported, and excluded items carry a reason (`reason`) |
| `open_host_database(path)` | Database factory (`HOST_DATABASE_GROUP`) → `DatabaseHandle` (None if absent) |
| `env_secret_lookup`, `secret_lookup`, `secret_providers_of`, `SECRET_PROVIDERS_REGISTRY` | The secret resolution chain (environment variables → the bundle's secret providers) |
| `SettingsCompat` (`RemovedSetting`, `EnvSetting`, `FlagSetting`, `SeedSetting`) / `compat_of`, `removed_settings`, `env_settings`, `compat_flags`, `flag_settings`, `seed_settings` | Host settings compatibility declared by modules (refusing removed keys; environment variables, command-line options, and other settings values → `modules.options.<id>`). `RemovedSetting(path, reason="", new=None).message()` is the refusal text (with the new location) |
| `NOT_READY` / `Assembly.running` | The `/health` 503 code before ready, and whether startup has finished |
| `Assembly.module_options(id, *, secret_paths=None, hide_paths=False, mask=OPTIONS_MASK)` / `read_module_options` / `ModuleOptions` / `mask_values` / `OPTIONS_MASK` / `SECRET_SCHEMA_KEY` / `SecretPathFinder` | Read-only view of module options (schema and masked current values, including disabled modules; None for unknown ids). Schema secret fields are always masked and plain-text secret judgement is injected; with `hide_paths`, path fields are masked too |
| `WsSubscribeRequest`, `WsReject`, `WsForward`, `WsTopicHandler` | WS topic handler types |
| `host.SecurityPolicy`, `SecurityMiddleware`, `resolve_token`, `is_loopback_host` | Security rules and middleware |
| `host.build_health_router`, `build_modules_router`, `default_modules_payload`, `websocket_endpoint`, `WsCodec`, `JsonWsCodec`, `create_host_app`, `install_error_map`, `install_feature_unavailable`, `include_routers`, `ROUTE_FIRST_KINDS` | Host assembly (`/health`, `/modules`, `/ws`, error handlers; link module routers first) |
| `host.build_module_options_router`, `default_module_options_payload(mask=)`, `options_yaml_snippet`, `OPTIONS_KEY_PATH`, `MASKED_LINE_NOTE` | `GET /modules/{id}/options` (read-only; unknown ids give 404 `not_found`) and the YAML snippet for the settings file. Replace with `create_host_app(options_payload=)` |
| `host.QueryRedactingFilter`, `install_log_redaction` | Masks tokens and secret-like query values in logs |
| `host.HostSettings`, `load_host_settings` | Host settings (unknown keys ignored) |
| `host.IfMatchHeader`, `if_match_version`, `etag`, `json_with_etag`, `attachment_response` | Versioned resources and body file responses |
| `host.with_issues(response, issues)`, `ISSUES_HEADER` | Carries warning issues to report after a successful save in the `X-Console-Issues` header (a JSON array, ASCII) without changing the body shape. Exposed in CORS `Access-Control-Expose-Headers` together with `ETag` |
| `standalone.run(module, argv, *, default_with=(), error_status=None, …)` | Standalone run. `default_with` = modules to attach when `--with` is not given (local providers from the same package's `testing` and so on), `error_status` = an error code → HTTP status table |
| `testing.fake_module`, `EchoModule`, `echo_module` | Fake and example modules |
| `testing.example_plugin_loader`, `open_recording_database`, `ECHO_SETTINGS_COMPAT` | Examples of host extension points (loaders, database factory, settings compatibility) |

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes development dependencies (dev group)
uv run ruff check .
uv run mypy
uv run pytest          # includes the README.md doctests
```
