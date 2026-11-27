# Execution backends

Agent nodes do not call models directly. They pass requests to an execution backend. The built-in backends (the
Claude Agent SDK, and a fake backend that runs without a model) are also implementations registered in the same group.
This page covers backends themselves, session archiving and model discovery (optional backend capabilities), and
secret providers, which resolve the secret references written in settings.

| What you want to do | Point |
| --- | --- |
| Run agents with another model SDK, CLI, or in-house gateway | [execution-backend](#execution-backend) |
| Archive and restore raw session files so conversations can resume in another app or at another path | [backend-session-archive](#backend-session-archive) |
| Fill the model field with the models a backend account can use, without calling a model | [backend-model-discovery](#backend-model-discovery) |
| Look up `secret://name` somewhere other than environment variables (a file, a keychain) | [secret-provider](#secret-provider) |

## backend-session-archive

**When to use**: when a backend leaves raw session files (conversation record files) in its own folder, and a
conversation can resume only if those files exist. For a conversation to resume after the project folder moves to
another PC or its path changes, the backend must tell the app how to archive those files and put them back. A backend
without raw session files (one that starts from scratch every time) does not need this capability.

**Minimal shape**: add the method `session_archive() -> SessionArchive | None` to the backend. `SessionArchive` has
three methods.

| Method | What it does |
| --- | --- |
| `files(session, cwd=)` | The list of raw files to archive. None if the session does not exist |
| `status(session, cwd=)` | Whether it can resume now: `available`, `relocatable` (at an old location inside this app), `missing` |
| `restore(archive_dir, session, cwd=)` | Puts the files from the archived copy (or the old location) where the session can resume |

If the raw files have the shape "root/<run folder key>/<session>.jsonl", pass only a key function to the shared
implementation `JsonlFolderSessionArchive`.

**Rules**

- All methods are synchronous and use only the file system. They do not call models or the network.
- Put only that session's raw files in `files`. Never include credentials, settings, or other sessions' files.
- The archive location (which folder to use) and turning it on and off are decided by the app assembly, not by the
  backend. The backend does not know folder names.
- If it cannot be used right now (a required folder is missing, and so on), `session_archive()` returns None. It does
  not raise.

**Common mistakes**: moving or creating files in `status`. `status` only reads; only `restore` moves files.

**Data left after removal**: when you remove the capability, the resume status of that backend shows as
`not_applicable`. Copies already archived are not deleted.

<!-- extdocs:facts backend-session-archive -->
- Registration: Give the implementation object (for example, a backend) the optional method `session_archive`. The host finds and uses it when it is there.
- Interface:
  - `agent_console_runtime:SessionArchiveCapable` — Optional capability: a backend that provides session record archive and restore.
  - `agent_console_runtime:SessionArchive` — Archive and restore backend session records: synchronous, file system only.
  - `agent_console_runtime:ArchiveFile` — One original file to archive.
- Built-in implementations: `ac-backend-claude-sdk (agent-console-backend-claude-sdk)`, `ac-backend-fake-agent (agent-console-backend-fake-agent)`
- Examples:
  - package: [examples/extensions/agent-console-example-backend](../../examples/extensions/agent-console-example-backend/README.md)
  - reference: [packages/py/features/ac-backend-claude-sdk](../../packages/py/features/ac-backend-claude-sdk/README.md) — Built-in backend that uses `JsonlFolderSessionArchive`
- Turning it off or removing it: Remove the method or return None to turn off only that capability.
<!-- /extdocs:facts -->

## execution-backend

**When to use**: when you want to run agents with a different runner. Examples are another company's agent SDK, an
in-house model gateway, and a test backend that answers from a prewritten script. The `backend` value of an agent
definition is this registration name.

**Minimal shape**: `descriptor` (`BackendDescriptor`), `async list_models()`, and
`async run(req, sink, cancel) -> AgentResult`. `req` (`AgentRequest`) contains the agent definition, the prompt, the
run folder, and the resource slots. Stream progress events to `sink`, and stop when `cancel` says so.

**Rules**

- **Only declared capabilities are used.** The engine and the screens do not use features that are not in the
  descriptor `capabilities` (streaming, tools, hooks, MCP, resume, cancel, subagents, resource slots, and so on). If a
  delegation strategy requires a capability that is missing, the team check blocks it with the error
  `team.backend_capability_missing`.
- If the backend needs constructor arguments, add the classmethod `from_options(options, *, secrets, environ)`
  (`ConfigurableBackend`). The server passes the administrator setting `modules.options.mod-runs.backends.<id>` as it
  is and does not know what the keys mean. Reject unknown keys with `ValueError`, and do not put values in the error
  text.
- Announce the shape of `backend_options` in agent definitions with the descriptor `config_schema`. The screens draw
  the form from this schema.
- Secret references in `req.agent` arrive already resolved. Do not put those values in events, logs, or errors. Do
  not put the run folder path or environment values in events either.
- For the event format, use the known `agent.*` events of the contract (`agent.text_delta`, `agent.message`,
  `agent.usage`, and so on), and emit anything else under your own prefix
  ([Contracts and events](contracts-events.md#plugin-owned-events)).
- To record more tool calls, hooks, and MCP activity of the built-in implementation, do not write a new backend. Use
  an [observation collector](logs.md#collector).

**Common mistakes**: fetching the model list over the network on every `list_models` call, which slows down the
screens. Provide the list from settings (`from_options`) or a cache. Another is not watching `cancel`, so canceling a
run never finishes.

**Data left after removal**: agents that chose that backend stay. When they run, the node fails with
`agent.unknown_backend`. If a node's settings choose the backend directly, the pre-save check also reports the same
code (an error). If the administrator setting `modules.options.mod-runs.backends.<id>` is left over, the server starts
and logs a warning that the backend is not registered. Raw session files the backend wrote are not deleted.

<!-- extdocs:facts execution-backend -->
- Registration: Register in the entry point group `agent_console.backends` (constant `agent_console_runtime:BACKENDS_GROUP`). The registration name is the id.
- Interface:
  - `agent_console_runtime:ExecutionBackend` — Execution backend adapter.
  - `agent_console_runtime:ConfigurableBackend` — Backend rebuildable from server administrator settings (app setting `backends.<id>`).
  - `agent_console_runtime:AgentRequest` — Backend run request. `agent` arrives with secret references (`secret://…`) already resolved.
  - `agent_console_runtime:AgentResult` — Backend run result.
- Settings: `modules.options.mod-runs.backends`
- Built-in implementations: `claude-agent-sdk (agent-console-backend-claude-sdk)`, `fake-agent (agent-console-backend-fake-agent)`
- Examples:
  - package: [examples/extensions/agent-console-example-backend](../../examples/extensions/agent-console-example-backend/README.md)
- Turning it off or removing it: Add the name to the setting `plugins.disabled`, or uninstall the package, then restart the server.
<!-- /extdocs:facts -->

## secret-provider

**When to use**: when you want to look up the `secret://name` references written in agent definitions and settings
somewhere other than environment variables. Examples are a local secrets file, the operating system keychain, and an
in-house secret store. The rule that secret values themselves are never written in settings files still applies
([Secrets](plugins.md#secrets)).

**Minimal shape**: one method, `get_secret(name) -> str | None`. None when there is no value.

**Lookup order**: the server first looks at environment variables (the server setting `secrets.env_prefix` + the
name, or the uppercase name when there is no prefix). If there is nothing there, it asks the registered providers in
registration order and stops at the first one that returns a value. The example below shows that assembly without a
server.

```python
>>> from agent_console_modkit import env_secret_lookup, secret_lookup
>>> class DictProvider:
...     def __init__(self, values):
...         self._values = values
...     def get_secret(self, name):
...         return self._values.get(name)
>>> lookup = secret_lookup(
...     env_secret_lookup({"API_TOKEN": "from-env"}), [DictProvider({"api_token": "x", "db_password": "y"})]
... )
>>> lookup("api_token"), lookup("db_password"), lookup("missing")
('from-env', 'y', None)

```

**Taking settings (optional)**: entry points are created without arguments. If the provider needs administrator
settings such as a file location, give the provider class two classmethods (the shape of
`agent_console_modkit:ConfigurableSecretProvider`; inheritance is not required). `options_schema()` returns the JSON
Schema of the options (defaults in `properties.*.default`), and `from_options(options, *, environ, base_dir)` returns
a new provider built from the server setting `secrets.providers.<name>`. `base_dir` is the folder of the settings file
(the base for relative paths). The server rebuilds only providers that have settings, and refuses to start on a wrong
value (`ValueError`, with only the key name in the message). The schema and the current values appear in
`plugin_options` of `GET /api/v1/server-info` (fields marked as secret and values that look like plain-text secrets
are masked, and when path display is off, `format: path` fields are masked too).

```python
>>> from agent_console_modkit import ExtensionRegistries, configure_secret_providers, secret_providers_of
>>> class FolderProvider:
...     def __init__(self, folder=None):
...         self.folder = folder
...     def get_secret(self, name):
...         return None
...     @classmethod
...     def options_schema(cls):
...         return {"type": "object", "properties": {"folder": {"type": "string", "format": "path"}}}
...     @classmethod
...     def from_options(cls, options, *, environ, base_dir):
...         return cls(options.get("folder"))
>>> bundle = ExtensionRegistries()
>>> _ = bundle.extension("secret_providers").register("folder-secrets", FolderProvider())
>>> setup = configure_secret_providers(
...     bundle, {"folder-secrets": {"folder": "./keys"}}, environ={}, base_dir=None
... )
>>> setup.configured, secret_providers_of(bundle)[0].folder
(['folder-secrets'], './keys')

```

**Rules**

- Do not put values in logs, exceptions, or `repr`. What you may record is about the source location (a file path)
  and counts. It is safer to keep names out of logs too.
- If the source cannot be read (no file, no permission), return None instead of raising, and log one warning. Other
  providers and environment variables must keep working.
- Do not hard-code the source location (a file path and so on). Take it from administrator settings (the settings
  hook), environment variables, or package data defaults. Do not put secret values themselves in settings.
- When a value changes, apply it from the next lookup (it is better not to require a restart).

**Common mistakes**: writing a provider to override environment variables. Environment variables always come first. A
provider only receives names that are not in the environment variables.

**Data left after removal**: an agent that uses a name only that provider had fails at run time, with the node
failing as `agent.secret_not_found` (the error contains only the name). The secret source (a file and so on) was not
created by the provider, so it stays.

<!-- extdocs:facts secret-provider -->
- Registration: Register in the entry point group `agent_console.secret_providers` (constant `agent_console_runtime:SECRET_PROVIDERS_GROUP`). The registration name is the id.
- Interface:
  - `agent_console_runtime:SecretProvider` — Secret provider. None when there is no value for the name.
  - `agent_console_modkit:ConfigurableSecretProvider` — Secret provider that can be rebuilt from server administrator settings (settings hook).
- Settings: `secrets.providers`
- Built-in implementations: —
- Examples:
  - package: [examples/extensions/agent-console-example-secret-provider](../../examples/extensions/agent-console-example-secret-provider/README.md)
- Turning it off or removing it: Add the name to the setting `plugins.disabled`, or uninstall the package, then restart the server.
<!-- /extdocs:facts -->

## backend-model-discovery

**When to use**: when a backend can find out which models its account may use (an API that lists models, or a CLI
that reports them at start-up) without calling a model. The model field then fills itself, even when the
administrator list `backends.<id>.models` is empty, and each option shows where it came from. A backend without such a
source does not need this capability: the model field keeps the administrator list and typed model ids.

**Minimal shape**: declare `capabilities.model_discovery = true` in the descriptor and add
`async discover_models(ctx, timeout_s) -> ModelDiscoveryResult`. Both are needed; a method without the declaration (or
the other way round) counts as no capability. `list_models()` keeps returning only the administrator list.

```python
>>> import asyncio
>>> from agent_console_contracts import BackendCapabilities, BackendDescriptor, ModelInfo
>>> from agent_console_runtime import BackendModelCatalogService, ModelDiscoveryResult

>>> class GatewayBackend:
...     descriptor = BackendDescriptor(
...         id="gateway", title="Gateway", capabilities=BackendCapabilities(model_discovery=True)
...     )
...     async def list_models(self):
...         return [ModelInfo(id="gw-large", title="Large (pinned)")]  # the administrator list
...     async def discover_models(self, ctx, timeout_s):
...         return ModelDiscoveryResult(
...             ok=True,
...             method="gateway_api",
...             models=[{"id": "gw-small", "title": "Small"}, {"id": "gw-large", "title": "Large"}],
...         )
...     async def run(self, req, sink, cancel): ...

>>> service = BackendModelCatalogService(lambda: {"gateway": GatewayBackend()})
>>> catalog = asyncio.run(service.catalog("gateway"))
>>> catalog.discovery.state
'ok'
>>> [(m.id, m.title, m.sources) for m in catalog.models]
[('gw-large', 'Large (pinned)', ['config', 'discovered']), ('gw-small', 'Small', ['discovered'])]

```

The shared service `BackendModelCatalogService` (assembled by the runs module, which serves it at
`GET /api/v1/backends/{id}/model-catalog` and as the merged list of `GET /api/v1/backends/{id}/models`) does the rest.
The backend only reports what it found:

- **Merging**: the administrator list comes first and in its order, models only the lookup found follow in the
  backend's order, and the same `id` (exact string match, an alias is a different id) is one entry where the
  administrator's non-empty `title`, `description`, `context_window` and its `attributes` keys win. `ModelInfo.sources`
  says `config`, `discovered` or both.
- **Caching**: per backend, in memory only. A success is reused for `ttl_s`, a failure for `failure_ttl_s`, parallel
  requests share one lookup, and the first lookup happens on the first request (not at server start). `refresh=true`
  skips the cache. The host calls `invalidate(backend_id)` after a sign-in or sign-out finishes.
- **States** (`discovery.state`): `ok`; `stale` (the last good list, while a new lookup runs or after it failed);
  `failed` (no good list yet, plus the warning issue `backend.model_discovery_failed` with `details.backend_id` and
  `reason`); `disabled` (turned off by the administrator); `unsupported` (no capability, or the backend said so).
  A failure is still a normal response with the administrator list, so the field keeps working.
- **Limits and masking**: the call is cut at `timeout_s` (`reason = timeout`). Ids over 200 characters are dropped,
  titles are cut at 200 and descriptions at 1000 characters, and at most 500 items are kept (`ModelListLimits`, set by
  the host). Text passes through the masking function the host injects (`redact`; the runs module uses the same rules
  as the readiness routes), and log lines carry only the backend id, state, reason, method, count, and duration.

**Rules**

- Never call a model to find models (no tokens). Use only a listing API, a start-up response, or local data.
- Report failures as `ModelDiscoveryResult(ok=False, reason=...)` instead of raising. Use the shared reason names in
  `ModelDiscoveryReasons` (`auth_missing`, `auth_failed`, `subscription_disabled`, `network`, `timeout`,
  `invalid_response`, `cli_missing`, `cli_no_models`, `error`) when they fit; other names are allowed. An exception is
  reported as `error` with only the exception type name in `details.error`.
- When this sign-in can never list models, return `ModelDiscoveryResult(ok=False, unsupported=True, reason=...)`: the
  state is `unsupported`, no warning is shown, and no earlier list is kept.
- Refuse without starting anything when the lookup cannot work (no key, no sign-in, a method the administrator turned
  off): return the reason right away.
- Keep keys and tokens out of `models`, `details` and log lines. `method` is an open name for logs and `details` only;
  the screen does not show it. Item names and descriptions are outside data: they are shown as they are, never
  translated.
- Do not read files outside the backend's own folders (for example a user's home settings) to guess models. Settings
  that differ between installations (addresses, header values, page sizes) belong in the backend's own administrator
  options, not in code.

**Common mistakes**: returning the administrator list again from `discover_models` (it is merged already), turning the
capability on when the backend cannot list models (the model field then shows a failure warning for nothing; use
`unsupported` instead), or keeping your own cache inside the backend (the service already caches and invalidates it after
sign-in).

**Data left after removal**: nothing is stored. The list lives in server memory and is fetched again after a restart.
Agents keep the model ids they chose, and the field shows them as typed values. Server administrators turn lookups off
with `modules.options.mod-runs.model_discovery.enabled: false` or for single backends with `disabled_backends`.

<!-- extdocs:facts backend-model-discovery -->
- Registration: Give the implementation object (for example, a backend) the optional method `discover_models`. The host finds and uses it when it is there.
- Interface:
  - `agent_console_runtime:ModelDiscoveryCapableBackend` — Optional capability: a backend that lists its account's models without a model call.
  - `agent_console_runtime:ModelDiscoveryResult` — Result of ``discover_models``: the models found, or a failure reason.
  - `agent_console_runtime:BackendModelCatalogService` — Backend model lists (configured list plus account lookup) with caching and failure handling.
  - `agent_console_runtime:merge_models` — Merge the configured list and the discovered list into one list (pure function).
- Settings: `modules.options.mod-runs.model_discovery`
- Built-in implementations: `ac-backend-claude-sdk (agent-console-backend-claude-sdk)`, `ac-backend-fake-agent (agent-console-backend-fake-agent)`
- Examples:
  - package: [examples/extensions/agent-console-example-backend](../../examples/extensions/agent-console-example-backend/README.md)
  - reference: [packages/py/features/ac-backend-claude-sdk](../../packages/py/features/ac-backend-claude-sdk/README.md) — Built-in backend that asks Claude Code or the Models API
- Turning it off or removing it: Remove the method or return None to turn off only that capability.
<!-- /extdocs:facts -->
