# agent-console-backend-fake-agent

An execution backend that imitates agent runs (responses, tools, delegation, questions, hooks, failures, delays) **according to settings data**, without a model.
For development, tests, and E2E. It is registered as the entry point `agent_console.backends:fake-agent`, and its display name is `가짜 에이전트(테스트용)`
(`FAKE_BACKEND_TITLE`).

**Hidden on screen by default**: the descriptor declares `ui_hints.hidden: true`. The web app leaves backends marked hidden out of
the run method choices and settings cards, and definitions that already name this backend still run. When the server administrator turns on the `mod-runs` setting
`show_hidden_backends: true` (environment variable `AGENT_CONSOLE_SHOW_HIDDEN_BACKENDS=1`), the server publishes the descriptor with hiding removed.
Tests, e2e, CI, and `pnpm app` turn it on with this setting. The old id `fake` was removed without an alias (if it remains in saved data,
it is an "unregistered execution backend" error).

## Installation

```bash
uv sync --all-packages                         # inside the workspace
uv pip install ./packages/py/features/ac-backend-fake-agent   # standalone
```

Dependencies: `agent-console-runtime`, `agent-console-contracts`, `pydantic`.

## Settings (`Agent.backend_options`, type `FakeBackendOptions`)

| Key | Default | Meaning |
| --- | --- | --- |
| `rules` | `[]` | The first matching rule from the top is used |
| `default` | `{response: "$prompt"}` | When no rule matches (by default, returns the prompt as is) |
| `delay_ms` | `0` | Delay between deltas |
| `chunk_chars` | `16` | Characters per delta |
| `echo_bundle` | `false` | Appends a summary of the received run bundle to the end of the response (to check resource delivery in E2E) |

Rules (`FakeRule`): conditions `contains`, `prefix`, `equals` (`ignore_case` defaults to true; all must hold; without conditions, always matches),
`response`(`string.Template`: `$prompt`·`$agent_id`·`$agent_name`·`$model`·`$session_id`·`$bundle`·
`$delegate_1`…), `structured`, `tool_calls` (`[{name, input, output, is_error}]`), `delegate` (below),
`ask` (below), `observe` (below), `fail` (`{code, message, after_chunks}`), `delay_ms` and `chunk_chars` (per-rule overrides),
`usage` (computed from word counts if absent), `llm_duration_ms` (the `duration_ms` of the last `agent.usage`; null when empty).
Platform tool calls (`host_tool_calls`) pass the generated call id to `call_host_tool(tool_use_id=)`.

Event order: `agent.session_started` → `usage.rate_limit`* (server administrator settings) → observation (start)* → (`agent.tool_call` →
`agent.tool_result`)* → observation (tool)* → delegation* → `agent.text_delta`* → `agent.message` → observation (end)* → `agent.usage`.
On failure, `failed` without `agent.message`; on cancellation, `cancelled` immediately during delays.

### Imitating subagent delegation (`delegate`)

```yaml
rules:
  - contains: 구현
    delegate:
      - to: be-node              # AgentRequest.subagents[].name (= the delegate node id)
        prompt: "API 작업: $prompt"   # the task to pass on (delegator variables)
        response: "$agent_name 끝: $prompt"   # the subagent result ($prompt = the task, $bundle = the target bundle)
        tool_calls: [{name: Write, input: {path: a.py}}]
        status: completed        # anything other than completed (failed and so on) makes the delegation tool result an error
        delay_ms: 0              # delay before finishing (cancellable)
        usage: {total_tokens: 120, tool_uses: 1, duration_ms: 900}   # word counts and measurements if absent
    response: "정리: $delegate_1"
```

Events of one delegation (the same shape as claude-sdk):

