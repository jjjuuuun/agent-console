# Changelog

## Unreleased (0.2.0)

- `fail.message` is optional (default `null`). Empty means the default text `fake 백엔드가 설정에 따라 실패했습니다`
  (in the message catalog `en`), so settings forms no longer prefill a Korean value. New method
  `FakeFailure.error_message()`.
- Model discovery stand-in. Administrator settings `discovered_models` (`null` = no capability), `discovery_failure`
  (a reason code; `unsupported` = state `unsupported`, constant `FAKE_DISCOVERY_UNSUPPORTED`) and
  `discovery_delay_s`, the method `FakeBackend.discover_models` and the counter `FakeBackend.discovery_calls`.
  `capabilities.model_discovery` is true only when one of the first two is set. Requires
  `agent-console-runtime>=0.2,<0.3` and `agent-console-contracts>=0.16.1,<0.17`. Consumer range:
  `agent-console-backend-fake-agent>=0.2,<0.3`.
- Message catalog `locales/en.json` is registered as the entry point `agent_console.message_catalogs`
  `ac-backend-fake-agent`, so the web app can show the fake backend description and option schema in English (data
  only, no API change).
- Follow-up: 10 more English entries in `locales/en.json` (option schema examples and the default rule shown by
  `GET /backends`; data only).
- Contract 0.13.1: `FAKE_SESSION_MISSING_CODE` uses the contract constant `ErrorCodes.FAKE_SESSION_MISSING` (same
  value).
- Scripted sign-in. When the server administrator setting `login` (`FakeLoginScript`, default null = no capability)
  is given, the backend provides `capabilities.login/logout`, `login_methods`, `start_login`
  (`FakeScriptedLoginDriver`: the code `success_code` succeeds, anything else gives `fail_reason`) and `logout`. The
  readiness check reports whether the in-memory sign-in is done (`login_required` / `always_ready`) and `actions`. No
  PTY or network.
- Reply template variable `$cwd` (the run folder of the request, or an empty string when there is none).
- `capabilities.host_tools = true`. The rule `host_tool_calls: [{tool, input, when?, append}]` (`FakeHostToolCall`,
  `FakeHostToolWhen`) calls platform tools, fills `$host_N` and `$host_N_status` and appends the results to the end of
  the reply.

## 0.1.0

- Set up as a standalone project: internal dependencies are declared by name and version range, with per-package
  pytest, mypy and ruff settings, a `dev` dependency group, LICENSE and CHANGELOG. No behavior change.
