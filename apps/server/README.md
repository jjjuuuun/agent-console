# agent-console-server

Agent Console 서버: 설정 로드 → 호스트 기본 서비스(레지스트리·DB·플러그인 로더, 확장 지점) → **모듈 조립(`agent-console-modkit`)**
(설치된 기능·연동 모듈 entry point) → FastAPI REST(`/api/v1`)·WebSocket(`/ws`). 서버는 모듈을 `assemble`에 넘기고 받은
라우터·WS 토픽·오류 맵을 붙이기만 한다. 기능 이름은 모른다.
웹은 기본적으로 **별도 프로세스**다(CORS + 토큰). `web.serve_static`(선택 기능, 기본 꺼짐)을 켜면 서버 하나가
웹 빌드까지 서빙한다(아래 "단일 실행").
비즈니스 로직(검증·실행·팀 의미·채팅·사용량·가져오기 규칙)은 각 패키지·모듈에 있고, 이 앱은 조립과 전송 계층만 맡는다.

## 설치

```bash
uv sync --all-packages          # 워크스페이스 안
uv pip install ./apps/server    # 단독
```

| 의존성 | 무엇을 | 왜 | 대안 |
| --- | --- | --- | --- |
| `fastapi` | REST·WS 라우팅, OpenAPI | Pydantic 계약 모델을 그대로 요청·응답 모델로 쓴다 | Starlette 단독 — OpenAPI·본문 검증을 직접 써야 한다 |
| `uvicorn` | ASGI 서버 | FastAPI 표준 실행기, WS 지원 | hypercorn |
| `websockets` | uvicorn WS 구현 | uvicorn 기본 WS 백엔드 | wsproto |
| `ruamel-yaml` | `agent-console.yaml` 읽기(safe 로더) | store와 같은 라이브러리 | PyYAML |
| `pydantic`·`starlette` | 설정 모델·미들웨어 | 서버가 직접 import하므로 직접 의존으로 선언한다 | — |
| 직접 쓰는 Agent Console 패키지 | `agent-console-contracts`·`registry`·`secret-rules`·`modkit[host]` | 계약 모델, 레지스트리, 비밀 규칙, 모듈 조립·보안 미들웨어·호스트 확장 지점 | — |
| 설치만 하는 플러그인 | `agent-console-resources-core`·`nodes-core`·`delegation-host`·`backend-claude-sdk[login]`·`backend-fake-agent`, 로그 출처 `logs-claude`·`hook-probe` | 기본 리소스 종류·노드·위임 방식·실행 백엔드(구독 로그인 PTY 포함)·로그 출처. 서버는 import하지 않고 entry point로만 들어온다 | — |
| 기능·연동 모듈 | `agent-console-mod-{definitions,resources,runs,chat,usage,imports,exports,versions,logs,projects}`, `agent-console-link-{definitions-resources,definitions-teams,exports-teams,runs-teams,runs-trace,runs-usage,chat-runs,logs-runs,logs-trace,logs-usage,projects-runs}` | 설치 의존으로만 둔다. 서버는 import하지 않고 entry point `agent_console.server_modules`로 조립한다(import-linter). 필요 없는 모듈은 설치에서 빼거나 설정으로 끈다 | — |
| `httpx`(dev) | `TestClient` | FastAPI 테스트 클라이언트 요구 | — |

CORS는 Starlette `CORSMiddleware` 대신 보안 미들웨어 안에서 처리한다: preflight도 Host 검사를 먼저 통과해야 하고,
보안 검사가 낸 오류 응답(401·403·413)에도 허용 출처 헤더가 붙어야 웹이 읽을 수 있기 때문이다.

## 최소 사용 예

```python
from agent_console_server import create_app, load_settings, serve

settings = load_settings()  # agent-console.yaml + AGENT_CONSOLE_* 환경변수
app = create_app(settings)  # ASGI 앱(구성 요소는 lifespan에서 조립)
serve(settings)  # uvicorn 실행(막힘)
```

```bash
python -m agent_console_server --config agent-console.yaml --port 8765 --disable-module mod-exports
```

명령행은 `main(argv, *, prog=, modules=)` 하나다. `python -m agent_console_server`와 `agent-console serve`(apps/cli)가
같은 옵션을 쓴다: `--config/-c`·`--host`·`--port`·`--workspace`·`--allow-origin ORIGIN`(여러 번, 설정의
`security.allowed_origins` 뒤에 덧붙임, `merge_origins`)·`--open/--no-open`·`--enable-module`·`--disable-module`, 그리고
설치된 모듈이 `SettingsCompat.flags`로 선언한 옵션(지금 기본 모듈에는 없다). 설정 오류는 표준 오류에 `<prog>: …`를 쓰고 종료 코드 2.

서버는 빈 워크스페이스로 시작한다. 에이전트·팀 구성은 사용자가 만들거나 가져오기(`mod-imports`)로 들인다.

## 모듈 조립

`create_app`은 entry point `agent_console.server_modules`로 설치된 모듈(`installed_modules()`, 테스트는
`create_app(modules=[...])`)을 `agent_console_modkit.assemble(modules, settings.modules)`로 조립한다. **서버는 기능 이름을
모른다**(import-linter "서버 앱은 modkit과 기반만" + `tests/test_agent_console_server_assembly.py`).
모듈 라우터는 연동 모듈 먼저 붙인다(고정 하위 경로가 기능 모듈의 매개변수 경로에 가리지 않게).

호스트 기본 서비스도 설치된 패키지가 modkit 확장 지점으로 알린 것을 쓴다: 레지스트리 묶음 공장
(`agent_console.host_registries`)·플러그인 로더(`agent_console.host_plugin_loaders`) → `load_host_plugins`, DB 공장
(`agent_console.host_database`) → `open_host_database`, 비밀 해석(환경변수 `secrets.env_prefix` → 묶음의 비밀 공급자) →
`secret_resolver`. 지운 설정 키·모듈 환경변수·모듈 명령행 옵션은 모듈의 `settings_compat` 선언으로 다룬다
(`settings_compat()`·`flag_overrides()`). `GET /health`는 모듈 시작 훅이 끝난 뒤에만 200이다(그 전·종료 뒤 503 `not_ready`).

설치된 모듈(entry point `agent_console.server_modules`, 웹 역할은 `/modules`의 `web_roles`). 패키지는 `packages/py/modules/`·`packages/py/links/`에 있고, 각 모듈 설정은 `modules.options.<모듈 id>`(키는 각 모듈 README)다.

