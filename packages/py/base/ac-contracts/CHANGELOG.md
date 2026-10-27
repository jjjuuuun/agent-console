# 변경 기록

## 0.10.0

- 계약 v9(5.7R.3, design §5.7R.5 공유 메모리). 사내 의존 범위는 `>=0.10,<0.11`(TS `^0.10.0`). 하위 계약 버전:
  새 `memory` 1.0.0, `modules` 1.2.0 → 1.3.0(WS `memory.changed`). `runs`·`logs`·`definitions` 모델은 그대로이고
  `KNOWN_RUN_EVENT_TYPES`도 그대로다.
- 새 하위 모듈 `memory`(`chat`·`exports`·`imports`·`architecture`와 같은 층, `common`·`runs`(`ConditionSpec`)·`definitions`(`Issue`)를 씀).
  - 사용자 데이터(`DefinitionModel`, 모르는 키 보존, 설정 폼 도움말 전부): `MemorySettings`(워크스페이스 설정 `memory` 섹션, 메모리
    모듈 소유, 공통 설정 모델에 필드 없음), `MemoryScopeKindSpec`(범위 종류: 이름·설명·id 틀), `MemoryRetentionSettings`·
    `MemoryRetentionRule`(`when: ConditionSpec`, `action: archive|delete`), 리소스 종류 `memory`의 config `MemoryAccessConfig`
    (`scopes: MemoryScopeAccess[]`·`default_scope`·`result_header`·`max_result_chars`·`tools: MemoryTools`). 도구 기본 이름·설명·
    결과 머리 줄은 패키지 데이터 `data/memory_access_defaults.json`(`memory_access_defaults()`)에서 온다. 범위 종류 이름은 계약에 없다.
  - 항목·버전·범위: `MemoryScopeRef{kind, id}`(`to_text`·`parse`, `<kind>:<id>`), `MemoryAuthor`(`kind` 열린 문자열,
    `KnownMemoryAuthorKinds`), `MemoryEntry`·`MemoryEntrySummary`(`preview`)·`MemoryEntryPage`, `MemoryVersion`·`MemoryVersionSummary`,
    `MemoryScopeSummary`, `MemoryAccessContext`(범위 id 틀이 읽는 맥락, `MEMORY_CONTEXT_FIELDS`).
  - REST DTO: `MemoryScopeKindInfo`·`MemoryScopeKindList`, `MemoryWriteRequest`·`MemoryUpdateRequest`·`MemoryMoveRequest`,
    `MemoryRetentionPlanRequest`·`MemoryRetentionPlan`·`MemoryRetentionPlanItem`·`MemoryRetentionResult`, `MemoryImportResult`(`dry_run`)·
    `MemoryImportProblem`, `MemoryTagList`·`MemoryTagCount`, `MemorySecretRejectedDetails{field, rules}`(값 없음), 정렬 값 `MEMORY_ENTRY_SORTS`.
  - 이벤트: `MemoryEventPayload`(RunEvent `memory.<op>`, **본문·검색어 원문 없음** — 크기·해시만), 문서 상수 `KNOWN_MEMORY_EVENT_TYPES`
    (`runs`의 알려진 이벤트 목록에 넣지 않음), WS payload `MemoryChanged`(+ `modules.MemoryChangedMessage`).
- 상수: `ErrorCodes.MEMORY_INVALID_KEY`·`MEMORY_TOO_LARGE`·`MEMORY_SECRET_REJECTED`(422), `KnownIssueCodes`에 `MEMORY_*`(도구 사유 코드,
  `memory.unknown_scope_kind`·`settings_invalid`·`storage_memory`·`search_fallback`), `TOOLS_*`(`tools.provider_failed`·`duplicate_name`·
  `backend_capability_missing`), `ARCHITECTURE_CONDITION_PATH_UNLISTED`. `x-constants`에 `KNOWN_MEMORY_EVENT_TYPES`·`MEMORY_ACCESS_OPS`·
  `MEMORY_CONTEXT_FIELDS`·`KNOWN_MEMORY_CONTEXT_FIELDS`·`MEMORY_SCOPE_SEPARATOR`·`MEMORY_ENTRY_SORTS`.

## 0.9.0

