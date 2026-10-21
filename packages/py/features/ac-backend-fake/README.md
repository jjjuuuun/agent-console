# agent-console-backend-fake

모델 없이 **설정 데이터대로** 결정적 응답을 주는 실행 백엔드(X3). 테스트·E2E·데모·오프라인용.
entry point `agent_console.backends:fake`로 등록된다. 설계: `specs/agent-console/design.md` §3.3, §6.2.

## 설치

```bash
uv sync --all-packages                         # 워크스페이스 안
uv pip install ./packages/py/features/ac-backend-fake   # 단독
```

의존: `agent-console-runtime`, `agent-console-contracts`, `pydantic`.

## 설정 (`Agent.backend_options`, 형식 `FakeBackendOptions`)

| 키 | 기본 | 의미 |
| --- | --- | --- |
| `rules` | `[]` | 위에서부터 처음 맞는 규칙을 쓴다 |
| `default` | `{response: "$prompt"}` | 맞는 규칙이 없을 때(기본은 프롬프트 그대로 반환) |
| `delay_ms` | `0` | 델타 사이 지연 |
| `chunk_chars` | `16` | 델타 하나의 글자 수 |
| `echo_bundle` | `false` | 응답 끝에 받은 실행 묶음 요약을 덧붙인다(E2E에서 리소스 전달 확인용) |

규칙(`FakeRule`): 조건 `contains`·`prefix`·`equals`(`ignore_case` 기본 true, 모두 만족해야 함, 없으면 항상 맞음),
`response`(`string.Template`: `$prompt`·`$agent_id`·`$agent_name`·`$model`·`$session_id`·`$bundle`·
`$delegate_1`…), `structured`, `tool_calls`(`[{name, input, output, is_error}]`), `delegate`(아래),
`ask`(아래), `observe`(아래), `fail`(`{code, message, after_chunks}`), `delay_ms`·`chunk_chars`(규칙별 덮어쓰기),
`usage`(없으면 단어 수로 계산).

이벤트 순서: `agent.session_started` → `usage.rate_limit`*(설치자 설정) → 관측(start)* → (`agent.tool_call` →
`agent.tool_result`)* → 관측(tool)* → 위임* → `agent.text_delta`* → `agent.message` → 관측(end)* → `agent.usage`.
실패면 `agent.message` 없이 `failed`, 취소면 지연 중 즉시 `cancelled`.

### 서브에이전트 위임 흉내 (`delegate`)

```yaml
rules:
  - contains: 구현
    delegate:
      - to: be-node              # AgentRequest.subagents[].name (= 위임 대상 노드 id)
        prompt: "API 작업: $prompt"   # 넘길 과제(위임자 변수)
        response: "$agent_name 끝: $prompt"   # 서브에이전트 결과($prompt = 과제, $bundle = 대상 묶음)
        tool_calls: [{name: Write, input: {path: a.py}}]
        status: completed        # completed 밖(failed 등)이면 위임 도구 결과가 오류
        delay_ms: 0              # 끝나기 전 지연(취소 가능)
        usage: {total_tokens: 120, tool_uses: 1, duration_ms: 900}   # 없으면 단어 수·측정값
    response: "정리: $delegate_1"
```

위임 하나의 이벤트(claude-sdk와 같은 모양, design §R3.4):

| 순서 | type | actor | node_path |
| --- | --- | --- | --- |
| 1 | `agent.tool_call`(이름 = 설치자 설정 `delegate_tool`, 입력 `{subagent_type, description, prompt}`) | 위임자 | 위임자 |
| 2 | `agent.subagent_started{subagent_id, name, tool_use_id, task_preview}` | 대상 `actor` | `sink.child_path(name)` |
| 3 | 대상의 `agent.tool_call`·`agent.tool_result`*, `agent.message`(델타 없음) | 대상 | 〃 |
| 4 | `agent.subagent_stopped{…, status, usage{total_tokens}, tool_uses, duration_ms, result_preview}` | 대상 | 〃 |
| 5 | `agent.tool_result`(위임 도구, `tool_use_id` = 1의 id) | 위임자 | 위임자 |

- 대상 경로는 `BackendEventSink.child_path(name)`(프로토콜 필수 메서드, `NodeContext`가 구현)로 얻는다.
- 요청에 없는 대상이면 1 다음 바로 오류 도구 결과(`is_error`)이고 `$delegate_N`은 빈 문자열이다.
- 위임 중 취소되면 `agent.subagent_stopped{subagent_id, name, tool_use_id, status: stopped}`(사용량·결과 없음)만 내고
  `cancelled`로 끝난다. 위임 도구 결과(5)와 결과 알림은 내지 않는다 — claude-sdk가 interrupt 때 내는 모양과 같다.
