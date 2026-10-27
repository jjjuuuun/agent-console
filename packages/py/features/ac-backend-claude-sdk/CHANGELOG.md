# 변경 기록

## 미출시

- 5.2R.82(F14 구독 로그인): 선택 능력 `start_login`·`logout`(`capabilities.login/logout`, `login_methods = [cli-login]`).
  `claude auth login`을 PTY로 중계하고 `claude auth status` 종료 코드 + `authMethod`로 판정한다. 앱은 토큰을 받거나
  저장하지 않는다. 설치자 설정 `login`(`ClaudeSdkLoginOptions`, 기본 켜짐, 화면 글자 규칙 `login.rules`), 상태 점검
  `actions`(로그인 파일 없음 = 주 버튼 login, 있음 = 다시 로그인·로그아웃). 새 의존 `agent-console-secret-rules`(규칙
  안전 검사), 선택 추가 기능 `login` = `agent-console-pty-session`(없으면 능력 없음 + 상태 `detail` 안내).
- 5.2R.94(잔해 정리): **공개 API 삭제** — `SubagentResultListener` 재내보내기를 뺐다. 정의가 있는
  `agent_console_runtime`에서 import한다(`from agent_console_runtime import SubagentResultListener`). 동작은 같다.
- 5.2R.94b(잔해 정리 S-04): **공개 API 삭제** — 참조가 없던 `CollectorRun.active_ids` 프로퍼티를 뺐다.
  켜진 수집기 목록은 `collector_reports`·`BackendDescriptor.collectors`로 본다.
- 5.2R.79(F13, 사용자 지시 "기본값은 구독형"): **기본은 구독(본인 책임), API 키도 선택 가능.** **동작 변경**:
  설치자 옵션 `allow_subscription_auth` 기본값 `false` → `true`, `ClaudeSdkAuth.mode` 기본값 `api_key` → `subscription`
  (`auth: {}`는 구독), 상태 점검 `readiness.auth` 기본값 `{mode: api_key, api_key: secret://anthropic_api_key}` →
  `{mode: subscription}`. 구독일 때 검증 warning `backend.subscription_auth_enabled`와 실행마다 `log.warning`은 그대로다.
  `auth`를 아예 비우면(`null`) 예전처럼 `env`·환경 정책만 따른다(바꾸지 않음). API 키는 `auth: {mode: api_key, ...}`로
  고른다. 구독을 막으려면 `allow_subscription_auth: false`.

- 5.2R.68(ux-overhaul §15.8 F8): `capabilities.status = true`·`capabilities.probe = true`, 디스크립터 `probe_cost_note`(`PROBE_COST_NOTE`). 선택 메서드 `ClaudeSdkBackend.status`(정적 점검, 모델 호출 없음, 비밀은 이름 존재만)·`probe`(도구 없는 한 턴 호출, 실행 파일 없음·구독 꺼짐·키 없음이면 호출 없이 거부, 시간 상한, 사유 `auth_failed`·`network`·`timeout`·`error`·`cli_missing`·`auth_missing`·`backend.subscription_auth_disabled`). 설치자 설정 `readiness`(`ClaudeSdkReadinessOptions`: 점검할 `auth`(기본 `secret://anthropic_api_key`)·`cli_path`·`subscription_files`·`probe_prompt`·`probe_model`·`probe_extra_args`·`texts`). 생성 인자 `readiness`·`cli_locator`·`path_exists`. 부품 `assess_readiness`·`classify_probe_messages`·`classify_probe_error`·`find_claude_cli`·`expand_path`, 상수 `ReadinessStates`·`ProbeReasonCodes`·`PROBE_CATEGORIES`.
- 5R.10: `capabilities.host_tools = true`. `AgentRequest.host_tools`를 in-process SDK MCP 서버(`create_sdk_mcp_server`)로 주고 `mcp__<서버>__<도구>`를 `allowed_tools`에 넣는다. 옵션 `host_tool_server`(기본 `agent-console`), 생성자 `tool_server_factory`, 부품 `build_host_tool_server`·`HostToolMapping`·`host_tool_rule`·`sdk_tool_handler`·`sdk_tool_server`, 테스트 도우미 `testing.SdkToolCall`·`call_sdk_mcp_tool`.
- 4R.8(X7): 관측을 수집기 레지스트리로 옮겼다. 공개 하위 모듈 `collectors`(`ClaudeSdkCollector` 프로토콜,
  `CollectorContext`, `BaseClaudeSdkCollector`, 기본 수집기 `sdk-hooks`·`mcp-calls`, entry point 그룹
  `agent_console.collectors`, `discover_collectors`·`select_collectors`·`resolve_collector_settings`, `CollectorRun`).
  설정 `observe.collectors` 해석(옛 키 `hooks`·`mcp`·`hook_events` 호환, 둘 다 있으면 `collectors` 우선).
  낸 이벤트 type·payload 키는 같다. 수집기 예외는 수집기별 경고 하나로 격리. `validate_settings`가
  `observe.unknown_collector`·`observe.collector_config_invalid` warning을 낸다. `BackendDescriptor.collectors` 채움.
  생성 인자 `collectors`, 속성 `collector_reports`, 공개 이름 `COLLECTOR_ISSUES`. 새 의존 `agent-console-registry`.
  **공개 API 변경**: `MessageTranslator`에서 `observe_hooks`·`observe_mcp`·`clock` 인자를 뺐다(관측 이벤트는 수집기가
  낸다), `MessageTranslator.target_of` 추가. `CLAUDE_SDK_BACKEND_ID` 정의 위치를 `_options`로 옮겼다(공개 이름 동일).

- 3R.29(TM-2, E-13): 설치자 옵션 `allow_subscription_auth`(기본 `false`). 꺼져 있으면 `auth.mode=subscription`은
  설정 검증 error `backend.subscription_auth_disabled`이고 실행을 거부한다(**동작 변경**: 예전에는 경고만 내고 실행).
  켜져 있으면 강화된 경고 문장. 새 공개 이름 `AUTH_ISSUES`·`SUBSCRIPTION_AUTH_DISABLED_MESSAGE`·`SUBSCRIPTION_AUTH_WARNING`,
  `ClaudeSdkErrorCodes.SUBSCRIPTION_AUTH_DISABLED`.

## 0.1.0

- 독립 프로젝트로 정리(3R.3): 사내 의존을 이름 + 버전 범위로 선언, 패키지별 pytest·mypy·ruff 설정과 `dev` 의존 그룹, LICENSE·CHANGELOG 추가. 동작 변경 없음.
