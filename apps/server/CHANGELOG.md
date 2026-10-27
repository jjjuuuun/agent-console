# 변경 기록

## 미출시

- 5.2R.100(README 현행화, 코드 변경 없음): README의 이력 문장을 여기로 옮기고 현재 동작 설명만 남겼다. 옮긴 이력: 라우터(`ac-routing`)·터미널 콘솔(`ac-console`)·`ac-client` 패키지와 WS `console.*` 메시지는 2R.20에서 삭제했다(되돌리기 기준점: 태그 `phase-2r`). WS `graph:` 토픽과 통짜 모듈은 3R.16에서 삭제했다. 채팅 대기열은 3R.15부터 서버 DB(`chat_queue`)에 저장한다(그 전에는 서버 메모리). `mod-imports.project_dir` 기본값은 4R.18부터 설정 파일 폴더다. claude-agent-sdk `allow_subscription_auth` 기본값은 5.2R.79부터 `true`다. README 모듈 표를 설치된 entry point 기준(기능 10개·연동 11개)으로 다시 만들고, 백엔드 로그인(`backend_login`) 절을 더했다.
- 5.2R.104(프리셋 기능 삭제): 의존 `agent-console-mod-presets`를 뺐다. 경로 `/presets`·`serve --apply-preset`·환경변수 `AGENT_CONSOLE_PRESET_DIRS`·`AGENT_CONSOLE_APPLY_PRESETS`가 없어졌다. 설정에 `presets` 또는 `modules.options.mod-presets`가 남아 있으면 "프리셋 기능은 삭제되었습니다" 설정 오류(`settings.removed_key`, `mod-definitions` 선언)로 시작을 거부한다.
- 5.2R.93(설정 호환 정리): 호스트 지운 키 표 `REMOVED_KEYS`(1R의 `console`·`default_manual_route_pattern`)를 지웠다. 남은 `console:` 등은 일반 설정 오류다(`extra="forbid"`). 읽기 호환 장치 `MovedKey`·`SETTINGS_MOVED_KEY`·`ServerSettings.moved_keys`·`migrate_moved_keys`와 `/server-info`의 `settings.moved_key` 경고를 지웠다. 지운 키 거부(`RemovedKey`·`SETTINGS_REMOVED_KEY`)와 기본값 채우기(`SeedSetting`, modkit `seed_settings`)는 그대로다. `_ws.py`·`testing.py` 이력 주석을 고쳤다.
- 5.2R.92: 명령행 옵션 해석을 `main` 하나로 합쳤다(`agent-console serve`도 이것을 부른다). `--allow-origin ORIGIN`(여러 번)과 공개 함수 `merge_origins`를 apps/cli에서 옮겨 왔고, `--config`에 `-c`를 더했다. `main(argv, *, prog="agent-console-server", modules=None)` — `prog`는 도움말·오류 줄의 명령 이름, `modules`는 옵션을 읽고 조립할 모듈(None이면 설치된 모듈). `serve(..., modules=None)`는 `create_app(modules=)`로 넘긴다. 설정 오류 줄은 표준 출력 대신 표준 오류에 쓴다(종료 코드 2는 그대로).
- 5.2R.91: 설치 의존에 `agent-console-link-projects-runs`를 더했다(누락 결함: 서버만 설치하면 프로젝트 실행 범위 연동이 빠졌다).
- 4R.18: 옛 최상위 설정 키 읽기 호환을 없앴다. 남아 있으면 `ConfigError(code="settings.removed_key", removed=[RemovedKey])`로 새 위치를 안내한다(`SETTINGS_REMOVED_KEY`·`RemovedKey` 공개). 지운 키는 한 번에 모두 보고한다. `testing.make_settings(options=)` 추가, `testing`의 httpx 요구를 문서화.
- 4R.10: 설치 의존에 `agent-console-mod-logs`·`agent-console-logs-claude`·`agent-console-hook-probe`를 더했다(로그 기능 모듈과 기본 로그 출처 플러그인, entry point로 들어온다). 서버 코드는 바뀌지 않았다.

## 0.1.0

