# 변경 기록

## 0.1.0

- 처음 만듦(6R.10): 패키지 기본 작업 문법 데이터 `data/default_syntax.yaml`, `load_default_syntax`·
  `merge_syntax`·`effective_syntax`(값마다 출처, 기본 끄기), `status_infos`·`document_state_infos`,
  `compile_syntax`, `parse_spec`(markdown-it-py 블록 구조 + 머리 줄 분석), `patch_task`(줄 하나만,
  줄 해시 충돌), 테스트 도우미 `agent_console_sdd.testing`.
- 6R.11: 계획 `plan`(graphlib 층 + 최장 경로, 순환, `weight` 역할), 추적 `trace`(빈 곳 5종·고아),
  관문 `gate_context`·`evaluate_gates`·`require_gates`·`gate_documents`, 규칙 검사 `check_rules`,
  실행 입력 `run_input_variables`·`run_input_values`·`render_run_input`, 틀 ↔ 스펙
  `instantiate`·`spec_to_template`·`definition_kinds`·`blank_documents`(`data/blank_spec.yaml`),
  `SpecRepository`(정의 저장소 위: 만들기·문서 본문·상태 전환·작업 고치기·틀로 저장),
  `SpecFiles`·`LocalSpecFiles`·`check_project_path`, `import_documents`·`export_documents`·
  `list_import_files`, 확장 지점 프로토콜 `VerificationSource`(X42)·`TaskIntegration`(X43)과 선택 능력,
  오류 `SddError` 하위, 테스트 가짜(`MemorySpecFiles`·`FakeVerificationSource`·`FakeTaskIntegration`·
  `memory_repository`). 의존 추가: conditions·store·text-template.
- 6R.13: `SpecRepository(template_store=…)` — 문서 틀을 스펙과 다른 저장소에서 읽고 쓴다(기본 = `store`).
- 계약 후속(0.13.1): 선택 능력 프로토콜 `TaskIssueSource.task_issues(ctx, tasks)`(X43 연동의 작업 이슈 →
  `ParsedTask.issues`)를 문서화하고 공개했다. 이미 쓰던 메서드 모양 그대로다.
- 6R.20d: `list_import_files`가 바로 아래 하위 폴더 `ImportFileListing.dirs`도 준다(재귀 없음, 숨김·링크·루트
  예약 폴더 제외, 이름 순, 각각 `limit`까지 — 넘으면 `truncated`).
- 6R.20a: `SpecRepository.create_template`(빈 틀, `taken` = 피할 id)·`save_template`(`If-Match`)·
  `delete_template` — 틀 저장소(`template_store`)에 쓴다.
