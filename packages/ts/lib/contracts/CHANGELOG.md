# 변경 기록: @agent-console/contracts

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따른다. 사내 의존 범위를 깨는 변경은 상대 패키지 버전을 올리고 여기에 적는다.

## [0.8.0]
- 계약 v7(5.2R.3, design §5.2R.3). 사내 의존 범위를 `^0.8.0`으로 올린다. 하위 계약 버전 `common`·`definitions`·`runs` 1.3.0, `resources`·`usage`·`chat`·`imports` 1.1.0, `modules` 1.2.0, 새 하위 경로 `@agent-console/contracts/projects`(1.0.0).
- 새 타입: `Project`·`ProjectCreate`·`ProjectUpdate`·`DefinitionKey`·`DefinitionMove`(`from` 키)·`MovePlan`·`MovePlanRequest`·`DeletePlan`·`ProjectDeleteMode`(projects), `ProjectPreferences`·`DefinitionScope`(definitions), `Fix`·`FixAction`·`FixTarget`(common), `BackendUnresolvedDetails`·`UnresolvedBackendNode`(runs), `UsageSetupSnippet`·`UsageWindowInfo`(usage), `ModuleOptionsView`(modules).
- 새 필드(모두 선택): `Agent`·`Graph`·`Resource.project`, `GraphSummary`·`ResourceSummary.project`, `WorkspaceSettings.projects`, `ApplyPresetRequest.project`, `ImportRequest.project`, `Run`·`CreateRunRequest`·`Conversation`·`ConversationSummary`·`CreateConversationRequest.project_id`, `ErrorInfo.fix`·`Issue.fix`, `UiHints.badge`, `BackendDescriptor.cost_note`·`ui_hints`, `EditorSettings.auto_connect_io`, `UsageSourceDescriptor.auto_enable`·`needs_setup`·`test_only`·`setup_snippets`·`windows`, `UsageSourceInfo.last_received_at`, `PresetSummary.badges`·`featured`·`start_graph`, `DelegationStrategyDescriptor.shares_session`(기본 true).
- 새 상수: `ERROR_CODES.BACKEND_UNRESOLVED`(`backend.unresolved`, 422), `X_UI`(`"x-ui"`)·`X_UI_TIERS`.
- 5.2R.3 후속: 알려진 이슈 코드·제안 id 표 `KNOWN_ISSUE_CODES`·`KNOWN_SUGGESTION_IDS`(이름 → 열린 문자열, `project.references_unavailable`·`project.definitions_unavailable`·`project.move_to_shared` 포함). 상수 전용 하위 경로 `@agent-console/contracts/constants`(x-constants 값만, 스키마 JSON을 싣지 않음).
- **기본값 변경**: `UsageIndicatorSettings.value_mode` 기본 `remaining` → `used`(사용자 지시). 값을 적은 설정은 그대로다.

## [0.7.0]
- 계약 v6(5R.2, design §5R.9). 사내 의존 범위를 `^0.7.0`으로 올린다. 하위 계약 버전 `common`·`definitions`·`runs` 1.2.0.
- 새 타입: `CyclePolicy`, `FlowSettings`, `ConditionSpec`·`ConditionItem`·`ConditionOutcome`·`ConditionItemOutcome`·`ConditionMode`, `ConditionOperatorDescriptor`, 이벤트 `EdgeSkippedEvent`·`LoopIterationEvent`·`LoopExhaustedEvent`·`RunChildStartedEvent`·`RunChildFinishedEvent`(와 각 payload).
- 새 필드(모두 선택): `EdgeTypeDescriptor.cycle`·`handles_failure`, `DelegationStrategyDescriptor.composable`, `BackendCapabilities.host_tools`, `NodeRun.call`·`invoked_by`, `Run.root_run_id`, `RunSnapshot.children`, `Interaction.root_run_id`, `EdgeTraversedPayload.condition`, `NodeStatusPayload.call`, `TraceSpan.iteration`·`call`·`run_id`, `TraceLink.run_id`, `WorkspaceSettings.flow`·`GraphSettings.flow`, `DelegationSettings.max_nesting`.
- 주의: `run.child_started`·`run.child_finished`는 `run.` 접두지만 부모 Run 상태 이벤트가 아니다(`run.child_finished.status`는 자식 상태). `run.*`를 상태로 읽는 코드는 이 둘을 빼야 한다.

## [0.6.0]
- 계약 v5(4R.3, design §4R.9). 사내 의존 범위를 `^0.6.0`으로 올린다.
- 하위 경로 `@agent-console/contracts/logs`(1.0.0): `LogEvent`·`LogEventPage`·`LogEventDetail`·`LogSourceInfo`·`LogScanReport`·`LogSessionSummary`·`LogTimeline`·`LogAggregateRequest`·`LogAggregateRow`·`LogArchive`·`LogSettings`·`LogTaxonomy`·`LogDashboard`·`LogWidget` 등. 하위 계약 버전 `definitions` 1.1.0, `runs` 1.1.0, `modules` 1.1.0.
- 새 필드: `WorkspaceSettings.logs`, `ObserveSettings.collectors`·`hook_probe`(`CollectorSetting`), `BackendDescriptor.collectors`(`CollectorDescriptor`). WS `WsServerMessage`에 `logs.ingested`(`LogsIngestedMessage`).
- `EdgeTraversedPayload.kind`(연결 종류 id, 선택).
- design §4R.9 필드 보강: `LogCategory.tone`, `LogLane`, `LogTimeline.total`·`truncated`, `LogEventDetail.usage`(`TokenSample`)·`detail_truncated`, `LogSessionSummary.tokens`·`project`·`thread_count`, `LogScanReport.new_events`·`sources[].source_id`, `HandoffCount.from`·`to`·`via`, `LogQuerySchema`(`GET /logs/schema`), 상수 `LOG_EVENT_ORDERS`·`LOG_PROJECT_UNGROUPED`.

## [0.5.1]
- 3R.16: `ERROR_CODES.NOT_READY`(`not_ready`, 503 — 모듈 시작 전·종료 중 `GET /health`). 준비 신호 의미는 그대로(200 = 준비).
- 하위 계약 버전 `common` 1.1.0, `modules` 1.0.1. `SubscribePayload.topic` 설명에서 `graph:<id>` 삭제(형식은 문자열 그대로).

## [0.5.0]
- 계약 v4(3R.7, design §3R.3). 사내 의존 범위를 `^0.5.0`으로 올린다.
- 하위 경로 `@agent-console/contracts/<하위 모듈>`(common·resources·definitions·runs·usage·chat·exports·imports·modules): 그 하위 모듈 타입과 `CONTRACT_MODULE`·`CONTRACT_VERSION`. 루트는 그대로 전부를 내보낸다.
- 새 타입: `ModuleInfo`·`ModuleStatus`·`FeatureUnavailableDetails`, `NodeLayout`·`EdgeLayout`·`GraphUiLayout`, `VersionUiSettings`. 새 필드: `NodeSpec.layout`·`EdgeSpec.layout`, `EditorSettings.default_direction`·`default_edge_shape`, `UiHints.direction`·`edge_shape`, `UiPreferences.versions`.
- `UsageReport.windows`·`rollups`가 `null`일 수 있다(= 요청하지 않은 부분, `GET /usage?parts=`).
- 새 상수: `CONTRACT_VERSIONS`, `USAGE_REPORT_PARTS`, `ERROR_CODES.FEATURE_UNAVAILABLE`(409).

## [0.4.0]
- 처음 만듦.