- 계약 v8(5.5R.3, design §5.5R.2.4 관측 구조도). 사내 의존 범위는 `>=0.9,<0.10`(TS `^0.9.0`). 하위 계약 버전:
  새 `architecture` 1.0.0, `runs` 1.3.0 → 1.4.0, `common` 1.3.0 → 1.4.0. 새 필드는 전부 선택이라 옛 데이터가 그대로 읽힌다.
- 새 하위 모듈 `architecture`(`chat`·`exports`·`imports`와 같은 층, `common`·`logs`·`definitions`·`runs`를 씀).
  - 사용자 데이터(`DefinitionModel`, 모든 층에서 모르는 키 보존): `ArchitectureSettings`(워크스페이스 설정 `architecture`
    섹션, 구조도 모듈이 소유. 공통 설정 모델에는 필드를 두지 않고 모르는 키로 왕복된다), `ArchitectureProfile`·`ArchitectureCanvas`·
    `ArchitectureZone`·`ArchitectureCell`·`ArchitectureEdge`(`from` 별칭)·`ArchitectureDrill`·`ArchitectureUnavailable`·
    `ArchitectureCoverage`·`ArchitectureOptions`. 칸·연결 종류·지표·색·모양 이름은 열린 문자열이고 값 검사는 프로필 검사가 한다.
    설정 폼 도움말(라벨·설명·`x-ui`) 전부.
  - 화면 명세(screen-architecture §9)의 영역 `description`과 연결 `label_max_w`는 **정식 필드**다(투영 결과에도 실린다).
  - 투영 결과(그리기 완결형): `ArchitectureView`·`ArchitectureCellView`·`ArchitectureEdgeView`·`ArchitectureGroupView`·
    `ArchitectureGroupRest`·`ArchitectureUnassignedView`·`ArchitectureUnavailableView`·`ArchitectureSourceCount`·
    `ArchitectureNote`, 지표 `ArchitectureMetric{status: observed|inferred|not_collected, value: number|null, detail?}`·
    `ArchitectureMetricDetail`(null은 0이 아니다), 칸·연결 상태 `observed|partial|not_collected`, 클릭 필터
    `ArchitectureSelector{arch, arch_group?, arch_sources?}`, `ArchitectureDrillTarget`, 이벤트 멤버십
    `ArchitectureMembership`·`ArchitectureGroupRef`.
  - REST: `ArchitectureProfileInfo`(`origin`·`overrides`·`disabled`·`issues`·`cells`·`edges` 수)·`ArchitectureProfileList`·
    `ArchitectureProfileDetail`·`ArchitectureProfileCheckRequest`(형식이 틀린 본문도 받음)·`ArchitectureProfileCheckResult`·
    `ArchitectureProjectRequest`·`ArchitectureScopeTooLargeDetails`.
  - 문서 상수: `KnownArchitectureMetrics`·`KnownArchitectureEdgeKinds`·`KnownArchitectureOrigins`·`KnownArchitectureTargets`·
    `KnownArchitectureNoteCodes`·`KnownArchitectureIssueCodes`.
- 오류 코드: `architecture.profile_not_found`(404), `architecture.scope_too_large`(422, `details` = `{events, limit}`).
- `runs` 1.4.0(C1·C2·C7): 새 알려진 이벤트 `agent.context_prepared`(`AgentContextPreparedPayload{resources:
  ContextResourceRef{id, kind, bytes?, sha256?}[], fragments?}`, **본문 없음**), `NodeStatusPayload.tool_use_id`(위임 도구
  호출 id), `AgentMessagePayload.duration_ms`·`AgentUsagePayload.duration_ms`(ms, 모르면 null).
- `common` 1.4.0: `x-ui` 키 `widget`(`XUiKeys.WIDGET`, `x_ui(widget=)`) — 화면이 등록한 위젯 이름, 모르면 기본 폼.
- 하위 호환: phase-4r·phase-5r 기준 파일의 이벤트를 다시 읽으면 `tool_use_id`·`duration_ms`가 null로 더해질 뿐이다
  (기준 비교 테스트의 "새 키" 목록에 넣었다). v7 버전 테스트는 "0.8.0 이상"으로 바꾸고 정확한 값은 v8 테스트가 고정한다.
- 테스트 전용 의존 `ruamel-yaml`(dev 그룹): 구조도 프로필 YAML 예시 왕복 테스트용. 대안 PyYAML은 저장소 다른 패키지가
  쓰지 않아 기존 의존을 재사용했다. 런타임 의존은 그대로 `pydantic`뿐이다.

