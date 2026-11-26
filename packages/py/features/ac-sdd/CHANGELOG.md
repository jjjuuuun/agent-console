# 변경 기록

## 미출시

- P1.5: `SpecRepository.save_as_template(..., taken=())` — `create_template`처럼 이름에서 만든 id와 `rename` 새 id가 `taken`(예: 경로 예약어, 대소문자 무시)을 피한다. 준 id는 그대로(거부는 호출자 몫). 생략 = 지금 동작.
- REL.5: 가져온 문서 본문 파일 이름의 번호 붙이기를 `agent_console_store.numbered_id`로 합쳤다(동작 같음).
- FU.5: `slug_id`·`unique_id`는 `agent_console_store`의 것을 다시 내보낸다(`_ids` 사본 삭제, 규칙 그대로).

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
- 6R.32: 줄 머리 낱말 상태 — 문법 `task.status_pattern`(이름 묶음 `status`)이 있으면 체크 칸 없는 작업
  줄의 상태를 그 낱말로 읽고(맞은 범위를 떼고 id·필드·제목), `patch_task`는 `status` 묶음 범위만 바꾸거나
  상태 없는 줄 본문 앞에 `task.status_format`을 넣는다. 필드 덧붙이는 모양은 `task.field_format`(인자
  `field_format`을 주면 인자 우선, 기본값 None = 문법). 두 모양의 기본값은 패키지 데이터
  (`"{marker} "`·`"[{key}: {value}]"`)이고 `{이름}` 자리만 바꾼다(`str.format` 아님). 문법 검사 경고
  `sdd.status_pattern_ignored`(`no_status_group`·`checkbox`). 필드만 고친 줄에서 상태를 다시 읽지 못하면
  `validation_failed`(`details.reason = status_lost`). `HeadLine.body_start`·`status_span`,
  `CompiledSyntax.status_pattern`·`status_format`·`field_format`. 기본 문법 동작은 그대로다.
- 6R.34: 규칙 검사가 실행 프로필 `document_state_on`을 본다 — 모르는 문서 `sdd.not_found`(문서 목록을 줄
  때만)·모르는 상태 `sdd.unknown_state`(error), `by`에 `run`이 든 그 상태 전환이 없음
  `sdd.transition_denied`(warning).
- 성능(§6R.14 `parse_spec` 300ms, 6R.10): 파싱 동안 순환 GC를 멈추고 끝나면 되돌린다(이미 꺼져 있으면
  두고, 예외에도 되돌림 — markdown-it 토큰이 한꺼번에 살아 있어 전체 힙 GC가 시간의 약 4분의 1을
  썼다), 머리 줄 분석의 위치 계산을 함수 대신 식으로, 한 줄 본문은 `textwrap.dedent` 대신 앞 공백·탭
  제거(결과 같음), 요구 문서의 빈 줄은 정규식을 돌리지 않음, 토큰 루프에서 하는 일 없는 토큰을 먼저
  거름. 400KB·작업 3,000개 약 315ms → 약 210ms. 출력은 그대로다.
