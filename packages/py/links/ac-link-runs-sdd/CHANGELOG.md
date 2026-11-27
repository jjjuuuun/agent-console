# 변경 기록

## Unreleased

- I.7c: Message catalog `locales/en.json` registered as entry point `agent_console.message_catalogs` `ac-link-runs-sdd`, so the web can show the link module description and settings in English (data only, no API change). Log lines are now English.

## 0.1.0

- 처음 만듦(scripts/pkgkit 템플릿 `link`).
- 6R.15: 작업 연동 `runs`(실행 프로필 동작·관문·입력 치환·비밀 검사·실행 라벨·시작), 실행 결과 →
  `status_on` 반영(줄 해시 충돌 규칙, `sdd.status_not_applied`), 실행 연결(`TaskLink`), 검증 출처
  `runs`, 프로필 그래프 검사, 가짜 실행·메모리 스펙 서비스(`testing`).
- 6R.16: 자동 진행 `SpecAutomation`(스펙 규칙 `automation`, 기본 꺼짐 — 끝날 때마다 `ready` 작업을
  `max_parallel`까지, 연속 실패 건너뜀 `sdd.automation_skipped`, `scope: stage` 단계 끝 멈춤,
  `stopped_reason` user·spec_done·stage_done·failures, 재시작 뒤 실행 기록에서 자기 `host_id` Run만
  되살림). `RunsTaskIntegration.automation_state`·`control`(`AutomationControl`). 설치자 옵션
  `automation_failure_outcomes`·`automation_retry_outcomes`. `FakeRuns.host`·`host_id`.
- 계약 후속: `AUTOMATION_SKIPPED`가 계약 문서 상수 `KnownIssueCodes.SDD_AUTOMATION_SKIPPED`를 쓴다(값 같음).
- 6R.34: 실행 결과로 문서 상태 바꾸기 — 프로필 `document_state_on`(계약 0.14.9)이 있으면 `status_on`과
  같은 사건에서 `change_document_state(by="run", run_id=…)`, 막히면 정보 이슈
  `sdd.document_state_not_applied`(`reason` = `transition_denied`·`gate_blocked`·`document_not_found`·
  `error`). 작업 줄 반영과 독립. 상수 `REASON_TRANSITION_DENIED`·`REASON_DOCUMENT_NOT_FOUND`·
  `ISSUE_STATUS`·`ISSUE_DOCUMENT`.
- 성능(§6R.14 `trace` 1초, 6R.15): 검증 출처 `runs`가 작업 키 → 작업 표를 한 번 만들어 쓴다(검증
  실행마다 작업 목록을 훑던 것 — 작업 5,000·연결 20,000에서 약 0.2초). 연동 경로 성능 테스트
  `test_agent_console_link_runs_sdd_perf.py`(기본 = 작은 규모 작업량, `AGENT_CONSOLE_PERF=strict` =
  기준 규모 벽시계).