## 0.8.0

- 5.2R.80(F14 구독 로그인, ux-overhaul §15.9): `BackendCapabilities.login`·`logout`(기본 false),
  `BackendDescriptor.login_methods: LoginMethodInfo[]`(`id`·`label`·`description`·`notice`·`writes`·`needs_browser`),
  `BackendReadiness.actions: ReadinessAction[]`(`kind` 열린 어휘 login·logout, `method_id`·`label`·`primary`), 새 모델
  `BackendLoginStartRequest`·`BackendLoginSession`(`phase` 닫힌 목록 `BackendLoginPhase`)·`BackendLoginInput`(`text`는
  `writeOnly`·`x-secret`, 최대 2048자, `text`·`key` 중 하나)·`BackendLogoutResult`, 상수 `BACKEND_LOGIN_TEXT_MAX_CHARS`.
  오류 코드 `backend.login_unsupported`·`backend.login_busy`·`backend.logout_unsupported`·
  `backend.subscription_auth_disabled`(409), `backend.login_session_not_found`(404). 새 필드는 전부 선택이라 하위 호환이다.

- 5.2R.85 N1 후속: `BackendCapabilities.login`·`logout` 설명에 "백엔드가 거절 이유를 알리면 그 코드(예: `backend.subscription_auth_disabled`)" 를 덧붙였다(`ac-runtime` `LoginRefusalAware`). 문구만 바뀌고 형식은 그대로다.
- 5.2R.104(프리셋 기능 삭제, 사용자 지시): `PresetSummary`·`ApplyPresetRequest`·`ApplyPresetResult`와 경로 `GET /presets`·`POST /presets/{id}/apply`를 지웠다. 생성 TS 타입·JSON Schema에서도 빠진다. `AppliedItemInfo`·`ConflictPolicy`는 가져오기가 계속 쓴다. 0.8.0은 아직 배포 전이라 하위 계약 버전(`definitions` 1.3.0)은 그대로 둔다. phase-5r 기준 파일에서 두 모델의 사례를 뺐다(나머지 사례는 그대로).
- 5.2R.94(잔해 정리): README의 "삭제(2R.20, 0.4.0)" 절을 이 기록의 0.4.0 항목으로 옮기고, README에는 옛 데이터 읽기 설명만 남겼다. 코드 변경 없음.
- 5.2R.64: 목록 요약 `GraphSummary.attributes`·`ResourceSummary.attributes`(`JsonObject`, 기본 `{}`, 선택). 원문 `attributes` 그대로이며 웹 목록 폴더(`ui.folder`)·임의 키 묶기에 쓴다. 수정 시각은 기존 `saved_at`(초 단위 epoch, 선택)을 그대로 쓴다. 새 필드는 선택이라 하위 호환이다.
- 5.2R.3 후속(5.2R.35 QA): 이슈 코드 문서 상수 `KnownIssueCodes.PROJECT_REFERENCES_UNAVAILABLE`(`project.references_unavailable`)·`PROJECT_DEFINITIONS_UNAVAILABLE`(`project.definitions_unavailable`), 새 문서 상수 `KnownSuggestionIds.PROJECT_MOVE_TO_SHARED`(`project.move_to_shared`). 둘 다 이름 → 값 표로 `x-constants`(`KNOWN_ISSUE_CODES`·`KNOWN_SUGGESTION_IDS`)에 내보낸다. 이슈 코드·제안 id는 여전히 열린 문자열이다(형식 불변).
- 5.2R.5: 사용자 문구 금지 패턴 데이터 `data/user_text_rules.json`과 `agent_console_contracts.user_text`(`find_forbidden_text`·`scan_forbidden_text`), 생성 상수 `USER_TEXT_RULES`. 계약 설명에서 설계 문서 번호를 뺐다(형식 불변).
- 계약 v7(5.2R.3, design §5.2R.3 표 1~11·§UX-P.4). 사내 의존 범위는 `>=0.8,<0.9`(TS `^0.8.0`). 하위 계약 버전:
  `common` 1.2.0 → 1.3.0, `definitions` 1.2.0 → 1.3.0, `runs` 1.2.0 → 1.3.0, `usage`·`chat` 1.0.0 → 1.1.0,
  `resources`·`imports` 1.0.0 → 1.1.0(`Resource.project`·`ResourceSummary.project`, `ImportRequest.project`),
  `modules` 1.1.0 → 1.2.0(`ModuleOptionsView`), 새 `projects` 1.0.0. 새 필드는 전부 선택이다.
