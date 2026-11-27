# 변경 기록

## Unreleased

- I.7c: Message catalogs `locales/en.json` and `locales/ko.json` registered as entry point `agent_console.message_catalogs` `ac-mod-memory`, so the web can show the module description and settings and the `memory.invalid_request` issue in English (data only, no API change). Log lines are now English.
- REL.16(계약 0.15.0, memory 1.3.0): WS `memory.changed`의 `MemoryChanged.space`를 채운다 — 공간
  서비스는 자기 공간 이름(등록 id), 라이브러리는 null. 공간 제공자 예외에 문자열 `reason`이 있으면 오류
  응답 `details.reason`으로 싣는다(예: `project.memory_unavailable`). `MemorySpaceError(reason=)`.

- FU.12: `search_query_hasher`는 공용 `query_hasher_from_env`를 쓴다(동작 그대로).
- FU.6: 설치자 옵션 `query_hash`(`hmac` 기본·`sha256`·`off`)·`query_hash_salt_env`(솔트 환경변수 이름) — 에이전트 검색 이벤트
  `query_sha256`. 기본이 솔트 없는 sha256에서 프로세스마다 무작위 솔트 HMAC으로 바뀌었다. `search_query_hasher(cfg, environ)`.

- 수정(11/20): 자동 정리가 서버 종료와 겹치면 기다리거나 남은 저장소를 하지 않고 끝난다. `run_retention_cycle(should_stop=)`·`RetentionCycleResult.stopped`, `run_retention_periodically(gate=, stop_wait=)`(취소되면 `WorkGate`를 닫고 하던 저장소가 끝나기를 기다린 뒤 취소를 다시 던짐 — 조립기가 종료 훅보다 먼저 하므로 공간 풀·저장소가 닫히기 전에 끝남), 종료 훅도 정리 스레드를 기다린 뒤 저장소를 닫는다.

- 5.7R.46: 서버 자동 정리가 공용 다음에 `memory.spaces` 제공자의 선택 메서드 `existing()`이 준 공간도
  돈다(대상 = 사용자 설정 `memory.retention.auto`, 공간마다 실패는 로그 + 건너뜀, 규칙이 없으면
  아무것도 열지 않음). `run_retention_cycle`·`RetentionCycleResult`·`retention_targets`,
  `MemorySpaceServices.existing()`·`MemoryService.existing_spaces()`, 포트 모양
  `MemorySpacesListing`. 설정 해석: `retention.auto`는 칸마다 검증(틀린 칸은
  `memory.settings_invalid` + 기본값, 규칙은 그대로).

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `module`).
- 5.7R.13: 공유 메모리 서버 모듈. REST `/memory/*`(범위 종류·범위·태그·항목 CRUD·버전·정리·설정 검사·내보내기/가져오기), WS 토픽 `memory.changed`, 사용자 설정 섹션 `memory`(깨진 부분만 빼고 읽기), 계보 `memory`(`memory_0001`), 저장 위치(호스트 DB 파일 / `store_path` / 메모리 + 경고), 정리 스케줄, 포트 `memory.service`, X29 호스트 플러그인 로더, 설치자 한도 옵션, 단독 실행.
- 5.7R.33z(design §PI.4.3): 선택 포트 `memory.spaces`(공간 이름 → 저장소 + 맥락 바꾸기), REST `?project=<id>`(항목·범위·태그·버전·정리·내보내기/가져오기·범위 종류, 제공자 없음 409 `feature_unavailable`, 모르는 공간 404 `project.not_found`, 제공자 예외 `code` 그대로), `POST /memory/copy`(`MemoryCopyRequest` → `MemoryCopyResult`, 같은 공간 400). `MemoryService.space(name)`·`copy`·`context_overrides`·`effective_context`, `MemorySpaceServices`, 오류 `MemorySpaceError`·`MemorySpacesUnavailable`·`UnknownMemorySpace`. 계보 `memory`의 범위에 `memory`(`MEMORY_DB_SCOPE`)를 더함 — 프로젝트 메모리 DB를 여는 연동이 찾는다. `build_router(service)`는 그대로(공간은 서비스의 `space`).