### 기능 모듈

| 모듈 id | 패키지 | 경로·WS | web_roles | 필수 포트 | 선택 포트 | 제공 포트 |
| --- | --- | --- | --- | --- | --- | --- |
| `mod-chat` | `ac-mod-chat` | `/conversations…`(대화·턴·메시지·대기열), WS `conversation:` | `conversations` | — | `chat.turn_launcher`·`chat.runs`·`chat.run_events`·`chat.interactions`·`chat.turn_sessions`·`definitions.lookup`·`workspace.settings` | `chat.conversations`·`server.warnings`(multi) |
| `mod-definitions` | `ac-mod-definitions` | `/agents`·`/graphs`(CRUD·복제)·`/settings`, 토픽 `definitions.saved` | `definitions:agent`·`definitions:graph`·`settings` | — | `definitions.checks`(multi)·`graphs.validation`·`graphs.entry_labels` | `definitions.store`·`definitions.lookup`·`workspace.settings`·`secrets.rules`·`definitions.checks`(multi)·`server.warnings`(multi) |
| `mod-exports` | `ac-mod-exports` | `/exporters`, `/exports/*` | `exports` | `definitions.lookup` | `exports.dependencies`·`secrets.rules` | — |
| `mod-imports` | `ac-mod-imports` | `/resources/import/*` | `imports` | `definitions.store` | `secrets.rules` | — |
| `mod-logs` | `ac-mod-logs` | `/logs…`(출처·분류기·수집·이벤트·세션·타임라인·집계·handoff·분류 체계·대시보드 템플릿·스키마), WS `logs` | `logs` | — | `logs.sources`(multi)·`workspace.settings`·`secrets.rules`·`logs.source_defaults`(multi) | `logs.query`·`logs.ingest`·`server.warnings`(multi) |
| `mod-projects` | `ac-mod-projects` | `/projects…`(CRUD·옮기기 계획·옮기기·범위 검사·삭제 계획) | `projects` | — | `definitions.lookup`·`definitions.store`·`definitions.references`(multi) | `projects.lookup`·`definitions.checks`(multi) |
| `mod-resources` | `ac-mod-resources` | `/resources…`(CRUD·본문·파일)·`/resource-types`·`/merge-strategies` | `definitions:resource` | `definitions.store` | `definitions.usages` | `resources.lookup`·`resources.types` |
| `mod-runs` | `ac-mod-runs` | `/runs…`·`/interactions`·디스크립터(`/node-types`·`/edge-types`·`/backends`·`/delegation-strategies`·`/interaction-kinds`)·`/agents/{id}/activity`·이어 가기·백엔드 상태·로그인(`backend_login`), WS `run:`·`interactions` | `runs` | `definitions.lookup` | `runs.preparers`(multi)·`runs.services`(multi)·`runs.scopes`(multi)·`runs.resume_handlers`(multi)·`workspace.settings`·`secrets.rules` | `runs.starter`·`runs.reader`·`runs.events`·`interactions.port`·`secrets.redact`·`server.warnings`(multi)·`server.attributes`(multi) |
| `mod-usage` | `ac-mod-usage` | `/usage`(`?parts=`), `/usage/sources` | `usage` | — | `usage.event_query`·`usage.token_rollups`·`workspace.settings`·`usage.sources`(multi) | `usage.service`·`server.warnings`(multi)·`definitions.checks`(multi) |
| `mod-versions` | `ac-mod-versions` | `{컬렉션}/versions…` | `versions` | `definitions.store` | `definitions.checks`(multi)·`secrets.rules` | — |

### 연동 모듈

| 모듈 id | 패키지 | 경로·WS | web_roles | 필수 포트 | 선택 포트 | 제공 포트 |
| --- | --- | --- | --- | --- | --- | --- |
| `link-chat-runs` | `ac-link-chat-runs` | — | `conversations:runs` | `chat.conversations`·`runs.starter`·`runs.reader`·`runs.events` | `interactions.port` | `chat.turn_launcher`·`chat.runs`·`chat.run_events`·`chat.interactions`·`chat.turn_sessions`·`runs.resume_handlers`(multi) |
| `link-definitions-resources` | `ac-link-definitions-resources` | — | — | `definitions.lookup`·`resources.types` | `resources.lookup`·`secrets.rules` | `definitions.checks`(multi) |
| `link-definitions-teams` | `ac-link-definitions-teams` | 사용처·유효 설정·실행 계획·묶음 미리보기 | `definitions:teams` | `definitions.lookup` | `workspace.settings`·`resources.lookup`·`resources.types`·`secrets.redact`·`secrets.rules`·`settings.scope_layers`(multi) | `graphs.entry_labels`·`definitions.usages`·`definitions.dependencies`·`definitions.references`(multi) |
| `link-exports-teams` | `ac-link-exports-teams` | — | — | `definitions.lookup` | `workspace.settings` | `exports.dependencies` |
| `link-logs-runs` | `ac-link-logs-runs` | `GET /runs/{id}/logs` | `logs:runs` | `logs.ingest`·`logs.query`·`runs.reader`·`runs.events` | — | `logs.sources`(multi) |
| `link-logs-trace` | `ac-link-logs-trace` | `GET /logs/sessions/{session}/trace` | `logs:trace` | `logs.query` | — | — |
| `link-logs-usage` | `ac-link-logs-usage` | — | — | `logs.query`·`usage.service` | `logs.ingest` | `usage.sources`(multi)·`logs.source_defaults`(multi) |
| `link-projects-runs` | `ac-link-projects-runs` | — | — | `projects.lookup` | — | `runs.scopes`(multi)·`settings.scope_layers`(multi) |
| `link-runs-teams` | `ac-link-runs-teams` | `POST /graphs/{id}/validate` | `runs:team-rules` | `runs.starter`·`definitions.lookup` | `workspace.settings`·`resources.lookup`·`resources.types`·`definitions.checks`(multi) | `runs.preparers`(multi)·`runs.services`(multi)·`graphs.validation` |
| `link-runs-trace` | `ac-link-runs-trace` | `/runs/{id}/trace`·`/runs/handoffs` | `runs:trace` | `runs.reader`·`runs.events` | `definitions.lookup` | — |
| `link-runs-usage` | `ac-link-runs-usage` | — | `usage:tokens` | `runs.reader`·`runs.events` | — | `usage.event_query`·`usage.token_rollups` |