- 새 하위 모듈 `projects`(`runs`·`usage`와 같은 층, `definitions`까지만 씀): `Project`·`ProjectCreate`·`ProjectUpdate`·
  `DefinitionKey`·`DefinitionMove`(`from` 별칭)·`MovePlanRequest`·`MovePlan`·`DeletePlan`·`ProjectDeleteMode`.
  `ProjectPreferences{new_definition_scope, fallback}`·`DefinitionScope`는 공통 설정 섹션이라 `definitions`에 있다
  (`projects`가 `AgentSettings`·`Issue`를 쓰므로 반대 방향 import를 피함). `projects`에서도 다시 내보낸다.
- 정의 범위: `Agent`·`Graph`·`Resource.project: Slug | None`(생략 = 공용, **지정하지 않으면 전체 직렬화에서도 뺀다** —
  내부 베이스 `OmitWhenUnsetModel`, `GraphSettings`의 기존 규칙을 옮김). `GraphSummary`·`ResourceSummary.project`,
  `WorkspaceSettings.projects`, `ApplyPresetRequest.project`·`ImportRequest.project`.
- 실행·대화: `Run`·`CreateRunRequest`·`Conversation`·`ConversationSummary`·`CreateConversationRequest.project_id`
  (불투명 문자열). 목록 질의 `GET /runs?project=&root_only=`·`GET /conversations?project=`는 모델 문서에 적었다.
- 오류 해결 데이터: `Fix`·`FixAction`·`FixTarget`(common), `ErrorInfo.fix`·`Issue.fix`. 백엔드 사전 점검
  `ErrorCodes.BACKEND_UNRESOLVED`(`backend.unresolved`, 422)·`BackendUnresolvedDetails{nodes: UnresolvedBackendNode[],
  options: BackendDescriptor[]}`. `BackendDescriptor.cost_note`·`ui_hints`, `UiHints.badge`.
- 편집기: `EditorSettings.auto_connect_io`(생략 = 켬), `default_edge_shape` 설명 "비우면 자동 경로". 팀 구성 층에서는
  지정했을 때만 직렬화한다(`GraphSettings._OMIT_WHEN_UNSET`).
- 사용량: **`UsageIndicatorSettings.value_mode` 기본값 `remaining` → `used`**(사용자 지시, 의미가 바뀌는 유일한 변경.
  값을 적은 설정은 그대로). `UsageSourceDescriptor.auto_enable`·`needs_setup`·`test_only`·`setup_snippets:
  UsageSetupSnippet[]`·`windows: UsageWindowInfo[]`, `UsageSourceInfo.last_received_at`.
- 프리셋 요약 `PresetSummary.badges`·`featured`·`start_graph`. 위임 방식 `DelegationStrategyDescriptor.shares_session`
  (기본 true). 모듈 옵션 읽기 전용 응답 `ModuleOptionsView{module_id, schema, values, yaml_snippet}`.
- `x-ui` 도우미 `x_ui(...)`·`X_UI`·`XUiKeys`·`X_UI_TIERS`(스키마 `x-constants`에도). 내용 채우기는 5.2R.28.
- 설정 폼 도움말 채우기(5.2R.28, 스키마 메타데이터만, 형식·직렬화 변경 없음): 정의 모델(`DefinitionModel`을 상속한
  모델과 그 참조 모델 `PortDef`·`Endpoint`·`Position`·`ResourceContentRef`, 플러그인이 쓰는 `UiHints`·`ReviewDecision`)
  모든 필드에 `title`·`description`(100자 이하, 사용자 말)·`x-ui.tier`(+ `when`·`example`·`group`·`unit`). 분류는 설정 폼
  분류표 그대로이며 팀 구성 층(`GraphSettings`)은 물려받은 에이전트 설정을 전부 고급 "에이전트 기본값" 묶음으로 보인다
  (모델 `json_schema_extra`). 개발자용 설명 문구(디스크립터 id, `config_schema`, JSON Pointer 등)를 사용자 문구로 바꿨다.