| Order | type | actor | node_path |
| --- | --- | --- | --- |
| 1 | `agent.tool_call` (name = server administrator setting `delegate_tool`, input `{subagent_type, description, prompt}`) | Delegator | Delegator |
| 2 | `agent.subagent_started{subagent_id, name, tool_use_id, task_preview}` | Target `actor` | `sink.child_path(name)` |
| 3 | The target's `agent.tool_call` and `agent.tool_result`*, `agent.message` (no deltas) | Target | 〃 |
| 4 | `agent.subagent_stopped{…, status, usage{total_tokens}, tool_uses, duration_ms, result_preview}` | Target | 〃 |
| 5 | `agent.tool_result` (delegation tool, `tool_use_id` = the id from 1) | Delegator | Delegator |

- The target path comes from `BackendEventSink.child_path(name)` (a required protocol method that `NodeContext` implements).
- If the target is not in the request, an error tool result (`is_error`) comes right after 1, and `$delegate_N` is an empty string.
- If cancelled during delegation, only `agent.subagent_stopped{subagent_id, name, tool_use_id, status: stopped}` (no usage or result) is emitted and
  it ends `cancelled`. The delegation tool result (5) and the result notification are not emitted, the same shape claude-sdk emits on interrupt.
- Subagent tokens are not added to the delegator's `agent.usage`.
- If the sink satisfies the optional capability `SubagentResultListener` (ac-runtime, `on_subagent_result(name, *, text, status, actor,
  tool_use_id)`), it is called with the full result each time one delegation ends (after 5).
  `status` is `succeeded` for `completed`, otherwise `failed`. The delegation strategy `sdk-subagents` (nodes-core) uses this to emit
  the target's replies. Failures give `log.warning`.

### Imitating platform tool calls (`host_tool_calls`)

`capabilities.host_tools = true`. The rule's `host_tool_calls` call the request's `AgentRequest.host_tools` (ac-runtime `HostTool`)
one at a time in order after delegation (`delegate`) (deterministic). For tests and E2E of the standalone delegation (`host`).

```yaml
rules:
  - contains: 기능
    response: "검토 결과: $host_1 ($host_1_status)"
    host_tool_calls:
      - tool: delegate                     # HostTool.name
        input: {target: reviewer, task: "$prompt"}   # strings are templates
        append: false                      # default true = append the result to the end of the response
      - tool: delegate
        input: {target: writer, task: "$host_1"}
        when: {contains: 반려}             # only when the previous call's result matches (after: N for another call, not_contains, is_error)
```

- Each call: `agent.tool_call{name: tool}` → handler (`call_host_tool`) → `agent.tool_result{is_error}`.
- `$host_N` (result text), `$host_N_status` (`succeeded`|`failed`|`skipped`|`cancelled`, `HostCallStatus`).
  `skipped` when `when` does not match, and also when there is no result to look at.
- A tool that is not in the request gives an error result (`UNKNOWN_HOST_TOOL_TEXT`). If the run is cancelled during the handler, `cancelled` without a result event.

### Imitating interactions (`ask`)

```yaml
rules:
  - contains: 배포
    ask:
      - kind: question                 # interaction kind id
        title: 확인
        payload: {text: "$prompt 진행할까요?"}   # strings are filled with delegator variables
        answer_path: /response         # the response location to put into $answer_1 (the whole response JSON if absent)
        timeout_seconds: 30            # optional
        # response_schema: {...}       # optional (the kind default if absent)
    response: "답: $answer_1 ($answer_1_status)"
```

- After delegation (`delegate`) and before the response text, `sink.request_input` is opened in order.
- **Conditions for opening**: only when the sink is an `InteractivePort` and the request's allowance (`AgentRequest.interactions.kinds`) includes that kind.
  Otherwise it is not opened: `log.warning` + `$answer_N` = `$answer_N_status` = `unavailable`
  (nodes without the edge cannot open requests).
- Result: when answered, `$answer_N` = the response value; when expired or cancelled, the status string (`expired`, `cancelled`). If the Run is cancelled,
  it ends `cancelled`. `capabilities.interactions = None` (no kind restriction).

### Imitating hook and MCP observations (`observe`)