- 모르는 WS 토픽을 구독하면 `error{reason: unknown_topic}`이다.
- 모듈 하나 끄기 매트릭스: `tests/test_agent_console_server_module_matrix.py`(설치된 모듈 전부 × 시작·상태·나머지 API·404).
- `link-chat-runs`를 끄면(또는 `mod-runs`가 없으면) 대화 목록·만들기·대기열은 동작하고 메시지 전송만 409
  `feature_unavailable{module: mod-chat, port: chat.turn_launcher}`다. 정의 모듈이 없으면 대화 만들기가 409
  (`port: definitions.lookup`). `mod-chat`을 끄면 대화 경로 404, `link-chat-runs`는 `unsatisfied`.
- `GET /server-info`는 호스트 경로다. 경고는 `server.warnings`(평문 점검·`team.rules_unavailable`·저장소 메모리 경고 등), 속성은
  `server.attributes`(`recovered_runs`)를 모은다.
- `mod-definitions`를 끄면 정의 포트가 없어 `mod-imports`·`mod-exports`·`mod-versions`·`mod-resources`·
  `mod-runs`·`link-*`는 `unsatisfied`, `mod-usage`는 외부 출처만으로 동작한다(토큰 집계 `[]`). `mod-chat`은 켜진 채로
  대화 목록만 보인다.
- `mod-runs`를 끄면 실행 경로·디스크립터가 404, `link-runs-*`·`link-chat-runs`는 `unsatisfied`, 정의 CRUD·대화 목록은
  그대로다.
- `mod-projects`를 끄면 `/projects…`가 404, `link-projects-runs`는 `unsatisfied`(실행의 `project_id` 기록·거르기는 그대로, 프로젝트
  층(작업 폴더·설정)만 빠진다). `mod-logs`를 끄면 `/logs…` 404, `link-logs-*`는 `unsatisfied`.
- 연동을 끄면: `link-definitions-resources` → 리소스 검사 없이 저장, `link-definitions-teams` → 해당 경로 404·목록 입구 이름·
  사용 수 null, `link-exports-teams` → 의존 자동 포함 없이 고른 항목만 내보내기, `link-runs-teams` → 엔진 검증만으로 실행
  (`team.rules_unavailable` 경고, 노드 서비스도 없어 에이전트 노드는 `agent.lookup_unavailable`), 검증 경로 404·목록 검증
  요약 null, `link-runs-trace` → 흐름·넘김 경로 404, `link-runs-usage` → 토큰 집계 `[]`, `link-logs-runs` → 로그에 플랫폼 실행이
  없고 `/runs/{id}/logs` 404, `link-logs-trace` → 세션 흐름 경로 404, `link-logs-usage` → 사용량 출처 `local-logs` 없음.
- 플러그인 레지스트리(노드·연결·백엔드·리소스 종류·사용량 출처·가져오기 출처·내보내기 형식 …)는 호스트가 `create_app`에서
  **한 번** 로드해(`agent_console_modkit.load_host_plugins` — 로더는 각 모듈 패키지가 entry point로 준다) 모든 모듈에 기본
  서비스 `registries`로 넘긴다.

- 호스트 경로(모듈과 상관없이 항상): `GET /health`, `GET /bootstrap`, `GET /modules`(`ModuleInfo[]`, 토큰 불필요),
  `GET /server-info`, `/ws` 다중화,
  보안 미들웨어, 정적 서빙(선택).
- 켜고 끄기: 설치자 설정 `modules{enabled, disabled, bindings, options}`, 명령행 `--enable-module ID`·`--disable-module ID`
  (`apply_module_flags`, 설정보다 우선, 같은 id면 끄기가 이김). 꺼진 모듈의 경로는 등록되지 않는다(404).
- 상태: `active | disabled | unsatisfied | failed | conflict`(`module_info`가 modkit `ModuleReport` → 계약 `ModuleInfo`).
  `ModuleInfo.requires` = 필수 + 선택 포트.
- 켜진 모듈 안에서 선택 포트가 없어 꺼진 동작은 모듈이 `raise ctx.unavailable(PORT)`(modkit `FeatureUnavailableError`)를 던지고,
  서버가 409 `feature_unavailable`, `details = FeatureUnavailableDetails{module, port}`로 바꾼다.
- 시작 훅 실패는 서버 기동 실패다(`Assembly.start(fail_fast=True)`, 이미 시작한 모듈은 역순 정리).
- 기능 예외 → 계약 오류 변환: 모듈은 자기 `error_map`(modkit `ErrorReply`로 `details`·헤더 포함)을 쓴다. 앱 수준
  `register_error_handlers`에는 공통 처리기(저장소·엔진 오류 등)가 있고, 같은 예외 형식이면 앱 수준
  처리기가 이긴다(같은 계약 본문). 대화 오류(`ChatError`)는 `mod-chat`의 오류 맵만 처리한다.

## 조립 순서와 종료

앱 생성(`create_app`): 레지스트리(노드·연결·백엔드·위임 방식·상호작용 종류 = `load_registries`, 비밀 공급자,
리소스 종류 플러그인 + `<workspace>/resource-types/*.yaml`, 사용량 출처, 가져오기 출처, 내보내기 형식, `plugins.modules`) →
모듈 조립(build). 로딩 보고는 `GET /server-info`의 `plugins`.

시작(lifespan, 조립 순서대로 모듈 시작 훅): `mod-definitions`(legacy 계보·평문 점검) → … → `mod-runs` — **이전 프로세스의
미종료 Run 정리**(`recover_unfinished_runs`: Run `interrupted`, 대기 상호작용 `expired(interrupted)`, 모듈 안에서 가장 먼저) →
백엔드 설치자 설정(`from_options`) → `mod-chat`(대화·대기열 저장소 = 호스트 DB 핸들, 실행 연결 `ChatService.connect`) →
`link-chat-runs`(채팅 대기열 재시작 정책 `chat.queue_after_restart`). 그 밖의 기능 모듈 — `mod-versions`(보존 개수 전체 적용),
`mod-usage` 배경 작업(관측값 정리).

종료(역순): `link-chat-runs`가 대기열 꺼내기를 멈추고 `runs.starter.shutdown()`(실행 중 Run을 끊김으로 정리, 시간 한도
`modules.options.mod-runs.runtime.shutdown_timeout` — 넘으면 남은 Run을 강제 취소하고 정리 기록까지 기다림)을 **먼저**
기다린 뒤 `mod-chat`이 채팅 감시를 정리한다. `mod-runs` 종료 훅은 같은 정리를 다시 기다리기만 한다(한 번만 정리). DB
핸들은 호스트가 마지막에 닫는다.