- 새 하위 모듈 `agent_console_contracts.schema_help`: `lint_schema_help`·`lint_contract_help`·`contract_form_roots`·
  `HelpIssue`, 규칙 데이터 `data/schema_help_rules.json`(공통 금지 패턴은 `user_text_rules.json`을 함께 씀).
  `x-ui.example: null`은 "예시 없음(목록에서 고름)"을 뜻한다.
- 도움말 보강(5.2R.28 후속): 기본(`basic`) 필드 전부와 자주 만지는 고급 필드(한도·권한·백엔드 옵션·채팅·상호작용·
  팀 설정 묶음)에 `x-ui.when`("~할 때 바꾸세요")을 채웠다. "위 층/아래 층"은 "공통·팀·에이전트 설정"으로, hook·MCP·SDK에는
  짧은 풀이를 붙였다. 린트 규칙 `missing-when`(기본 필드, 오류)·`hard-term`(어려운 용어, 경고)과 `HelpIssue.severity`,
  규칙 데이터 `when_required_tiers`·`hard_terms`(풀이 패턴 `explained`)·`severity`를 더했다.
- tier 재조정(5.2R.28 후속): 새 모델 `AgentDefaults(AgentSettings)`(필드 같음, 제목 "에이전트 기본값")를
  `WorkspaceSettings.agent_defaults`의 형식으로 쓴다. 스키마 훅으로 실행 백엔드만 `basic`(+ when)이다. 에이전트·팀 폼의
  실행 백엔드는 그대로 고급이다. `AgentSettings` 인스턴스도 받는다(지정한 필드만 옮김). 직렬화 형식은 같다.
- 이슈 코드 문서 상수: `backend.unresolved`, `project.shared_uses_project`, `project.cross_project`, `project.unknown`.
- 하위 호환: phase-5r(0.7.0) 기준 파일(`tests/fixtures/phase5r_reference.json`)과 비교한다. 정의(그래프·에이전트·
  리소스·팀 구성 층)는 전체 직렬화·해시까지 같다. 그 밖의 모델은 새 필드가 기본값으로 더해질 뿐이고, 값을 적지 않은
  `value_mode`만 `used`로 읽힌다. 그래프 버전 해시(`ac-graph`)는 `project`를 뺀다.

## 0.7.0

- 계약 v6(5R.2, design §5R.9 표 1~9). 사내 의존 범위는 `>=0.7,<0.8`(TS `^0.7.0`). 하위 계약 버전:
  `common` 1.1.0 → 1.2.0(이슈 코드 문서 상수), `definitions` 1.1.0 → 1.2.0, `runs` 1.1.0 → 1.2.0. 새 필드는 전부 선택이다.
- 연결 종류 `EdgeTypeDescriptor.cycle: CyclePolicy{max_iterations ≥ 1, title?}`·`handles_failure`. 위임 방식
  `DelegationStrategyDescriptor.composable`, 백엔드 능력 `BackendCapabilities.host_tools`.
- 실행 기록: `NodeRun.call`(호출 회차, 기본 0)·`invoked_by`(위임자 노드 경로), `Run.root_run_id`(기존 `parent_run_id`·
  `parent_node_id`에 설명), `RunSnapshot.children: Run[] | null`(null = 서버가 채우지 않음), `Interaction.root_run_id`.
  설계 표의 `RunSummary`·`RunDetail`은 지금 목록·상세 응답 모델인 `Run`·`RunSnapshot`이다.
- 이벤트(알려진 형식): `loop.iteration{edge_id, iteration, nodes}`, `loop.exhausted{edge_id, iteration, max_iterations?}`,
  `run.child_started{child_run_id, node_id, graph_id?}`(status 없음), `run.child_finished{child_run_id, node_id, status}`
  (`status` = 자식 Run 상태), `edge.skipped{edge_id, source, target, kind?, reason?, condition?}`.
  `edge.traversed.condition`, `node.*` payload `call`.
- 조건(X22): `ConditionSpec{all?, any?, negate?}`·`ConditionItem{path(JSON Pointer), op(열린 문자열), value?}`(정의
  데이터, 모르는 키 보존), 판정 근거 `ConditionOutcome{result, combinator?, negate?, items?[{path, op, value?, actual?,
  result, mode?, reason?}]}`(화면 명세 screen-delegation §12 S1 모양), `ConditionOperatorDescriptor{id, title,
  description, value_schema, applies_to?, ui_hints?}`(`GET /condition-operators`).
