# agent-console-example-backend

An example that adds a new **execution backend** and the optional capabilities **session record archive** and **model discovery** with a single plugin package.
No engine, server, or web code changes. Once installed, it appears in the backend list (`GET /api/v1/backends`)
and can be chosen in agent settings; it disappears when removed.

Backend `example.scripted` (script backend)
- It calls no model and no network. It looks at the rules `{contains, reply}` written in the agent definition's `backend_options` (the script)
  from the top and answers with the `reply` of the first matching rule, or with `default_reply` (default `$prompt`) when none matches.
  It fills `$prompt`, `$agent_name`, `$model`, and `$turn` in the reply text. What to answer is entirely data.
- Declared capabilities: `streaming` (streams the answer in pieces of the setting `chunk_chars`), `cancel`, and `resume` (only when there is a session record folder).
  Tools, subagents, and platform tools are not declared; the engine and screens look only at the declarations and do not use those features.
- Administrator settings hook `from_options`: the app passes the setting `modules.options.mod-runs.backends."example.scripted"` as it is
  (the app does not know what the keys mean). Unknown keys are rejected, and error messages do not include values.
- Session record archive (optional): with `session_dir`, every run appends one line to `<session_dir>/<project folder key>/<session>.jsonl`,
  and `session_archive()` provides archiving and restoring that file (it only passes a key function to the shared implementation `JsonlFolderSessionArchive`).
  A request that continues a session fails with `example.session_missing` when there is no record.