- 위임자 `agent.usage`에는 서브에이전트 토큰을 더하지 않는다.
- sink가 선택 능력 `SubagentResultListener`(ac-runtime, `on_subagent_result(name, *, text, status, actor,
  tool_use_id)`)를 만족하면 위임 하나가 끝날 때마다(5 다음) 결과 전문으로 부른다.
  `status`는 `completed`면 `succeeded`, 아니면 `failed`. 위임 방식 `sdk-subagents`(nodes-core)가 이것으로
  대상의 답변을 낸다. 실패는 `log.warning`.

### 플랫폼 도구 호출 흉내 (`host_tool_calls`, 5R.10, design §5R.6)

`capabilities.host_tools = true`. 규칙의 `host_tool_calls`가 요청의 `AgentRequest.host_tools`(ac-runtime `HostTool`)를
위임(`delegate`) 다음에 순서대로 하나씩 부른다(결정적). 독립 위임(`host`) 테스트·E2E용이다.

```yaml
rules:
  - contains: 기능
    response: "검토 결과: $host_1 ($host_1_status)"
    host_tool_calls:
      - tool: delegate                     # HostTool.name
        input: {target: reviewer, task: "$prompt"}   # 문자열은 템플릿
        append: false                      # 기본 true = 결과를 응답 끝에 붙인다
      - tool: delegate
        input: {target: writer, task: "$host_1"}
        when: {contains: 반려}             # 앞 호출 결과가 맞을 때만(after: N으로 다른 호출, not_contains·is_error)
```

- 호출마다 `agent.tool_call{name: 도구}` → 핸들러(`call_host_tool`) → `agent.tool_result{is_error}`.
- `$host_N`(결과 텍스트)·`$host_N_status`(`succeeded`|`failed`|`skipped`|`cancelled`, `HostCallStatus`).
  `when`이 맞지 않으면 `skipped`, 볼 결과가 없어도 `skipped`.
- 요청에 없는 도구면 오류 결과(`UNKNOWN_HOST_TOOL_TEXT`). 핸들러 도중 실행 취소면 결과 이벤트 없이 `cancelled`.

### 상호작용 흉내 (`ask`, design §R14.9)

```yaml
rules:
  - contains: 배포
    ask:
      - kind: question                 # 상호작용 종류 id
        title: 확인
        payload: {text: "$prompt 진행할까요?"}   # 문자열은 위임자 변수로 채움
        answer_path: /response         # $answer_1에 넣을 응답 위치(없으면 응답 전체 JSON)
        timeout_seconds: 30            # 선택
        # response_schema: {...}       # 선택(없으면 종류 기본값)
    response: "답: $answer_1 ($answer_1_status)"
```

- 위임(`delegate`) 다음, 응답 텍스트 전에 순서대로 `sink.request_input`을 연다.
- **열 수 있는 조건**: sink가 `InteractivePort`이고 요청의 허용(`AgentRequest.interactions.kinds`)에 그 종류가
  있을 때만. 아니면 열지 않고 `log.warning` + `$answer_N` = `$answer_N_status` = `unavailable`
  (연결이 없는 노드는 요청을 열지 못한다, §R14.2).
- 결과: answered면 `$answer_N` = 응답 값, 만료·취소면 상태 문자열(`expired`·`cancelled`). Run이 취소되면
  `cancelled`로 끝난다. `capabilities.interactions = None`(종류 제한 없음).

### hook·MCP 관측 흉내 (`observe`, design §2R.5·§8.3)

```yaml
default:
  tool_calls: [{name: mcp__docs__lookup, input: {q: x}}]
  observe:
    - type: hook.invoked                 # 이벤트 이름은 데이터(fake 코드에 hook 종류 목록 없음)
      payload: {event: PreToolUse, hook_type: sdk-callback, tool_name: Bash}
    - type: mcp.call_started
      after: tool                        # start(기본) | tool | end
      payload: {server: docs, tool: lookup, tool_use_id: "$session_id:tool0"}   # 문자열은 템플릿
    - type: lsp.diagnostics              # 다른 계열은 켜는 키를 직접 준다
      when: lsp
```

- **요청의 관측 설정이 켜졌을 때만** 낸다: `AgentRequest.observe`(= `AgentSettings.observe`)에서 `when` 키가 `true`여야 한다.
  `when`을 생략하면 type의 첫 세그먼트로 정한다(`DEFAULT_OBSERVE_SWITCHES`: `hook` → `hooks`, `mcp` → `mcp`). 모르는
  계열인데 `when`이 없으면 설정 검증 오류.
