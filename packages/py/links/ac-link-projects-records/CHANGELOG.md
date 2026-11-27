# 변경 기록

## 미출시

- I.7c: Message catalog `locales/en.json` registered as entry point `agent_console.message_catalogs` `ac-link-projects-records`, so the web can show the link module description and settings in English (data only, no API change). Log lines are now English.
- REL.2: `RecordsSpacePool.batch()`(`BatchRecordsSpaces`) — 블록 안에서 연 공간은 상한(`max_open_spaces`)으로 밀어내지 않고 가장 바깥 블록이 끝날 때 맞춘다. 프로젝트가 상한보다 많을 때 순회(사용량 집계)가 오래 안 쓴 순서 캐시를 매번 전부 다시 열던 것을 막는다. README 설정 표.
- FU.2: `session_archive.dir` 설명 — `.gitignore` 틀이 이 이름을 따른다(`mod-projects.sessions_dir`가 이어받음).
- 정리(11/20 후속): 열린 핸들 캐시를 `agent_console_store.OpenCache`로 옮겼다(메모리 공간 풀과 공용, 동작 같음).

- 수정(11/20): `RecordsSpacePool.shutdown()`(서버 종료, 모듈 종료 훅이 부름) — 열린 핸들을 닫고 그 뒤 `open`은 파일을 열지 않는 `link_disabled` 핸들을 준다. 종료 전에 받은 핸들도 `link_disabled`. 종료 순서상 풀이 먼저 닫힌 뒤에도 배경 로그 수집 스레드가 공간을 새로 열어 연결이 남았다. `close_all()`은 지금처럼 닫기만 한다(다시 열 수 있음).

## 0.1.0

- 처음 만듦(5.7R.33w2): 포트 `records.spaces`(공간 이름 → 프로젝트 기록 DB 핸들, 상한·유휴 닫기), `host_id`, 쓰기 실패 대기 파일과 다시 쓰기.
- 계약 0.13.1: `ARCHIVE_FAILED_CODE`가 계약 문서 상수 `KnownIssueCodes.RECORDS_SESSION_ARCHIVE_FAILED`를 쓴다(값 같음).
