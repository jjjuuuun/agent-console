# agent-console-backend-claude-sdk

The execution backend adapter for the Claude Agent SDK (`claude-agent-sdk`, `ClaudeSDKClient`).
entry point `agent_console.backends:claude-agent-sdk`.

## Installation

```bash
uv sync --all-packages                               # inside the workspace
uv pip install ./packages/py/features/ac-backend-claude-sdk   # standalone
```

Dependencies: `agent-console-runtime`, `agent-console-contracts`, `agent-console-claude-format`, `agent-console-registry`, `agent-console-secret-rules`, `pydantic`,
`claude-agent-sdk`, `httpx`. Optional: `[hook-probe]`, `[login]`.

| Dependency | What | Why | Alternatives |
| --- | --- | --- | --- |
| `claude-agent-sdk` (checked version 0.2.166, bundles the CLI) | Runs Claude Code agents | Uses hook callbacks, MCP, and interrupt together, and installation is simple | Adding a separate backend that drives the CLI `stream-json` directly (the agent_bench approach) |
| `agent-console-registry` (internal) | Loads and checks observation collector entry points (`load_entry_points`, failures = reports) | The same registration method as other extension points | Iterating `importlib.metadata` directly (failure reports and validator rules would have to be rebuilt) |
| `agent-console-claude-format` (internal) | The folder key `project_key` for session archives (project folder → `projects/<key>`) | One place for the same function as the log source (no copies). Only `ruamel.yaml` comes along | Depending on `agent-console-logs-claude` (drags in the log index dependency) / copying the rule |
| `agent-console-hook-probe` (internal, **optional** extra `hook-probe`) | Hook command wrapping arguments (`wrap_command`, `wrap_command_line`) when `observe.hook_probe` is on | Keeps the wrapping rules and record format in one place, the probe package. Optional so that the dependencies of the record source and classifier (`agent-console-logs`) are not pulled into a standalone backend install | A required dependency (heavier backend install) / rebuilding the wrapping arguments here (copying the same logic) |

| `httpx` (BSD-3) | Async Anthropic Models API calls for model discovery (time limit per request, page by page) | Async with timeouts out of the box; tests replace the network with `httpx.MockTransport` (no real calls). Already in the lock through `claude-agent-sdk` → `mcp` | The standard library `urllib` (blocking, needs a thread wrapper and a separate test double) |
| `agent-console-secret-rules` (internal) | Safety checks of the subscription sign-in screen text rules (user-editable regexes, through `ac-safe-regex`) | The rule that user regexes go through one validator | Plain `re.compile` (cannot block dangerous regexes) |
| `agent-console-pty-session` (internal, **optional** extra `login`) | Starts `claude auth login` in a PTY, reads the screen text, and sends input (subscription sign-in) | The CLI sign-in screen requires a TTY. PTY handling and terminal text interpretation live in one package | The user runs `claude auth login` in a terminal themselves (no sign-in from the app screen) |

Install them together with `pip install "agent-console-backend-claude-sdk[hook-probe]"`. Without it, even with `observe.hook_probe` on,
nothing is wrapped and a `log.warning` is emitted (everything else works). The server app installs `[login]` too (subscription sign-in is on by default).

## Minimal usage

```python
>>> import asyncio
>>> from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock
>>> from agent_console_backend_claude_sdk import ClaudeSdkBackend
>>> from agent_console_backend_claude_sdk.testing import FakeSdkClient, ValidatingSink
>>> from agent_console_contracts import Agent, Limits
>>> from agent_console_runtime import (
...     AgentRequest,
...     CancelToken,
...     EnvSecretProvider,
...     SecretResolver,
... )

>>> agent = Agent(
...     id="coder",
...     name="Coder",
...     model="<설정의 모델 id>",
...     tools=["Read", "Bash"],
...     # this example uses the API key mode. Keep the value only as a secret store reference.
...     backend_options={"auth": {"mode": "api_key", "api_key": "secret://anthropic_api_key"}},
... )

```

In real use, omit `client_factory` (the SDK client). Here a fake client that emits predefined messages is injected.

```python
>>> script = [
...     AssistantMessage(content=[TextBlock("안녕하세요")], model="m"),
...     ResultMessage(
...         subtype="success",
...         duration_ms=1,
...         duration_api_ms=1,
...         is_error=False,
...         num_turns=1,
...         session_id="sess-1",
...         result="안녕하세요",
...     ),
... ]
>>> clients = []
>>> def factory(options):
...     clients.append(FakeSdkClient(options, script))
...     return clients[-1]
>>> secrets = SecretResolver([EnvSecretProvider({"ANTHROPIC_API_KEY": "sk-test-0000"})])
>>> backend = ClaudeSdkBackend(client_factory=factory, secrets=secrets, environ={})
>>> req = AgentRequest(agent=agent, prompt="인사해", cwd="/ws", limits=Limits(commands=["git status"]))
>>> result = asyncio.run(backend.run(req, ValidatingSink(), CancelToken()))
>>> result.status, result.text, result.session.session_id
('succeeded', '안녕하세요', 'sess-1')
>>> options = clients[0].options  # the SDK options the backend built
>>> options.cwd, options.allowed_tools, "ANTHROPIC_API_KEY" in options.env
('/ws', ['Read', 'Bash'], True)

```

Tests inject a fake client with `ClaudeSdkBackend(client_factory=...)` (`FakeSdkClient` from `agent_console_backend_claude_sdk.testing`,
and `ValidatingSink`, `ListeningSink`, `InteractiveSink` re-exported from the shared `agent_console_runtime.testing_sink`).

## Authentication

| Method | Settings | Behavior |
| --- | --- | --- |
| **Your own subscription sign-in credentials (default, at your own risk)** | `auth: {mode: subscription}` (+ optional `oauth_token: secret://…`). `auth: {}` is the same | Overrides `ANTHROPIC_API_KEY` with an empty value so an API key does not get in the way. With a token, it is passed as `CLAUDE_CODE_OAUTH_TOKEN`; otherwise the CLI reads the sign-in credentials from the app-only credentials folder (see "App-only credentials folder" below) |
| API key (optional) | `auth: {mode: api_key, api_key: secret://anthropic_api_key}` | Passed as `ANTHROPIC_API_KEY`, and `CLAUDE_CODE_OAUTH_TOKEN` is cleared. Without a key, nothing runs (`auth_missing`) |

- **The default is the subscription (at your own risk); an API key is also available**. The default of `ClaudeSdkAuth.mode` is
  `subscription`, the default of the server administrator setting `allow_subscription_auth` is `true`, and the status check `readiness.auth` also defaults to the subscription.
  Anthropic's documentation recommends API keys for apps built on the Agent SDK, so using subscription credentials is at your own risk, and the warnings below are still emitted.
