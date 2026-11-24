# 변경 기록

## 미출시

- FU.5: `merge_access_layers(items, *, entries_key, entry_key, default_ops)`와 키 상수 `ACCESS_CONFIG_FIELD`·`ACCESS_TOOLS_FIELD`·
  `ACCESS_OPS_FIELD` — 도구 공급자(메모리·위키 연동)가 칸의 접근 설정 첨부를 같은 규칙으로 합친다(두 연동의 사본을 옮김).

- FU.4: `resolve_paths(values, base)`·`path_placeholders(base)`·`WORKSPACE_PLACEHOLDER` — agent 노드가
  `limits.directories`의 틀(`{workspace}`)·상대 경로를 `WORKING_DIRECTORY` 기준 실제 경로로 풀어 `AgentRequest.limits`
  (와 `agent.limits`)에 넘긴다(전에는 틀 그대로 백엔드 `add_dirs`·도구 검사로 갔다). 기준이 없으면 그대로.
- FU.4: `resolve_working_directory(value, base)` — 상대 `working_directory`를 노드 서비스 `WORKING_DIRECTORY`
  기준으로 잇는다(절대·`~`·드라이브는 그대로). agent 노드의 `AgentRequest.cwd`가 이 규칙을 쓴다(전에는 상대
  경로를 그대로 넘겨 백엔드가 서버 프로세스 작업 폴더 기준으로 읽었다).
- 5.2R.94(잔해 정리): `__init__` docstring·README의 2R.20 노드 삭제 이력 문장을 이 기록으로 옮겼다. 코드 변경 없음.
- 5.2R.43: `WhenEdge(redact=)`·`use_redactor(redact)`(`ac-conditions.RedactorConsumer`) — 판정 근거를 자르기 전에 가린다. `sdk-subagents` 디스크립터 `shares_session=True` 명시.
- 5.2R.34: 서비스 키 `SCOPE_LAYERS`(`nodes_core.scope_layers`) — agent 노드 유효 설정에 공통 바로 아래 범위 층(예: 프로젝트
  층)을 끼운다.
- 5.2R.5: 서비스 키 `ERROR_FIXES`(`ErrorFixer`) — 에이전트 노드 실패에 해결 버튼을 붙인다. 에이전트 노드 선택 훅 `display_name`(묶인 정의 이름). 디스크립터 설명에서 설계 번호를 뺐다.
- 5R.13: `WhenEdge.use_operators(provider)`(`ac-conditions.OperatorConsumer`) — 실행 모듈이 호스트의 조건 연산자 레지스트리를 준다.

- 5R.11: 노드 타입 `team`(`team.TeamNode`, 중첩 팀 — `binds{graph, team_ref}`, role `team`, `ui_hints.shape
  stacked`, config `TeamNodeConfig{team_ref, version, input_key, reply, reply_separator, settings}`). `ctx.run_child`로
  자식 Run 실행, 답변 고르기 `pick_replies`, 대화 세션 경로 키 `session_path_key`·`child_sessions`, 서비스 키
  `TEAM_LOOKUP`, 오류 코드 `team.lookup_unavailable`·`team.team_not_found`·`team.invalid_settings`·
  `team.child_failed`, 대기 이유 `TEAM_CHILD_WAITING`. `handoff`·`loop`·`when`·`on_error`·`message`·`reply`
  연결의 `connects`에 역할 `team`을 더했다.

- 5R.9: 연결 종류 `delegate`(`edges.DelegateEdge`, none + invocation `host`, config `DelegateEdgeConfig{strategy,
  result}`, `HOST_STRATEGY`). `sdk-subagents`를 `composable=true`로 바꾸고 `contribute`(하위 에이전트 + 답변 sink
  감싸기)를 더했다. agent 노드 config `delegation`(방식 id → 방식 config)과 혼합 위임(방식별 묶음 → 모두
  composable이면 `contribute` 합쳐 백엔드 한 번, 아니면 `agent.mixed_strategies`). 테스트 전용 dev 의존
  `agent-console-delegation-host`.

- 5R.8: 연결 종류 `when`(`conditional.WhenEdge`, config `conditions`, 판정 근거·경고, 저장 전 검사
  `validate_edge` → `ac-conditions.condition_issues`), `on_error`(`conditional.OnErrorEdge`, `handles_failure`).
  `condition_subject`, `CONDITION_FALSE`. agent 노드가 백엔드 `AgentResult.structured`를 `NodeResult.structured`로
  넘긴다. 새 의존 `agent-console-conditions`.
- 5R.5: 연결 종류 `loop`(`loops.LoopEdge`, flow + 디스크립터 `cycle{max_iterations: 3}`, config `LoopEdgeConfig.max_iterations`), `DEFAULT_LOOP_MAX_ITERATIONS`. agent 노드가 같은 노드 직전 반복 회차 세션(`ctx.previous_session_id`)을 이어 쓰고, 이어 쓸 때 남아 있던 입력(`Incoming.carried`)을 프롬프트에서 뺀다.

## 0.1.0

- 2R.20(이전 이력): 1R에서 보류했던 `input`·`output`·`router` 노드를 지웠다.
- 독립 프로젝트로 정리(3R.3): 사내 의존을 이름 + 버전 범위로 선언, 패키지별 pytest·mypy·ruff 설정과 `dev` 의존 그룹, LICENSE·CHANGELOG 추가. 동작 변경 없음.