실행 시작(`POST /runs`, 채팅 턴 공통 = `mod-runs`의 `RunService.start_run`): 엔진 그래프 검증 → 실행 전 준비자
(`runs.preparers` — `link-runs-teams`가 `ac-teams.team_rules_apply`이면 `validate_team`, 같은 뜻은 `merge_validation`으로 뺌) →
차단 이슈(`blocks_run`)가 있으면 거부 → 준비자 `prepare`(`prepare_run` — grant·상호작용 설정) →
`GraphRuntime.start(conversation_id=, services=노드 서비스(+ 대화 턴이면 SESSIONS), interaction_grants=, interaction_settings=)`.
준비자가 없으면(`link-runs-teams` 꺼짐) 엔진 검증만으로 실행하고 `GET /server-info`에 `team.rules_unavailable` 경고가 나온다.
노드 서비스(`runs.services`, `link-runs-teams`): `AGENT_LOOKUP`, `WORKSPACE_SETTINGS`, `WORKING_DIRECTORY`,
`RESOURCE_LOOKUP`(`resources.lookup` 포트), `RUN_FILES_ROOT = <workspace>/.state/runs`, `DEFAULT_BACKEND`.
`plugins.modules`는 플러그인 로더 뒤에 같은 묶음으로 로드해(`load_host_plugins`) 각 레지스트리 검사기와 `plugins.enabled`를
거친다(꺼진 key는 `disabled`).

## REST (`/api/v1`)

| 영역 | 경로 |
| --- | --- |
| 준비 신호 | `GET /api/v1/health` → `HealthResponse{status:"ok", server_version, contracts_version}`(토큰 불필요, 비밀 없음. 200이면 요청을 받을 준비가 된 것) |
| 모듈 | `GET /modules` → `ModuleInfo[]`(id 순, 토큰 불필요, 비밀 없음) |
| 부트스트랩·정보(호스트) | `GET /bootstrap`, `GET /server-info`(경고 = 모듈의 `server.warnings`, 속성 = 바인딩·출처 + 모듈의 `server.attributes`(`recovered_runs` 등)) |
| 디스크립터(`mod-runs`, 리소스 종류·병합은 `mod-resources`) | `GET /node-types`, `POST /node-types/{id}/ports`, `GET /edge-types`, `GET /backends`, `GET /backends/{id}/models`, `GET /delegation-strategies`, `GET /interaction-kinds`, `GET /resource-types`, `GET /merge-strategies` |
| 에이전트 | `GET/POST /agents`, `GET/PUT/DELETE /agents/{id}`, `GET /agents/{id}/usages`, `GET /agents/{id}/effective-settings`, `GET /agents/{id}/activity?limit=`(RunEvent[], 최신순) |
| 팀 구성 | `GET /graphs?validate=`(요약마다 `validation{blocks_run, error_count, warning_count, codes}`, 워크스페이스 개정별 캐시, `validate=false`면 null), `POST /graphs`, `GET/PUT/DELETE /graphs/{id}`, `POST /graphs/{id}/duplicate {id,name}`(201 VersionedGraph, 409), `POST /graphs/{id}/validate`(`link-runs-teams`), `GET /graphs/{id}/plan`(TeamPlanSummary), `GET /graphs/{id}/nodes/{node}/effective-settings`, `GET /graphs/{id}/nodes/{node}/bundle-preview`(BundlePreview{bundle, warnings}) |
| 팀 구성 초안(저장 안 함) | `POST /graphs/plan {graph}`(TeamPlanSummary), `POST /graphs/effective-settings {graph, node_id}`(EffectiveSettings), `POST /graphs/bundle-preview {graph, node_id}`(BundlePreview). 비밀 가림은 저장본 경로와 같다 |
| 실행(`mod-runs`, 흐름·넘김은 `link-runs-trace`) | `POST /runs`, `GET /runs?graph_id=&conversation_id=&agent_id=&status=&limit=`, `GET /runs/handoffs`(같은 필터), `GET /runs/{id}`, `POST /runs/{id}/cancel`, `GET /runs/{id}/events?actor=&type_prefix=&since_seq=`, `GET /runs/{id}/trace`, `GET /runs/{id}/resume-options`, `POST /runs/{id}/resume` |
| 상호작용(`mod-runs`) | `GET /interactions?status=&conversation_id=&limit=`(최신순), `GET /runs/{id}/interactions`, `POST /runs/{run}/interactions/{id}/respond {response}`(200·404·409 `interaction_closed`·422) |
| 채팅 | `GET/POST /conversations`, `GET/PATCH/DELETE /conversations/{id}`, `GET /conversations/{id}/turns?before=<run_id>&limit=`, `POST /conversations/{id}/messages`(202 Run 또는 `{queued: true, id, position, text}`, 409 `conversation_busy`), `GET /conversations/{id}/queue`, `DELETE /conversations/{id}/queue/{queued_id}`(204) |
| 리소스 | `GET /resources?type=`, `POST /resources`, `GET/PUT/DELETE /resources/{id}`(ETag, PUT은 If-Match 필수), `GET /resources/{id}/usages`, `GET/PUT /resources/{id}/content`(텍스트 본문 + ETag, If-Match, 412면 현재 ETag) |
| 리소스 여러 파일 | `GET /resources/{id}/files`(ResourceFile[] 경로 순), `GET /resources/{id}/files/{path}`(내용 + ETag, 텍스트 형식이면 `text/plain` 그 밖 `application/octet-stream`), `PUT …/files/{path}`(본문 = 바이트)·`DELETE …/files/{path}` — If-Match = 리소스 `version_hash`(없음 428·다름 412), 응답 = 정의 원문 + 새 ETag. 쓰기는 종류 디스크립터 `content.multi_file`일 때만(아니면 422 `resource.not_multi_file`). 경로 규칙 위반 400, 총량 한도(`modules.options.mod-definitions.max_content_bytes`) 초과 413 |
| 가져오기(`mod-imports`) | `GET /resources/import/sources`, `POST /resources/import/preview {source}`(후보 + `warnings`: 링크라서 건너뜀 `import.skipped_link` 등), `POST /resources/import {source, items}` — 원본 읽기만 |
| 내보내기(`mod-exports`) | `GET /exporters`(ExporterDescriptor[]), `POST /exports/plan`(ExportRequest → ExportPlan, 쓰기 없음, `root`·`subdir`를 주면 그 폴더 기준 create·skip·conflict), `POST /exports/archive`(zip 응답 `application/zip` + `Content-Disposition`, 디스크에 쓰지 않음), `GET /exports/roots`(**토큰 필수**, ExportRootInfo[], 비면 폴더 쓰기 꺼짐, `modules.options.mod-exports.expose_paths=false`(생략하면 `security.expose_paths` 값)면 path 빈 문자열), `POST /exports/write`(ExportWriteRequest → ExportResult, `on_conflict` 기본 fail → 409 `already_exists` `details.paths`). 형식 없음·루트 없음·정의 없음 404, 종류·옵션·경로 잘못 422(`details.issues`, path = 요청 기준 `/items/0/kind`·`/options/…`·`/subdir`), 형식이 error 경고를 내면 archive·write 422 |
| 사용량(`mod-usage`) | `GET /usage?parts=windows,tokens`(생략 = 전부, 요청하지 않은 부분은 null, `windows`만이면 실행 기록을 읽지 않음), `GET /usage/sources` |
| 설정 | `GET/PUT /settings` |
| 버전(종류 공통, `mod-versions`) | `{컬렉션}` = `/agents/{id}`·`/graphs/{id}`·`/resources/{id}`·`/settings`(표는 설정 데이터 `modules.options.mod-versions.collections`): `GET {컬렉션}/versions`, `GET …/versions/{hash}`(content = 원문), `GET …/versions/{a}/diff[/{b}]`(DefinitionDiff, b 생략 = 현재, 비밀 위치 `secret:true`·값 `***`, 본문은 sha256만 `content_changes`), `GET …/versions/{hash}/files[/{path}]`(본문 스냅샷 없으면 404, 내용은 텍스트면 `text/plain` 그 밖 `application/octet-stream`), `POST …/versions/{hash}/restore {message?}`(새 버전 저장, 정의가 있으면 If-Match 필수 428/412, 지운 정의는 없이 되살림, 저장 전 검사 동일 → 422, 응답 DefinitionVersion + ETag, 기본 메시지 `restored from <hash>`) |