- **The subscription method works only when the server administrator setting `allow_subscription_auth` (default `true`) is on**.
  - Off (when the server administrator changed it to `false`): `validate_settings` emits error `backend.subscription_auth_disabled` (`AUTH_ISSUES.SUBSCRIPTION_DISABLED`)
    with the sentence `SUBSCRIPTION_AUTH_DISABLED_MESSAGE` (it says that Anthropic's documentation recommends API keys for Agent SDK apps,
    and that to use your own subscription credentials you turn on allow_subscription_auth in the server administrator settings, at your own risk).
    `run` returns a failure with the same code (`ClaudeSdkErrorCodes.SUBSCRIPTION_AUTH_DISABLED`) before resolving secrets or calling the SDK.
  - On: `validate_settings` emits warning `backend.subscription_auth_enabled`, and every run emits a `log.warning`, both with the same strengthened
    sentence (`SUBSCRIPTION_AUTH_WARNING`, the at-your-own-risk notice).
  - This package has **no path that receives or stores OAuth tokens.** Tokens are read only through `secret://` references the user keeps in their own
    secret store (using only the resolver's `resolve`), passed to the CLI child process env, and never left in events, results, or files.
    There is no path to connect someone else's subscription credentials either. Tests: `tests/…_subscription_3r29.py`.
  - The 5-hour and weekly usage (`usage.rate_limit`) is meaningful only with the subscription method.
- If `auth` is left out entirely (`null`, no key), only `env` and the environment policy apply as before (if the server environment has
  `ANTHROPIC_API_KEY`, the CLI uses it; otherwise the Claude Code sign-in. The subscription allowance check and warnings happen only when `auth`
  is written). The variable names can be changed with `api_key_env` and `oauth_token_env`.
- The default of `setting_sources` is `["project"]`, and `user` is not included (isolating the user's `~/.claude` settings).

### App-only credentials folder

Subscription sign-in is **one sign-in per app**. Credentials are kept in one place inside the **app workspace** (server
`--workspace`, the app data folder), neither `~/.claude` nor a project folder, and every project and every run shares them. The default is `<workspace>/.state/claude`
(the app state folder `.state/`, the same place as the database and run folders), and this folder is passed as `CLAUDE_CONFIG_DIR` to the child processes of SDK runs, connection tests, and the sign-in
PTY (`claude auth login`, `status`, `logout`). If credentials exist they are used automatically; otherwise the status is
`subscription_login_required` (sign-in required). **It never falls back to `~/.claude` (HOME) or the server environment's `CLAUDE_CONFIG_DIR`.**
The app writes nothing into project folders for credentials (the `.gitignore` line goes only to the workspace).

> `<project>/.agent-console/claude` created by earlier versions is neither moved nor deleted. There are no credentials at the new location, so
> the status shows sign-in required; **sign in once more**. If you do not need the old folder, delete it yourself.

- Path resolution happens in one place: `ClaudeSdkBackend.credential_dir(person_id=None) -> Path | None` (public) → `resolve_auth_dir`
  (`AuthDirLocation`: absolute path, relative path for display, environment variable name, sign-in files). The base is the app workspace, and there is no project
  argument. The app passes the workspace with `from_options(..., host=BackendHostContext(workspace_dir=…))` (`mod-runs` uses the
  host `paths.workspace`). Personal mode has only `person_id=None`. Team mode (credentials per person) is extended only through the `{person}` slot of the `config_dir` template
  (`PERSON_PLACEHOLDER`, for example `.state/people/{person}/claude`) and this argument. In standalone use, if no
  workspace is given (and the path is relative), the app-only folder is not used and the child process environment is followed as is.
- Preparation (`prepare_auth_dir`, right before runs, connection tests, sign-in, and sign-out; idempotent): create the folder (700) → add a `.state/` line to the **workspace** folder's
  `.gitignore` (meaningful when the workspace is inside a git repository; if the file does not exist it is created; if it is the user's file, only the line is appended
  at the end; if a line differing only by leading or trailing `/` already exists, it is left alone) → narrow the permissions of the folder and the files directly under it (700, 600). If preparation fails,
  runs fail with `backend.auth_dir_unavailable` and sign-in is refused (the message contains no paths or credential contents).
- The status check (`status`) does not create the folder. It only narrows the permissions of existing folders and files, and if they cannot be narrowed (file systems without permission support),
  it reports through the check item `auth_dir_permissions` and `detail`. The `note` and `detail` of the check item `auth_dir` carry the location (a path relative to
  the workspace).
- Credential file contents are never read (only existence and permissions). Contents never go to logs, responses, or the screen.
- Even if the agent's `backend_options.env` sets `CLAUDE_CONFIG_DIR`, the app-only folder wins and a `log.warning` is emitted.
- The existing `oauth_token: secret://…` method and the API key method stay the same (only `CLAUDE_CONFIG_DIR` is passed along).
- Even if `setting_sources` includes `user`, the CLI looks at the user settings in `CLAUDE_CONFIG_DIR` (= the app credentials folder). `~/.claude`
  is read only with `auth_dir.config_dir: null` (app-only folder turned off).

Server administrator setting `auth_dir` (`ClaudeSdkAuthDirOptions`):

| Key | Default | Meaning |
| --- | --- | --- |
| `config_dir` | `.state/claude` | The credentials folder. Relative paths are relative to the app workspace; `~`, `${NAME}`, and `{person}` (team mode template) are allowed. With `null`, no app-only folder is used (the server environment's `CLAUDE_CONFIG_DIR` or `~/.claude`). If you change it, also change `workspace_roots` of the log source `claude-code-jsonl` (default `.state/claude/projects`) |
| `env_var` | `CLAUDE_CONFIG_DIR` | The environment variable name given to child processes |
| `login_files` | `[".credentials.json"]` | Files that mean signed in (inside the folder; only existence is checked) |
| `dir_mode`, `file_mode` | `0o700`, `0o600` | Permissions (POSIX) |
| `gitignore`, `gitignore_entry` | `true`, `null` (= the first folder relative to the workspace + `/`) | Whether to add to the workspace `.gitignore` and the line to add. Not added when the folder is outside the workspace |

```python
>>> from pathlib import Path
>>> from agent_console_backend_claude_sdk import ClaudeSdkAuthDirOptions, ClaudeSdkBackend, resolve_auth_dir
>>> loc = resolve_auth_dir(ClaudeSdkAuthDirOptions(), workspace="/data/app", environ={})
>>> loc.display, loc.path == Path("/data/app/.state/claude")
('.state/claude', True)
>>> ClaudeSdkBackend(workspace="/data/app", environ={}).credential_dir() == loc.path
True

```

Log collection (`ac-logs-claude`) reads only sessions of registered project folder keys, from two places: `.state/claude/projects` in the app workspace (sessions the app ran) and `~/.claude/projects` (CLI sessions,
read-only) (the include pattern is `*.jsonl`, so credential files are not read).
Export and import build from definitions or read only the project `.claude/`, so they do not touch this folder. Tests:
`tests/…_auth_dir_57r30.py` (present, absent, permission problems, ignoring `~/.claude` with an empty HOME, the workspace `.gitignore`, project folders
unchanged, projects A and B sharing the same folder, the per-person template of `credential_dir`, FakePty sign-in writing to the same folder).

### Status check and connection test

The descriptor declares `capabilities.status = true` and `capabilities.probe = true` and implements both optional methods
(`agent_console_runtime.StatusCapableBackend`, `ProbeCapableBackend`). The server wraps them in `BackendReadinessService` and publishes them at
`GET /api/v1/backends/{id}/status` and `POST /api/v1/backends/{id}/probe`. Both look at the authentication method of the server administrator setting `readiness.auth`
(default `{mode: subscription}`, the subscription sign-in; the API key `{mode: api_key, api_key: secret://anthropic_api_key}` is also available); per-agent `auth`
is checked separately at run time by `validate_settings` and `run`.

- **`status(ctx)`: a static check, no model or network calls.** For secrets it only asks whether the name exists (`ctx.has_secret`, without
  reading the value), and for sign-in files it only checks existence. Results are `state` (`ReadinessStates`, an open vocabulary), `tone`, `summary`, `fixes`:

  | `state` | Tone | When |
  | --- | --- | --- |
  | `auth_ready` | ok | The API key secret exists |
  | `auth_missing` | error | The API key secret is missing (fix button for where to put the API key) |
  | `subscription_disabled` | warn | Subscription method but `allow_subscription_auth` is off (fix button for the server administrator settings) |
  | `subscription_ready` | warn | The subscription method is on and a token secret or sign-in file exists (the at-your-own-risk text in `detail`) |
  | `subscription_login_required` | warn | No sign-in file in the app-only credentials folder (sign-in required). Only this folder is checked |
  | `subscription_unverified` | warn | With the app-only folder turned off (`auth_dir.config_dir: null`), no sign-in file (`readiness.subscription_files`) was found |

  If the app-only credentials folder exists, only its `auth_dir.login_files` are checked. The rules below apply only when the app-only folder is turned off.
  Only **the first candidate that resolves** is checked as the sign-in file (`login_file`). Like the CLI, if the child process would receive
  `CLAUDE_CONFIG_DIR` (after the environment policy is applied; an empty value = none), only that folder is checked; otherwise `~/.claude`.
  If `CLAUDE_CONFIG_DIR` is an empty folder, the result is `subscription_unverified` even if the home folder has a sign-in file.
  | `subscription_token_missing` | error | The secret that the `oauth_token` reference points to is missing |
  | `cli_missing` | error | The Claude Code executable was not found (`readiness.cli_path` → the SDK bundle → PATH, in that order) |

  `checks` contain only "present/absent" per item and secret **names** (no values or partial values).
- **`probe(ctx, timeout_s)`: a short real call made only when the user presses the button.** It sends one line of `readiness.probe_prompt` with no tools (`tools=[]`), one turn
  (`max_turns=1`), no settings files (`setting_sources=[]`), no MCP, an empty system prompt, a temporary project folder, and
  session persistence off (`readiness.probe_extra_args` default `--no-session-persistence`). The model is `readiness.probe_model` (the CLI default when empty).
  - **Refused without a call**: no executable (`cli_missing`), subscription method with the server administrator setting off
    (`backend.subscription_auth_disabled`, no workaround call), no key or token (`auth_missing`).
  - **Time limit**: cut a little before `timeout_s` and the connection is closed (`timeout`). The server limit is applied by the service.
  - **Failure reasons** (`ProbeReasonCodes`, `details.category` = `PROBE_CATEGORIES`): authentication `auth_failed`
    (`AssistantMessage.error=authentication_failed` or HTTP 401 or 403), network `network` (`CLIConnectionError`,
    `ConnectionError`), timeout `timeout`, other `error`. `details` contain only the model id, error kind, HTTP code, and exception type
    name, never response text, exception messages, or secret values. CLI stderr is discarded.
  - The cost notice is the descriptor's `probe_cost_note` (`PROBE_COST_NOTE`).
- Text and fix buttons (web route roles, settings sections) are data: `readiness.texts` (`ClaudeSdkReadinessTexts`, `FixLink`).
  Sentences with values (missing secret name, credentials location, loose permissions, secret check note, connection test
  timeout) are also sent as source template + values in `text_templates` (`/detail` one entry per sentence, `/checks/<i>/note`,
  `/message`), so the web can show them in the screen language. Text you change in `texts` is not translated (it no longer
  matches the catalog key); to translate it, put your template as a `text` key in a catalog folder (`mod-i18n.catalog_dirs`).
- The parts can be used on their own: `assess_readiness` (authentication interpretation → status), `classify_probe_messages`, `classify_probe_error`,
  `find_claude_cli`, `expand_path`.

```python
>>> from agent_console_backend_claude_sdk import ClaudeSdkReadinessOptions, assess_readiness
>>> a = assess_readiness(
...     ClaudeSdkReadinessOptions(),
...     allow_subscription_auth=True,
...     has_secret=lambda name: False,
...     cli_found=True,
...     environ={"HOME": "/srv/me"},
...     path_exists=lambda path: path == "/srv/me/.claude/.credentials.json",
... )
>>> a.state, a.tone, a.probe_block
('subscription_ready', 'warn', None)
>>> from agent_console_backend_claude_sdk import ClaudeSdkAuth
>>> a = assess_readiness(
...     ClaudeSdkReadinessOptions(auth=ClaudeSdkAuth(mode="api_key", api_key="secret://anthropic_api_key")),
...     allow_subscription_auth=True,
...     has_secret=lambda name: False,
...     cli_found=True,
...     environ={},
... )
>>> a.state, a.tone, a.probe_block
('auth_missing', 'error', 'auth_missing')

```

Tests (`tests/…_readiness_52r68.py`) use only fake SDK clients and check that the status check and refused connection tests create zero real
`ClaudeSDKClient` instances, and that key values (and parts of them) appear nowhere in responses, logs, or exceptions.

### Model discovery (optional capability)

The descriptor declares `capabilities.model_discovery = true` and implements `discover_models(ctx, timeout_s)`
(`agent_console_runtime.ModelDiscoveryCapableBackend`). The server wraps it in `BackendModelCatalogService` (cache, merging with the
administrator list `models`, failures as data) and fills the model field (`GET /api/v1/backends/{id}/models`, `…/model-catalog`).
**Neither method calls a model** (no token usage):

- `sdk_init` (subscription): starts the Claude Code CLI with the connection test's options (app-only credentials folder, a temporary
  working folder, no tools, no settings files, session persistence off) and only calls `connect()`, `get_server_info()` and
  `disconnect()` — never `query()`. The `models` items of the CLI initialize response (`value` → id, `displayName` → title,
  `description`, other keys → `attributes`) become `ModelInfo`; items without `value` are skipped (`details.skipped`). A response
  without `models` is `unsupported` (`cli_no_models`). `disconnect()` always runs, also on timeout or error.
- `models_api` (API key): `GET {base}/v1/models` page by page (`limit` = `page_limit`, `after_id` = `last_id` while `has_more`) with
  the headers `x-api-key` and `anthropic-version`. `id` → id, `display_name` → title, `max_input_tokens` → `context_window`, other
  keys (except `type`) → `attributes`. 401 and 403 → `auth_failed`, connection errors → `network`, timeouts → `timeout`, other
  shapes → `invalid_response`, other HTTP errors → `error` (`details.http_status`). The key is only in the request header, never in
  results, `details`, or logs.
- Refused without a CLI start or HTTP call: subscription method with `allow_subscription_auth` off (`subscription_disabled`), no key,
  token, or app-only sign-in (`auth_missing`), no executable for `sdk_init` (`cli_missing`).

Administrator setting `model_discovery` (`ClaudeSdkModelDiscoveryOptions`):

| Key | Default | Meaning |
| --- | --- | --- |
| `method` | `auto` | `auto` = `models_api` when `readiness.auth` is an API key, `sdk_init` when it is a subscription. `sdk_init` or `models_api` forces one |
| `api_base_url` | `null` | Models API address (proxy or gateway). Empty = environment variable `ANTHROPIC_BASE_URL`, then the official address |
| `api_version` | `2023-06-01` | The `anthropic-version` header |
| `page_limit` | `1000` | Models per page (1–1000) |

Turning discovery on or off and the cache and wait times are server settings for every backend
(`modules.options.mod-runs.model_discovery`). Injection points for tests: `client_factory` (an object with `get_server_info`,
`ServerInfoClient`) and `http_client_factory` (`HttpClientFactory`).

Known limits:
- The list follows the administrator check authentication (`readiness.auth`), the same one the connection test uses. Agents that set
  a different `backend_options.auth` are not looked up separately; pick their model by typing it.
- The subscription list is what the installed Claude Code CLI puts in its initialize response for its own model picker (checked with
  CLI 2.1.299 bundled in `claude-agent-sdk` 0.2.166). Another CLI version may list different models or none (`unsupported`). The app
  does not read `~/.claude` or other home settings files to find models.

```python
>>> from agent_console_backend_claude_sdk import models_from_server_info
>>> parsed = models_from_server_info({"models": [{"value": "m-1", "displayName": "One"}]})
>>> parsed.models, parsed.skipped
([{'id': 'm-1', 'title': 'One'}], 0)

```

### Subscription sign-in

Start and finish the Claude subscription sign-in from the app screen (no terminal needed). The server starts `claude auth login` as a PTY child
process, reads the screen text, and relays the sign-in address and code request to a web dialog. **The Claude Code CLI writes the sign-in credentials to
the app-only credentials folder (`CLAUDE_CONFIG_DIR` = default `<app workspace>/.state/claude`). The app never receives or stores
tokens.** Once signed in, status checks and runs use the same folder. It is separate from the sign-in of Claude Code in the terminal (`~/.claude`).

- Descriptor: `capabilities.login = true`, `capabilities.logout = true`, `login_methods = [cli-login]` (text, the at-your-own-risk
  notice, and write paths are data). The service and endpoints are `agent_console_runtime.BackendLoginService` and `mod-runs`.
- **When the capability is absent**: server administrator setting `login.enabled = false`, `allow_subscription_auth = false`, or no usable PTY (`[login]`
  not installed, platform not supported). Without a PTY, it is not a failure; install instructions are added to the status `detail`. With `allow_subscription_auth =
  false`, `login_refusal()` (`LoginRefusalAware`) gives the reason, so sign-in and sign-out requests are refused with 409 `backend.subscription_auth_disabled`
  rather than `backend.login_unsupported`.
- `actions` of `status()`: with the subscription method and no sign-in file (`subscription_login_required`, `subscription_unverified`), the main button `login`; with one
  (`subscription_ready`), `login` (sign in again) and `logout` in the menu. With the token secret (`oauth_token`) method, there are no buttons.
  The status check still looks **only at file existence** (`claude auth status` starts a Node process, which is too expensive to run on every poll;
  it is used only to confirm a successful sign-in).
- Flow (`ClaudeCliLoginDriver`): `starting` → when the rules `open_url` and `needs_code` match, `waiting_user` (only https addresses on
  `allowed_url_hosts` are passed on; OSC 8 link targets are checked too) → the pasted code + `submit_keys` (default Enter) → when the rule `success`
  matches, `on_success_keys` (default Enter) are sent → when the CLI ends (or `exit_wait_s` after the success text), the child process is cleaned up and
  confirmed with `status_command` (`verifying`) → `succeeded` or `failed`.
- **The verdict is always `status_command`**: the exit code must be 0, and if `authMethod` was read from the output JSON, it must be in `success_auth_methods`
  (default `["claude.ai"]`). Without the success text but with status 0, it succeeds; with the success text but status 1,
  `verify_failed`. If the output is not JSON, only the exit code is checked.
- Failure reasons (`LoginReasonCodes`, an open vocabulary): `cli_missing`, `pty_unavailable`, `exited` (ended with a nonzero code without the success
  text), `verify_failed`, `start_failed`. Sign-out: `logout_failed`, `timeout`.
- Security: run arguments come only from the server administrator settings. The child process environment inherits only the same environment policy as runs + `env_inherit`
  (`CLAUDE_CONFIG_DIR` and browser opening variables), and `env_clear` (`ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`,
  `CLAUDE_CODE_OAUTH_TOKEN`) are always empty. The PTY echoes the pasted code, so the driver reports it through `secrets_to_mask`
  and the service masks it in screen lines, text, and details. Raw output lives only in session memory and is never logged.
- Sign-out: runs `logout_command` (default `claude auth logout`) in a PTY. Claude Code in this PC's terminal is signed out too.

Server administrator setting `login` (`ClaudeSdkLoginOptions`, all data; **the screen text rules live in `login.rules`**):

| Key | Default | Meaning |
| --- | --- | --- |
| `enabled` | `true` | When off, the capability is not declared (no button) |
| `command`, `status_command`, `logout_command` | `null` = [`find_claude_cli()`, `auth`, `login`/`status`/`logout`] | Run arguments (cannot be changed by requests). The executable is `readiness.cli_path` → the SDK bundle → PATH |
| `success_auth_methods` | `["claude.ai"]` | `authMethod` values that count as success (only the exit code when empty) |
| `rules` | `open_url: https://\S+/oauth/authorize\S*`, `needs_code: (?i)paste code`, `success: (?i)login successful`, `failure: (?i)(error\|failed)` | A list of regexes per signal. Checked with `ac-safe-regex` (dangerous ones are settings errors) |
| `allowed_url_hosts` | `claude.ai`, `claude.com`, `console.anthropic.com`, `platform.claude.com` | Hosts to pass on through `open_url` (https, including subdomains) |
| `on_success_keys`, `submit_keys` | `["enter"]`, `["enter"]` | Keys to send after the success text and after the code |
| `pty_size` | `{cols: 400, rows: 40}` | Wide, so long URLs do not wrap |
| `cwd` | `null` | Working folder |
| `env`, `env_inherit`, `env_clear` | `{TERM: xterm-256color}`, `CLAUDE_CONFIG_DIR`, `BROWSER`, `DISPLAY`, `WAYLAND_DISPLAY`, `XDG_*`, the 3 key and token variables | The child process environment (add variables to pass on in your environment to `env_inherit`) |
| `writes` | `${CLAUDE_CONFIG_DIR}/.credentials.json`, `~/.claude/.credentials.json` | With the app-only folder turned off, the write path shown in the start confirmation dialog (the first one that resolves). With the app-only folder, its location (relative path) and `texts.writes_private` |
| `status_timeout_s`, `logout_timeout_s`, `exit_wait_s`, `terminate_grace_s` | `20`, `20`, `10`, `2` | Times (seconds) |
| `screen_lines` | `40` | Number of screen lines carried in progress |
| `texts` | `ClaudeSdkLoginTexts` | Text for buttons, steps, reasons, and the at-your-own-risk notice. The environment variable warning and the sign-out failure and timeout sentences are also sent as `text_templates` (`/warnings/<i>`, `/message`); changed text is not translated unless a catalog folder has it as a `text` key |

```python
>>> from agent_console_backend_claude_sdk import ClaudeSdkLoginOptions, allowed_open_url
>>> opts = ClaudeSdkLoginOptions()
>>> allowed_open_url("https://claude.ai/oauth/authorize?x=1", opts.allowed_url_hosts) is not None
True
>>> allowed_open_url("https://evil.example/oauth/authorize", opts.allowed_url_hosts) is None
True
>>> ClaudeSdkLoginOptions.model_validate({"rules": {"success": ["(a+)+$"]}})  # doctest: +IGNORE_EXCEPTION_DETAIL
Traceback (most recent call last):
pydantic_core.ValidationError: 위험한 정규식(rules.success)

```

Tests (`tests/…_login_52r82.py`) never call the real CLI. They inject the stub `tests/claude_cli_stub.py` as
`[sys.executable, stub, scenario, auth, login|status|logout]` and write only to a temporary `CLAUDE_CONFIG_DIR`. Scenarios:
code paste success / callback success (without a code) / code rejected / stuck without a URL (cancel, timeout) / exit without the success text + status 0
/ success text + status 1 / SIGTERM ignored on cancel (forced kill). They check that no child process remains (`/proc/<pid>`), that the key and token variables
are empty, and that the code string (and its first 5 characters) appears in no response or log.

#### Manual subscription sign-in smoke test (the steps for a person to actually sign in)

Automated tests never really sign in. The steps below are for a person to check with their own account. The sign-in is written only to the app-only
folder in the app workspace (`<app workspace>/.state/claude`), and `~/.claude` does not change.

```bash
uv run agent-console serve --open       # 127.0.0.1:8765, project folder = the settings file folder
```

1. At first, the Claude Agent SDK card in the execution backend settings shows sign-in required and the credentials location (`.state/claude`),
   with the **subscription sign-in** button → pressing it opens the start confirmation dialog (the at-your-own-risk notice, write path =
   `.state/claude/.credentials.json`). At this point `ps -ef | grep "auth login"` shows no child process.
2. Start the sign-in → a browser window opens, or open it with the open sign-in page button → sign in in the browser. If the browser's
   sign-in completion signal does not reach the server, paste the code shown in the browser into the dialog's code field and confirm.
3. When the dialog shows signed in with the Claude subscription, in another terminal run
   `CLAUDE_CONFIG_DIR=<앱 workspace>/.state/claude claude auth status; echo $?`
   → the JSON `authMethod` is `claude.ai` and the exit code is 0.
4. Close the dialog and press [Test connection] on the card; it passes (one short request, which uses a little subscription usage).
5. Start the subscription sign-in again → press [Cancel] while it is in progress; it reports that it was canceled, and `ps` shows no leftover `auth login`. For the
   timeout, shorten it with the setting `modules.options.mod-runs.backend_login.timeout_s: 30` and wait 30 seconds to check (no process
   remains).
6. Card `…` › sign out (disconnect) → confirm → the card shows sign-in required again (`subscription_login_required`)
   and the exit code of `claude auth status` is 1.

If the screen text does not match (a CLI version change), look at the screen with the dialog's CLI screen view and fix `login.rules`. The verdict is
`claude auth status`, so even wrong rules never give a false success.

## Subagents (`AgentRequest.subagents`, delegation strategy `sdk-subagents`)

`capabilities.subagents = true`. The list of `SubagentSpec` filled in by the delegation strategy (nodes-core `sdk-subagents`) becomes
`ClaudeAgentOptions.agents={name: AgentDefinition}`, and the delegation tool (`delegation_tool`, default `Agent`) is added to
`tools` and `allowed_tools` (not added if it is in the setting `disallowed_tools`). It also sets `subagent_env`
(default: depth 1 `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1`, foreground runs `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`,
built-in subagents off `CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS=1`).

| SubagentSpec | AgentDefinition |
| --- | --- |
| `name` (target node id) | `agents` key |
| `description` / `model` | `description` / `model` |
| `prompt` + bundle instructions (+ file notes) | `prompt` |
| `tools` + bundle tools (deny wins; only names for parenthesized rules) | `tools` (None = the SDK default when both are absent) |
| `disallowed_tools` + bundle denies | `disallowedTools` |
| bundle mcp_servers | `mcpServers` (inline) |
| `options` | Other `AgentDefinition` fields (for example `maxTurns`) |

Bundle slots that cannot be split per target (the files folder, tools.commands) are merged into the delegator session with a `log.warning`.

**Target tool rules and delegator pre-approval**: there is one SDK session, so `allowed_tools` (pre-approval) applies to the delegator too.
So by default the target's tool rules are not put into the delegator's `allowed_tools` (`subagent_tools_preapprove=false`),
and if there are target rules missing from the delegator's pre-approval, `log.warning{details.not_preapproved}` is emitted (in modes that do not ask, target
calls can be refused). With `subagent_tools_preapprove=true`, they are merged, and the widened rules are reported with `log.warning{details.added}`.
Either way, the delegator's available tools (`tools`) are not widened.
Secret masking: delegation tool results (the notification `text`) and every preview (`task_preview`, `result_preview`) are emitted after known secret values and shapes
are masked.

**Event attribution**: when the `subagent_type` in a delegation tool call's input is a registered name, events from messages whose `parent_tool_use_id` is that call id
are emitted with `actor=SubagentSpec.actor` and `node_path=sink.child_path(name)`
(`BackendEventSink.child_path`, which `NodeContext` implements). The order is the same as the fake backend: the delegator's `agent.tool_call`
→ the target's `agent.subagent_started{subagent_id, name, tool_use_id, task_type, task_preview}` (TaskStarted) →
the target's tool_call, tool_result, and message → the target's `agent.subagent_stopped{status, usage{total_tokens}, tool_uses,
duration_ms, result_preview}`(TaskNotification, 끝난 TaskUpdated) → 위임자 `agent.tool_result`.
Delegations that never got Task events get a start and stop pair built from the delegation tool call id at the end of the run. Delegations with unregistered names are
attributed to the delegator. Usage from subagent messages is not added to the delegator's `agent.usage`.

**Result notification**: when the sink is a `SubagentResultListener` (imported from `agent_console_runtime`;
`on_subagent_result(name, *, text, status, actor, tool_use_id)`),
it is notified for each delegation tool result (with the trailing `agentId:` line removed). The delegation strategy uses this to emit the target node's replies (`ctx.emit_replies`).
The backend does not know node port names, so it never emits replies itself.

## Run bundle (`AgentRequest.bundle`)

`capabilities.resource_slots = ["instructions", "files", "mcp_servers", "tools", "skills", "rules"]`(`RESOURCE_SLOTS`)
+ `hooks` only when the server administrator sets `allow_command_hooks: true`. When it is off, the reason is given in `slot_notes.hooks` (`HOOKS_DISABLED_NOTE`),
and validation and bundle previews show `resource.slot_unsupported` (details.reason). `subagent_slots` = instructions, mcp_servers, tools, skills, rules.
The slot value shapes are in `packages/py/features/ac-resources-core/README.md`. Values in other slots only produce a `log.warning`.

| Slot | SDK |
| --- | --- |
| `instructions` | `Agent.system_prompt` + the instructions concatenated into `system_prompt` (preset + append when `system_prompt_mode=claude_code_append`) |
| `files` | File paths the node wrote (`str` or `{path, root?}`) → the folders are added to `add_dirs` and to the allowed directories of the run scope, and a file list notice (`files_notice`) goes at the end of the instructions. Items without a path are not passed on and produce a warning |
| `mcp_servers` | `name` → `McpServerConfig` (overlaid on the setting `mcp_servers`; for the same name the later one wins). `secret://` in `env` and `headers` is resolved with the injected `SecretResolver` and masked in raw and payload |
| `tools` | Allows are unioned (added to `tools` and `allowed_tools`), denies win (`disallowed_tools`), and `commands` are unioned into the run scope's allowed commands (`log.warning` when widened) |
| `skills` | The tree the node wrote `{name, root, tree_root}` (`root = tree_root/skills/name`) → `plugins=[{type: local, path: tree_root}]` (plugin name = folder name = node id) + `skills=[skill_name_template]` (default `{plugin}:{skill}`) + `skill_tool` (default `Skill`) in `tools`. Subagents use `AgentDefinition.skills`; plugin folders are loaded into the session together, and the delegator's `skills` contain only its own (`[]` if none) |
| `rules` | `rule_delivery=instructions` (default): the item's `instruction` (path header + body) goes into the instructions. `files`: the item's `root` (containing `.claude/rules/<name>.md`) goes into `add_dirs` + `rule_files_env` (default `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1`) |
| `hooks` | Only when the server administrator turns on `allow_command_hooks`. `hook_delivery=callback` (default): for each item, `HookMatcher(matcher, [callback], timeout)` is attached under `event`. The callback runs as a child process without a shell (`hook_runner`, default `subprocess_runner`) **only after passing `ToolGuard.check_command` (limits.commands)**: stdin = the hook input JSON, stdout JSON = returned to the SDK as is, exit code 2 = `{"decision": "block", "reason": stderr}`, other nonzero = a non-blocking error. Environment = server variables the environment policy allows + `CLAUDE_PROJECT_DIR` (explicit env such as authentication keys is not passed). Events `hook.started` → `hook.finished{event, matcher, command_preview (masked, 200 characters), exit_code, duration_ms, decision, error?}`. `settings`: only items that pass the run scope go into the `settings` inline JSON (`{"hooks": {event: [{matcher, hooks: [{type: command, command, timeout}]}]}}`), and the CLI runs them directly (events only through the `hook.*` observations). Subagent hooks are merged into the session with a warning |

Nothing is written to the user's project (cwd) or `~/.claude`. Skill and rule files point only to what the agent node wrote into the run folder (`<workspace>/.state/runs/<run>/<node>/_bundle/<node>/`).
The default of `setting_sources` (`["project"]`) is not changed even when delivering skills.

### Hook probe wrapping

When the effective observation setting `observe.hook_probe` is `true` (off by default), command hooks (the `hooks` slot) **that this backend delivers** are
run wrapped in `agent-console-hook-probe`. The probe runs the original command as is (same input, output, and exit code) and keeps the record
`hook-probe/1` in `AgentRequest.run_folder/<hook_probe_folder>/<session>.jsonl` (read by the log source `hook-probe-jsonl`).

- Callback path: `wrap_command(shlex arguments, out=…, probe=hook_probe_command, matcher, context=run_context)` (exec form).
  Settings path: `wrap_command_line(command string, …)` (keeps the shell form). The run scope check (`limits.commands`) uses **the original command**.
- The `--context` is `AgentRequest.run_context` (`run_id`, `node_path`). `hook_probe: true` in the `hook.started` and `hook.finished` payloads.
- Not wrapped (with a `log.warning`) when: there is no `run_folder`, or `agent-console-hook-probe` is not installed. When off, commands are unchanged.
- User settings files (`~/.claude`) and `.claude` exports (`ac-exports`) are not touched (original commands).
- Bundle preview: when on, the optional hook `ClaudeSdkBackend.preview_notes(effective, bundle)` (ac-teams `PreviewNotes`) emits
  info `observe.hook_probe_wrapped` (hook wrapping on, `details.hooks` = the number of hooks to wrap).

```python
>>> from agent_console_backend_claude_sdk import plan_hook_probe
>>> plan, warnings = plan_hook_probe(
...     {"hook_probe": True}, run_folder="/state/runs/r1/lead",
...     run_context={"run_id": "r1", "node_path": "lead"}, probe_command=["probe"],
... )
>>> plan.argv(["fmt", "--check"], "Write")
['probe', '--out', '/state/runs/r1/lead/hook-probe', '--matcher', 'Write', '--context', 'run_id=r1', '--context', 'node_path=lead', '--exec', '--', 'fmt', '--check']
>>> plan_hook_probe({}, run_folder="/x", run_context={}, probe_command=None)
(None, [])

```

## Interactions while running: questions and tool approvals

`capabilities.interactions = ["question", "tool_permission"]`. The kind names are mapping data, so they can be changed with the server administrator setting
`interaction_kinds{question, tool_permission}` (the engine does not know the names).

- **Conditions for opening**: opened only when the sink is an `InteractivePort` (`request_input`, which `NodeContext` implements) and `AgentRequest.interactions`
  (the grant) includes that kind. Other asking requests are handled with `unmatched_permission` (default deny).
- **Callback registration**: `can_use_tool` is attached when the permission mode is not bypass and either it is in `prompting_permission_modes` (default `default`, `acceptEdits`, `plan`)
  or there is a grant.
- **Question tool** (`question_tool`, default `AskUserQuestion`): added to `tools` when there is a question grant (not pre-approved).
  Otherwise it goes into `disallowed_tools`.
- **Order**: run scope (ToolGuard, in both the hook and the callback) → the "allow for this run" memory → interaction → `unmatched_permission`.
  Even if the user allows it, the run scope is not bypassed.

| Callback | Interaction payload | Response → SDK |
| --- | --- | --- |
| `AskUserQuestion` | `question`: `{questions[{question, header?, options[{label, description?}], multi_select}]}` | `{answers, response?}` → `PermissionResultAllow(updated_input={…input, answers, response?})`. Denied when there is no answer |
| Other tools | `tool_permission`: `{tool_name, input_preview, title?, display_name?, description?, blocked_path?, decision_reason?, tool_use_id?, agent_id?}` (only fields present in the context) | `allow` (+`updated_input`) → Allow, `allow_for_run` → Allow + this run's memory (tool name + sorted input), `deny` (+`message`) → Deny |

- `input_preview` is a string preview of the scrubbed input. The original input goes back only to the SDK.
- The request's `title` and `message` are masked before opening too.
- The `updated_input` of an allow response (for questions, the input merged with answers) is checked against the run scope (ToolGuard) again. If it goes outside, it is denied with
  a message that contains no input values. The `allow_for_run` memory key is the final input that was actually allowed.
- When closed by Run cancellation (`reason=cancelled`), `PermissionResultDeny(interrupt=True)`. When expired, the `expire_response` the engine gave is
  interpreted as the response, and denied if it cannot be interpreted.
- `updated_permissions` is not used (so nothing is written to the user project's `.claude/settings.local.json`).
- **Subagent attribution**: `ToolPermissionContext.agent_id` is matched to the task_id of TaskStarted (or the delegation tool call id) and the request is opened
  with `actor` and `node_path=sink.child_path(target)`. If it cannot be matched, it is the delegator's request. Subagent questions are not opened
  (not available in the SDK).
- **Settings validation hook** `validate_settings(effective, grant)`: in an asking mode without the tool approval kind in the grant,
  an `interaction.no_path` warning (`details.kinds` has the needed kinds). Asking modes are not subject to `risky_option_warnings`
  (the bypass warning stays).
- Test helpers: `testing.InteractiveSink` (a response function), `testing.PermissionCall` (callback calls from the fake client).

## Usage limits

`RateLimitEvent` → `usage.rate_limit{window (rate_limit_type, or "unspecified"), status, utilization, resets_at,
overage_status}`. Values are never made up (null when absent).

Model call duration: `ResultMessage.duration_api_ms` (the total model API wait across the whole run) is carried as the `duration_ms` of the last
`agent.usage`. Null when the value is missing or negative.

## Server administrator settings (`ConfigurableBackend` hook)

`ClaudeSdkBackend.from_options(options, *, secrets, environ, host=None)` is the ac-runtime `ConfigurableBackend` implementation. The server passes the setting
`backends.claude-agent-sdk` to this hook to replace the instance created from the entry point (without arguments). Only this package knows what the keys mean.

| Key | Default | Meaning |
| --- | --- | --- |
| `models` | `[]` | The `list_models()` list (`ModelInfo`). Model ids are not in the code. The account lookup adds its models after these (this list keeps its order and wins on the same id) |
| `model_discovery` | `ClaudeSdkModelDiscoveryOptions()` | Account model discovery method and Models API address and header (see "Model discovery" above) |
| `env_policy` | `null` (= the default allow list) | Child process environment inheritance (`EnvPolicy{inherit, allow}`) |
| `max_raw_chars` | `DEFAULT_MAX_RAW_CHARS` | The maximum JSON length of one event raw |
| `cancel_grace` | `5.0` | Interrupt wait after cancellation (seconds) |
| `interaction_kinds` | `{question: question, tool_permission: tool_permission}` | The interaction kind ids it opens (`capabilities.interactions`) |
| `allow_command_hooks` | `false` | Allows running command hooks (the `hooks` slot). When off, the `hooks` slot is not accepted (the reason is in the warning) |
| `allow_subscription_auth` | `true` | Allows your own subscription sign-in credentials (`auth.mode=subscription`) (subscription by default, at your own risk; an API key is also available). Turning it off with `false` gives the validation error `backend.subscription_auth_disabled` and refuses runs; when on, the strengthened warning |
| `hook_probe_command` | `null` (= `[current Python, -m, agent_console_hook_probe]`) | The probe run arguments that wrap hook commands when `observe.hook_probe` is on (see "Hook probe wrapping" above) |
| `hook_probe_folder` | `hook-probe` | The record folder name under the node run folder (a name without path separators) |
| `auth_dir` | `ClaudeSdkAuthDirOptions()` (`.state/claude`, relative to the app workspace) | The app-only credentials folder (`CLAUDE_CONFIG_DIR`, see "App-only credentials folder" above) |
| `login` | `ClaudeSdkLoginOptions()` (on) | Subscription sign-in and sign-out from the app screen (see "Subscription sign-in" above) |
| `readiness` | `ClaudeSdkReadinessOptions()` | The authentication method (`auth`) the status check and connection test look at, `cli_path`, `subscription_files`, `probe_prompt`, `probe_model`, `probe_extra_args`, the text `texts` (see "Status check and connection test" above) |

`secrets` is used to resolve remaining `secret://` references and to mask raw data, and `environ` is the parent environment the environment policy applies to.
Unknown keys and invalid values raise `ValueError` (location and reason only). Type model: `ClaudeSdkInstallOptions`.

## Settings (`Agent.backend_options`, type `ClaudeSdkBackendOptions`)

The defaults are on the safe side: `permission_mode="dontAsk"`, `setting_sources=["project"]` (isolates the user's `~/.claude` settings;
`[]` means no file settings at all), `strict_mcp_config=true`, `mcp_servers={}`, and no built-in tools unless tools are set.
Also: `tools` (a list or `"claude_code"`), `allowed_tools` (pre-approval, **not an availability limit**), `disallowed_tools`,
`network_tools`, `command_input_keys`, `path_input_keys`, `unmatched_permission`, `system_prompt_mode`,
`include_partial_messages`, `max_turns`, `max_budget_usd`, `fallback_model`, `effort`, `add_dirs`, `env`, `cli_path`,
`sandbox`, `auth`, `forward_subagent_text` (default true), `delegation_tool`, `delegation_tool_names`, `subagent_env`,
`files_notice`, `prompting_permission_modes`, `question_tool`, `skill_tool`, `skill_name_template`, `rule_delivery`
(`instructions`|`files`), `rule_files_env`, `hook_delivery` (`callback`|`settings`), `hook_timeout_seconds` (default 60), `sdk_options` (other `ClaudeAgentOptions` field names as is, except `cwd`, `hooks`, `can_use_tool`, `resume`,
and `agents`).
Model ids are not in the code; they come from `Agent.model`. `list_models()` returns the constructor argument `models` (settings data, empty by default).

For observation (`AgentRequest.observe` = the effective `ObserveSettings`), see "Observation collectors" below.

## Observation collectors (`agent_console_backend_claude_sdk.collectors`)

Observation (hooks, MCP, and so on) is done by **collectors**, not the backend. The backend does not know collector names, and passes SDK hook callbacks
(`on_hook`) and SDK messages (`on_message`, after the translated events) to enabled collectors. Events that collectors emit with `ctx.emit`
go out as generic RunEvents (raw sanitized, subagent attribution through `parent_tool_use_id`).

- Default collectors (first implementations, registered through the entry point `agent_console.collectors`):
  - `sdk-hooks`: SDK observation hook callbacks → `hook.invoked` (hook_type `sdk-callback`), CLI settings hook runs
    (`include_hook_events`) → `hook.invoked|completed` (hook_type `settings`). The setting `events` (hook events to attach callbacks to,
    default `DEFAULT_OBSERVED_HOOK_EVENTS`).
  - `mcp-calls`: `mcp.server_status`, `mcp.call_started|call_completed` (`duration_ms` from the injected clock).
  - The payload keys are the same as the imitated observations of the fake backend (`ac-backend-fake-agent`).
- Settings: `observe.collectors{id: {enabled?, config?}}`. The old keys are read as `hooks` → `sdk-hooks.enabled`,
  `mcp` → `mcp-calls.enabled`, `hook_events` → `sdk-hooks.config.events` (the mapping is the data
  `LEGACY_OBSERVE_KEYS`). When both exist, fields with values in `collectors` win (`config` as a whole).
  Collectors that are not set are off.
- Collector exceptions (including settings interpretation) do not affect the run. One `log.warning` per collector per run
  (`details.collector`, `stage`, `error` type name; no exception message). If the sink fails while emitting collected events,
  it is swallowed. Hook callbacks always return `{}`.
- Validation (`validate_settings`): an id this backend does not have → warning `observe.unknown_collector`; settings that do not match the collector
  schema → warning `observe.collector_config_invalid`.
- Registration: `ClaudeSdkBackend(collectors=...)` (None = the default collectors); `from_options` finds them in entry points with
  `discover_collectors()` (only those whose `descriptor.backend` equals the backend id;
  reports in `collector_reports`). The descriptors go into `BackendDescriptor.collectors`.

A new collector inherits `BaseClaudeSdkCollector`, overrides only the methods it needs, and registers with one entry point.

```python
>>> import asyncio
>>> from typing import ClassVar
>>> from agent_console_backend_claude_sdk.collectors import (
...     BaseClaudeSdkCollector, CollectorContext, CollectorRun, resolve_collector_settings,
... )
>>> class PromptCount(BaseClaudeSdkCollector):
...     id: ClassVar[str] = "prompt-count"
...     title: ClassVar[str] = "프롬프트 수"
...     emits: ClassVar[tuple[str, ...]] = ("prompt.count",)
...     default_backend: ClassVar[str] = "claude-agent-sdk"
...     def hook_events(self, config):
...         return ["UserPromptSubmit"]
...     async def on_hook(self, event, data, tool_use_id, ctx: CollectorContext):
...         ctx.state["n"] = ctx.state.get("n", 0) + 1
...         ctx.emit("prompt.count", {"count": ctx.state["n"]})
>>> sent = []
>>> async def out(event):
...     sent.append((event.type, dict(event.payload)))
>>> async def warn(warning):
...     sent.append(("log.warning", warning.details))
>>> run = CollectorRun(
...     [PromptCount()],
...     resolve_collector_settings({"collectors": {"prompt-count": {"enabled": True}}}),
...     clock=lambda: 0.0, redact=lambda v: v, out=out, warn=warn,
... )
>>> run.hook_events()
['UserPromptSubmit']
>>> asyncio.run(run.hook_callback("UserPromptSubmit")({"prompt": "hi"}, None, None))
{}
>>> sent
[('prompt.count', {'count': 1})]

```

```toml
[project.entry-points."agent_console.collectors"]
prompt-count = "my_pkg.collectors:PromptCount"
```

## Run scope and `capabilities.enforce`

- `commands: true`: a `PreToolUse` hook on every tool call (including subagents) checks the command keys of the input against
  `limits.commands` (an empty list = deny all, `"*"` = allow all; shell chaining, substitution, and redirection are rejected; token prefix matching).
  Commands that MCP servers run internally are not covered.
- `directories: false`: only the path inputs of file tools are checked (best effort). Files touched by allowed commands cannot be blocked.
- `network: false`: when the network is not allow, it only turns off `network_tools`; it cannot block communication by MCP, server-side tools, or allowed commands.

## Child process environment and limitations

- **Environment inheritance**: the SDK (0.2.166) passes the server's whole `os.environ` to the CLI child process with no option to turn it off.
  With the constructor argument `env_policy` (`EnvPolicy`, default `inherit="allowlist"`), this backend **overrides with empty values** keys outside the allow list (`DEFAULT_ENV_ALLOW`:
  OS-essential keys such as PATH, HOME, LANG, LC_*, TMPDIR/TEMP/TMP, SystemRoot, plus `CLAUDE_CONFIG_DIR`; replaceable with settings data).
  Values are not passed, but key names remain. `inherit="all"` emits a `log.warning` on every run.
  Do not inherit API keys from the server environment; set them explicitly with `backend_options.env` (`secret://…`).
- **Operating guidance**: do not put commands that read the environment or files or run arbitrary code, such as `env`, `printenv`, `set`, `cat`, `python`, `node`, `sh`,
  into `limits.commands`. Explicit `env` values can be read inside the agent process.
- **Settings that reverse the safe defaults**: the defaults can be changed with `setting_sources` (`["user"]` and so on), `strict_mcp_config=false`, `permission_mode`, and
  `sdk_options` (for example `permission_mode="bypassPermissions"`). Such values are not blocked, but a `log.warning` event is emitted at the start of the run
  (`risky_option_warnings`). In the permission bypass mode, Claude Code permission rules and
  `can_use_tool` are off, but this backend's `PreToolUse` run scope checks (commands + file tool paths) remain.

## Platform tools (`AgentRequest.host_tools`)

`capabilities.host_tools = true`. The `HostTool`s (ac-runtime, runtime only) a delegation strategy (for example the standalone delegation `host`) built are
bundled into one in-process SDK MCP server and given to the model. The backend does not know tool names or purposes.

- Server: `create_sdk_mcp_server(name=<backend_options.host_tool_server>, tools=[tool(name, description, input_schema)(handler)])`
  → `ClaudeAgentOptions.mcp_servers[<server>]`. The default server name is the option schema default `agent-console` (`DEFAULT_HOST_TOOL_SERVER`),
  `[A-Za-z0-9_-]` only, no `__`. If the name overlaps the setting `mcp_servers` or the bundle MCP servers, `validation_failed` before running.
- Naming rule: the name the model calls = `mcp__<server>__<tool>` (`host_tool_rule`). This name is put into `allowed_tools` (pre-approval)
  (removed if it is in `disallowed_tools`; denies win). Tool names are `[A-Za-z0-9_-]` and unique within a request (an error before running on overlap).
  A `log.warning` when the full name exceeds 64 characters (`MODEL_TOOL_NAME_LIMIT`).
- Input schema: passed in top-level object shape (`object_input_schema`; without `type` and `properties`, the SDK reads the schema
  as a "name → Python type" table). Schema checks (for example a target enum) are done by the SDK before the handler, and violations are error results.
- Calls: `agent_console_runtime.call_host_tool`. Handler exceptions are error results (exception type name only, no message), `HostToolResult.is_error` is
  MCP `isError`, and when the run cancel token is cancelled, the running handler is cancelled and an error result is returned.
- Observation: the model's calls are `agent.tool_call`/`agent.tool_result` like other MCP tools, and with the collector `mcp-calls` on they are
  recorded as `mcp.call_started`/`mcp.call_completed{server, tool, is_error, duration_ms}` (no special path in the backend).
- `sdk_options.mcp_servers` and `sdk_options.allowed_tools` overwrite the values above as a whole, so they emit a `log.warning`.
- The server builder can be replaced with the constructor's `tool_server_factory` (default `sdk_tool_server`).

Installed SDK check (2026-10-18, `claude-agent-sdk 0.2.166`, actual import):

| API | Confirmed signature |
| --- | --- |
| `claude_agent_sdk.create_sdk_mcp_server` | `(name: str, version: str = '1.0.0', tools: list[SdkMcpTool[Any]] \| None = None) -> McpSdkServerConfig` (`{"type": "sdk", "name", "instance"}`) |
| `claude_agent_sdk.tool` | `(name: str, description: str, input_schema: type \| dict[str, Any], annotations: ToolAnnotations \| None = None)` → decorator → `SdkMcpTool` |
| Handler | `async (args: dict) -> {"content": [{"type": "text", "text"}], "is_error": bool}`. The SDK turns unknown tools, schema violations, and handler exceptions into `isError` results |

`test_installed_sdk_has_in_process_mcp_api` checks that these exist. The test helpers `testing.SdkToolCall` and `call_sdk_mcp_tool` call the in-process server
over JSON-RPC (`initialize` → `tools/call`) like the CLI does (using the SDK internal `claude_agent_sdk._internal.sdk_mcp_bridge`; if the SDK
changes, only these helpers need fixing). Items to confirm with real calls are 21 to 26 below.

SDK handlers receive only the input (not even the `_meta` of the MCP request), so they do not know the tool call id. So the `tool_use_id` of the target
NodeRun called by a delegation tool is null with this backend.

## Session record archiving and restore

`ClaudeSdkBackend.session_archive()` returns a `SessionArchive` that handles `projects/<key>/<session>.jsonl` and the files under `<session>/`
only when the app-only credentials folder (`<workspace>/.state/claude`) exists (key = `agent_console_claude_format.project_key`).
`.credentials.json`, `settings.json`, and other session files are not archived, and restore writes only to `projects/<current key>/`. Without the credentials folder
(standalone use, `auth_dir.config_dir: null`), it returns None, so `~/.claude` is never read.

## Unconfirmed SDK behavior (items to check with a real-call smoke test)

1. Whether the delegator's usage (`ResultMessage.usage`, `agent.usage`) includes subagent tokens. If it does, ac-usage needs a rule to avoid double counting.
2. Whether `TaskStartedMessage` and `TaskNotificationMessage` appear in foreground runs and whether `tool_use_id` is filled. If they are not received, a start and stop pair is built from the delegation tool call id at the end of the run.
3. The `agentId:` format of delegation tool results (a separate text block or the last line). Both are removed.
4. Whether `forward_subagent_text` actually forwards subagent text blocks.
5. Subagent tool availability: whether built-in tools not in the session `tools` can be used through the target `AgentDefinition.tools` alone, and whether target calls are allowed in modes that do not ask without the delegator session's pre-approval (`allowed_tools`) (by default they are not pre-approved and a warning is emitted; turn on with `subagent_tools_preapprove`).
6. Whether the 3 environment variables (`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`, `CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS`) work in the installed CLI version.
7. Whether the CLI treats an empty `ANTHROPIC_API_KEY=""` as "not set", and whether it reads subscription sign-in credentials even without `user` in `setting_sources`.
8. Whether `RateLimitEvent.utilization` is empty before the warning threshold.

Unconfirmed items for skill, rule, and hook delivery (checked in the real-call smoke test; unit tests use the fake SDK client):
15. Whether `skills/<name>/SKILL.md` in a folder without a manifest, passed as `plugins=[{type: local, path}]`, is picked up as a skill, and whether its name
    is `<folder name>:<skill>` (documentation: the manifest is optional, and with `--plugin-dir` the folder name is the plugin name). If not, change `skill_name_template`.
16. Whether the `Skill` tool must be included to use skills when `tools` is given as a list (the `skills` option fills only `allowed_tools`).
17. Whether `skills=[]` hides subagent skills from the delegator's list while they stay visible to the target through `AgentDefinition.skills`.
18. `rule_delivery=files`: whether `--add-dir` + `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1` reads `.claude/rules/*.md` in the added folders
    (yes according to the documentation), and whether `paths` conditions are relative to the added folder or the project (conditional rules may not apply if they do not match project paths). This environment variable
    also makes the CLI read `CLAUDE.md` in other added folders (limits.directories, the files folder).
19. `hook_delivery=settings`: whether command hooks in the `settings` inline JSON run, and their precedence when used with `setting_sources=["project"]`.
20. Whether the callback's `{"decision": "block", "reason"}` is treated as blocking for every event (for PreToolUse, `permissionDecision` is the recommended form),
    and the CLI behavior when an event name not in the SDK `HookEvent` is put into `hooks`.

Unconfirmed platform tool items (unit tests use an SDK mock):
21. Whether a `type: sdk` server attaches even with `strict_mcp_config=true` and `setting_sources=["project"]` (the init `mcp_servers` status).
22. Whether `mcp__<server>__<tool>` in `allowed_tools` is allowed without asking in `dontAsk`, and whether MCP tools are visible when a `tools` list is given.
23. The CLI behavior when a full tool name exceeds 64 characters (only a warning for now).
24. Whether the CLI cuts in-progress tool calls with `notifications/cancelled` on interrupt (the backend stops separately with the run cancel token).
25. Whether parallel tool calls in the same turn call handlers concurrently (serializing the same target is the engine's job).
26. Whether long-running handlers (target runs of several minutes) hit the CLI's MCP tool time limit (`MCP_TOOL_TIMEOUT` and so on). If so, raise it through `env`.

Unconfirmed interaction items (smoke tests `test_live_question_once`, `test_live_tool_permission_once`):
9. Whether the `can_use_tool` stream is kept with `ClaudeSDKClient` + an always-present `PreToolUse` hook.
10. Whether the fields of `ToolPermissionContext` in the installed version (0.2.166) are actually filled (`title`, `display_name`, and so on).
11. Whether `agent_id` is the same value as `TaskStartedMessage.task_id`.
12. Whether there is a bug in Python where AskUserQuestion proceeds with an empty answer before the callback completes.
13. Whether the callback is called in `dontAsk` and `auto` modes (with a grant it is registered but may not be called).
14. The `resume` behavior when a tool call cut off without a result remains in the session record.

## Development and standalone reuse

This folder is a standalone project. Copy only this folder and the commands below still work. Internal dependencies
are declared as a name plus a version range, so outside the repository pass the wheelhouse (`uv run poe wheels` in the repository → `dist/wheelhouse`)
as a find-links path (`uv sync --find-links <wheelhouse>`). Check inside the repository: `uv run poe portability --package ac-backend-claude-sdk`.

```bash
uv sync                  # includes the dev group (pytest, mypy, ruff, internal packages the tests use)
uv run ruff check . && uv run mypy && uv run pytest
```

In a standalone install (copying only this folder, `portability`), 2 tests in `tests/test_agent_console_backend_claude_sdk_qa_1r29.py` are
**skipped** (the default interaction kinds are not installed). These checks compare the payloads and responses the adapter opens against the schemas of the `question` and `tool_permission` kinds registered through the entry point
`agent_console.interaction_kinds`, but those kinds are registered by
`agent-console-nodes-core`, which this package does not depend on (the backend does not know node kinds).
In the repository workspace, nodes-core is installed too, so both tests run. Real-call tests (`-k live`) run
only with `AGENT_CONSOLE_CLAUDE_SDK_LIVE=1`.

## Testing

```bash
uv run pytest packages/py/features/ac-backend-claude-sdk/tests
AGENT_CONSOLE_CLAUDE_SDK_LIVE=1 uv run pytest packages/py/features/ac-backend-claude-sdk/tests -k live -s   # real calls (opt-in, including one subagent call)
```
