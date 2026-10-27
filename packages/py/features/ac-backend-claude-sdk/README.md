# agent-console-backend-claude-sdk

Claude Agent SDK(`claude-agent-sdk`, `ClaudeSDKClient`) 실행 백엔드 어댑터(X3).
entry point `agent_console.backends:claude-agent-sdk`.

## 설치

```bash
uv sync --all-packages                               # 워크스페이스 안
uv pip install ./packages/py/features/ac-backend-claude-sdk   # 단독
```

의존: `agent-console-runtime`, `agent-console-contracts`, `agent-console-registry`, `agent-console-secret-rules`, `pydantic`,
`claude-agent-sdk`. 선택: `[hook-probe]`, `[login]`.

| 의존성 | 무엇을 | 왜 | 대안 |
| --- | --- | --- | --- |
| `claude-agent-sdk` (확인 버전 0.2.166, CLI 번들) | Claude Code 에이전트 실행 | design §7.4 결정: 훅 콜백·MCP·interrupt를 함께 쓰고 설치가 단순 | CLI `stream-json` 직접 구동(agent_bench 방식) 백엔드를 별도로 추가 |
| `agent-console-registry` (사내) | 관측 수집기(X7) entry point 로딩·검사(`load_entry_points`, 실패 = 보고서) | 다른 확장 지점과 같은 등록 방식(4R.8) | `importlib.metadata` 직접 순회(실패 보고·검사기 규칙을 다시 만들어야 함) |
| `agent-console-hook-probe` (사내, **선택** 추가 기능 `hook-probe`) | `observe.hook_probe`일 때 hook 명령 감싸기 인자(`wrap_command`·`wrap_command_line`) | 감싸기 규칙·기록 형식을 probe 패키지 한 곳에 둔다(4R.9). 선택인 이유: 기록 출처·분류기 쪽 의존(`agent-console-logs`)을 백엔드 단독 설치에 끌어오지 않기 위해 | 필수 의존(백엔드 설치가 무거워짐) / 감싸기 인자를 여기서 다시 만들기(같은 로직 복사) |

| `agent-console-secret-rules` (사내) | 구독 로그인 화면 글자 규칙(사용자가 고치는 정규식)의 안전 검사(`ac-safe-regex`를 거침) | 사용자 정규식은 한 곳의 검사기를 거친다는 규칙(design §2R.4) | `re.compile` 그대로(위험한 정규식을 막지 못함) |
| `agent-console-pty-session` (사내, **선택** 추가 기능 `login`) | `claude auth login`을 PTY로 띄워 화면 글자를 읽고 입력을 보냄(구독 로그인) | CLI 로그인 화면이 TTY를 요구한다. PTY·터미널 글자 해석을 한 패키지에 둔다(5.2R.81) | 사용자가 터미널에서 직접 `claude auth login`(앱 화면 로그인 없음) |

`pip install "agent-console-backend-claude-sdk[hook-probe]"`로 함께 설치한다. 없으면 `observe.hook_probe`가 켜져도
감싸지 않고 `log.warning`을 낸다(나머지는 그대로 동작). 서버 앱은 `[login]`을 함께 설치한다(구독 로그인 기본 켜짐).

## 최소 사용 예

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
...     # 기본 경로: API 키 방식. 값은 비밀 저장소 참조로만 둔다.
...     backend_options={"auth": {"mode": "api_key", "api_key": "secret://anthropic_api_key"}},
... )

```

실제로는 `client_factory`를 생략한다(SDK 클라이언트). 여기서는 정해 둔 메시지를 내는 가짜 클라이언트를 주입한다.

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
>>> options = clients[0].options  # 백엔드가 만든 SDK 옵션
>>> options.cwd, options.allowed_tools, "ANTHROPIC_API_KEY" in options.env
('/ws', ['Read', 'Bash'], True)

```

테스트는 `ClaudeSdkBackend(client_factory=...)`로 가짜 클라이언트를 주입한다(`agent_console_backend_claude_sdk.testing`
의 `FakeSdkClient`, 공용 `agent_console_runtime.testing_sink`를 다시 내보낸 `ValidatingSink`·`ListeningSink`·`InteractiveSink`).

## 인증 (§R13-10)

| 방식 | 설정 | 동작 |
| --- | --- | --- |
| **본인 구독 로그인 자격(기본, 본인 책임)** | `auth: {mode: subscription}` (+ 선택 `oauth_token: secret://…`). `auth: {}`도 같다 | `ANTHROPIC_API_KEY`를 빈 값으로 덮어써 API 키가 끼어들지 않게 한다. 토큰을 주면 `CLAUDE_CODE_OAUTH_TOKEN`으로, 없으면 CLI가 HOME 아래 로그인 자격(Claude Code 로그인)을 읽는다 |
| API 키(선택) | `auth: {mode: api_key, api_key: secret://anthropic_api_key}` | `ANTHROPIC_API_KEY`로 넘기고 `CLAUDE_CODE_OAUTH_TOKEN`은 비운다. 키가 없으면 실행하지 않는다(`auth_missing`) |

- **기본은 구독(본인 책임), API 키도 선택 가능**(5.2R.79, 사용자 지시 F13). `ClaudeSdkAuth.mode` 기본값은
  `subscription`, 설치자 설정 `allow_subscription_auth` 기본값은 `true`, 상태 점검 `readiness.auth` 기본값도 구독이다.
  Anthropic 문서상 Agent SDK 기반 앱에는 API 키 사용이 안내되므로, 구독 자격 사용은 본인 책임이고 아래 경고는 그대로 낸다.
