# agent-console-example-secret-provider

An example and writing guide that adds a secret value provider with **a single plugin package** (extension point "secret value providers").
No engine, server, or web code changes. Once installed, secret references in definitions (`secret://name`) that are not found in environment variables are
looked up in the local file you specify. There is no external service and no network.

Provider `example-file`
- Reads the `KEY=VALUE` lines of one file. Empty lines and comment (`#`) lines are ignored, `=` inside a value is kept as it is, and one pair of matching
  quotes around a value is removed. For duplicate names, the later line wins. When a name is not found, it looks once more with the uppercase name (the same rule as the
  environment variable provider).
- **The file path is a setting**: the server setting `secrets.providers.example-file.path` (settings hook), or otherwise the environment variable
  `AGENT_CONSOLE_EXAMPLE_SECRETS_FILE` (the name is the package data `path_env`).
- When the file changes, it is read again on the next lookup (no restart needed). When the file does not exist or cannot be read, it **returns no value and only logs a warning**.
- **Values never leave**: logs, exceptions, and `repr` contain only the file path, line numbers, and the number of names (names are not logged either).
  In run history and response events, the engine masks resolved values as `[REDACTED]`.
- The line rules (comment markers, name regular expression, quotes, uppercase fallback, size limit) are option data (`data/defaults.json`).
- Dependencies: the run engine library (`agent-console-runtime`, the `SecretProvider` protocol) and `pydantic`.

This package is not a uv workspace member. When it is not installed, it changes nothing.

## How to build a provider

A provider follows one protocol, `agent_console_runtime.SecretProvider`: `get_secret(name) -> str | None` (None when missing).
The engine resolves references with a `SecretResolver` that asks the providers in order, and it remembers the resolved values to mask them in every record.

Using only this provider, without a server:

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_runtime import EnvSecretProvider, SecretResolver
>>> from agent_console_example_secret_provider import FileSecretProvider

>>> tmp = tempfile.TemporaryDirectory()
>>> path = Path(tmp.name) / "secrets.env"
>>> _ = path.write_text("# 로컬 비밀\nEXAMPLE_TOKEN=example-value-1\n", encoding="utf-8")
>>> provider = FileSecretProvider(path)
>>> provider.get_secret("example_token")  # falls back to the uppercase name
'example-value-1'
>>> resolver = SecretResolver([EnvSecretProvider({}), provider])  # order = environment variables -> file
>>> resolver.resolve_refs({"headers": {"Authorization": "secret://EXAMPLE_TOKEN"}})
{'headers': {'Authorization': 'example-value-1'}}
>>> resolver.redact("응답에 example-value-1 이 섞였다")
'응답에 [REDACTED] 이 섞였다'
>>> "example-value-1" in repr(provider)
False
>>> FileSecretProvider(Path(tmp.name) / "none.env").get_secret("EXAMPLE_TOKEN") is None  # warning only
True
>>> tmp.cleanup()

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

Rules
1. **None when missing**: do not raise. The next provider is asked, and when no provider has it, the engine fails only that node with `SecretNotFoundError`
   (name only, no value).
2. **Do not put values in logs, exceptions, or `repr`**: even for a wrong line, report only the line number (that line may contain a value).
3. **Do not repeat the same warning**: the provider is called on every lookup, so warn once only when the state changes.
4. **Inject external dependencies**: the path is received by `FileSecretProvider(path)`. Only the entry point value
   `EnvFileSecretProvider` (called without arguments) reads the process environment, and tests pass it with `EnvFileSecretProvider(environ)`.
5. **Thread safety**: the engine can call it from several runs at the same time.
6. **Receive administrator settings through the settings hook** (optional): when the class has two classmethods, the server passes the setting
   `secrets.providers.<key>` (see "Settings hook" below).

## Registration

One entry point in `pyproject.toml`. Group = `agent_console.secret_providers` (`agent_console_runtime.SECRET_PROVIDERS_GROUP`);
name = provider key. **The value is a class called without arguments.**

```toml
[project.entry-points."agent_console.secret_providers"]
"example-file" = "agent_console_example_secret_provider:EnvFileSecretProvider"
```

At server startup, the host plugin loader of the runs module reads this group. The lookup order is **environment variables (setting `secrets.env_prefix`)
first, then the registered providers (in key order)**. When the same name is in an environment variable, the environment variable wins.

To use it without installing, list the registration function in the server setting `plugins.modules` (it goes into the same registry):

```yaml
plugins:
  modules:
    - agent_console_example_secret_provider:register
```

When it is installed, do not add it. The entry point already registers `example-file`, so the same key would be registered twice and that plugin would
remain `failed`.

## Settings example

```bash
export AGENT_CONSOLE_EXAMPLE_SECRETS_FILE="$HOME/.config/agent-console/secrets.env"   # in the shell that starts the server
```

The secret file (do not commit it to the repository; when possible, make it readable only by you):

```text
# NAME=value
EXAMPLE_TOKEN=your-real-value
```

Definitions use references instead of values (for example `secret://EXAMPLE_TOKEN` in resource settings).

| Option (`data/defaults.json`) | Default | Meaning |
| --- | --- | --- |
| `path_env` | `AGENT_CONSOLE_EXAMPLE_SECRETS_FILE` | Name of the environment variable that holds the file path |
| `comment_prefixes` | `["#"]` | Comment line markers |
| `name_pattern` | `^[A-Za-z_][A-Za-z0-9_.-]*$` | Name regular expression (lines that do not match are skipped) |
| `strip_quotes` | `true` | Remove one pair of matching quotes around a value |
| `upper_fallback` | `true` | When a name is not found, look again with the uppercase name |
| `max_file_bytes` | 64KiB | Files larger than this are not read |