- 고정 경로(`/runs/handoffs`, 연동 모듈)는 `{id}` 경로(기능 모듈)보다 먼저 맞는다: 호스트가 연동 모듈 라우터를 먼저
  붙인다(`agent_console_modkit.host.include_routers`). `/resources/import/*`(모듈 라우터)는
  리소스 `{id}` 경로와 메서드·깊이가 겹치지 않는다.
- 4xx는 모두 `ErrorResponse{error{code, message, details}}`. 422는 `details.issues`. 412는 `ETag` 헤더에 현재 버전.
- **정의 응답은 저장 원문**이다(에이전트·팀 구성·리소스·설정의 GET·POST·PUT, 에이전트 목록, `VersionedGraph.graph`).
  생략한 키는 응답에도 없고, 명시한 null·빈 목록·기본값과 같은 값은 그대로 있다("생략 = 상속").
  기본값·출처를 채운 값은 `.../effective-settings`가 준다. `GET /settings`는 파일이 없으면 `{}`(ETag 없음).
  GET 결과를 그대로 PUT해도 파일이 불어나지 않는다. `response_model`은 OpenAPI 문서용으로만 남는다.
- **리소스 저장 전 검사**: `POST /resources`·`PUT /resources/{id}`는 종류 검사(`agent_console_resources.validate_resource`)에
  error 이슈(예: `resource.plain_secret` — MCP `env`·`headers`의 평문 값)가 있으면 422 `validation_failed`로 거부한다.
  `details.issues[].path`는 리소스 문서 기준 JSON Pointer(`/config/env/API_KEY`), 메시지에는 값이 없다. 모르는 종류는 막지 않는다.
  이 검사는 `link-definitions-resources`가 포트 `definitions.checks`로 주는 `DefinitionChecker`다.
- **첨부 덮어쓰기 검사**: 에이전트(`POST/PUT /agents`), 팀 구성(`POST/PUT /graphs` — 팀 층·노드 층·리소스 연결),
  공통 설정(`PUT /settings` — `agent_defaults`)을 저장할 때 리소스 첨부의 `config_override`를 리소스 config에 얕게
  덮어 종류 검사를 한다(`ac-teams.attachment_issues`). error면 422 `validation_failed`, path는 첨부 위치 기준
  (`/resources/0/config_override/env/API_KEY`). `ref` 리소스가 없으면 스키마를 모르므로 비밀 의심 규칙
  (`ac-secret-rules`, ac-imports와 같은 규칙 + 설정 `secrets.extra_*`)으로 보고 걸리면 422 `resource.override_secret_suspected`,
  아니면 warning만 내고 저장한다
  (`link-definitions-resources`의 `DefinitionChecker` 하나가 REST·버전 되돌리기 공통).
- **표시용 가리기**: `GET .../effective-settings`(에이전트·노드)와 `GET .../bundle-preview`는 리소스 종류 config 스키마의
  `x-secret` 위치에서 `secret://`가 아닌 값을 `***`로 바꿔 보낸다(검사 전에 저장된 데이터의 안전망).
- **비밀 규칙**: `mod-definitions`(`WorkspaceState`·`SecretRuleCheck`·`PlainSecretScan`)가 조립한다(로직은 `ac-secret-rules`).
  - 공통 설정 `secrets.extra_key_names`·`extra_value_patterns`는 기본 규칙에 **더하기만** 한다. 패턴은 `ac-safe-regex`
    검사 — 위험·잘못된 정규식이면 `PUT /settings` 422(`secret.invalid_rule`, path `/secrets/extra_value_patterns/<i>`).
  - `secrets.redact_suspected_in_logs`(기본 true): 런타임 `SecretResolver(extra_redact=)`로 실행 기록(이벤트·Run·NodeRun)·
    상호작용 저장 직전 의심 값을 `[REDACTED]`로 가린다. false면 원문(디버깅용). 설정은 Run 시작 때 반영된다.
  - 평문 점검: 시작 시와 `GET /server-info`(캐시)에서 리소스·에이전트·팀 구성·설정을 훑어 `warnings`에
    `secret.plain_found`(warning, `details{kind, id}`, path = 정의 문서 기준, 값 없음)를 낸다. 저장 검사의 평문 이슈
    (`resource.plain_secret`·`resource.override_secret_suspected`)와 문서 전체 의심 판정을 합친다. 캐시는 정의가
    새 버전으로 저장될 때(토픽 `definitions.saved` — 모든 모듈의 쓰기 포함)와 삭제될 때 버린다.
    원문 GET은 가리지 않는다.
  - 선언형 리소스 종류는 스키마 `x-secret: true` 위치의 평문이 일반 규칙으로 거부된다(`resource.plain_secret`).