- 자리: `start` = 세션 시작(·`usage.rate_limit`) 직후, `tool` = 규칙의 도구 호출 다음(위임 전), `end` = `agent.message`
  다음·`agent.usage` 앞(실패여도 낸다, 취소면 내지 않는다).
- payload 문자열은 응답과 같은 변수(`$prompt`, `$session_id`, `$agent_id` …)로 채운다. 규칙 도구 호출의 id는
  `$session_id:tool0`, `$session_id:tool1`…이라 MCP 호출 쌍을 도구 호출과 같은 `tool_use_id`로 맞출 수 있다.
- `hook_events`(관측할 hook 이벤트 목록)는 fake가 해석하지 않는다(낼 이벤트는 규칙 데이터가 정한다).
- 스위치는 `observe.collectors`(4R.8)도 읽는다(`observe_switch_on`): `collectors[<수집기 id>].enabled`가 bool이면 옛 키를
  이긴다. 옛 키 → 수집기 id 대응표 `DEFAULT_OBSERVE_COLLECTORS`(`hooks` → `sdk-hooks`, `mcp` → `mcp-calls`, claude-sdk
  `LEGACY_OBSERVE_KEYS`와 같은 규칙)는 설치자 설정 `observe_collectors`로 바꾼다. 대응표에 없는 `when`은 그 이름을
  수집기 id로도 본다(`when: example.tool_count` → `collectors.example.tool_count.enabled`).

### hook probe 기록 흉내 (`hook_probe`, 4R.9, design §4R.7)

```yaml
default:
  hook_probe:
    - event: PreToolUse
      matcher: Bash
      tool: Bash
      tool_use_id: "$session_id:tool0"   # 문자열은 템플릿
      input: {tool_input: {command: ls}}
      decision: allow                    # decision.value(기본 none)
      duration_ms: 25
    - {event: Stop, after: end, exit_code: 2, decision: block, reason: no}
```

- 관측 설정 `observe.hook_probe`가 켜졌고(수집기가 아니라 별도 키다 — claude-sdk와 같음) 요청에 실행 폴더
  (`AgentRequest.run_folder`)가 있을 때만 `<run_folder>/<hook_probe_folder>/<세션>.jsonl`에 실제 probe 형식(`format`
  기본 `hook-probe/1`) 한 줄씩 덧붙인다. 키: `format, probe_id(<세션>:probeN), event, session_id, tool_use_id, tool,
  matcher, context(= run_context), started_at, ended_at, duration_ms, exit_code, error, decision{value, source: fake,
  reason}, input, agent_id, agent_type, cwd, simulated: true` + `fields`(덧붙이거나 덮어쓸 키, 형식이 바뀌면 데이터로).
  로그 출처 `hook-probe-jsonl`·분류기 `hook-probe`가 그대로 읽는다(테스트로 확인). 명령은 실행하지 않는다.
- 실행 폴더가 없으면 `log.warning` 하나. 꺼져 있으면(기본) 아무것도 쓰지 않는다.
- `echo_hooks`가 켜져 있으면 묶음 `hooks` 항목마다 기록 한 줄도 남긴다(`hook.*` payload에 `hook_probe: true`).
- 묶음 미리보기 훅 `FakeBackend.preview_notes`: `observe.hook_probe`면 claude-sdk와 같은 코드
  `observe.hook_probe_wrapped`(info, `details.simulated: true`)를 흉내 낸다.

### 실행 묶음 요약 (`echo_bundle`, `$bundle`)

`bundle: instructions=2 [team-guide, pl-guide]; mcp_servers=1 [github]; ignored=[hooks]` — 칸 이름순,
칸별 항목 수와 출처 ref만 싣고 칸 값은 싣지 않는다. `capabilities.resource_slots`에 없는 칸은 `ignored`.
`secret://…` 모양은 `secret://***`로 가린다. 묶음이 없으면 `bundle: -`. 함수 `bundle_summary`로 따로 쓸 수 있다.

## 최소 사용 예