## Settings hook

The entry point is called without arguments. A provider that needs administrator settings has two classmethods on its class
(the shape of `agent_console_modkit.ConfigurableSecretProvider`; no subclassing or import needed):

- `options_schema() -> dict`: the options JSON Schema (defaults = `properties.*.default`). The server puts the schema, the current values (defaults filled in, secrets and paths masked),
  the settings location, and a YAML snippet into `plugin_options` of `GET /api/v1/server-info`.
  The top-level `title` and `description` of the schema become the form header of the *Extension options* section of the settings screen. A schema built from a Pydantic model
  would contain the class name and docstring as they are, so this example uses `ConfigDict(title=...)` and a one-sentence docstring, and sets
  a human-readable header in `options_schema()`.
- `from_options(options, *, environ, base_dir) -> provider`: builds a new provider from the value of the server setting `secrets.providers.<key>`.
  `base_dir` is the settings file folder (the base for relative paths), and `environ` is the server environment. Wrong values raise `ValueError` (key names only), and
  the server refuses to start (settings error).

The server rebuilds through the hook only the providers that **have** settings. Without settings, the provider stays as the entry point built it (this example uses the
environment variable path). Settings for an unknown key, or for a provider without the hook, only leave a server warning (`plugins.config`).

```yaml
secrets:
  providers:
    example-file:
      path: ./secrets.env        # a relative path is relative to the settings file folder; empty = the environment variable path
      comment_prefixes: ["#", ";"]
```

The settings hold only the file **location** and the line rules. The secret values themselves are never written in the settings file.

```python
>>> from agent_console_example_secret_provider import EnvFileSecretProvider, PATH_OPTION
>>> schema = EnvFileSecretProvider.options_schema()
>>> schema["properties"][PATH_OPTION]["format"], schema["properties"]["max_file_bytes"]["default"]
('path', 65536)
>>> made = EnvFileSecretProvider.from_options(
...     {PATH_OPTION: "secrets.env"}, environ={}, base_dir=Path("conf")
... )
>>> made.path == Path("conf") / "secrets.env"
True
>>> EnvFileSecretProvider.from_options({"token": "x"}, environ={}, base_dir=None)
Traceback (most recent call last):
...
ValueError: 비밀 파일 설정이 잘못됐습니다: token

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

To change the line rules in code, you can also use a small `register` function that registers `FileSecretProvider(path, settings=load_settings({...}))` directly,
through `plugins.modules`.

## Install and remove

Run these from the repository root. On WSL (`/mnt/c`), add the environment variables.

```bash
export UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=$HOME/.cache/agent-console-wsl-venv   # WSL only
uv pip install --python "$UV_PROJECT_ENVIRONMENT" -e examples/extensions/agent-console-example-secret-provider   # install
uv pip uninstall --python "$UV_PROJECT_ENVIRONMENT" agent-console-example-secret-provider                        # remove
```

Entry points are read at server startup, so **restart the server** after installing or removing.
- Install: `plugins` of `GET /api/v1/server-info` shows `example-file` (group `agent_console.secret_providers`) as `loaded`.
  Without the path environment variable, there is one warning at startup.
- Remove: when a definition uses a name that existed only in this file, that node fails at run time because the secret cannot be found (the error contains only the name).
  The secret file is not deleted (this package never writes files).
- Keep it installed but not loaded: remove `example-file` from the server setting `plugins.enabled` (allow list).

Note: `uv sync` removes packages that are not in the lock file. To sync with the example installed, use `uv sync --all-packages --inexact`.

## Test

The tests run without installing (pytest setting `pythonpath = ["src"]`). The `examples` step of the root `uv run poe check` runs mypy and pytest
with this folder's settings (`uv run poe examples`). Outside the repository, copy only this folder, run `uv sync --find-links <wheelhouse>`
(`uv run poe wheels` in the repository), and then `uv run pytest`.

```bash
cd examples/extensions/agent-console-example-secret-provider
uv run --project ../../.. python -m pytest
```

- `tests/test_agent_console_example_secret_provider.py`: the entry point declaration, loading with the registry loader, `register`, line rules
  (option data), uppercase fallback, missing file = one warning → read without a restart once the file appears, rereading a changed file, **no values or names
  in logs, `repr`, or the `SecretNotFoundError` message**, the size limit, no path set (one warning on first use), and the settings hook (schema and defaults,
  relative path = settings file folder, the environment variable when there is no path, wrong options report key names only).
- `tests/test_engine.py`: even when an engine test node puts a resolved value into events, results, and errors, **the saved Run, NodeRun, and events do not contain
  the value** (`[REDACTED]`), and environment variables come before the file.
- `tests/test_server.py`: the integrated server (registered through `plugins.modules` when not installed, and only through the entry point when installed; using both
  registers the same key twice and the plugin fails). In a team run the reference is resolved to this file's value and used, but
  **response events, run status, `/server-info`, and logs do not contain the value**; without the file the server starts and only that node fails, with a warning.
  When the administrator setting `secrets.providers.example-file` gives the path, that file is read without the environment variable and a view appears in `plugin_options`;
  wrong options refuse to start (key names only); settings for an unknown provider give a server warning.
