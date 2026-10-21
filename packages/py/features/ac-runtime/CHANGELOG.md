# 변경 기록

## 미출시

- 5.2R.34: `GraphRuntime.start(run_context=, start_warnings=)` — `run.started` payload에 더할 Run 맥락(상태
  필드는 덮지 않음)과 `run.started` 뒤 `log.warning`으로 낼 경고. 자식 Run은 `ChildRunPreparation.run_context`가 없으면
  부모 맥락을 물려받는다.
- 5.2R.5: 선택 훅 `NODE_NAME_HOOK`(`display_name(config, services)`)·`node_display_name`. 실행 실패 요약은 노드를 이름으로 부르고(`'<이름>' 실패: …`, `details{node_id, node_name, error}`) 원인 `fix`를 잇는다. 위임 거절·seed·이어 가기 이슈 문구에서 노드 id를 뺐다(`details.node_id`). 자식 Run 이어 가기 거절은 상태 검사보다 먼저이며 `details`에 `status`를 더했다. 테스트 노드 `t.step`에 `name`·`fix`.
- 5R.13: 자식 Run(`root_run_id`)은 따로 이어 가지 않는다 — `resume_options`는 빈 목록, `ResumeService.resume`은 `RunNotResumableError`(`details{run_id, root_run_id, parent_run_id}`).

- 5R.9: X12 혼합 위임 — 선택 프로토콜 `ComposableDelegation`(`contribute(plan, ctx) -> DelegationContribution`),
  `DelegationContribution{subagents, host_tools, options, wrap_sink}`, 순수 함수 `merge_contributions`(이름 겹침·
  옵션 충돌 = `DelegationIssueCodes`)·`apply_contribution`, 타입 `SinkWrapper`(`_delegation.py`).

- 5R.8: 엣지 판정 결과의 근거·경고 — `Activation.condition`·`warnings`, 새 결과 `Blocked(reason, condition,
  warnings)`(dead-path + `edge.skipped`), 엔진이 `edge.traversed.condition`을 싣고 경고를 `log.warning`으로 낸다.
  선택 능력 `EdgeValidator.validate_edge`(`EdgeValidationContext`)를 `validate_graph_with`가 부른다.
  `NodeResult.structured`·`NodeRunView.structured`(저장하지 않는 구조화 결과).
- 5R.5: 반복(사이클 연결) 실행 — 디스크립터 `cycle` 연결이 반복 영역을 새 회차(`NodeRun.iteration`)로 다시 연다, `loop.iteration`/`loop.exhausted` 이벤트, 한도 상속(엣지 config → `flow_settings` → 디스크립터), 안전 한도 `flow.max_node_runs`(`RuntimeErrorCodes.MAX_NODE_RUNS_EXCEEDED`), `GraphRuntime(flow_settings=)`·`start(flow_settings=)`, `NodeRunView.iteration`, `Incoming.carried`, `NodeContext.previous_session_id`, 검증 `cycle_edge=descriptor_cycle_edge`, 복구·이어 가기의 회차 처리, 테스트 연결 `t.loop`·`t.step` config `per_iteration`·`session`, `Probe.seen`(`NodeSeen`).
- 5R.10: 플랫폼 도구 런타임 타입 `HostTool`·`HostToolResult`·`HostToolHandler`와 `AgentRequest.host_tools`(런타임 전용, 직렬화 제외), 백엔드 공용 `call_host_tool`·`duplicate_host_tool_names`·`object_input_schema`(새 모듈 `_host_tools.py`).

## 0.1.0

- 독립 프로젝트로 정리(3R.3): 사내 의존을 이름 + 버전 범위로 선언, 패키지별 pytest·mypy·ruff 설정과 `dev` 의존 그룹, LICENSE·CHANGELOG 추가. 동작 변경 없음.
