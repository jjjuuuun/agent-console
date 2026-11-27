# Changelog

## Unreleased

- I.7c: Message catalog `locales/en.json` registered as entry point `agent_console.message_catalogs` `ac-link-projects-memory`, so the web can show the link module description and settings in English (data only, no API change). Log lines are now English.
- REL.16(계약 0.15.0): `MemoryDbUnavailable`의 오류 코드를 `feature_unavailable`에서 계약의 새 코드
  `project.memory_unavailable`(409)로 바꿨다. 예외는 `reason`(`REASON_NO_MIGRATIONS`·`REASON_MIGRATE_FAILED`·
  `REASON_SHUTTING_DOWN`)을 갖고, 메모리 모듈이 응답 `details.reason`으로 싣는다. 모듈이 꺼진 경우는 그대로
  `feature_unavailable`이다.

- FU.2: `memory.sqlite3`가 없으면 보기(GET 목록·검색·범위·태그)만으로 만들지 않는다 — 저장소를
  `DeferredMemoryStore`로 주고 첫 쓰기 때 만들고 계보를 올린다. 파일이 생긴 뒤 다시 열면 SQLite 저장소
  그대로 준다. 계보가 없으면 전처럼 열 때 `MemoryDbUnavailable`.

- 수정(11/20): `ProjectMemoryPool.shutdown()`(모듈 종료 훅이 부름) — 닫고 그 뒤 `open`은 `MemoryDbUnavailable`(파일을 열지 않음), `existing()`은 빈 목록, `is_shut`. 캐시는 `agent_console_store.OpenCache`(기록 공간 풀과 공용). `close_all()`은 닫기만 한다(다시 열 수 있음).

- 5.7R.46: 선택 포트 `projects.lookup`, `ProjectMemoryPool.existing()`(`memory.spaces` 선택 메서드 —
  보관 안 됨·폴더 있음·구성 폴더 쓸 수 있음·`memory.sqlite3`가 이미 있는 등록 id, 아무것도 만들지
  않음, 서버 자동 정리 대상). `testing.folder_spaces_module`이 `projects.lookup`(목록)도 준다
  (`archived`·`listing` 인자, `ListedProject`).

## 0.1.0

- 첫 판(5.7R.33z): `memory.spaces` 제공 — 프로젝트 폴더 `memory.sqlite3` 열기·계보 올리기(범위
  `memory`)·맥락 `project_id` = 폴더 id·열린 저장소 캐시(상한·유휴)·읽기 전용 폴더 보호·네트워크
  드라이브 `DELETE` 저널.