- 채팅 대기열은 `mod-chat`이 서버 DB(표 `chat_queue`)에 저장한다. 서버를 다시 시작하면 `link-chat-runs`가 워크스페이스 설정
  `chat.queue_after_restart`대로 처리한다. DB가 없으면 메모리에 두고 `chat.storage_memory` 경고를 낸다.

## WebSocket `/ws?token=`

토픽: `run:<id>`(`mod-runs`, `since_seq` 재생 → 실시간), `conversation:<id>`(`mod-chat`, 구독 직후 현재 요약 + `conversation.updated`),
`interactions`(`mod-runs`, 구독 직후 대기 목록을 `interaction.updated`로 하나씩, 이후 변화마다). 토픽은 켜진 모듈이 정한다
(모르는 토픽은 `error{reason: unknown_topic}`). 모르는 메시지 종류는 `error{code: bad_request}`.

## 공개 API

| 이름 | 설명 |
| --- | --- |
| `load_settings(config_path=None, *, environ=None, cwd=None, overrides=None, compat=None) -> ServerSettings` | 우선순위: overrides(명령행) > 환경변수 > 설정 파일 > 기본값. `compat` = 모듈 설정 호환 선언(None이면 설치된 모듈). `ConfigError`(값은 메시지에 넣지 않음) |
| `settings_compat(modules=None)`, `SETTINGS_COMPAT_CONTEXT` | 모듈의 `SettingsCompat` 모음(`ServerSettings.model_validate(..., context={SETTINGS_COMPAT_CONTEXT: …})`) |
| `flag_overrides(values, compat=None)` | 모듈이 선언한 명령행 옵션 값(`{"echo-tag": [...]}`) → 설정 덮어쓰기. 선언한 모듈이 없으면 `ConfigError` |
| `create_app(settings=None, *, environ=None, token=None, modules=None) -> FastAPI` | `environ` = 비밀 공급자·백엔드·모듈(가져오기 HOME 등)이 읽을 환경(기본 `os.environ`). `modules` = 조립할 모듈(None이면 설치된 entry point). `app.state.assembly` = 조립 결과 |
| `installed_modules(group=MODULES_GROUP) -> list[Module]` | entry point로 설치된 서버 모듈(읽기 실패는 경고 로그) |
| `apply_module_flags(settings, *, enable=(), disable=()) -> ServerSettings` | `--enable-module`·`--disable-module` 적용 사본 |
| `module_info(report) -> ModuleInfo` | modkit 보고 → 계약 모델 |
| `serve(settings=None, *, environ=None, token=None, opener=None)` | uvicorn 실행. 토큰은 로그에 남기지 않는다. 준비되면 준비 줄을 남기고 `web.open.enabled`면 `opener(url)`(없으면 `build_opener(web.open)`) |
| `build_opener(web_open, *, browser=None, spawn=None) -> Opener` | `web.open.command`가 있으면 그 명령(셸 없이, `{url}` 치환), 없으면 기본 브라우저(`webbrowser.open`). 브라우저·하위 프로세스 주입 |
| `RemovedKey`, `SETTINGS_REMOVED_KEY`, `ConfigError.code`·`ConfigError.removed` | 지운 옛 키가 남아 있으면 `load_settings`가 `ConfigError(code="settings.removed_key", removed=[RemovedKey{old, new, message}])`를 낸다. 메시지에 이유·새 위치를 적는다. 지운 키는 모듈 선언(`SettingsCompat.removed`)에서만 온다 |
| `build_openapi(app)` | OpenAPI 문서(컴포넌트 = 계약 JSON Schema `$defs`) |
| `QueryRedactingFilter`, `install_log_redaction` | 로그의 비밀성 쿼리 값 가리기 |
| `SecurityPolicy`, `TOKEN_HEADER`, `TOKEN_QUERY`, `WS_CLOSE_UNAUTHORIZED`(4401), `WS_CLOSE_FORBIDDEN`(4403), `API_PREFIX`, `WS_PATH` | 보안·경로 상수(보안 미들웨어·토큰·`/health`·WS 다중화·로그 가림은 `agent-console-modkit[host]`에서 온다) |

## 설정 파일 `agent-console.yaml`

찾는 순서: `--config`/`load_settings(path)` → `AGENT_CONSOLE_CONFIG` → 현재 폴더의 `agent-console.yaml`. 상대 경로는 설정 파일 폴더(없으면 현재 폴더) 기준.

