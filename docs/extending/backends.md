# Execution backends

Agent nodes do not call models directly. They pass requests to an execution backend. The built-in backends (the
Claude Agent SDK, and a fake backend that runs without a model) are also implementations registered in the same group.
This page covers backends themselves, session archiving (an optional backend capability), and secret providers, which
resolve the secret references written in settings.

| What you want to do | Point |
| --- | --- |
| Run agents with another model SDK, CLI, or in-house gateway | [execution-backend](#execution-backend) |
| Archive and restore raw session files so conversations can resume in another app or at another path | [backend-session-archive](#backend-session-archive) |
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
- Built-in implementations: —
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
