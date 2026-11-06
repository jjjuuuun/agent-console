# 변경 기록

## 미출시

- 6R.20k(계약 0.13.2): 선택 포트 `graphs.session_summary`(`GraphSessionSummarySource.session_summary(graph)`, `GRAPH_SESSION_SUMMARY`). 있으면 `GET /graphs` 행의 `session_summary`를 채운다(라이브러리·공간 목록 모두). 없거나 제공자가 예외를 내면 null. `DefinitionService(session_summary=)` 선택 인자.
- 계약 0.13.1(5.7R.33y2 후속): 설정 `secrets.weak_key_names`(null = 기본 데이터 `DEFAULT_WEAK_KEY_NAMES`, 빈 목록 = 끔, 주면 그 목록)를 `build_rules`가 `SecretRules(weak_key_names=...)`로 넘긴다. 저장 전 검사가 잘못된 이름을 `secret.invalid_rule`(`/secrets/weak_key_names/<i>`)로 막고, 손으로 고친 파일의 잘못된 이름은 빼고 경고 로그(위치만). `weak_name_problems` 추가.
- 6R.5: 선택 포트 `definitions.kind_contributions`(X44, `KIND_CONTRIBUTIONS` = 키트 `DEFINITION_KIND_CONTRIBUTIONS`). `library=True` 기여 종류를 라이브러리 저장소에 더한다(build 때 + 시작 훅에서 한 번 더, `register_contributed_kinds`·`DefinitionFileStore.contributed`). `library=False` 종류의 라이브러리 요청은 모르는 종류라 404. 기본 종류와 같은 이름의 기여는 경고 로그 후 건너뛴다. 기여가 없으면 종류 목록이 전과 같다.
- 5.7R.33x: 선택 포트 `definitions.spaces`(공간 이름 → 정의 저장소, `ac-store.DefinitionSpaces`). 에이전트·팀 구성 경로가 `?project=<공간>`을 받는다(목록·조회·만들기·저장·삭제·복제). 포트가 없으면 `?project=` 요청은 409 `feature_unavailable`, 모르는 공간 404 `project.not_found`, 질의 없는 요청은 그대로 라이브러리. 공간 쓰기의 평문 비밀 거부는 422 `details.issues`(필드 위치), 쓰기 불가 폴더 409 `project.config_readonly`. 공간 목록의 `validation`은 null. `SavedDefinition.space`(기본 None) 추가. **깨는 변경**: `build_router(service)`의 `service`가 공간 이름 하나를 받는다(`Callable[[str | None], DefinitionService]`).
- 5.2R.104: 프리셋 기능을 지웠다. 남은 설정 키 `presets`·`modules.options.mod-presets`를 `RemovedSetting`으로 선언해 호스트가 "프리셋 기능은 삭제되었습니다" 오류로 시작을 거부한다(`PRESETS_REMOVED_REASON`). 개발 의존 `agent-console-mod-presets`를 뺐다.
- 5.2R.33: `LazyVersionRepository`·`versions_for`를 `ac-store`로 옮겼다(이 모듈 `store`는 다시 내보낸다, 동작 같음).
- 4R.18: 옛 최상위 `resources` 읽기 호환 제거(`settings.removed_key` 오류로 새 위치 안내).

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `module`).
- `apps/server`의 정의 저장소 조립·에이전트/팀 구성/공통 설정 CRUD·비밀 규칙·평문 점검을 옮겼다(3R.12). 제공 포트 `definitions.store`·`definitions.lookup`·`workspace.settings`·`secrets.rules`·`definitions.checks`(공통 설정 비밀 규칙 검사)·`server.warnings`(평문 점검), 토픽 `definitions.saved`. 평문 점검 캐시는 `definitions.saved`·삭제로 버린다(쓰기 요청 미들웨어 대체), 세대 비교·대입을 짧은 상태 잠금 안에서 한다(3R.10 QA 후속). 버전 기록은 호스트 DB 핸들(legacy), 없으면 메모리. 설정 `max_content_bytes`(옛 `resources.*`), `plain_secret_issue_codes`.
- 3R.13(3R.12 QA 후속): DB 핸들이 없어 버전 기록이 메모리로 떨어지면 `server.warnings`에 `definitions.versions_memory` 경고를 더한다.