```yaml
host: 127.0.0.1               # 루프백이 아니면 security.allow_remote: true 필요
port: 8765
workspace: .agent-console      # 정의 YAML 폴더(선언형 리소스 종류는 <workspace>/resource-types)
database: null                 # 기본 <workspace>/.state/console.sqlite3
log_level: info
plugins:
  enabled: null                # entry point 이름 목록(모든 그룹 공통). null = 설치된 것 전부
  modules: []                  # 설치 안 한 플러그인 `pkg.mod:attr`(register(registries))
security:
  token: null                  # 비우면 시작마다 무작위
  allow_remote: false
  allowed_hosts: []            # 추가 Host(루프백 + 바인딩 포트는 항상 허용)
  allowed_origins: []          # CORS·bootstrap 허용 출처(예: http://localhost:5173 — 웹 개발 서버)
  expose_paths: true           # false면 GET /server-info에서 workspace 절대 경로를 뺀다(내보내기 루트 경로의 기본값도 됨)
  max_request_bytes: 1048576
  max_ws_message_bytes: 1048576
  max_ws_subscriptions: 256
secrets: {env_prefix: "", min_redact_chars: 4}   # 비밀 해석(호스트 기본 서비스). min_redact_chars는 mod-runs 기본값으로도 넘어간다
web:
  serve_static: false          # 선택 기능. 켜면 웹 빌드 폴더를 SPA로 서빙(단일 실행)
  static_dir: null             # 웹 빌드 폴더(예: apps/web/dist). 비우면 패키지 포함 빌드
  open:
    enabled: false             # 준비되면 웹 화면을 연다(serve --open/--no-open이 덮어씀)
    url: null                  # 열 주소({host}·{port} 치환). 비우면 serve_static일 때 서버 주소
    command: null              # 브라우저 대신 실행할 명령(예: [msedge, "--app={url}"])
    wait_seconds: 30           # 준비 신호를 기다리는 최대 초
modules:                       # 서버 모듈 켜고 끄기(웹에서는 읽기 전용, serve --enable-module/--disable-module이 우선)
  enabled: null                # null = 설치된 모듈 전부. 목록이면 그것만
  disabled: []                 # enabled 뒤에 끈다(예: [mod-usage])
  bindings: {}                 # 같은 포트를 여러 모듈이 줄 때 고른 모듈 {포트: 모듈 id}
  options:                     # 모듈 id → 그 모듈 설정(각 모듈 settings_schema로 검증, 키는 각 모듈 README)
    mod-usage:
      retention_seconds: 2592000   # 사용량 관측값 보존(초). null = 지우지 않음
      prune_interval_seconds: 3600
      rollup_run_limit: 500        # GET /usage 토큰 집계에 쓰는 최근 Run 수
      source_timeout_seconds: 10
    mod-imports:
      home: null               # ~/.claude의 부모. 비우면 환경변수 HOME·USERPROFILE
      project_dir: null        # 프로젝트 .claude/·.mcp.json 위치. 비우면 설정 파일 폴더(작업 폴더를 따라가지 않는다)
      options: {}              # 출처 공장 이름 → 옵션(예: claude: {mapping: {...}})
    mod-exports:
      roots: []                # 폴더 쓰기 허용 루트 [{id, label, path}]. 비우면 보관 파일(zip)만
      home: null               # protected_in_home 기준 홈. 비우면 HOME·USERPROFILE
      protected_in_home: [.claude] # 홈 기준 쓰기 금지 폴더(루트로 등록해도 이 안에는 쓰지 않는다)
      protected: []            # 그 밖의 쓰기 금지 폴더
      options: {}              # 형식 이름 → 공장 옵션(예: claude-dir: {mapping: {...}, layout: {...}})
      expose_paths: true       # GET /exports/roots에 절대 경로를 보일지
    mod-versions:
      max_per_definition: null # 정의마다 남길 버전 수(null = 모두, D3). 저장할 때와 시작할 때 적용
    mod-definitions:
      max_content_bytes: 10485760  # 정의 하나(리소스 등)의 본문 파일 총량 한도(바이트, null = 무제한). 넘으면 413
    mod-runs:
      working_directory: null  # 에이전트 작업 폴더(WORKING_DIRECTORY 서비스). 기본 base_dir
      run_files_dir: runs      # 실행 묶음 파일 폴더(상태 폴더 기준)
      runtime: {max_concurrency: null, cancel_grace: 2.0, event_queue_size: 10000, shutdown_timeout: 10.0}
      show_hidden_backends: false  # 개발·테스트용 백엔드(디스크립터 ui_hints.hidden, 예: fake-agent)의 숨김 풀기. 환경변수 AGENT_CONSOLE_SHOW_HIDDEN_BACKENDS
      backends:                # 백엔드 id → 그 백엔드의 from_options 훅에 넘길 값(키는 각 백엔드 README)
        claude-agent-sdk: {models: [], allow_command_hooks: false, allow_subscription_auth: true}  # 구독 기본(본인 책임)
        fake-agent: {models: [], echo_hooks: false}
      backend_login: {enabled: true, timeout_s: 300}  # 앱 화면 백엔드 로그인(아래 "백엔드 로그인")
```

**지운 키**: 모듈 설정은 `modules.options.<모듈 id>`에만 둔다. 최상위 `usage`·`imports`·`exports`·`versions`·`resources`·
`runtime`·`backends`·`working_directory` 같은 키는 읽지 않는다. 남아 있으면 서버가 시작하지 않고 새 위치를 알려 주는
설정 오류(`settings.removed_key`, 예: `usage: 설정 키 usage는 더 이상 읽지 않습니다. modules.options.mod-usage로 옮기세요`)를 낸다.
지운 키 목록은 각 모듈이 `SettingsCompat.removed`(`RemovedSetting(old, new=...)`)로 선언한다 — 서버에 표가 없다.
다른 설정의 값을 기본값으로 넘기는 것은 호스트 설정에서만 한다(경고 없음, 새 위치에 값이 없을 때만):
`security.expose_paths: false` → `mod-exports.expose_paths`, `secrets.min_redact_chars` → `mod-runs.min_redact_chars`.
모듈끼리는 기본값을 주고받지 않는다(H3): `mod-imports.project_dir`는 생략하면 호스트 `paths.base_dir`(설정 파일 폴더)이고
`mod-runs.working_directory`를 따라가지 않는다. `mod-exports.home`도 `mod-imports.home`을 따라가지 않는다(생략 시 HOME·USERPROFILE).
환경변수 `WORKING_DIRECTORY`·`MAX_CONCURRENCY`는 새 위치(`modules.options.mod-runs.*`)로 들어간다.

삭제된 프리셋 기능의 설정(최상위 `presets`, `modules.options.mod-presets`)이 남아 있으면 "프리셋 기능은 삭제되었습니다" 설정
오류(`settings.removed_key`, `mod-definitions`가 선언)로 시작하지 않는다. 그 밖에 모르는 키(예: 옛 `console`)는 일반 설정
오류다(호스트 설정은 `extra="forbid"`).
워크스페이스 `settings.yaml`에 남은 `console`·`default_entry`는 사용자 데이터라 모르는 키로 그대로 보존한다(오류 없음).

환경변수(`AGENT_CONSOLE_` 접두어, 빈 값은 무시): `CONFIG`, `HOST`, `PORT`, `WORKSPACE`, `DATABASE`, `WORKING_DIRECTORY`, `LOG_LEVEL`, `TOKEN`, `WEB_DIR`, `MAX_CONCURRENCY`, `SECRET_ENV_PREFIX`, 불리언(1/true/yes/on) `ALLOW_REMOTE`·`SERVE_STATIC`·`OPEN`, 쉼표 목록 `PLUGINS_ENABLED`, `PLUGIN_MODULES`, `ALLOWED_HOSTS`, `ALLOWED_ORIGINS`(`WORKING_DIRECTORY`·`MAX_CONCURRENCY`는
그것을 선언한 모듈의 `modules.options.<id>`로 들어간다 — 모듈의 `settings_compat` 선언).

## 단일 실행: 서버 하나로 API·WS·웹

