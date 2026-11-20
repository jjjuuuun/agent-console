# Changelog

## Unreleased

- 수정(11/20): `ProjectMemoryPool.shutdown()`(모듈 종료 훅이 부름) — 닫고 그 뒤 `open`은 `MemoryDbUnavailable`(파일을 열지 않음), `existing()`은 빈 목록, `is_shut`. 캐시는 `agent_console_store.OpenCache`(기록 공간 풀과 공용). `close_all()`은 닫기만 한다(다시 열 수 있음).

- 5.7R.46: 선택 포트 `projects.lookup`, `ProjectMemoryPool.existing()`(`memory.spaces` 선택 메서드 —
  보관 안 됨·폴더 있음·구성 폴더 쓸 수 있음·`memory.sqlite3`가 이미 있는 등록 id, 아무것도 만들지
  않음, 서버 자동 정리 대상). `testing.folder_spaces_module`이 `projects.lookup`(목록)도 준다
  (`archived`·`listing` 인자, `ListedProject`).

## 0.1.0

- 첫 판(5.7R.33z): `memory.spaces` 제공 — 프로젝트 폴더 `memory.sqlite3` 열기·계보 올리기(범위
  `memory`)·맥락 `project_id` = 폴더 id·열린 저장소 캐시(상한·유휴)·읽기 전용 폴더 보호·네트워크
  드라이브 `DELETE` 저널.
