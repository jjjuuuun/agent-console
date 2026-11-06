# 변경 기록

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