- 흐름(trace): `TraceSpan.iteration`·`call`·`run_id`, `TraceLink.run_id`(5R.14용).
- 설정: `FlowSettings{max_iterations?, max_node_runs?(기본 200)}`(`WorkspaceSettings.flow`·`GraphSettings.flow`),
  `DelegationSettings.max_nesting`(기본 3, null = 제한 없음). 전부 "생략 = 상속".
- 이슈 코드 문서 상수: `flow.max_iterations_invalid`, `flow.max_node_runs_exceeded`, `condition.unknown_operator`,
  `condition.invalid_value`, `team.mixed_strategies`, `team.recursive`, `team.nesting_exceeded`, `team.team_not_found`,
  `team.child_no_entry`, `delegation.depth_exceeded`.
- 하위 호환: phase-4r(0.6.0) 계약으로 읽고 쓴 기준 파일(`tests/fixtures/phase4r_reference.json`)과 비교한다. 정의
  (그래프·에이전트)는 전체 직렬화·해시까지 같다 — `GraphSettings`가 지정하지 않은 `flow`·`delegation.max_nesting`을
  직렬화하지 않기 때문이다(그래프 버전 해시는 전체 직렬화로 계산). 실행 기록·디스크립터·`WorkspaceSettings`의
  전체 직렬화에는 새 필드가 기본값으로 더해지고(`exclude_unset` 저장 형식·해시는 그대로), 4R 이벤트는 같은 형식으로 읽힌다.

## 0.6.0

- 계약 v5(4R.3, design §4R.9). 사내 의존 범위는 `>=0.6,<0.7`(TS `^0.6.0`). 하위 계약 버전: 새 `logs` 1.0.0,
  `definitions` 1.0.0 → 1.1.0, `runs` 1.0.0 → 1.1.0, `modules` 1.0.1 → 1.1.0.
- 새 하위 모듈 `logs`(`resources`와 같은 층, `common`만 씀, `definitions`가 씀): `LogEvent`(`from` 별칭,
  목록에서는 `detail`·`raw` null), `LogDocumentRef`, `LogEventPage`, `LogEventDetail`, `LogEvidenceLink`,
  `LogSourceDescriptor`, `LogClassifierDescriptor`, `LogSourceInfo`·`LogSourceStatus`, `LogScanReport`·`LogSourceScanResult`,
  `LogSessionSummary`(`tokens`·`project`·`thread_count`·`models`), `LogTimeline`(`lanes: LogLane[]`·`total`·`truncated`), `TokenSample`, `LogTokenTotals`, `LogProjectRef`, `LogAggregateRequest`, `LogAggregateRow`, `LogArchive`(v1),
  설정 `LogSettings`·`LogSourceSetting`·`LogTaxonomy`·`LogCategory`·`LogProjectSettings`·`LogProjectGroup`·`LogDashboard`·
  `LogWidget`·`LogWidgetQuery`, 고정 어휘 `LogUngroupedPolicy`, 문서 상수 `KnownLogCategories`.
- `WorkspaceSettings.logs`(기본 빈 `LogSettings`, 안의 필드는 전부 생략 = 상속).
- design §4R.9 필드 보강 표(F-19~F-25): `LogCategory.tone`(문서 상수 `KnownLogTones`, 오류 표시 근거는 `danger`뿐),
  `LogEventDetail.usage: TokenSample`·`detail_truncated`(근거 상한 `truncated`와 별개), `LogEvent.duration_ms`,
  `LogScanReport.new_events`·`sources[{source_id, new_events, error_code?, message?}]`, `HandoffCount`에 셀 모양
  `from`·`to`·`via`(옛 `source`·`target`·`kind`와 서로 채움, `runs` 하위 호환), 상수 `LOG_EVENT_ORDERS`(asc·desc)·
  `LOG_PROJECT_UNGROUPED`(`~ungrouped`), `LogWidget.options` 예약 키 `w`·`h`, `LogQuerySchema{dimensions, metrics, filters[{id, title?, multi?}]}`
  (`GET /logs/schema`)·문서 상수 `KnownLogDimensions`·`KnownLogMetrics`.
- `ObserveSettings.collectors: {id: CollectorSetting{enabled?, config?}}`·`hook_probe`(생략 = 상속). 옛 키
  `hooks`·`mcp`·`hook_events`는 그대로 읽힌다(해석은 백엔드).
