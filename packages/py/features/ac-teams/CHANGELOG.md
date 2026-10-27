# 변경 기록

## 미출시

- 5.2R.94(잔해 정리): **공개 API 삭제** — `TeamIssueCodes.DELEGATION_TOO_DEEP`(옛 별칭)을 뺐다.
  `TeamIssueCodes.DELEGATION_DEPTH_EXCEEDED`를 쓴다(값 `delegation.depth_exceeded`는 같다).
- 5.2R.43: 위임 방식 디스크립터 `shares_session` 반영. `session_grant`는 false 방식(예: `host`) 대상의 상호작용 종류·대기 한도를 위임자 세션에 더하지 않는다. 새 공개 함수 `shares_session(link, strategies)`·`runs_in_own_session(plan, node_id, strategies)`, `session_owner(plan, node_id, strategies=None)`(자기 세션 대상에서 멈춤), `prepare_run(..., strategies=None)`(주면 엔진 대기 grant = 세션 grant). 백엔드 `validate_settings` 훅은 자기 세션 대상도 자기 grant로 검사한다. 테스트 키트 `s_far`는 `shares_session=False`.
- 5.2R.34: `team_settings(graph, workspace, *, scope_layers=())`(팀 구성 수준 유효 값),
  `resolve_backends(scope_layers=)`, `Layer` 다시 내보내기.
- 5.2R.5: `TeamPlan.label_of`는 label → 묶인 정의 id → 노드 타입 title, `node_display_name`과 검증 문구는 label → 에이전트 정의 이름 → 그 순서(노드 id는 마지막 대체값).
- 5.2R.31: `layers_for`·`agent_layers`·`node_settings`·`effective_settings`에 선택 인자 `scope_layers`
  (공통 바로 아래에 그대로 끼우는 일반 층, 예: 프로젝트 층). 기본 `()` = 기존과 같다. 패키지는 프로젝트를 모른다.

- 5R.15: `graph_dependencies`가 중첩 팀 노드의 자식 팀 구성을 넣는다(`DefinitionDependency(kind = team_kind,
  node_id, version)`, 새 필드 `version`). 내보내기·프리셋 적용 순서용.

- 5R.11: 중첩 팀 규칙 `_rules_teams.check_nested_teams`(`team.recursive`·`team.nesting_exceeded`·
  `team.team_not_found`·`team.child_no_entry`), `validate_team(teams=)`, `TeamLookup`·`find_team`·
  `with_team_settings`·`merge_overrides`, `TeamPlan.team_refs`·`team_versions`, `TeamConventions.team_kind`·
  `node_version_key`, `TeamIssueCodes.TEAM_*`. 테스트 도구 `Kit`에 중첩 팀 노드(`nest`)·`graph(graph_id=)`.

- 5R.9: `RunPreparation.delegation_settings`(유효 설정 `delegation`: 기본값 → 공통 → 팀 구성,
  `GraphRuntime.start(delegation_settings=)` — 실행 중 위임 깊이 한도)와 `delegation_settings()`.

- 5R.12: 검증 규칙 갱신(design §5R.8). 그래프 검사에 `cycle_edge=descriptor_cycle_edge`(사이클 연결이 닫은 흐름 사이클·검토 반려 되돌리기 허용), `flow.max_iterations_invalid`·`flow.loop_invoked_only`, 혼합 위임 `composable` 판정과 `team.mixed_strategies` 제안(연결 종류 바꾸기), 위임 깊이 코드 값을 `delegation.depth_exceeded`로(`details.path`), 사이클 연결만 들어오는 노드는 `team.unreachable`. `validate_team(edge_checks=)` 주입, `flow_settings()`, `SuggestionBuilder.replace_kind`, `make_issue(path=)`. `testing.Kit`에 사이클 연결 종류·합쳐 실행할 수 있는 원격 위임 방식 추가(`inner`도 composable).
- 5R.5: `RunPreparation.flow_settings`(유효 설정 `flow`: 기본값 → 공통 → 팀 구성, `GraphRuntime.start(flow_settings=)`용).

## 0.1.0

- 3R.12: `TeamCatalog`·`catalog_from_registries`(플러그인 레지스트리 묶음 → 노드·엣지·위임 방식·백엔드 디스크립터, `plan`·`try_plan`). 연동 모듈이 같은 읽기를 공유한다.

- 독립 프로젝트로 정리(3R.3): 사내 의존을 이름 + 버전 범위로 선언, 패키지별 pytest·mypy·ruff 설정과 `dev` 의존 그룹, LICENSE·CHANGELOG 추가. 동작 변경 없음.
