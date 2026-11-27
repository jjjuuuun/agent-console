# Changelog

## Unreleased (0.2.0)

- Sentences with values are also sent as source template + values (contracts 0.16.1 `text_templates`). Status:
  `/detail` has one template per sentence when it joins several sentences or carries a value (`auth_missing_detail`
  `{name}`, `auth_dir_detail` `{path}`, `permissions_loose_detail` `{names}`, `login_required_detail` `{path}`, and the
  sign-in install note), and `/checks/<i>/note` has templates for `note_secret` (`{name}`, `{state}` = nested
  `note_found`/`note_missing`) and `note_permissions_loose` (`{names}`). Connection test timeout `/message`
  (`probe_timeout` now uses `{seconds}` instead of `{seconds:g}`, same output). Sign-in: the environment variable
  warning `/warnings/<i>` (`warning_env`), and the sign-out failure and timeout `/message` (`logout_failed` `{code}`,
  `logout_timeout` now `{seconds}`). New: `ReadinessAssessment.detail_parts`, `note_templates`,
  `text_templates(extra)`, `probe_message_template`, `env_warning_templates` and `logout_timeout_template`;
  `ClaudeCliLoginDriver(warnings=)` also takes `TextTemplate` items. English entries for these templates in
  `locales/en.json`. Text a server administrator changes through `texts` is not translated by the web app; add it to a
  catalog folder to translate it.
- Account model discovery (`capabilities.model_discovery = true`, no model call). `ClaudeSdkBackend.discover_models`
  picks the method from the administrator setting `model_discovery.method` (`auto` = the Models API when
  `readiness.auth` is an API key, the Claude Code CLI initialize response when it is a subscription; `sdk_init` and
  `models_api` force one). `sdk_init` only calls `connect()`, `get_server_info()` and `disconnect()` (never
  `query()`), with the connection test's credentials folder, a temporary run folder and session persistence off; the
  response's `models` items (`value`, `displayName`, `description`, other keys as `attributes`) become `ModelInfo`, and
  a response without `models` is `unsupported` (`cli_no_models`). `models_api` reads `GET {base}/v1/models` page by
  page (`limit`, `after_id`, headers `x-api-key` and `anthropic-version`; base = `model_discovery.api_base_url` →
  `ANTHROPIC_BASE_URL` → the official address). Reasons: `subscription_disabled`, `auth_missing`, `cli_missing`,
  `auth_failed`, `network`, `timeout`, `invalid_response` and `error`; the key never reaches results, details or logs.
  New: `ClaudeSdkModelDiscoveryOptions`, the injection points `ServerInfoClient` and `HttpClientFactory` (constructor
  `http_client_factory=`), the helpers `models_from_server_info`, `models_from_api_page`, `list_models_api` and
  `api_base_url`, and the constants `METHOD_SDK_INIT`, `METHOD_MODELS_API`, `DEFAULT_ANTHROPIC_API_BASE_URL`,
  `DEFAULT_ANTHROPIC_API_VERSION` and `ANTHROPIC_BASE_URL_ENV`. New dependency `httpx>=0.27`. Requires
  `agent-console-runtime>=0.2,<0.3` and `agent-console-contracts>=0.16.1,<0.17`. Consumer range:
  `agent-console-backend-claude-sdk>=0.2,<0.3`.
- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `ac-backend-claude-sdk`, so the web app can show the backend description, option
  schema, readiness and sign-in texts and the backend issue and reason codes in English (data only, no API change).
  Default texts that carried values are now fixed or language-neutral so they can be looked up by source text:
  `ClaudeSdkLoginTexts.writes_credentials` is `{path}`, `ClaudeSdkReadinessTexts.note_files` is `{found}/{count}`, and
  `login_required_detail` no longer names the folder (the path is in the credentials location check).
- Subscription sign-in: the optional capabilities `start_login` and `logout` (`capabilities.login/logout`,
  `login_methods = [cli-login]`). The backend relays `claude auth login` through a PTY and decides the result from the
  exit code of `claude auth status` plus `authMethod`. The app never receives or stores the token. Server
  administrator setting `login` (`ClaudeSdkLoginOptions`, on by default, screen text rules `login.rules`), and readiness
  check `actions` (no sign-in file = main button login; file present = sign in again and sign out). New dependency
  `agent-console-secret-rules` (rule safety checks); optional extra `login` = `agent-console-pty-session` (without it
  there is no capability, and the status `detail` explains why).
- Cleanup: **removed public API**: the re-export of `SubagentResultListener`. Import it from
  `agent_console_runtime`, where it is defined (`from agent_console_runtime import SubagentResultListener`). Same
  behavior.
