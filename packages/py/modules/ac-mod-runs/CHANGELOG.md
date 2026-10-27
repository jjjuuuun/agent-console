# 변경 기록

## 미출시

- 5.5R.13(B-10): 관측 탭 이벤트 type 접두어를 웹 상수(`OBSERVE_PREFIXES`)에서 데이터로 옮겼다. 패키지 기본 데이터
  `data/observe_event_prefixes.json`(`hook.`·`mcp.`), 설치자 옵션 `observe_event_prefixes`(null = 기본, 목록 = 교체,
  `[]` = 끔), 경로 `GET /observe-event-prefixes`(`list[str]`, 계약 변경 없음), 공개 API
  `DEFAULT_OBSERVE_EVENT_PREFIXES`·`load_observe_event_prefixes`·`observe_event_prefixes_of`,
  `build_router(observe_event_prefixes=)`.

- 5.2R.80(F14): 백엔드 계정 로그인 경로 6개(`POST /backends/{id}/login`·`GET /backends/login/current`·
  `GET|DELETE /backends/login/{sid}`·`POST /backends/login/{sid}/input`·`POST /backends/{id}/logout`), 설정
  `backend_login`(`enabled` 기본 켬·`timeout_s`·`timeout_max_s`·`heartbeat_s`·`retain_s`·`screen_max_lines`),
  `readiness.build_login_service`, 오류 맵(로그인 409·404·422·413), 종료 훅에서 진행 중 세션 취소. 입력 본문은 직접
  검사해 기본 검증 오류가 값을 되돌려 보내지 않게 했다.

- 5.2R.43: `plugins.bind_redactor(registries, redact)` — 비밀 해석기를 만든 뒤 판정 근거를 만드는 노드·엣지 종류(`RedactorConsumer`)에 `secrets.redact`를 준다.
- 5.2R.34: 선택 포트 `runs.scopes`(`RunScoper`·`RunScope`) — 시작마다 요청 `project_id`로 이 Run의 노드 서비스·경고를
  정한다(검사·준비 전). 준비 결과 선택 속성 `run_context`(키별 덮어쓰기) → `run.started` payload, 자식 Run 준비에도 전달.
- 5.2R.5: 준비자 선택 메서드 `annotate_issues`(`RunIssueAnnotator`). 차단 응답 문구 = 머리 + 첫 오류 이슈, `fix` = 첫 버튼. 자식 Run 이어 가기 409에 [맨 위 실행 열기](역할 `runs`).
- 5R.13: `GET /condition-operators`, `GET /runs?root=`, `GET /runs/{id}`의 `children`(직접 자식, 만든 순), `GET /interactions?root=`. 플러그인 로더에 조건 연산자 그룹(`condition_operators`)과 `bind_condition_operators`(연산자를 쓰는 노드·엣지 종류에 묶음 레지스트리를 줌). 자식 Run 준비자 `RunService.prepare_child`(같은 `runs.preparers` 검사·준비)를 엔진에 꽂는다. `InteractionService.list(root_run_id=)`. 의존 `agent-console-conditions` 추가.

- 5R.5: 준비 결과 선택 속성 `flow_settings`(`RunPreparation.flow_settings`, None이 아닌 마지막 값)를 `GraphRuntime.start(flow_settings=)`로 넘긴다. 이 속성이 없는 옛 준비자도 그대로 동작한다.

- 5R.4: 마이그레이션 계보 `runs`(`runs_0001` 빈 기준점, `runs_0002` 계보 새 열·색인, 버전 테이블 `alembic_version_runs`). `storage.py`는 `storage/` 패키지(`BRANCH`)가 됐다. 모듈 서술자 `migrations=(BRANCH,)`.

- 4R.18: 옛 최상위 `runtime`·`backends`·`working_directory` 읽기 호환 제거. 환경변수 `WORKING_DIRECTORY`·`MAX_CONCURRENCY`는 그대로.

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `module`).
- `apps/server`의 실행 조립(엔진·Run·이벤트·상호작용·이어 가기·디스크립터·에이전트 활동 경로, WS `run:`·`interactions`, 재시작 복구, 백엔드 설정 적용)을 옮겼다(3R.13). 팀 규칙·노드 서비스·대화 이어 가기는 `runs.preparers`·`runs.services`·`runs.resume_handlers`로 받는다. 설정 `runtime`·`backends`·`working_directory`(옛 최상위 키)·`run_files_dir`·`min_redact_chars`·`resume_origin`·`activity_limit`.