- Model discovery (optional): with `models_file`, the backend declares `capabilities.model_discovery` and `discover_models()` reads that JSON list
  (`[{"id": ..., "title": ...}, ...]`, standing in for a list that a gateway hands out). The server merges it after the configured `models`
  (see [Model discovery](#model-discovery)). A missing file is reason `models_file_missing`, a file that is not a JSON list is `invalid_response`.
- Events (`agent.session_started`, `agent.text_delta`, `agent.message`, `agent.usage`) carry only the session id, backend id, model id, and reply text.
  They do not carry the project folder or record folder paths or environment values (the tests check this).

This package is not a uv workspace member. When it is not installed, it changes nothing.

## Minimal code

A backend needs only three things: `descriptor`, `list_models`, and `run`. `run` emits events through `sink.emit` and returns a result.

```python
>>> import asyncio
>>> from agent_console_contracts import AgentMessagePayload, Agent, BackendDescriptor
>>> from agent_console_runtime import AgentResult, CancelToken, ExecutionBackend, AgentRequest
>>> from agent_console_runtime.testing_sink import ValidatingSink

>>> class Echo:
...     descriptor = BackendDescriptor(id="echo", title="되돌려 주기")
...     async def list_models(self):
...         return []
...     async def run(self, req, sink, cancel):
...         await sink.emit("agent.message", AgentMessagePayload(role="assistant", text=req.prompt))
...         return AgentResult(status="succeeded", text=req.prompt)

>>> isinstance(Echo(), ExecutionBackend)
True
>>> req = AgentRequest(agent=Agent(id="a", name="A"), prompt="안녕")
>>> asyncio.run(Echo().run(req, ValidatingSink(), CancelToken())).text
'안녕'

```

The real implementation is `src/agent_console_example_backend/_backend.py` (script model `ScriptOptions`, administrator settings `InstallOptions`,
capability declarations, streaming and cancel, session records). Below, that implementation is loaded as if it were registered as an entry point, and run.

```python
>>> import tempfile
>>> from importlib.metadata import EntryPoint
>>> from pathlib import Path
>>> from agent_console_runtime import (
...     BACKENDS_GROUP, BackendHostContext, Registries, SecretResolver, load_registries, session_archive_of,
... )

>>> ep = EntryPoint("example.scripted", "agent_console_example_backend:ScriptedBackend", BACKENDS_GROUP)
>>> registries = Registries()
>>> _ = load_registries(registries, entry_points=[ep])   # when installed: load_registries(registries)
>>> backend = registries.backends.get("example.scripted")
>>> backend.descriptor.capabilities.resume
False

>>> workspace = Path(tempfile.mkdtemp())                 # the app builds it again through the settings hook
>>> backend = type(backend).from_options(
...     {"session_dir": "scripted-sessions"},
...     secrets=SecretResolver([]), environ={}, host=BackendHostContext(workspace_dir=workspace),
... )
>>> backend.descriptor.capabilities.resume, session_archive_of(backend) is not None
(True, True)

>>> bot = Agent.model_validate({
...     "id": "bot", "name": "봇", "backend": "example.scripted",
...     "backend_options": {"rules": [{"contains": "안녕", "reply": "반가워요($turn)"}]},
... })
>>> first = asyncio.run(backend.run(
...     AgentRequest(agent=bot, prompt="안녕", cwd=str(workspace)), ValidatingSink(), CancelToken()
... ))
>>> again = asyncio.run(backend.run(
...     AgentRequest(agent=bot, prompt="안녕", cwd=str(workspace), session=first.session),
...     ValidatingSink(), CancelToken(),
... ))
>>> first.text, again.text, again.session == first.session
('반가워요(1)', '반가워요(2)', True)

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

## Registration and settings

```toml
[project.entry-points."agent_console.backends"]   # agent_console_runtime.BACKENDS_GROUP
"example.scripted" = "agent_console_example_backend:ScriptedBackend"
```

The entry point value is called without arguments. When construction needs arguments, add the classmethod `from_options(options, *, secrets, environ, host=None)`
(`ConfigurableBackend`). For the session record archive, the method `session_archive()` returns a `SessionArchive` or None (`SessionArchiveCapable`).

Administrator settings (the server settings file). All of them can be omitted.

```yaml
modules:
  options:
    mod-runs:
      backends:
        example.scripted:
          models: [{id: script-1, title: "Script 1"}]  # model list (labels only)
          session_dir: scripted-sessions             # a relative path is relative to the app workspace; empty = no records, archive, or continuation
          chunk_chars: 8                             # stream the answer 8 characters at a time; 0 = all at once
```

The agent definition (the agent editor on the screen, or a definition file). The script schema is published as the backend descriptor's `config_schema`.

```yaml
backend: example.scripted
backend_options:
  rules:
    - {contains: "hello", reply: "Nice to meet you. I am $agent_name"}
    - {contains: "Status", reply: "Status: OK (turn $turn)", ignore_case: false}
  default_reply: "Received: $prompt"
```

## Model discovery

The optional capability lists the models an account can use **without calling a model**. Declare `capabilities.model_discovery = true`
and add `discover_models(ctx, timeout_s)`, which returns a `ModelDiscoveryResult`. Report a failure as `ok=False` with a `reason` (open
vocabulary, `ModelDiscoveryReasons` has the shared names) instead of raising; report "this setup cannot list models" as `unsupported=True`.
The shared service `BackendModelCatalogService` adds caching, one lookup for parallel requests, the time limit, length limits, masking, and
the warning issue `backend.model_discovery_failed`; the configured list stays first and wins on the same id (`merge_models`).

```python
>>> from agent_console_contracts import BackendCapabilities, BackendDescriptor, ModelInfo
>>> from agent_console_runtime import BackendModelCatalogService, ModelDiscoveryResult

>>> class Listing:
...     descriptor = BackendDescriptor(
...         id="listing", title="Listing", capabilities=BackendCapabilities(model_discovery=True)
...     )
...     async def list_models(self):
...         return [ModelInfo(id="m-mine", title="Mine")]          # administrator list
...     async def discover_models(self, ctx, timeout_s):
...         return ModelDiscoveryResult(ok=True, models=[{"id": "m-mine"}, {"id": "m-other"}])
...     async def run(self, req, sink, cancel): ...

>>> service = BackendModelCatalogService(lambda: {"listing": Listing()})
>>> catalog = asyncio.run(service.catalog("listing"))
>>> catalog.discovery.state, [(m.id, m.sources) for m in catalog.models]
('ok', [('m-mine', ['config', 'discovered']), ('m-other', ['discovered'])])

```

Server settings: turning discovery on or off and the cache times are `modules.options.mod-runs.model_discovery`
(`enabled`, `ttl_s`, `failure_ttl_s`, `timeout_s`, `disabled_backends`). For this example:

```yaml
modules:
  options:
    mod-runs:
      backends:
        example.scripted:
          models_file: scripted-models.json   # relative = app workspace; empty = no discovery capability
```

End-to-end tests can do the same without this package: the built-in test backend `fake-agent` takes `discovered_models`
(the list the lookup returns; the test picks the ids), `discovery_failure` (a reason code, `unsupported` for "cannot list"), and
`discovery_delay_s` under `modules.options.mod-runs.backends.fake-agent`.

## Install and remove

Run these from the repository root. Install into the same Python environment as the server. When the server runs in a different virtual environment,
add `--python <path to that virtual environment>` (for example, when you set it with `UV_PROJECT_ENVIRONMENT`, `--python "$UV_PROJECT_ENVIRONMENT"`).

```bash
uv pip install -e examples/extensions/agent-console-example-backend   # install
uv pip uninstall agent-console-example-backend                        # remove
```

**Restart the server** after installing or removing.
- Install: `GET /api/v1/backends` lists `example.scripted` with an *Example* badge. Choose it as an agent's execution backend and run a team, and it answers according to the script.
- Remove: it disappears from the list. Leftover administrator settings `backends."example.scripted"` only leave a "not registered" warning at server startup,
  and nodes of agents that chose this backend fail with `agent.unknown_backend`. Session record files that already exist are not deleted.
- Turn off while installed: remove it from the server setting `plugins.enabled` (allow list).

Note: `uv sync` removes packages that are not in the lock file. To sync with the example installed, use `uv sync --all-packages --inexact`.

## Test

```bash
cd examples/extensions/agent-console-example-backend
uv run --project ../../.. python -m pytest
```

The tests run without installing (`pythonpath = ["src"]`). There are unit tests (capabilities, rules, streaming, cancel, settings hook, session records, archive and restore, no paths or secret values in events),
engine tests (a handoff chain with the default node and edge types), and server assembly tests (runs module + test host: shown in the list → team run completes → removed → warning).
The `examples` step of the root `uv run poe check` runs mypy and pytest with this folder's settings (`uv run poe examples`).