```yaml
default:
  tool_calls: [{name: mcp__docs__lookup, input: {q: x}}]
  observe:
    - type: hook.invoked                 # event names are data (no list of hook kinds in the fake code)
      payload: {event: PreToolUse, hook_type: sdk-callback, tool_name: Bash}
    - type: mcp.call_started
      after: tool                        # start (default) | tool | end
      payload: {server: docs, tool: lookup, tool_use_id: "$session_id:tool0"}   # strings are templates
    - type: lsp.diagnostics              # other families give the switch key directly
      when: lsp
```

- Emitted **only when the request's observation settings are on**: the `when` key must be `true` in `AgentRequest.observe` (= `AgentSettings.observe`).
  If `when` is omitted, it is decided by the first segment of the type (`DEFAULT_OBSERVE_SWITCHES`: `hook` → `hooks`, `mcp` → `mcp`). An unknown
  family without `when` is a settings validation error.
- Position: `start` = right after the session start (and `usage.rate_limit`), `tool` = after the rule's tool calls (before delegation), `end` = after `agent.message`
  and before `agent.usage` (emitted even on failure, not on cancellation).
- payload strings are filled with the same variables as the response (`$prompt`, `$session_id`, `$agent_id` …). The ids of rule tool calls are
  `$session_id:tool0`, `$session_id:tool1`…, so MCP call pairs can be matched to tool calls with the same `tool_use_id`.
- `hook_events` (the list of hook events to observe) is not interpreted by the fake (the rule data decides which events to emit).
- Switches also read `observe.collectors` (`observe_switch_on`): when `collectors[<collector id>].enabled` is a bool, it wins over the old key.
  The mapping from old keys to collector ids, `DEFAULT_OBSERVE_COLLECTORS` (`hooks` → `sdk-hooks`, `mcp` → `mcp-calls`; the same rule as claude-sdk's
  `LEGACY_OBSERVE_KEYS`), is changed with the server administrator setting `observe_collectors`. A `when` not in the mapping is also treated as
  a collector id (`when: example.tool_count` → `collectors.example.tool_count.enabled`).

### Imitating hook probe records (`hook_probe`)

```yaml
default:
  hook_probe:
    - event: PreToolUse
      matcher: Bash
      tool: Bash
      tool_use_id: "$session_id:tool0"   # strings are templates
      input: {tool_input: {command: ls}}
      decision: allow                    # decision.value (default none)
      duration_ms: 25
    - {event: Stop, after: end, exit_code: 2, decision: block, reason: no}
```

- Only when the observation setting `observe.hook_probe` is on (a separate key, not a collector, the same as claude-sdk) and the request has a run folder
  (`AgentRequest.run_folder`), it appends one line at a time in the real probe format (`format`
  default `hook-probe/1`) to `<run_folder>/<hook_probe_folder>/<session>.jsonl`. Keys: `format, probe_id(<session>:probeN), event, session_id, tool_use_id, tool,
  matcher, context(= run_context), started_at, ended_at, duration_ms, exit_code, error, decision{value, source: fake-agent,
  reason}, input, agent_id, agent_type, cwd, simulated: true` + `fields` (keys to add or override, as data when the format changes).
  The log source `hook-probe-jsonl` and the classifier `hook-probe` read it as is (checked by tests). No command is run.
- Without a run folder, one `log.warning`. When off (default), nothing is written.
- With `echo_hooks` on, one record line is also kept for each item in the bundle's `hooks` (`hook_probe: true` in the `hook.*` payload).
- Bundle preview hook `FakeBackend.preview_notes`: with `observe.hook_probe`, it imitates the same code as claude-sdk,
  `observe.hook_probe_wrapped` (info, `details.simulated: true`).

### Run bundle summary (`echo_bundle`, `$bundle`)

`bundle: instructions=2 [team-guide, pl-guide]; mcp_servers=1 [github]; ignored=[hooks]`: in slot name order,
it carries only the item count and source refs per slot, never slot values. Slots not in `capabilities.resource_slots` are `ignored`.
`secret://…` shapes are masked as `secret://***`. Without a bundle, `bundle: -`. The function `bundle_summary` can be used on its own.