- **구독 방식은 설치자 설정 `allow_subscription_auth`(기본 `true`)가 켜져 있어야 동작한다**(3R.29, TM-2·E-13).
  - 꺼짐(설치자가 `false`로 바꿨을 때): `validate_settings`가 error `backend.subscription_auth_disabled`(`AUTH_ISSUES.SUBSCRIPTION_DISABLED`)를
    내고, 문장은 `SUBSCRIPTION_AUTH_DISABLED_MESSAGE`("Anthropic 문서상 Agent SDK 기반 앱에는 API 키 사용이
    안내됩니다. 본인 구독 자격으로 쓰려면 설치자 설정에서 allow_subscription_auth를 켜세요(본인 책임).")다.
    `run`은 비밀을 해석하거나 SDK를 부르기 전에 같은 코드(`ClaudeSdkErrorCodes.SUBSCRIPTION_AUTH_DISABLED`)로 실패를 돌려준다.
  - 켜짐: `validate_settings`가 warning `backend.subscription_auth_enabled`를, 실행마다 `log.warning`을 같은 강화된
    문장(`SUBSCRIPTION_AUTH_WARNING`, 본인 책임 안내)으로 낸다.
  - 이 패키지에는 OAuth 토큰을 **받아 두거나 저장하는 경로가 없다.** 토큰은 사용자가 자기 비밀 저장소에 둔
    `secret://` 참조로만 읽어(해석기 `resolve`만 씀) CLI 하위 프로세스 env로 넘기고, 이벤트·결과·파일에 남기지 않는다.
    다른 사람의 구독 자격을 연결하는 경로도 없다(team-mode-design TM-0). 테스트: `tests/…_subscription_3r29.py`.
  - 5시간·주간 사용량(`usage.rate_limit`)은 구독 방식에서만 의미가 있다.
- `auth`를 아예 비우면(`null`·키 없음) 예전처럼 `env`·환경 정책만 따른다(5.2R.79에서도 유지 — 서버 환경의
  `ANTHROPIC_API_KEY`가 있으면 CLI가 그것을, 없으면 Claude Code 로그인을 쓴다. 구독 허용 검사·경고는 `auth`를
  적었을 때만 한다). 변수 이름은 `api_key_env`·`oauth_token_env`로 바꿀 수 있다.
- `setting_sources` 기본값은 `["project"]`이고 `user`는 들어 있지 않다(사용자 `~/.claude` 설정 격리).

### 상태 점검과 연결 테스트 (5.2R.68, ux-overhaul §15.8)

디스크립터가 `capabilities.status = true`·`capabilities.probe = true`를 선언하고 두 선택 메서드를 구현한다
(`agent_console_runtime.StatusCapableBackend`·`ProbeCapableBackend`). 서버는 `BackendReadinessService`로 감싸
`GET /api/v1/backends/{id}/status`·`POST /api/v1/backends/{id}/probe`에 낸다. 둘 다 설치자 설정 `readiness.auth`
(기본 `{mode: subscription}` — 구독 로그인, API 키 `{mode: api_key, api_key: secret://anthropic_api_key}`도 선택 가능)의 인증 방식을 본다 — 에이전트마다 다른 `auth`는 실행
때 `validate_settings`·`run`이 따로 검사한다.

- **`status(ctx)` — 정적 점검, 모델·네트워크 호출 없음.** 비밀은 이름이 있는지만 묻고(`ctx.has_secret`, 값을
  읽지 않음) 로그인 파일은 있는지만 본다. 결과 `state`(`ReadinessStates`, 열린 어휘)·`tone`·`summary`·`fixes`:

  | `state` | 톤 | 언제 |
  | --- | --- | --- |
  | `auth_ready` | ok | API 키 비밀이 있음 |
  | `auth_missing` | error | API 키 비밀이 없음(해결 버튼 "API 키 넣는 곳 보기") |
  | `subscription_disabled` | warn | 구독 방식인데 `allow_subscription_auth`가 꺼짐(해결 버튼 "설치자 설정 보기") |
  | `subscription_ready` | warn | 구독 방식이 켜져 있고 토큰 비밀 또는 로그인 파일이 있음("본인 책임" 문구를 `detail`에) |
  | `subscription_unverified` | warn | 구독 방식이 켜져 있으나 로그인 파일(`readiness.subscription_files`)을 찾지 못함 |

  로그인 파일은 후보 중 **처음 풀리는 하나만** 본다(`login_file`). CLI처럼 하위 프로세스가 받을
  `CLAUDE_CONFIG_DIR`(환경 정책 적용 후, 빈 값 = 없음)가 있으면 그 폴더만, 없으면 `~/.claude`를 본다.
  `CLAUDE_CONFIG_DIR`가 빈 폴더면 홈에 로그인 파일이 있어도 `subscription_unverified`다.
  | `subscription_token_missing` | error | `oauth_token` 참조가 가리키는 비밀이 없음 |
  | `cli_missing` | error | Claude Code 실행 파일을 찾지 못함(`readiness.cli_path` → SDK 번들 → PATH 순) |

  `checks`에는 항목별 "있음/없음"과 비밀 **이름**만 담는다(값·앞뒤 일부 없음).
- **`probe(ctx, timeout_s)` — 사용자가 누를 때만 하는 짧은 실제 호출.** 도구 없음(`tools=[]`)·한 턴
  (`max_turns=1`)·설정 파일 안 읽음(`setting_sources=[]`)·MCP 없음·빈 시스템 프롬프트·임시 작업 폴더·
  세션 기록 끔(`readiness.probe_extra_args` 기본 `--no-session-persistence`)으로 `readiness.probe_prompt` 한 줄을
  보낸다. 모델은 `readiness.probe_model`(비우면 CLI 기본).
  - **호출 없이 거부**: 실행 파일 없음(`cli_missing`), 구독 방식인데 설치자 설정 꺼짐
    (`backend.subscription_auth_disabled`, 우회 호출 없음), 키·토큰 없음(`auth_missing`).
  - **시간 상한**: `timeout_s`보다 조금 먼저 끊고 연결을 닫는다(`timeout`). 서버 상한은 서비스가 자른다.
  - **실패 사유**(`ProbeReasonCodes`, `details.category` = `PROBE_CATEGORIES`): 인증 `auth_failed`
    (`AssistantMessage.error=authentication_failed` 또는 HTTP 401·403), 네트워크 `network`(`CLIConnectionError`·
    `ConnectionError`), 시간 초과 `timeout`, 기타 `error`. `details`에는 모델 id·오류 종류·HTTP 코드·예외 형식
    이름만 담고 응답 글·예외 문장·비밀 값은 담지 않는다. CLI stderr는 버린다.
  - 비용 안내는 디스크립터 `probe_cost_note`(`PROBE_COST_NOTE`).
- 문구·해결 버튼(웹 라우트 역할·설정 섹션)은 데이터다: `readiness.texts`(`ClaudeSdkReadinessTexts`, `FixLink`).
- 부품은 단독으로 쓸 수 있다: `assess_readiness`(인증 해석 → 상태), `classify_probe_messages`·`classify_probe_error`,
  `find_claude_cli`, `expand_path`.

```python
>>> from agent_console_backend_claude_sdk import ClaudeSdkReadinessOptions, assess_readiness
>>> a = assess_readiness(
...     ClaudeSdkReadinessOptions(),
...     allow_subscription_auth=True,
...     has_secret=lambda name: False,
...     cli_found=True,
...     environ={"HOME": "/home/me"},
...     path_exists=lambda path: path == "/home/me/.claude/.credentials.json",
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

테스트(`tests/…_readiness_52r68.py`)는 가짜 SDK 클라이언트만 쓰고, 상태 점검·거부된 연결 테스트에서 실제
`ClaudeSDKClient` 생성 수가 0인지, 키 값(과 그 일부)이 응답·로그·예외 어디에도 없는지 확인한다.

### 구독 로그인 (5.2R.82, ux-overhaul §15.9)

앱 화면에서 Claude 구독 로그인을 시작하고 끝낸다(터미널을 열지 않는다). 서버가 `claude auth login`을 PTY 하위
프로세스로 띄우고 화면 글자를 읽어 로그인 주소·코드 요청을 웹 대화상자로 중계한다. **로그인 자격은 Claude Code CLI가
자기 위치(`CLAUDE_CONFIG_DIR` 또는 `~/.claude/.credentials.json`)에 쓴다. 앱은 토큰을 받거나 저장하지 않는다.** 한 번
로그인하면 상태 점검·실행·터미널의 Claude Code가 같은 로그인을 그대로 쓴다.

- 디스크립터: `capabilities.login = true`·`capabilities.logout = true`, `login_methods = [cli-login]`(문구·본인 책임
  안내·쓰기 경로는 데이터). 서비스·엔드포인트는 `agent_console_runtime.BackendLoginService`·`mod-runs`(5.2R.80)다.
- **능력이 없는 경우**: 설치자 설정 `login.enabled = false`, `allow_subscription_auth = false`, PTY를 쓸 수 없음(`[login]`
  미설치·플랫폼 미지원). PTY가 없으면 실패가 아니라 상태 `detail`에 설치 안내를 더한다. `allow_subscription_auth =
  false`이면 `login_refusal()`(`LoginRefusalAware`)이 이유를 알려 로그인·로그아웃 요청이 `backend.login_unsupported`가
  아니라 409 `backend.subscription_auth_disabled`로 거절된다.
- `status()`의 `actions`: 구독 방식이고 로그인 파일이 없으면(`subscription_unverified`) 주 버튼 `login`, 있으면
  (`subscription_ready`) 메뉴의 `login`(다시 로그인)·`logout`. 토큰 비밀(`oauth_token`) 방식이면 버튼이 없다.
  상태 점검은 계속 **파일 존재만** 본다(`claude auth status`는 Node 프로세스를 띄워 폴링마다 쓰기엔 비싸다 —
  로그인 성공 판정에만 쓴다).
- 흐름(`ClaudeCliLoginDriver`): `starting` → 규칙 `open_url`·`needs_code`가 맞으면 `waiting_user`(주소는 https +
  `allowed_url_hosts`만 넘긴다, OSC 8 링크 대상도 본다) → 붙여 넣은 코드 + `submit_keys`(기본 Enter) → 규칙 `success`가
  맞으면 `on_success_keys`(기본 Enter)를 보냄 → CLI가 끝나면(또는 성공 문구 뒤 `exit_wait_s`) 하위 프로세스를 정리하고
  `status_command`로 확인(`verifying`) → `succeeded`·`failed`.
- **판정은 늘 `status_command`**: 종료 코드 0이어야 하고, 출력 JSON의 `authMethod`를 읽었으면 `success_auth_methods`
  (기본 `["claude.ai"]`)에 있어야 한다. 성공 문구가 없어도 status 0이면 성공, 성공 문구가 있어도 status 1이면
  `verify_failed`. 출력이 JSON이 아니면 종료 코드만 본다.
- 실패 사유(`LoginReasonCodes`, 열린 어휘): `cli_missing`, `pty_unavailable`, `exited`(성공 문구 없이 0이 아닌 코드로
  끝남), `verify_failed`, `start_failed`. 로그아웃: `logout_failed`, `timeout`.
- 보안: 실행 인자는 설치자 설정에서만 온다. 하위 프로세스 환경은 실행과 같은 환경 정책 + `env_inherit`
  (`CLAUDE_CONFIG_DIR`·브라우저 열기 변수)만 물려주고 `env_clear`(`ANTHROPIC_API_KEY`·`ANTHROPIC_AUTH_TOKEN`·
  `CLAUDE_CODE_OAUTH_TOKEN`)는 늘 빈 값이다. 붙여 넣은 코드는 PTY가 에코하므로 드라이버가 `secrets_to_mask`로
  알리고 서비스가 화면 줄·문구·상세에서 가린다. 원시 출력은 세션 메모리에만 있고 로그에 남기지 않는다.
- 로그아웃: `logout_command`(기본 `claude auth logout`)를 PTY로 실행한다. 이 PC의 터미널 Claude Code도 로그아웃된다.

설치자 설정 `login`(`ClaudeSdkLoginOptions`, 전부 데이터 — **화면 글자 규칙의 위치는 `login.rules`**):

| 키 | 기본 | 의미 |
| --- | --- | --- |
| `enabled` | `true` | 끄면 능력을 선언하지 않는다(버튼 없음) |
| `command` · `status_command` · `logout_command` | `null` = [`find_claude_cli()`, `auth`, `login`·`status`·`logout`] | 실행 인자(요청으로 바꿀 수 없다). 실행 파일은 `readiness.cli_path` → SDK 번들 → PATH |
| `success_auth_methods` | `["claude.ai"]` | 성공으로 볼 `authMethod`(비우면 종료 코드만) |
| `rules` | `open_url: https://\S+/oauth/authorize\S*`, `needs_code: (?i)paste code`, `success: (?i)login successful`, `failure: (?i)(error\|failed)` | 신호마다 정규식 목록. `ac-safe-regex` 검사(위험하면 설정 오류) |
| `allowed_url_hosts` | `claude.ai`, `claude.com`, `console.anthropic.com`, `platform.claude.com` | `open_url`로 넘길 호스트(https, 하위 도메인 포함) |
| `on_success_keys` · `submit_keys` | `["enter"]` · `["enter"]` | 성공 문구 뒤·코드 뒤에 보낼 키 |
| `pty_size` | `{cols: 400, rows: 40}` | 긴 URL이 줄바꿈되지 않게 넓게 |
| `cwd` | `null` | 작업 폴더 |
| `env` · `env_inherit` · `env_clear` | `{TERM: xterm-256color}` · `CLAUDE_CONFIG_DIR`·`BROWSER`·`DISPLAY`·`WAYLAND_DISPLAY`·`XDG_*`·`WSL_*` · 키·토큰 변수 3개 | 하위 프로세스 환경 |
| `writes` | `${CLAUDE_CONFIG_DIR}/.credentials.json`, `~/.claude/.credentials.json` | 시작 확인 창에 보일 쓰기 경로(처음 풀리는 하나) |
| `status_timeout_s` · `logout_timeout_s` · `exit_wait_s` · `terminate_grace_s` | `20` · `20` · `10` · `2` | 시간(초) |
| `screen_lines` | `40` | 진행에 싣는 화면 줄 수 |
| `texts` | `ClaudeSdkLoginTexts` | 버튼·단계·사유·본인 책임 안내 문구 |

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

테스트(`tests/…_login_52r82.py`)는 실제 CLI를 부르지 않는다. 스텁 `tests/claude_cli_stub.py`를
`[sys.executable, stub, 시나리오, auth, login|status|logout]`로 주입하고 임시 `CLAUDE_CONFIG_DIR`에만 쓴다. 시나리오:
코드 붙여 넣기 성공 / 콜백 성공(코드 없이) / 코드 거부 / URL 없이 멈춤(취소·시간 초과) / 성공 문구 없이 종료 + status 0
/ 성공 문구 + status 1 / 취소 때 SIGTERM 무시(강제 종료). 하위 프로세스가 남지 않는지(`/proc/<pid>`), 키·토큰 변수가
빈 값인지, 코드 문자열(과 앞 5자)이 응답·로그에 없는지 확인한다.

#### 구독 로그인 수동 스모크(사람이 실제로 로그인해 보는 순서)

자동 테스트는 실제 로그인을 하지 않는다. 아래는 사람이 자기 계정으로 확인하는 순서다. **실제 `~/.claude` 로그인이
바뀐다**(터미널의 Claude Code도 같은 로그인을 쓴다). 실제 로그인을 건드리기 싫으면 빈 폴더를 `CLAUDE_CONFIG_DIR`로
주고 같은 셸에서 서버를 띄운다(그 폴더에만 쓴다).

```bash
export CLAUDE_CONFIG_DIR=$HOME/.cache/agent-console-login-smoke   # 선택: 실제 ~/.claude 대신
mkdir -p "$CLAUDE_CONFIG_DIR"
claude auth logout || true              # 시작 상태: 로그아웃(위 폴더를 쓰면 이미 비어 있다)
uv run agent-console serve --open       # 127.0.0.1:8765
```

1. 로그아웃 상태에서 설정 › 실행 백엔드의 Claude Agent SDK 카드가 "구독 로그인 정보를 찾지 못함"이고 **[구독으로
   로그인]**이 보인다 → 누르면 시작 확인 창(본인 책임 안내, 쓰기 경로 = `$CLAUDE_CONFIG_DIR/.credentials.json` 또는
   `~/.claude/.credentials.json`)이 뜬다. 이때 `ps -ef | grep "auth login"`에 하위 프로세스가 없다.
2. [로그인 시작] → 브라우저 창이 열리거나 [로그인 페이지 열기]로 연다 → 브라우저에서 로그인한다. WSL처럼 콜백이 닿지
   않으면 브라우저에 보이는 코드를 대화상자의 코드 칸에 붙여 넣고 [확인]을 누른다.
3. 대화상자가 "로그인됨 — Claude 구독"을 보이면 다른 터미널에서 같은 `CLAUDE_CONFIG_DIR`로 `claude auth status; echo $?`
   → JSON의 `authMethod`가 `claude.ai`이고 종료 코드 0이다.
4. 대화상자를 [닫기]로 닫고 카드의 [연결 테스트]를 누르면 통과한다(짧은 요청 한 번, 구독 사용량이 조금 든다).
5. 다시 [구독으로 로그인] → 진행 중에 [취소]를 누르면 "취소했습니다"이고 `ps`에 `auth login`이 남지 않는다. 시간
   초과는 설정 `modules.options.mod-runs.backend_login.timeout_s: 30`으로 줄여 두고 30초 기다려 확인한다(프로세스가
   남지 않는다).
6. 카드의 `…` › 로그아웃(연결 해제) → 확인 → 카드가 다시 "구독 로그인 정보를 찾지 못함"(`subscription_unverified`)
   이고 `claude auth status` 종료 코드가 1이다.

화면 문구가 맞지 않으면(CLI 버전 변화) 대화상자의 "CLI 화면 보기"로 화면을 보고 `login.rules`를 고친다. 판정은
`claude auth status`라 규칙이 틀려도 거짓 성공은 없다.

## 서브에이전트 (`AgentRequest.subagents`, X12 `sdk-subagents`)

`capabilities.subagents = true`. 위임 방식(nodes-core `sdk-subagents`)이 채운 `SubagentSpec` 목록을
`ClaudeAgentOptions.agents={이름: AgentDefinition}`로 바꾸고 위임 도구(`delegation_tool`, 기본 `Agent`)를
`tools`·`allowed_tools`에 더한다(설정 `disallowed_tools`에 있으면 더하지 않는다). 그 밖에 `subagent_env`
(기본: 깊이 1 `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=1`, 전경 실행 `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`,
기본 서브에이전트 끄기 `CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS=1`)를 넣는다.

| SubagentSpec | AgentDefinition |
| --- | --- |
| `name`(대상 노드 id) | `agents` 키 |
| `description` / `model` | `description` / `model` |
| `prompt` + 묶음 instructions(+ 파일 안내) | `prompt` |
| `tools` + 묶음 tools(금지 우선, 괄호 규칙은 이름만) | `tools`(둘 다 없으면 None = SDK 기본) |
| `disallowed_tools` + 묶음 금지 | `disallowedTools` |
| 묶음 mcp_servers | `mcpServers`(인라인) |
| `options` | 그 밖의 `AgentDefinition` 필드(예: `maxTurns`) |

대상별로 나눌 수 없는 묶음 칸(files 폴더, tools.commands)은 위임자 세션에 합치고 `log.warning`을 낸다.

**대상 도구 규칙과 위임자 사전 승인**: SDK 세션은 하나라 `allowed_tools`(사전 승인)가 위임자에게도 적용된다.
그래서 대상의 도구 규칙은 기본으로 위임자 `allowed_tools`에 넣지 않고(`subagent_tools_preapprove=false`),
위임자 사전 승인에 없는 대상 규칙이 있으면 `log.warning{details.not_preapproved}`을 낸다(묻지 않는 모드에서 대상
호출이 거부될 수 있음). `subagent_tools_preapprove=true`로 켜면 합치고, 넓힌 규칙을 `log.warning{details.added}`로
알린다. 어느 쪽이든 위임자의 가용 도구(`tools`)는 넓히지 않는다.
비밀 가림: 위임 도구 결과(알림 `text`)와 모든 미리보기(`task_preview`·`result_preview`)는 알려진 비밀 값·형식을
가린 뒤 낸다.

**이벤트 귀속**: 위임 도구 호출 입력의 `subagent_type`이 등록한 이름이면, `parent_tool_use_id`가 그 호출 id인
메시지에서 나온 이벤트를 `actor=SubagentSpec.actor`, `node_path=sink.child_path(name)`으로 낸다
(`BackendEventSink.child_path`, `NodeContext`가 구현). 순서는 fake 백엔드와 같다: 위임자 `agent.tool_call`
→ 대상 `agent.subagent_started{subagent_id, name, tool_use_id, task_type, task_preview}`(TaskStarted) →
대상 tool_call·tool_result·message → 대상 `agent.subagent_stopped{status, usage{total_tokens}, tool_uses,
duration_ms, result_preview}`(TaskNotification, 끝난 TaskUpdated) → 위임자 `agent.tool_result`.
Task 이벤트를 못 받은 위임은 실행 끝에 위임 도구 호출 id로 시작·종료 쌍을 만든다. 등록하지 않은 이름의 위임은
위임자에게 귀속한다. 서브에이전트 메시지의 사용량은 위임자 `agent.usage`에 더하지 않는다.

**결과 알림**: sink가 `SubagentResultListener`(`agent_console_runtime`에서 가져온다;
`on_subagent_result(name, *, text, status, actor, tool_use_id)`)면
위임 도구 결과마다(끝의 `agentId:` 줄 제거) 알린다. 위임 방식이 이것으로 대상 노드의 답변(`ctx.emit_replies`)을
낸다. 백엔드는 노드 포트 이름을 모르므로 답변을 직접 내지 않는다.

## 실행 묶음 (`AgentRequest.bundle`, §R12.5)

`capabilities.resource_slots = ["instructions", "files", "mcp_servers", "tools", "skills", "rules"]`(`RESOURCE_SLOTS`)
+ 설치자 `allow_command_hooks: true`일 때만 `hooks`. 꺼져 있으면 `slot_notes.hooks`(`HOOKS_DISABLED_NOTE`)로 이유를 알리고,
검증·묶음 미리보기에 `resource.slot_unsupported`(details.reason)가 나온다. `subagent_slots` = instructions·mcp_servers·tools·skills·rules.
칸 값 모양은 `packages/py/features/ac-resources-core/README.md`. 그 밖의 칸에 값이 있으면 `log.warning`만 낸다.

| 칸 | SDK |
| --- | --- |
| `instructions` | `Agent.system_prompt` + 지침들을 이어 붙인 `system_prompt`(`system_prompt_mode=claude_code_append`면 preset + append) |
| `files` | 노드가 쓴 파일 경로(`str` 또는 `{path, root?}`) → 폴더를 `add_dirs`와 실행 범위 허용 디렉터리에 더하고, 지침 끝에 파일 목록 안내(`files_notice`). 경로 없는 항목은 전달하지 않고 경고 |
| `mcp_servers` | `name` → `McpServerConfig`(설정 `mcp_servers` 위에 덮어씀, 같은 이름은 뒤가 이김). `env`·`headers`의 `secret://`는 주입한 `SecretResolver`로 풀고 raw·payload에서 가린다 |
| `tools` | 허용 합집합(`tools`·`allowed_tools`에 더함), 금지가 우선(`disallowed_tools`), `commands`는 실행 범위 명령 허용에 합집합(넓히면 `log.warning`) |
| `skills` | 노드가 쓴 트리 `{name, root, tree_root}`(`root = tree_root/skills/name`) → `plugins=[{type: local, path: tree_root}]`(플러그인 이름 = 폴더 이름 = 노드 id) + `skills=[skill_name_template]`(기본 `{plugin}:{skill}`) + `skill_tool`(기본 `Skill`)을 `tools`에. 서브에이전트는 `AgentDefinition.skills`, 플러그인 폴더는 세션에 함께 올리고 위임자 `skills`는 위임자 것만(없으면 `[]`) |
| `rules` | `rule_delivery=instructions`(기본): 항목 `instruction`(경로 머리말 + 본문)을 지침에. `files`: 항목 `root`(안에 `.claude/rules/<name>.md`)를 `add_dirs`에 + `rule_files_env`(기본 `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1`) |
| `hooks` | 설치자 `allow_command_hooks`가 켜졌을 때만. `hook_delivery=callback`(기본): 항목마다 `HookMatcher(matcher, [콜백], timeout)`를 `event` 아래 건다. 콜백은 **`ToolGuard.check_command`(limits.commands) 통과 후에만** 셸 없이 하위 프로세스(`hook_runner`, 기본 `subprocess_runner`)로 실행: stdin = hook 입력 JSON, stdout JSON = SDK에 그대로 돌려줌, 종료 코드 2 = `{"decision": "block", "reason": stderr}`, 그 밖 0 아님 = 막지 않는 오류. 환경 = 환경 정책이 허용하는 서버 변수 + `CLAUDE_PROJECT_DIR`(인증 키 등 명시 env는 넘기지 않음). 이벤트 `hook.started` → `hook.finished{event, matcher, command_preview(가림·200자), exit_code, duration_ms, decision, error?}`. `settings`: 실행 범위를 통과한 항목만 `settings` 인라인 JSON(`{"hooks": {event: [{matcher, hooks: [{type: command, command, timeout}]}]}}`)으로 — CLI가 직접 실행(이벤트는 관측 `hook.*`로만). 서브에이전트 hook은 세션에 합치고 경고 |

사용자 프로젝트(cwd)·`~/.claude`에는 쓰지 않는다. skill·규칙 파일은 agent 노드가 실행 폴더(`<workspace>/.state/runs/<run>/<node>/_bundle/<node>/`)에
쓴 것만 가리킨다. `setting_sources` 기본값(`["project"]`)은 skill 전달 때도 바꾸지 않는다.

### hook probe 감싸기 (4R.9, design §4R.7, F-16)

유효 관측 설정 `observe.hook_probe`가 `true`이면(기본 꺼짐) **이 백엔드가 전달하는** 명령형 hook(`hooks` 칸)을
`agent-console-hook-probe`로 감싸 실행한다. probe는 원래 명령을 그대로 돌리고(입출력·종료 코드 동일) 기록
`hook-probe/1`을 `AgentRequest.run_folder/<hook_probe_folder>/<세션>.jsonl`에 남긴다(로그 출처 `hook-probe-jsonl`이 읽음).

- callback 경로: `wrap_command(shlex 인자, out=…, probe=hook_probe_command, matcher, context=run_context)`(실행 형식).
  settings 경로: `wrap_command_line(명령 문자열, …)`(셸 형식 유지). 실행 범위 검사(`limits.commands`)는 **원래 명령**으로 한다.
- 맥락 `--context`는 `AgentRequest.run_context`(`run_id`·`node_path`)다. `hook.started`·`hook.finished` payload에 `hook_probe: true`.
- 감싸지 않는 경우(경고 `log.warning`): `run_folder`가 없음, `agent-console-hook-probe` 미설치. 꺼져 있으면 명령은 그대로다.
- 사용자 설정 파일(`~/.claude`)·`.claude` 내보내기(`ac-exports`)는 건드리지 않는다(원래 명령).
- 묶음 미리보기: 선택 훅 `ClaudeSdkBackend.preview_notes(effective, bundle)`(ac-teams `PreviewNotes`)가 켜져 있으면
  info `observe.hook_probe_wrapped`("hook 감싸기 켜짐", `details.hooks` = 감쌀 hook 수)를 낸다.

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

## 실행 중 상호작용: 되묻기·도구 승인 (§R14.8)

`capabilities.interactions = ["question", "tool_permission"]`. 종류 이름은 연결표 데이터라 설치자 설정
`interaction_kinds{question, tool_permission}`으로 바꿀 수 있다(엔진은 이름을 모른다).

- **열 수 있는 조건**: sink가 `InteractivePort`(`request_input`, `NodeContext`가 구현)이고 `AgentRequest.interactions`
  (grant)에 그 종류가 있을 때만 연다. 그 밖의 묻는 요청은 `unmatched_permission`(기본 deny)으로 처리한다.
- **콜백 등록**: 권한 모드가 bypass가 아니고, `prompting_permission_modes`(기본 `default`·`acceptEdits`·`plan`)에
  들거나 grant가 있을 때 `can_use_tool`을 건다.
- **되묻기 도구**(`question_tool`, 기본 `AskUserQuestion`): 질문 grant가 있으면 `tools`에 더한다(사전 승인은 하지 않음).
  없으면 `disallowed_tools`에 넣는다.
- **순서**: 실행 범위(ToolGuard, 훅과 콜백 양쪽) → "이번 실행 동안 허용" 메모리 → 상호작용 → `unmatched_permission`.
  사용자가 허용해도 실행 범위는 우회되지 않는다.

| 콜백 | 상호작용 payload | 응답 → SDK |
| --- | --- | --- |
| `AskUserQuestion` | `question`: `{questions[{question, header?, options[{label, description?}], multi_select}]}` | `{answers, response?}` → `PermissionResultAllow(updated_input={…입력, answers, response?})`. 답이 없으면 거부 |
| 그 밖의 도구 | `tool_permission`: `{tool_name, input_preview, title?, display_name?, description?, blocked_path?, decision_reason?, tool_use_id?, agent_id?}`(컨텍스트에 있는 필드만) | `allow`(+`updated_input`) → Allow, `allow_for_run` → Allow + 이번 실행 메모리(도구 이름 + 정렬한 입력), `deny`(+`message`) → Deny |

- `input_preview`는 가린(scrub) 입력의 문자열 미리보기다. 원본 입력은 SDK로만 돌아간다.
- 요청의 `title`·`message`도 가린 뒤 연다.
- 허용 응답의 `updated_input`(질문은 answers를 합친 입력)도 실행 범위(ToolGuard)로 다시 검사한다. 벗어나면 입력 값 없는
  문구로 거부한다. `allow_for_run` 메모리 키는 실제로 허용한 최종 입력이다.
- Run 취소로 닫히면(`reason=cancelled`) `PermissionResultDeny(interrupt=True)`. 만료면 엔진이 준 `expire_response`를
  응답으로 해석하고, 해석할 수 없으면 거부한다.
- `updated_permissions`는 쓰지 않는다(사용자 프로젝트 `.claude/settings.local.json`에 쓰지 않기 위해).
- **서브에이전트 귀속**: `ToolPermissionContext.agent_id`를 TaskStarted의 task_id(또는 위임 도구 호출 id)와 맞춰
  `actor`·`node_path=sink.child_path(대상)`로 연다. 못 맞추면 위임자 요청이다. 서브에이전트의 되묻기는 열지 않는다
  (SDK에서 쓸 수 없음).
- **설정 검증 훅** `validate_settings(effective, grant)`: 묻는 모드인데 grant에 도구 승인 종류가 없으면
  `interaction.no_path` 경고(`details.kinds`에 필요한 종류). 묻는 모드는 `risky_option_warnings` 대상이 아니다
  (bypass 경고는 유지).
- 테스트 도우미: `testing.InteractiveSink`(응답 함수), `testing.PermissionCall`(가짜 클라이언트에서 콜백 호출).

## 사용량 한도

`RateLimitEvent` → `usage.rate_limit{window(rate_limit_type, 없으면 "unspecified"), status, utilization, resets_at,
overage_status}`. 값을 지어내지 않는다(없으면 null).

모델 호출 소요(design §5.5R.1 C2): `ResultMessage.duration_api_ms`(실행 전체의 모델 API 대기 합)를 마지막
`agent.usage`의 `duration_ms`로 싣는다. 값이 없거나 음수면 null이다.

## 설치자 설정 (`ConfigurableBackend` 훅)

`ClaudeSdkBackend.from_options(options, *, secrets, environ)` — ac-runtime `ConfigurableBackend` 구현. 서버는 설정
`backends.claude-agent-sdk`를 이 훅에 넘겨 entry point로(인자 없이) 만든 인스턴스를 교체한다. 키의 의미는 이 패키지만 안다.

| 키 | 기본 | 의미 |
| --- | --- | --- |
| `models` | `[]` | `list_models()` 목록(`ModelInfo`). 모델 id는 코드에 없다 |
| `env_policy` | `null`(= 기본 허용 목록) | 하위 프로세스 환경 상속(`EnvPolicy{inherit, allow}`) |
| `max_raw_chars` | `DEFAULT_MAX_RAW_CHARS` | 이벤트 raw 하나의 최대 JSON 길이 |
| `cancel_grace` | `5.0` | 취소 후 interrupt 대기(초) |
| `interaction_kinds` | `{question: question, tool_permission: tool_permission}` | 여는 상호작용 종류 id(`capabilities.interactions`) |
| `allow_command_hooks` | `false` | 명령형 hook(`hooks` 칸) 실행 허용. 꺼져 있으면 `hooks` 칸을 받지 않는다(경고에 이유) |
| `allow_subscription_auth` | `true` | 본인 구독 로그인 자격(`auth.mode=subscription`) 허용(기본 구독, 본인 책임 — API 키도 선택 가능). `false`로 끄면 검증 error `backend.subscription_auth_disabled`·실행 거부, 켜져 있으면 강화된 경고(§인증) |
| `hook_probe_command` | `null`(= `[현재 파이썬, -m, agent_console_hook_probe]`) | `observe.hook_probe`일 때 hook 명령을 감쌀 probe 실행 인자(아래 "hook probe 감싸기") |
| `hook_probe_folder` | `hook-probe` | 노드 실행 폴더 아래 기록 폴더 이름(경로 구분자 없는 이름) |
| `login` | `ClaudeSdkLoginOptions()`(켜짐) | 앱 화면 구독 로그인·로그아웃(§인증 "구독 로그인") |
| `readiness` | `ClaudeSdkReadinessOptions()` | 상태 점검·연결 테스트가 볼 인증 방식(`auth`), `cli_path`, `subscription_files`, `probe_prompt`·`probe_model`·`probe_extra_args`, 문구 `texts`(§인증 "상태 점검과 연결 테스트") |

`secrets`는 남은 `secret://` 해석과 raw 가리기에, `environ`은 환경 정책을 적용할 부모 환경으로 쓴다.
모르는 키·잘못된 값은 `ValueError`(위치와 사유만). 형식 모델: `ClaudeSdkInstallOptions`.

## 설정 (`Agent.backend_options`, 형식 `ClaudeSdkBackendOptions`)

기본값은 안전한 쪽: `permission_mode="dontAsk"`, `setting_sources=["project"]`(사용자 `~/.claude` 설정 격리,
`[]`면 파일 설정 전혀 없음), `strict_mcp_config=true`, `mcp_servers={}`, 도구를 정하지 않으면 내장 도구 없음.
그 밖에 `tools`(목록 또는 `"claude_code"`), `allowed_tools`(사전 승인 — **가용성 제한이 아님**), `disallowed_tools`,
`network_tools`, `command_input_keys`, `path_input_keys`, `unmatched_permission`, `system_prompt_mode`,
`include_partial_messages`, `max_turns`, `max_budget_usd`, `fallback_model`, `effort`, `add_dirs`, `env`, `cli_path`,
`sandbox`, `auth`, `forward_subagent_text`(기본 true), `delegation_tool`, `delegation_tool_names`, `subagent_env`,
`files_notice`, `prompting_permission_modes`, `question_tool`, `skill_tool`, `skill_name_template`, `rule_delivery`
(`instructions`|`files`), `rule_files_env`, `hook_delivery`(`callback`|`settings`), `hook_timeout_seconds`(기본 60), `sdk_options`(그 밖의 `ClaudeAgentOptions` 필드 이름 그대로, `cwd`·`hooks`·`can_use_tool`·`resume`·
`agents` 제외).
모델 id는 코드에 없다 — `Agent.model`. `list_models()`는 생성 인자 `models`(설정 데이터, 기본 빈 목록).

관측(`AgentRequest.observe` = 유효 `ObserveSettings`)은 아래 "관측 수집기(X7)"를 본다.

## 관측 수집기 (X7, `agent_console_backend_claude_sdk.collectors`, design §4R.3)

관측(hook·MCP 등)은 백엔드가 아니라 **수집기**가 한다. 백엔드는 수집기 이름을 모르고, 켜진 수집기에
SDK 훅 콜백(`on_hook`)과 SDK 메시지(`on_message`, 번역 이벤트 뒤)를 넘긴다. 수집기가 `ctx.emit`으로 낸
이벤트는 RunEvent 일반형으로 나간다(raw 정제, `parent_tool_use_id`로 서브에이전트 귀속).

- 기본 수집기(첫 구현, entry point `agent_console.collectors`로 등록):
  - `sdk-hooks`: SDK 관찰 훅 콜백 → `hook.invoked`(hook_type `sdk-callback`), CLI 설정 hook 실행
    (`include_hook_events`) → `hook.invoked|completed`(hook_type `settings`). 설정 `events`(콜백을 걸 훅
    이벤트, 기본 `DEFAULT_OBSERVED_HOOK_EVENTS`).
  - `mcp-calls`: `mcp.server_status`, `mcp.call_started|call_completed`(`duration_ms`는 주입 clock).
  - payload 키는 design §8.3 표 그대로다.
- 설정: `observe.collectors{id: {enabled?, config?}}`. 옛 키 `hooks`→`sdk-hooks.enabled`,
  `mcp`→`mcp-calls.enabled`, `hook_events`→`sdk-hooks.config.events`로 읽는다(대응표는 데이터
  `LEGACY_OBSERVE_KEYS`). 둘 다 있으면 `collectors`의 값 있는 칸이 이긴다(`config`는 통째로).
  정하지 않은 수집기는 꺼짐이다.
- 수집기 예외(설정 해석 포함)는 실행에 영향이 없다. 실행마다 수집기별 `log.warning` 하나
  (`details.collector`·`stage`·`error` 형식 이름, 예외 문장은 싣지 않음). 수집 이벤트를 내보내다 sink가
  실패해도 삼킨다. 훅 콜백은 항상 `{}`를 돌려준다.
- 검증(`validate_settings`): 이 백엔드에 없는 id → warning `observe.unknown_collector`, 설정이 수집기
  스키마와 다름 → warning `observe.collector_config_invalid`.
- 등록: `ClaudeSdkBackend(collectors=...)`(None = 기본 수집기), `from_options`는
  `discover_collectors()`로 entry point에서 찾는다(`descriptor.backend`가 백엔드 id와 같은 것만,
  보고서는 `collector_reports`). `BackendDescriptor.collectors`에 디스크립터가 실린다.

새 수집기는 `BaseClaudeSdkCollector`를 상속해 필요한 메서드만 고치고 entry point 하나로 등록한다.

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

## 실행 범위(§4.7)와 `capabilities.enforce`

- `commands: true` — 모든 도구 호출(서브에이전트 포함)에 거는 `PreToolUse` 훅이 입력의 명령 키를
  `limits.commands`로 검사(빈 목록 = 전부 거부, `"*"` = 전부 허용, 셸 연결·치환·리다이렉트 거부, 토큰 접두 일치).
  MCP 서버가 내부에서 실행하는 명령은 대상이 아니다.
- `directories: false` — 파일 도구의 경로 입력만 검사(최선 노력). 허용된 명령이 건드리는 파일은 막지 못한다.
- `network: false` — 네트워크가 allow가 아니면 `network_tools`를 끌 뿐, MCP·서버 측 도구·허용 명령의 통신은 못 막는다.

## 하위 프로세스 환경과 한계

- **환경 상속**: SDK(0.2.166)는 서버의 `os.environ` 전체를 CLI 하위 프로세스에 물려주며 끄는 옵션이 없다.
  이 백엔드는 생성 인자 `env_policy`(`EnvPolicy`, 기본 `inherit="allowlist"`)로 허용 목록(`DEFAULT_ENV_ALLOW`:
  PATH·HOME·LANG·LC_*·TMPDIR/TEMP/TMP·SystemRoot 등 OS 필수 키와 `CLAUDE_CONFIG_DIR`, 설정 데이터로 교체 가능) 밖의 키를
  **빈 값으로 덮어쓴다**. 값은 넘어가지 않지만 키 이름은 남는다. `inherit="all"`은 실행마다 `log.warning`을 낸다.
  API 키는 서버 환경에서 물려받지 말고 `backend_options.env`(`secret://…`)로 명시한다.
- **운영 지침**: `limits.commands`에 `env`, `printenv`, `set`, `cat`, `python`, `node`, `sh` 등 환경·파일을 읽거나
  임의 코드를 실행하는 명령을 넣지 않는다. 명시 `env` 값은 에이전트 프로세스 안에서는 읽힐 수 있다.
- **안전 기본값을 뒤집는 설정**: `setting_sources`(`["user"]` 등), `strict_mcp_config=false`, `permission_mode`·
  `sdk_options`(예: `permission_mode="bypassPermissions"`)로 기본값을 바꿀 수 있다. 이런 값은 막지 않고 실행 시작 때
  `log.warning` 이벤트를 낸다(`risky_option_warnings`). 권한 우회 모드에서는 Claude Code 권한 규칙과
  `can_use_tool`이 꺼지지만, 이 백엔드의 `PreToolUse` 실행 범위 검사(명령 + 파일 도구 경로)는 유지된다.

## 플랫폼 도구 (`AgentRequest.host_tools`, 5R.10, design §5R.6)

`capabilities.host_tools = true`. 위임 방식(예: 독립 위임 `host`)이 만든 `HostTool`(ac-runtime, 런타임 전용)을
in-process SDK MCP 서버 하나로 묶어 모델에게 준다. 백엔드는 도구 이름·용도를 모른다.

- 서버: `create_sdk_mcp_server(name=<backend_options.host_tool_server>, tools=[tool(name, description, input_schema)(handler)])`
  → `ClaudeAgentOptions.mcp_servers[<서버>]`. 서버 이름 기본값은 옵션 스키마 기본값 `agent-console`(`DEFAULT_HOST_TOOL_SERVER`),
  `[A-Za-z0-9_-]`만, `__` 금지. 설정 `mcp_servers`·묶음 MCP 서버와 이름이 겹치면 실행 전 `validation_failed`.
- 이름 규칙: 모델이 부르는 이름 = `mcp__<서버>__<도구>`(`host_tool_rule`). 이 이름을 `allowed_tools`(사전 승인)에
  넣는다(`disallowed_tools`에 있으면 빼고 금지가 이긴다). 도구 이름은 `[A-Za-z0-9_-]`, 요청 안에서 유일(겹치면 실행 전 오류).
  전체 이름이 64자(`MODEL_TOOL_NAME_LIMIT`)를 넘으면 `log.warning`.
- 입력 스키마: 최상위 object 모양으로 맞춰 넘긴다(`object_input_schema` — `type`·`properties`가 없으면 SDK가 스키마를
  "이름 → 파이썬 타입" 표로 읽기 때문). 스키마 검사(예: 대상 enum)는 SDK가 핸들러 전에 하고 위반은 오류 결과다.
- 호출: `agent_console_runtime.call_host_tool` — 핸들러 예외는 오류 결과(예외 형식 이름만, 메시지 없음), `HostToolResult.is_error`는
  MCP `isError`, 실행 취소 토큰이 취소되면 진행 중 핸들러를 취소하고 오류 결과를 돌려준다.
- 관측: 모델의 호출은 다른 MCP 도구처럼 `agent.tool_call`/`agent.tool_result`이고, 수집기 `mcp-calls`가 켜져 있으면
  `mcp.call_started`/`mcp.call_completed{server, tool, is_error, duration_ms}`로 남는다(백엔드에 특별 경로 없음).
- `sdk_options.mcp_servers`·`sdk_options.allowed_tools`는 위 값을 통째로 덮어쓰므로 `log.warning`을 낸다.
- 서버 생성기는 생성자 `tool_server_factory`(기본 `sdk_tool_server`)로 바꿀 수 있다.

설치 SDK 확인(2026-10-18, `claude-agent-sdk 0.2.166`, 실제 import):

| API | 확인한 시그니처 |
| --- | --- |
| `claude_agent_sdk.create_sdk_mcp_server` | `(name: str, version: str = '1.0.0', tools: list[SdkMcpTool[Any]] \| None = None) -> McpSdkServerConfig` (`{"type": "sdk", "name", "instance"}`) |
| `claude_agent_sdk.tool` | `(name: str, description: str, input_schema: type \| dict[str, Any], annotations: ToolAnnotations \| None = None)` → 데코레이터 → `SdkMcpTool` |
| 핸들러 | `async (args: dict) -> {"content": [{"type": "text", "text"}], "is_error": bool}`. 알 수 없는 도구·스키마 위반·핸들러 예외는 SDK가 `isError` 결과로 바꾼다 |

`test_installed_sdk_has_in_process_mcp_api`가 이 존재를 확인한다. 테스트 도우미 `testing.SdkToolCall`·`call_sdk_mcp_tool`은 CLI처럼
JSON-RPC(`initialize` → `tools/call`)로 in-process 서버를 부른다(SDK 내부 `claude_agent_sdk._internal.sdk_mcp_bridge` 사용 — SDK가
바뀌면 이 도우미만 고친다). 실호출 확인 항목은 아래 21~26.

SDK 핸들러는 입력만 받아(MCP 요청의 `_meta`도 넘기지 않음) 도구 호출 id를 모른다. 그래서 위임 도구가 부른 대상
NodeRun의 `tool_use_id`(design §5.5R.1 C7)는 이 백엔드에서 null이다.

## 미확인 SDK 동작 (실호출 스모크로 확인할 항목)

1. 위임자 사용량(`ResultMessage.usage`·`agent.usage`)에 서브에이전트 토큰이 포함되는지. 포함되면 ac-usage에 이중 집계 방지 규칙이 필요하다.
2. 전경 실행에서 `TaskStartedMessage`·`TaskNotificationMessage`가 나오는지, `tool_use_id`가 채워지는지. 못 받으면 실행 끝에 위임 도구 호출 id로 시작·종료 쌍을 만든다.
3. 위임 도구 결과의 `agentId:` 형식(별도 텍스트 블록인지 마지막 줄인지). 둘 다 제거하게 했다.
4. `forward_subagent_text`가 실제로 서브에이전트 텍스트 블록을 넘기는지.
5. 서브에이전트 도구 가용성: 세션 `tools`에 없는 내장 도구를 대상 `AgentDefinition.tools`만으로 쓸 수 있는지, 위임자 세션 사전 승인(`allowed_tools`) 없이 묻지 않는 모드에서 대상 호출이 허용되는지(기본은 사전 승인에 넣지 않고 경고, `subagent_tools_preapprove`로 켬).
6. 환경변수 3개(`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH`, `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`, `CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS`)가 설치 CLI 버전에서 동작하는지.
7. 빈 `ANTHROPIC_API_KEY=""`를 CLI가 "설정 안 됨"으로 보는지, `setting_sources`에 `user`가 없어도 구독 로그인 자격을 읽는지.
8. `RateLimitEvent.utilization`이 경고 임계 전에는 비어 있는지(§R4.3).

skill·rule·hook 전달(2R.12) 미확인 항목(실호출 스모크 C1에서 확인, 단위 테스트는 가짜 SDK 클라이언트):
15. `plugins=[{type: local, path}]`로 넘긴 매니페스트 없는 폴더의 `skills/<name>/SKILL.md`가 skill로 잡히는지, 이름이
    `<폴더 이름>:<skill>`인지(문서: 매니페스트 선택, `--plugin-dir`면 폴더 이름이 플러그인 이름). 아니면 `skill_name_template`을 바꾼다.
16. `tools`를 목록으로 줄 때 `Skill` 도구를 넣어야 skill을 쓸 수 있는지(`skills` 옵션은 `allowed_tools`만 채운다).
17. `skills=[]`가 위임자 목록에서 서브에이전트 skill을 숨기면서 `AgentDefinition.skills`로 대상에는 보이는지.
18. `rule_delivery=files`: `--add-dir` + `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1`이 추가 폴더의 `.claude/rules/*.md`를 읽는지
    (문서상 예), `paths` 조건이 추가 폴더 기준인지 프로젝트 기준인지(프로젝트 경로와 맞지 않으면 조건부 규칙이 안 걸릴 수 있음). 이 환경변수는
    다른 추가 폴더(limits.directories·files 폴더)의 CLAUDE.md도 읽게 한다.
19. `hook_delivery=settings`: `settings` 인라인 JSON의 명령형 hook이 실행되는지, `setting_sources=["project"]`와 함께 쓰일 때 우선순위.
20. 콜백의 `{"decision": "block", "reason"}`이 모든 이벤트에서 막기로 처리되는지(PreToolUse는 `permissionDecision`이 권장 형식),
    SDK `HookEvent`에 없는 이벤트 이름을 `hooks`에 넣었을 때 CLI 동작.

플랫폼 도구(5R.10, design §R3.7 9) 미확인 항목(2R.C1 보류 목록, 단위 테스트는 SDK 목):
21. `type: sdk` 서버가 `strict_mcp_config=true`·`setting_sources=["project"]`에서도 붙는지(init `mcp_servers` 상태).
22. `allowed_tools`의 `mcp__<서버>__<도구>`가 `dontAsk`에서 묻지 않고 허용되는지, `tools` 목록을 줘도 MCP 도구가 보이는지.
23. 전체 도구 이름이 64자를 넘을 때 CLI 동작(지금은 경고만).
24. interrupt 때 CLI가 진행 중 도구 호출을 `notifications/cancelled`로 끊는지(백엔드는 실행 취소 토큰으로 따로 멈춘다).
25. 같은 턴의 병렬 도구 호출이 핸들러를 동시에 부르는지(같은 대상 직렬은 엔진 몫).
26. 오래 걸리는 핸들러(대상 실행 수 분)가 CLI의 MCP 도구 시간 제한(`MCP_TOOL_TIMEOUT` 등)에 걸리는지. 걸리면 `env`로 늘린다.

상호작용(1R.30) 미확인 항목(스모크 `test_live_question_once`·`test_live_tool_permission_once`):
9. `ClaudeSDKClient` + 항상 있는 `PreToolUse` 훅으로 `can_use_tool` 스트림이 유지되는지.
10. 설치 버전(0.2.166)의 `ToolPermissionContext` 필드가 실제로 채워지는지(`title`·`display_name` 등).
11. `agent_id`가 `TaskStartedMessage.task_id`와 같은 값인지.
12. Python에서 AskUserQuestion이 콜백 완료 전에 빈 답으로 진행되는 버그가 있는지.
13. `dontAsk`·`auto` 모드에서 콜백이 불리는지(grant가 있으면 등록은 하지만 불리지 않을 수 있다).
14. 결과 없이 끊긴 도구 호출이 세션 기록에 남았을 때 `resume` 동작.

## 개발·재사용(단독)

이 폴더는 독립 프로젝트다(design §3R.2). 폴더만 복사해도 아래 명령이 그대로 돈다. 사내 의존은 이름 + 버전
범위로 선언돼 있으므로, 저장소 밖에서는 휠 모음(저장소에서 `uv run poe wheels` → `dist/wheelhouse`)을
찾기 경로로 준다(`uv sync --find-links <wheelhouse>`). 저장소 안 검사: `uv run poe portability --package ac-backend-claude-sdk`.

```bash
uv sync                  # dev 그룹(pytest·mypy·ruff, 테스트가 쓰는 사내 패키지) 포함
uv run ruff check . && uv run mypy && uv run pytest
```

단독 설치(이 폴더만 복사, `portability`)에서는 `tests/test_agent_console_backend_claude_sdk_qa_1r29.py`의 2건이
**skip**("기본 상호작용 종류가 설치되어 있지 않음")된다. 이 검사는 어댑터가 여는 payload·응답을 entry point
`agent_console.interaction_kinds`로 등록된 `question`·`tool_permission` 종류 스키마와 맞춰 보는데, 그 종류는
`agent-console-nodes-core`가 등록하고 이 패키지는 그것에 의존하지 않기 때문이다(백엔드는 노드 종류를 모른다).
저장소 워크스페이스에서는 nodes-core가 함께 설치되어 두 건이 실행된다. 실제 호출 테스트(`-k live`)는
`AGENT_CONSOLE_CLAUDE_SDK_LIVE=1`일 때만 돈다.

## 테스트

```bash
uv run pytest packages/py/features/ac-backend-claude-sdk/tests
AGENT_CONSOLE_CLAUDE_SDK_LIVE=1 uv run pytest packages/py/features/ac-backend-claude-sdk/tests -k live -s   # 실제 호출(opt-in, 서브에이전트 1회 포함)
```