- `CollectorDescriptor`(X7), `BackendDescriptor.collectors`(기본 빈 목록).
- `EdgeTraversedPayload.kind`(연결 종류 id, 선택, `runs` 1.1.0에 포함, 4R.18 요청).
- WS `logs.ingested{source_ids, count, max_seq}`(토픽 `logs`).
- 문서 상수 `KnownIssueCodes`에 `logs.source_failed`·`logs.redaction_unavailable`·`logs.storage_memory`·`logs.unknown_classifier`.
- 기존 YAML·실행 스냅샷은 그대로 읽힌다. 해시 영향: `WorkspaceSettings`에 기본값 필드 하나가 늘어 `model_dump()`(exclude_unset 없이)
  결과에 `logs` 키가 생긴다. 정의 해시는 exclude_unset 정규 문서를 쓰므로 바뀌지 않는다.

## 0.5.1

- 3R.16(통짜 모듈 제거). 하위 계약 버전: `common` 1.0.0 → 1.1.0, `modules` 1.0.0 → 1.0.1.
- `ErrorCodes.NOT_READY`(`not_ready`, HTTP 503): 모듈 시작 훅이 끝나기 전·종료 중의 `GET /health`.
  준비 신호 의미는 그대로다(`/health` 200 = 준비).
- `SubscribePayload.topic` 설명에서 `graph:<id>`를 뺐다(보낼 메시지가 없던 토픽, 받던 통짜 모듈 삭제).
  토픽은 켜진 서버 모듈이 정하고 모르는 토픽 구독은 `error`다. 형식(문자열)은 그대로다.

## 0.5.0

- 계약 v4(3R.7, design §3R.3). 사내 의존 범위는 `>=0.5,<0.6`.
- 기능별 하위 모듈로 고정: `common`·`resources`·`definitions`·`runs`·`usage`·`chat`·`exports`·`imports`·`modules`(`CONTRACT_SUBMODULES`). 하위 모듈별 버전 `CONTRACT_VERSIONS`, 하위 모듈 사이 import 규칙(위 층만 아래 층을 import, import-linter layers + 패키지 테스트). 옛 파일 `api`·`descriptors`·`events`·`interactions`·`trace`·`ws` 모듈 경로는 없어졌다(루트 export는 그대로). `Issue`·`IssueSuggestion`·`GraphPatch`·`IssueSeverity`는 `definitions`에 있다.
- 새 모델: `ModuleInfo`·`ModuleStatus`·`FeatureUnavailableDetails`, `NodeLayout`·`EdgeLayout`·`GraphUiLayout`, `VersionUiSettings`. 새 필드: `NodeSpec.layout`·`EdgeSpec.layout`, `EditorSettings.default_direction`·`default_edge_shape`, `UiHints.direction`·`edge_shape`, `UiPreferences.versions`.
- `ErrorCodes.FEATURE_UNAVAILABLE`(409), 문서 상수 `KnownModuleStatus`, 상수 `USAGE_REPORT_PARTS`. `UsageReport.windows`·`rollups`는 null = 요청하지 않은 부분.
- 스키마 루트에 `x-modules`(하위 모듈 → 모델 이름), `x-constants`에 `CONTRACT_VERSIONS`·`USAGE_REPORT_PARTS`.
- 해시 영향: `EditorSettings`에 기본값 필드 2개가 늘어 `settings.editor`가 있는 기존 그래프는 업그레이드 뒤 정규 문서 해시가 한 번 바뀐다(저장소가 외부 변경 감지 버전 행 1개를 기록, 업그레이드 전 실행의 resume 해시 비교에 걸림). `layout`은 해시에서 빠지므로 layout만 다른 그래프는 해시가 그대로다.

## 0.4.0

- 2R.20: 라우터(`RoutingDecision`, `RouteVerdict`, `route.decided` 이벤트)와 콘솔(`ConsoleSettings`, `console.*` WS 메시지·
  `ConsoleStyle`·`CONSOLE_STYLES`, `WorkspaceSettings.default_entry`·`console`, `RUN_ORIGINS`의 `console`)을 지웠다.
- 독립 프로젝트로 정리(3R.3): 사내 의존을 이름 + 버전 범위로 선언, 패키지별 pytest·mypy·ruff 설정과 `dev` 의존 그룹, LICENSE·CHANGELOG 추가. 동작 변경 없음.