## Minimal usage

```python
>>> import asyncio
>>> from agent_console_backend_fake_agent import FakeBackend
>>> from agent_console_backend_fake_agent.testing import ValidatingSink  # the shared one (ac-runtime.testing_sink), re-exported
>>> from agent_console_contracts import Agent
>>> from agent_console_runtime import AgentRequest, CancelToken

>>> agent = Agent(
...     id="a",
...     name="A",
...     backend_options={
...         "rules": [{"contains": "spec", "response": "스펙: $prompt", "delay_ms": 20}],
...     },
... )
>>> sink = ValidatingSink()  # records events while validating them against the contracts
>>> result = asyncio.run(
...     FakeBackend().run(AgentRequest(agent=agent, prompt="spec 써 줘"), sink, CancelToken())
... )
>>> result.status, result.text
('succeeded', '스펙: spec 써 줘')
>>> sink.types
['agent.session_started', 'agent.text_delta', 'agent.message', 'agent.usage']
>>> asyncio.run(  # without a matching rule, returns the prompt as is
...     FakeBackend().run(AgentRequest(agent=agent, prompt="hello"), ValidatingSink(), CancelToken())
... ).text
'hello'

```

`FakeBackend(models=[...], rate_limits=[...], resource_slots=[...], delegate_tool="Agent", clock=time.time)`.
`capabilities`: streaming, tools, resume, cancel, subagents = true, `interactions = None` (no restriction),
`resource_slots` = the constructor argument (default: every known slot), `enforce` is all false (it runs nothing, but it enforces nothing either).

### Readiness and connection test (optional capabilities)

`capabilities.status` and `probe` = true. `status(ctx)` is always `state: always_ready` (`FAKE_READY_STATE`) with tone ok, and
`probe(ctx, timeout_s)` returns `ok: true, latency_ms: 0, details: {models: n}` without delay (no network or keys).
`probe_cost_note` is a "no cost" message. When the scripted sign-in (below) is on, the status follows the in-memory sign-in state.

### Scripted sign-in (optional capability)

Reproduces the whole flow of the Claude subscription sign-in dialog **without a PTY, network, or files**, for e2e and web development. It turns on when the server administrator setting
`backends.fake-agent.login` (`FakeLoginScript`) is given (default `null` = no capability, so no sign-in button appears on the default card).

```yaml
backends:
  fake-agent:
    login: {}                     # the default script: code ok = success, anything else = verify_failed
    # login: {needs_code: false, callback_after_s: 1}   # the callback path (success after 1 second without a code)
    # login: {start_delay_s: 0.5, verify_delay_s: 0.5, start_logged_in: true, logout_ok: false}
```

- When on, `capabilities.login/logout = true`, `login_methods = [{id: script, label: 구독으로 로그인, notice, writes}]`.
- Flow: `starting` →(`start_delay_s`) `waiting_user` (`open_url` default `https://login.example.com/oauth/authorize?fake=1`,
  `needs_code`, `screen` lines) → code entry → `verifying` →(`verify_delay_s`) if the code is `success_code` (default `ok`),
  `succeeded`; otherwise `failed` (`reason` = `fail_reason`, default `verify_failed`). With `needs_code: false` +
  `callback_after_s`, it succeeds without a code. Cancellation (`DELETE`), heartbeat expiry, and timeouts (`timeout_s`) are handled by the service;
  the script only waits.
- Status check: before sign-in, `state: login_required` (`FAKE_LOGIN_REQUIRED_STATE`, warn, main button `login`); after sign-in,
  `always_ready` (ok, menu `login` (sign in again) and `logout`). The state is instance memory (`FakeBackend.login_state`), so restarting
  the server returns it to `start_logged_in`.