```python
>>> import asyncio
>>> from agent_console_backend_fake import FakeBackend
>>> from agent_console_backend_fake.testing import ValidatingSink  # 공용(ac-runtime.testing_sink) 다시 내보냄
>>> from agent_console_contracts import Agent
>>> from agent_console_runtime import AgentRequest, CancelToken

>>> agent = Agent(
...     id="a",
...     name="A",
...     backend_options={
...         "rules": [{"contains": "spec", "response": "스펙: $prompt", "delay_ms": 20}],
...     },
... )
>>> sink = ValidatingSink()  # 이벤트를 계약으로 검증하며 기록
>>> result = asyncio.run(
...     FakeBackend().run(AgentRequest(agent=agent, prompt="spec 써 줘"), sink, CancelToken())
... )
>>> result.status, result.text
('succeeded', '스펙: spec 써 줘')
>>> sink.types
['agent.session_started', 'agent.text_delta', 'agent.message', 'agent.usage']
>>> asyncio.run(  # 맞는 규칙이 없으면 프롬프트를 그대로 돌려준다
...     FakeBackend().run(AgentRequest(agent=agent, prompt="hello"), ValidatingSink(), CancelToken())
... ).text
'hello'

```

`FakeBackend(models=[...], rate_limits=[...], resource_slots=[...], delegate_tool="Agent", clock=time.time)`.
`capabilities`: streaming·tools·resume·cancel·subagents = true, `interactions = None`(제한 없음),
`resource_slots` = 생성 인자(기본 알려진 칸 전부), `enforce`는 모두 false(아무것도 실행하지 않지만 강제하는 것도 없다).

### 준비 상태·연결 테스트 (선택 능력, ux-overhaul §15.8)

`capabilities.status`·`probe` = true. `status(ctx)`는 늘 `state: always_ready`(`FAKE_READY_STATE`), 톤 ok,
`probe(ctx, timeout_s)`는 지연 없이 `ok: true, latency_ms: 0, details: {models: n}`(네트워크·키 없음).
`probe_cost_note`는 "비용이 들지 않습니다".

### 설치자 설정 (`ConfigurableBackend` 훅)

`FakeBackend.from_options(options, *, secrets, environ)` — ac-runtime `ConfigurableBackend` 구현. 서버는 설정
`backends.fake`를 이 훅에 넘겨 entry point로 만든 인스턴스를 교체한다(키의 의미는 이 패키지만 안다).

| 키 | 기본 | 의미 |
| --- | --- | --- |
| `models` | `[]` | `list_models()` 목록(`ModelInfo`) |
| `rate_limits` | `[]` | 실행마다 낼 `usage.rate_limit`: `[{window, status?, utilization?, resets_at? \| resets_in_seconds?, overage_status?}]` |
| `resource_slots` | 알려진 칸 전부 | `capabilities.resource_slots` |
| `delegate_tool` | `Agent` | 위임 도구 호출 이벤트의 도구 이름 |
| `observe_collectors` | `{hooks: sdk-hooks, mcp: mcp-calls}` | 옛 관측 키 → 수집기 id(`observe.collectors`가 옛 키를 이긴다) |
| `hook_probe_folder` | `hook-probe` | 실행 폴더 아래 hook probe 기록 흉내 폴더 이름 |
| `echo_hooks` | `false` | 실행 묶음 `hooks` 칸 항목마다 `hook.started`·`hook.finished{event, matcher, command_preview, exit_code: 0, duration_ms: 0, decision: null, simulated: true}`를 낸다(명령은 실행하지 않음, `observe` 규칙 없이도, 2R.12). `hooks`를 받지 않게 설정했으면 내지 않는다 |

모르는 키·잘못된 값은 `ValueError`(위치와 사유만, 값은 넣지 않는다). 형식 모델: `FakeInstallOptions`, `FakeRateLimit`.

## 테스트 도우미

`agent_console_backend_fake.testing`은 `agent_console_runtime.testing_sink`의 `ValidatingSink`·`ListeningSink`
(서브에이전트 결과 알림 기록)·`InteractiveSink`(상호작용 응답 흉내)를 다시 내보낸다. 구현은 ac-runtime 한 곳뿐이다.

## 개발·재사용(단독)

이 폴더는 독립 프로젝트다(design §3R.2). 폴더만 복사해도 아래 명령이 그대로 돈다. 사내 의존은 이름 + 버전
범위로 선언돼 있으므로, 저장소 밖에서는 휠 모음(저장소에서 `uv run poe wheels` → `dist/wheelhouse`)을
찾기 경로로 준다(`uv sync --find-links <wheelhouse>`). 저장소 안 검사: `uv run poe portability --package ac-backend-fake`.

```bash
uv sync                  # dev 그룹(pytest·mypy·ruff, 테스트가 쓰는 사내 패키지) 포함
uv run ruff check . && uv run mypy && uv run pytest
```

## 테스트

```bash
uv run pytest packages/py/features/ac-backend-fake/tests
```