- 독립 프로젝트로 정리(3R.3): 사내 의존을 이름 + 버전 범위로 선언, 패키지별 pytest·mypy·ruff 설정과 `dev` 의존 그룹, LICENSE·CHANGELOG 추가. 동작 변경 없음.
- 서버 호스트화(3R.9): `create_app`이 modkit `assemble`로 모듈을 조립한다. 지금의 기능 전부는 임시 통짜 모듈
  `server-monolith`(`MonolithModule`)로 감쌌다(동작 불변). 호스트 경로 `GET /modules`(`ModuleInfo[]`) 추가,
  `GET /bootstrap`은 호스트 경로로 옮겼다(경로·응답 동일). 설치자 설정 `modules`, `python -m agent_console_server
  --enable-module/--disable-module`, `create_app(modules=)`, `apply_module_flags`·`module_info`·`installed_modules`.
  `FeatureUnavailableError` → 409 `feature_unavailable` `{module, port}`. 기능 라우터는 접두 없이 만들고 앱이
  `/api/v1` 아래 붙인다.
- 3R.10: 사용량·가져오기·내보내기·프리셋·버전을 기능 모듈(`agent-console-mod-*`, entry point)로 떼어 냈다. 통짜 모듈은
  그 모듈들이 쓰는 포트(`definitions.store`·`definitions.lookup`·`definitions.checks`·`secrets.rules`·`workspace.settings`·
  `exports.dependencies`·`usage.*`)를 제공하고 정의 저장마다 모듈 이벤트 `definitions.saved`를 낸다. 웹 역할 `usage`·`imports`·
  `exports`·`presets`·`versions`가 각 모듈로 갔다. 플러그인 레지스트리는 `create_app`에서 한 번 로드해 기본 서비스 `registries`로
  넘긴다(`_plugins.load_plugins`). 설정 `presets`·`usage`·`imports`·`exports`·`versions`는 `modules.options.<모듈 id>`로 옮겼다
  (옛 키 읽기 호환 + `settings.moved_key` 경고 — 시작 로그·`/server-info` `warnings`). 공개 API에서 `apply_presets`·
  `list_presets`·`PresetNotFoundError`를 뺐다(→ `agent-console-mod-presets`), `ServerSettings.preset_paths`·`ServerContext`의
  `usage`·`imports`·`exports`·`apply_presets` 삭제, `build_context(plugins=, on_saved=)`. 의존에서 presets·settings 제거.
- 정의·리소스 분리(3R.12): 정의 저장소·에이전트/팀 구성/공통 설정 CRUD·비밀 규칙·평문 점검은 `mod-definitions`, 리소스
  경로·`/resource-types`·`/merge-strategies`는 `mod-resources`, 저장 전 검사(`DefinitionChecker`)는
  `link-definitions-resources`, 사용처·유효 설정·실행 계획·묶음 미리보기는 `link-definitions-teams`, 내보내기 의존은
  `link-exports-teams`로 옮겼다(`_checks.py`·`_secret_rules.py`·`_rest_graph_views.py`·`_rest_resources.py`·
  `_rest_resource_files.py` 삭제). 통짜 모듈은 `definitions.store`·`workspace.settings`·`secrets.rules`를 받고(필수)
  `graphs.validation`·`secrets.redact`를 준다. 웹 역할은 `runs`·`conversations`만 남았다. 평문 점검 캐시 무효화는 쓰기
  요청 미들웨어 대신 `definitions.saved`(+삭제). 설정 `resources.*` → `modules.options.mod-definitions`(옛 키 읽기 + 경고).
  `build_context`는 정의 저장소·설정·비밀 규칙 포트를 인자로 받는다(`definition_kinds` 공개 이름 삭제 — mod-definitions로).
- 채팅 분리(3R.14): 대화·턴·메시지·대기열 경로와 WS `conversation:`은 `mod-chat`, 대화 턴 시작·이어 가기
  (`runs.resume_handlers`)·`runs.event` 구독 알림·재시작 대기열 정책·종료 순서는 `link-chat-runs`로 옮겼다(`_context.py`·
  `_rest_chat.py`·`_rest_queue.py`·`_rest.py` 삭제). 통짜 모듈은 WS `graph:`만 남은 껍데기(`MonolithModule(server_version=)`,
  포트·훅·웹 역할 없음, 계약 `modules`만). 공개 API에서 `ServerContext`·`build_context`·`RuntimeTurnLauncher`를 뺐다
  (→ `agent-console-link-chat-runs.RuntimeTurnLauncher`), `app.state.ctx` 없음, 앱 수준 `ChatError` 처리기 삭제(모듈 오류 맵),
  의존에서 `agent-console-chat` 제거·`agent-console-mod-chat`·`agent-console-link-chat-runs` 추가. 대화 저장소는 호스트 DB
  핸들을 쓴다(따로 열지 않음).