- Sign-out: clears the in-memory state. With `logout_ok: false`, `ok: false, reason: logout_failed`.
- Accepted keys: `accepts_keys` (when empty, the service defaults enter, up, down, escape). Keys are only recorded.
- Text is changed with `texts` (`FakeLoginTexts`). Received codes are reported through `secrets_to_mask` so the service masks them in responses.

```python
>>> import asyncio
>>> from agent_console_backend_fake_agent import FakeBackend
>>> from agent_console_runtime import BackendLoginService
>>> async def login(code: str) -> tuple[str, bool]:
...     backend = FakeBackend(login={})
...     service = BackendLoginService(lambda: {"fake-agent": backend}, tick_s=0.01)
...     sid = (await service.start("fake-agent")).session_id
...     await service.send_input(sid, text=code)
...     while service.get(sid).phase not in {"succeeded", "failed"}:
...         await asyncio.sleep(0.01)
...     phase = service.get(sid).phase
...     await service.aclose()
...     return phase, backend.login_state.logged_in
>>> asyncio.run(login("ok")), asyncio.run(login("nope"))
(('succeeded', True), ('failed', False))

```

### Server administrator settings (`ConfigurableBackend` hook)

`FakeBackend.from_options(options, *, secrets, environ)` is the ac-runtime `ConfigurableBackend` implementation. The server passes the setting
`backends.fake-agent` to this hook to replace the instance created from the entry point (only this package knows what the keys mean).

| Key | Default | Meaning |
| --- | --- | --- |
| `models` | `[]` | The `list_models()` list (`ModelInfo`) |
| `rate_limits` | `[]` | `usage.rate_limit` to emit on every run: `[{window, status?, utilization?, resets_at? \| resets_in_seconds?, overage_status?}]` |
| `resource_slots` | Every known slot | `capabilities.resource_slots` |
| `delegate_tool` | `Agent` | The tool name of delegation tool call events |
| `observe_collectors` | `{hooks: sdk-hooks, mcp: mcp-calls}` | Old observation keys → collector ids (`observe.collectors` wins over old keys) |
| `hook_probe_folder` | `hook-probe` | Folder name under the run folder for imitated hook probe records |
| `login` | `null` | Scripted sign-in (`FakeLoginScript`, "Scripted sign-in" above). `{}` is the default script |
| `echo_hooks` | `false` | Emits `hook.started` and `hook.finished{event, matcher, command_preview, exit_code: 0, duration_ms: 0, decision: null, simulated: true}` for each item in the run bundle's `hooks` slot (commands are not run; works even without `observe` rules). Not emitted when the settings say not to accept `hooks` |

Unknown keys and invalid values raise `ValueError` (location and reason only, no values). Type models: `FakeInstallOptions`, `FakeRateLimit`, `FakeLoginScript`.

## Imitating session records

With the server administrator setting `session_dir` (relative paths = relative to the app workspace), each run leaves one line in `<folder>/<cwd key>/<session>.jsonl`, and a request
to continue a session whose file is missing fails with `fake.session_missing` (the case where a real backend cannot find the session record). `session_archive()`
provides archiving and restore. The default (null) keeps the current behavior (continuation status `not_applicable`).

## Test helpers

`agent_console_backend_fake_agent.testing` re-exports `ValidatingSink`, `ListeningSink`
(records subagent result notifications), and `InteractiveSink` (imitates interaction responses) from `agent_console_runtime.testing_sink`. The implementation lives only in ac-runtime.

## Development and standalone reuse

This folder is a standalone project. Copy only this folder and the commands below still work. Internal dependencies
are declared as a name plus a version range, so outside the repository pass the wheelhouse (`uv run poe wheels` in the repository → `dist/wheelhouse`)
as a find-links path (`uv sync --find-links <wheelhouse>`). Check inside the repository: `uv run poe portability --package ac-backend-fake-agent`.

```bash
uv sync                  # includes the dev group (pytest, mypy, ruff, internal packages the tests use)
uv run ruff check . && uv run mypy && uv run pytest
```

## Testing

```bash
uv run pytest packages/py/features/ac-backend-fake-agent/tests
```