- Cleanup: **removed public API**: the unused property `CollectorRun.active_ids`. See the enabled collectors through
  `collector_reports` and `BackendDescriptor.collectors`.
- **Subscription is the default (at your own responsibility); an API key is still available.** **Behavior change**:
  the server administrator option `allow_subscription_auth` defaults to `true` (was `false`), `ClaudeSdkAuth.mode`
  defaults to `subscription` (was `api_key`; `auth: {}` means subscription), and the readiness check `readiness.auth`
  defaults to `{mode: subscription}` (was `{mode: api_key, api_key: secret://anthropic_api_key}`). With a subscription,
  the validation warning `backend.subscription_auth_enabled` and the `log.warning` on every run are unchanged. When
  `auth` is empty (`null`), only `env` and the environment policy apply, as before (unchanged). Choose an API key with
  `auth: {mode: api_key, ...}`. To block subscriptions, set `allow_subscription_auth: false`.
- `capabilities.status = true` and `capabilities.probe = true`, and the descriptor `probe_cost_note`
  (`PROBE_COST_NOTE`). Optional methods `ClaudeSdkBackend.status` (a static check with no model call; secrets are only
  checked for existence by name) and `probe` (a one-turn call without tools; refused without a call when the
  executable is missing, subscriptions are off or there is no key; with a time limit; reasons `auth_failed`,
  `network`, `timeout`, `error`, `cli_missing`, `auth_missing` and `backend.subscription_auth_disabled`). Server
  administrator setting `readiness` (`ClaudeSdkReadinessOptions`: the `auth` to check (default
  `secret://anthropic_api_key`), `cli_path`, `subscription_files`, `probe_prompt`, `probe_model`, `probe_extra_args`
  and `texts`). Constructor arguments `readiness`, `cli_locator` and `path_exists`. Parts `assess_readiness`,
  `classify_probe_messages`, `classify_probe_error`, `find_claude_cli` and `expand_path`, and the constants
  `ReadinessStates`, `ProbeReasonCodes` and `PROBE_CATEGORIES`.
- `capabilities.host_tools = true`. `AgentRequest.host_tools` is given to an in-process SDK MCP server
  (`create_sdk_mcp_server`), and `mcp__<server>__<tool>` is added to `allowed_tools`. Option `host_tool_server`
  (default `agent-console`), constructor `tool_server_factory`, parts `build_host_tool_server`, `HostToolMapping`,
  `host_tool_rule`, `sdk_tool_handler` and `sdk_tool_server`, and test helpers `testing.SdkToolCall` and
  `call_sdk_mcp_tool`.
- Moved observation to a collector registry. Public submodule `collectors` (the `ClaudeSdkCollector` protocol,
  `CollectorContext`, `BaseClaudeSdkCollector`, the default collectors `sdk-hooks` and `mcp-calls`, the entry point
  group `agent_console.collectors`, `discover_collectors`, `select_collectors`, `resolve_collector_settings` and
  `CollectorRun`). The setting `observe.collectors` is resolved (compatible with the old keys `hooks`, `mcp` and
  `hook_events`; when both are present, `collectors` wins). The emitted event types and payload keys are unchanged.
  Collector exceptions are isolated into one warning per collector. `validate_settings` gives the warnings
  `observe.unknown_collector` and `observe.collector_config_invalid`. Fills `BackendDescriptor.collectors`.
  Constructor argument `collectors`, attribute `collector_reports`, public name `COLLECTOR_ISSUES`. New dependency
  `agent-console-registry`. **Public API change**: removed the `observe_hooks`, `observe_mcp` and `clock` arguments
  from `MessageTranslator` (observation events are emitted by collectors), and added `MessageTranslator.target_of`.
  Moved the definition of `CLAUDE_SDK_BACKEND_ID` to `_options` (same public name).
- Server administrator option `allow_subscription_auth` (default `false`). When it is off, `auth.mode=subscription`
  is the settings validation error `backend.subscription_auth_disabled` and runs are refused (**behavior change**:
  previously it only warned and ran). When it is on, the warning text is stronger. New public names `AUTH_ISSUES`,
  `SUBSCRIPTION_AUTH_DISABLED_MESSAGE` and `SUBSCRIPTION_AUTH_WARNING`, and
  `ClaudeSdkErrorCodes.SUBSCRIPTION_AUTH_DISABLED`.

## 0.1.0

- Set up as a standalone project: internal dependencies are declared by name and version range, with per-package
  pytest, mypy and ruff settings, a `dev` dependency group, LICENSE and CHANGELOG. No behavior change.