웹 빌드를 서버가 함께 서빙하면 같은 출처가 되어 `allowed_origins`·CORS 설정이 필요 없다. 기본은 꺼짐이고, 꺼 두면 서버는 웹을 몰라도 동작한다.

```bash
pnpm --filter @agent-console/web build                     # apps/web/dist 생성(코드를 받을 때마다)
AGENT_CONSOLE_SERVE_STATIC=1 AGENT_CONSOLE_WEB_DIR=apps/web/dist \
  uv run agent-console serve --open                        # http://localhost:8765/ 를 연다
```

같은 내용을 설정 파일로 두려면 `web: {serve_static: true, static_dir: apps/web/dist, open: {enabled: true}}`.

정적 폴더 경로 기준: `web.static_dir`과 `AGENT_CONSOLE_WEB_DIR`의 **상대 경로는 설정 파일이 있는 폴더 기준**이다(설정 파일이
없으면 `serve`를 띄운 현재 폴더). 환경변수로 준 값도 같은 기준이라, 저장소 밖 설정 파일(`--config ~/console/agent-console.yaml`)과
`AGENT_CONSOLE_WEB_DIR=apps/web/dist`를 함께 쓰면 `~/console/apps/web/dist`를 찾는다. 위치가 헷갈리면 **절대 경로**를 쓴다.
폴더가 없으면 패키지에 포함된 빌드를, 그것도 없으면 안내 페이지를 보여 준다.
설치한 PWA 창이나 다른 브라우저로 열려면 `web.open.command`(예: `[msedge, "--app={url}"]`), 별도 웹 서버 주소를 열려면 `web.open.url`.

- 준비 신호: 스크립트·바로가기·데스크톱 셸은 `GET /api/v1/health`가 200이 될 때까지 기다린다. 서버 로그에도 `준비됨: <URL>` 줄이 남는다(포트 0이면 실제 포트).
- 열기는 준비 뒤에 한 번만 한다. 열 주소가 없거나(정적 서빙 꺼짐 + `url` 없음) 열기에 실패하면 경고만 남기고 서버는 계속 돈다.
- `/api/…`·`/ws`는 정적 서빙이 가로채지 않는다(모르는 API 경로는 JSON 404). 빌드가 없으면 안내 페이지를 보여 준다.

## 백엔드 로그인 (`mod-runs`)

앱 화면에서 실행 백엔드에 로그인·로그아웃한다(기본 켜짐). 기본 백엔드 `claude-agent-sdk`는 `claude auth login`을 PTY 하위 프로세스로
띄워 로그인 주소·코드 입력을 화면으로 중계한다. 로그인 자격은 Claude Code CLI가 자기 위치에 쓰고 **서버는 토큰을 받거나 저장하지
않는다.** 입력한 코드는 응답·로그·오류에 남지 않는다. 로그인 능력이 없는 백엔드에는 경로가 409다.

- 경로: `POST /backends/{id}/login`(201 세션), `GET /backends/login/current`, `GET /backends/login/{sid}`(폴링 = 하트비트),
  `POST /backends/login/{sid}/input`, `DELETE /backends/login/{sid}`(취소), `POST /backends/{id}/logout`. 상태 점검은
  `GET /backends/status`·`GET /backends/{id}/status`, 연결 테스트는 `POST /backends/{id}/probe`.
- 설정 `modules.options.mod-runs.backend_login`: `enabled`(기본 true, 끄면 경로 없음), `timeout_s`·`timeout_max_s`(300·900),
  `heartbeat_s`(30), `retain_s`(60), `screen_max_lines`(40). 실행 인자·화면 글자 규칙은 백엔드 설치자 설정
  (`backends.claude-agent-sdk.login`, 키는 `ac-backend-claude-sdk` README "구독 로그인")에 있다.

## 보안

- 기본 바인딩 127.0.0.1. 다른 주소는 `security.allow_remote: true`일 때만.
- Host: 루프백 이름 + 바인딩 포트, 또는 `allowed_hosts`(DNS 리바인딩 차단) → 403 `forbidden`. preflight도 같다.
- CORS: `allowed_origins`에 **명시된** 출처만 `Access-Control-Allow-Origin`(+ `Expose-Headers: ETag`). 허용 헤더
  `X-Console-Token`·`If-Match`·`Content-Type`. 목록 밖 preflight는 403.
- Origin: 변경 요청과 `GET /bootstrap`은 같은 출처 또는 `allowed_origins`만. `/bootstrap`의 `Sec-Fetch-Site: cross-site`는
  명시 출처일 때만 허용.
- 토큰: POST/PUT/PATCH/DELETE(상호작용 응답 포함)는 `X-Console-Token` → 401. WS는 `?token=`.
- 본문 크기: `max_request_bytes` 초과 → 413.
- 가져오기: `~/.claude`·프로젝트 `.claude/`는 읽기만 한다. MCP 서버의 평문 비밀은 저장하지 않고 `secret://` 참조로 바꾼다.
- 내보내기: 기본은 zip 응답(서버 디스크에 쓰지 않음). 폴더 쓰기는 `modules.options.mod-exports.roots`에 등록한 루트 아래에만, 경로 탈출·링크·
  보호 위치(`~/.claude` 등, 루트로 등록해도) 거부. 산출물은 `ac-secret-rules`로 마지막 검사해 평문 비밀 의심 값을 가린다.
- 비밀: 토큰은 로그에 남기지 않는다. 500 응답은 내부 메시지를 담지 않는다. 묶음 미리보기·플러그인 오류 문구는
  `SecretResolver.redact`로 가린다. 셸 명령 실행 API는 없다.

## 테스트

```bash
uv run pytest apps/server/tests
```

공용 도우미는 공개 하위 모듈 `agent_console_server.testing`(임시 설정 `make_settings(tmp_path, options={모듈 id: 설정}, **호스트 키)`·
앱 클라이언트·테스트 그래프·WS 도우미). 이 모듈은 `fastapi.testclient`를 쓰므로 **`httpx`가 있어야 import된다**. `httpx`는 서버의
런타임 의존이 아니라 개발 의존(dev 그룹)이라, 저장소 밖에서 쓰려면 `pip install agent-console-server httpx`처럼 함께 설치한다
(없으면 `ModuleNotFoundError: httpx`).
TS 계약 생성물·루트 예시 설정을 읽는 검사는 저장소 `tests/integration/`에 있다.
상호작용 통합 테스트는 실제 SQLite + 엔진 + fake 백엔드로 대기 → 응답 → 완료, 동시 응답, 재시작 정리, 종료 순서를 본다.
