# 변경 기록: @agent-console/contracts

형식은 [Keep a Changelog](https://keepachangelog.com/ko/1.1.0/)를 따른다. 사내 의존 범위를 깨는 변경은 상대 패키지 버전을 올리고 여기에 적는다.

## [0.14.2]
- 계약 0.14.2(7R.19·7R.20·7R.21 서버 후속). 더하기만. 사내 의존 범위는 `^0.14.0` 그대로. `wiki` 1.2.0, `common` 1.12.0.
- 새 선택 필드: `WikiInfo.rules_kind?: string | null`, `WikiRuleEntry.applies_to?`·`path?`·`title?`, `WikiLintReport.partial?`·`skipped?`·`enabled_checks?`, `WikiGraphNode.scheme_target?: LabelDisplayTarget | null`.
- 새 상수: `KNOWN_ISSUE_CODES.WIKI_LINT_FAILED`(`wiki.lint_failed`), `KNOWN_WIKI_LINT_CHECKS`(생성 이름은 생성기를 따른다).

## [0.14.1]
- 계약 0.14.1(7R.13·7R.17 계약 후속). 더하기와 기본값 변경. 사내 의존 범위는 `^0.14.0` 그대로. `wiki` 1.1.0, `common` 1.11.0.
- **기본값 변경(보안 강화)**: 스키마 `WikiSettings.secret_scan` 기본값에 `system: "reject"`를 더했다(`{user: warn, agent: reject, system: reject}`). 웹 설정 폼의 기본 표시가 바뀐다.
- 새 선택 필드: `WikiInfo.writable?: boolean | null`(false = 읽기 전용 공간, null·생략 = 옛 서버).
- 새 상수: `KNOWN_ISSUE_CODES.WIKI_UPDATE_UNAVAILABLE`(`wiki.update_unavailable`).

## [0.14.0]
- 계약 0.14.0(7R.3). 사내 의존 범위 `^0.14.0`(minor 올림 — 소비자 package.json 범위를 함께 올림). 새 하위 경로 **`@agent-console/contracts/wiki`**(1.0.0). `common` 1.10.0, `projects` 3.3.0, `sdd` 1.2.0, `modules` 1.5.0.
- 새 타입: `wiki` 전부(`WikiDefinition`·`WikiRulesDefinition`·`WikiSyntax`·`WikiSettings`·`WikiAccessConfig`·`WikiInfo`·`WikiPageView`·`WikiLink`·`WikiPageVersion`·`WikiGraph`·`WikiSearchResult`·`WikiLintReport`·`WikiMoveResult`·`WikiEventPayload`·`WikiChanged` 등), `WikiChangedMessage`(modules, `WsServerMessage` 유니온에 더함).
- 7R.2a 결정(design §7R.18.1): `WikiPagePreview`·`WikiLinkText`·`WikiTemplateRender`·`WikiRulesListItem`·`WikiRulesView`·`WikiHistoryPage`·`WikiImportItem`·`WikiPageNotFoundDetails`·`WikiTextRange` 등, `WikiLink.status`·`label`·`outside`·`suggested_path`, `WikiImportResult`는 `items`로 한 벌(목록 넷 없음). 스키마 `x-ui.variables`·`x-ui.enum_tones`, 위젯 `wiki-rule-refs`.
- 새 선택 필드: `CopyKindInfo.title?`, `SpecTemplateSummary.kind?`.
- 새 상수: `KNOWN_UI_WIDGETS.WIKI_REF`·`GLOB`, `ERROR_CODES.WIKI_*`, `KNOWN_ISSUE_CODES.WIKI_*`·`TOOLS_INSTRUCTIONS_UNSUPPORTED`, `KNOWN_WIKI_*`, `WIKI_ACCESS_OPS`, `WIKI_WRITE_SUBJECT_PATHS`·`WIKI_LINT_SUBJECT_PATHS`, `KNOWN_WIKI_EVENT_TYPES`.

## [0.13.2]
- 계약 0.13.2(6R.19 서버 후속). 더하기만 한다(새 필드는 선택). 사내 의존 범위는 `^0.13.0` 그대로. `runs` 1.8.0, `definitions` 1.7.0.
- 새 선택 필드: `Run.has_children?: boolean | null`(직접 자식 Run 유무, `GET /runs/page` 행에서 채움, null·생략 = 서버가 채우지 않음).
- 새 선택 필드(6R.20k, `definitions` 1.7.0): `GraphSummary.session_summary?: GraphSessionSummary | null`(`GET /graphs` 행의 세션 집계 `{nodes, delegated: {세션 값: 수}}`, null·생략 = 계산하지 않음 또는 세션 값이 있는 연결 없음). 새 타입 `GraphSessionSummary`.
- 새 선택 필드(6R.20d, `sdd` 1.1.0): `ImportFileListing.dirs?: ImportDir[]`(가져오기 폴더의 하위 폴더, 생략 = 옛 서버). 새 타입 `ImportDir`·`SpecTemplateCreateRequest`(6R.20a).
- 새 타입(6R.20a, `projects` 3.2.0): `CopyKindInfo`·`CopyItem`(`GET /projects/copy/kinds`·`/projects/copy/items`).

## [0.13.1]
- 계약 0.13.1(계약 후속 6R.15·6R.16·5.7R.33y2·5.7R.33y3). 더하기만 한다(새 필드는 모두 선택). 사내 의존 범위는 `^0.13.0` 그대로. `common` 1.9.0, `definitions` 1.6.0, `sdd` 1.0.1.
- 새 선택 필드: `SecretRuleSettings.weak_key_names?: string[] | null`(null·생략 = 기본 데이터, 빈 목록 = 끔).
- 새 상수: `ERROR_CODES.FAKE_SESSION_MISSING`(`fake.session_missing`), `KNOWN_ISSUE_CODES.RECORDS_SESSION_ARCHIVE_FAILED`(`records.session_archive_failed`)·`RUN_MOVE_BUSY`(`run.move_busy`). `SDD_AUTOMATION_SKIPPED`는 0.13.0부터 있다.
- 설명만: `ParsedTask.issues`(작업 연동의 선택 메서드 `task_issues`가 낸 이슈도 담김).

## [0.13.0]
- 계약 0.13.0(6R.3). 사내 의존 범위 `^0.13.0`. 새 하위 경로 **`@agent-console/contracts/sdd`**(1.0.0). `common` 1.8.0, `logs` 1.2.0, `runs` 1.7.0, `chat` 1.3.0, `modules` 1.4.0.
- 새 타입: `sdd` 전부(`SpecTemplate`·`SpecDefinition`·`SpecRules`·`SpecView`·`ParsedTask`·`TaskPlan`·`TraceMatrix`·`SddInfo` 등), `LabelDisplay`·`LabelDisplayTarget`·`RecordSource`(common), `RunPage`(runs), `ConversationPage`(chat), `SddChangedMessage`(modules, `WsServerMessage` 유니온에 더함). 새 선택 필드: `Run.labels`, `CreateRunRequest.labels`, `ModuleInfo.description`·`label_display`, `LogSourceInfo.default_effective`.
- 새 상수: `RUN_LABEL_LIMITS`, `RECORD_SOURCES`, `KNOWN_UI_WIDGETS`, `KNOWN_DOCUMENT_ROLES`·`KNOWN_TASK_FIELD_ROLES`·`KNOWN_GATE_TARGETS`·`KNOWN_TRANSITION_ACTORS`·`KNOWN_TRACE_GAPS`·`KNOWN_TASK_LINK_KINDS`·`KNOWN_AUTOMATION_STOP_REASONS`·`KNOWN_SYNTAX_SOURCES`·`KNOWN_TASK_ACTION_STATUSES`, `RUN_ORIGINS`에 `sdd`, 오류·이슈 코드 `sdd.*`.
- 요청 변경: `CreateConversationRequest`에 모르는 키를 보내면 서버가 422로 거부한다.

## [0.12.2]
- 계약 0.12.2(5.7R.34·5.7R.38). 더하기만 한다(새 필드는 모두 선택). 사내 의존 범위는 `^0.12.0` 그대로. `runs` 1.6.0, `definitions` 1.5.0.
- 새 선택 필드: `DelegationStrategyDescriptor.session`·`backend`·`nestable`(서버가 `session`은 `shares_session`, `nestable`은 `max_depth`에서 채워 보낸다), `EdgeTypeDescriptor.session`, `NodeTypeDescriptor.opens_session`(기본 true), `Issue.hint`·`group: IssueGroup{key, message}`, `GraphPatch.unset_node_fields: NodeFieldRef{node_id, path}[]`.
- 새 상수: `KNOWN_DELEGATION_SESSIONS`(same·separate)·`KNOWN_DELEGATION_BACKENDS`(delegator·target).

## [0.12.1]
- 계약 0.12.1(5.7R.33c3, design §PI.4.6·§PI.16). 더하기만 한다(새 필드는 모두 선택). 사내 의존 범위는 `^0.12.0` 그대로. `@agent-console/contracts/projects` 3.1.0, `runs` 1.5.0, `chat` 1.2.0, `common` 1.7.0.
- 새 타입: `ExistingProjectProbe`·`ManifestResetRequest`·`ManifestResetResult`·`RecordsMoveRequest`·`RecordsMoveResult`·`RecordsMoveSelect`·`ProjectRecordsUnavailableDetails`(projects), `SessionStatus`·`ConversationSessions`·`MissingSessionPolicy`(chat). 새 선택 필드: `ProjectView.config_dir`·`records_state`·`records_writable`·`records_issue`, `FolderCheck.existing`·`suggested_id`·`config_dir`, `Run.host_id`, `PostMessageRequest.on_missing_session`, `QueuedMessage.held_reason`.
- 새 상수: `KNOWN_PROJECT_RECORDS_STATES`·`KNOWN_RECORDS_UNAVAILABLE_REASONS`·`KNOWN_EXISTING_PROJECT_STATES`·`KNOWN_SESSION_STATES`·`KNOWN_QUEUE_HOLD_REASONS`, `ERROR_CODES`·`KNOWN_ISSUE_CODES`의 `PROJECT_RECORDS_UNAVAILABLE`·`CHAT_SESSION_UNAVAILABLE`(409), `KNOWN_ISSUE_CODES`의 `PROJECT_NETWORK_FS`·`PROJECT_GITIGNORE_OUTDATED`·`RUN_OTHER_HOST`(정보 이슈만). `PROJECT_MEMORY_NETWORK_FS`는 deprecated 별칭.

## [0.12.0]
- 계약 v11(5.7R.33c2, design §PI.10). 사내 의존 범위를 `^0.12.0`으로 올린다. `@agent-console/contracts/projects` 3.0.0, `memory` 1.1.0, `common` 1.6.0.
- 깨지는 변경(projects 3.0): `ProjectUse`·`ProjectUseMode`·`ProjectImportMode`·`ProjectUsesUpdate`·`UseCopyRequest`·`UseCopyResult`·`DefinitionCopy`·`LegacyUse`·`LegacyUsesPlan`·`LegacyUsesApplyRequest`·`LegacyUseResult`·`LegacyUsesApplyResult` 삭제, `Project`·`ProjectCreate`·`ProjectUpdate`의 `uses`·`import_mode` 삭제, `ProjectNotImportedDetails`의 `reason`·`import_mode` → `in_library`.
- 새 타입: `ProjectRegistration`·`ProjectManifest`, `SpaceRef`(common), `CopyPlanRequest`·`CopyPlan`·`CopyPlanItem`·`CopyApplyRequest`·`CopyApplyItem`·`CopyApplyResult`·`CopyApplyItemResult`, `FolderCapabilities`·`FolderPickRequest`·`FolderPickResult`, `MemoryCopyRequest`·`MemoryCopyFilter`·`MemoryScopeRemap`·`MemoryCopyResult`·`MemoryCopyConflict`. 새 선택 필드 `ProjectView.config_writable`·`manifest_id`·`kinds`·`issues`.
- 새 상수: `KNOWN_COPY_ACTIONS`·`KNOWN_COPY_TARGET_STATES`·`KNOWN_COPY_STATUSES`·`KNOWN_FOLDER_PICK_STATUSES`·`PROJECT_MANIFEST_FORMAT`, `KNOWN_PROJECT_STATUSES.MANIFEST_INVALID`, `ERROR_CODES`·`KNOWN_ISSUE_CODES`의 `PROJECT_NOT_FOUND`·`PROJECT_MANIFEST_INVALID`·`PROJECT_CONFIG_READONLY`·`PROJECT_COPY_CONFLICT`·`FOLDERS_DIALOG_UNAVAILABLE`·`FOLDERS_DIALOG_BUSY`·`FOLDERS_DIALOG_TIMEOUT`, `KNOWN_ISSUE_CODES.PROJECT_MEMORY_NETWORK_FS`(정보 이슈만).

## [0.11.0]
- 계약 v10(5.7R.33c, design §PI.10). 사내 의존 범위를 `^0.11.0`으로 올린다. `@agent-console/contracts/projects` 2.0.0, `common` 1.5.0, `definitions` 1.4.0, `logs` 1.1.0.
- 깨지는 변경(projects 2.0): `Project.working_directory`·`log_projects` 삭제 → `Project.folder: string | null`(필수 키), `ProjectCreate.folder` 필수(`id`·`name` 선택), `ProjectUpdate`에서 `working_directory`·`log_projects` 삭제·`folder`·`uses`·`import_mode`·`archived` 추가.
- 새 타입: `ProjectUse`·`ProjectImportMode`·`ProjectUseMode`·`ProjectStatus`·`ProjectView`·`ProjectUsesUpdate`·`UseCopyRequest`·`UseCopyResult`·`DefinitionCopy`·`FolderCheckRequest`·`FolderCheck`·`FolderConflict`·`FolderListing`·`FolderEntry`·`FolderRoot`·`ProjectNotImportedDetails`·`ProjectFolderConflictDetails`·`ProjectFolderUnavailableDetails`·`ProjectOutsideFolderDetails`·`OutsideFolderPath`·`AssignProjectRequest`·`AssignProjectResult`·`AssignProjectSkip`·`ProjectCounts`·`LegacyUse`·`LegacyUsesPlan`·`LegacyUsesApplyRequest`·`LegacyUseResult`·`LegacyUsesApplyResult`, `LogSessionSummary.project_id`.
- 새 상수: `X_PATH`·`X_PATH_KINDS`·`KNOWN_PROJECT_STATUSES`·`KNOWN_FOLDER_CHECK_STATUSES`·`KNOWN_FOLDER_CONFLICT_RELATIONS`, `ERROR_CODES`·`KNOWN_ISSUE_CODES`의 `PROJECT_*`·`FOLDERS_*`·`SETTINGS_IGNORED_KEY`·`LOGS_NO_PROJECTS`.
- `@deprecated`: `LogSettings.projects`, `WorkspaceSettings.projects`, `LogSessionSummary.project`.

## [0.10.0]
- 계약 v9(5.7R.3, design §5.7R.5). 사내 의존 범위를 `^0.10.0`으로 올린다. 새 하위 경로 `@agent-console/contracts/memory`(1.0.0), `modules` 1.3.0(`WsServerMessage`에 `memory.changed`).
- 새 타입(memory): `MemorySettings`·`MemoryScopeKindSpec`·`MemoryRetentionSettings`·`MemoryRetentionRule`·`MemoryAccessConfig`·`MemoryScopeAccess`·`MemoryTools`·`MemoryToolText`, `MemoryScopeRef`·`MemoryAuthor`·`MemoryEntry`·`MemoryEntrySummary`·`MemoryEntryPage`·`MemoryVersion`·`MemoryVersionSummary`·`MemoryScopeSummary`·`MemoryScopeKindInfo`·`MemoryScopeKindList`, REST `MemoryWriteRequest`·`MemoryUpdateRequest`·`MemoryMoveRequest`·`MemoryRetentionPlanRequest`·`MemoryRetentionPlan`·`MemoryRetentionPlanItem`·`MemoryRetentionResult`·`MemoryImportResult`·`MemoryImportProblem`·`MemoryTagList`·`MemoryTagCount`·`MemorySecretRejectedDetails`, 이벤트 `MemoryEventPayload`(본문·검색어 원문 없음), WS `MemoryChanged`·`MemoryChangedMessage`.
- 새 상수: `KNOWN_MEMORY_EVENT_TYPES`·`MEMORY_ACCESS_OPS`·`MEMORY_CONTEXT_FIELDS`·`KNOWN_MEMORY_CONTEXT_FIELDS`·`MEMORY_SCOPE_SEPARATOR`·`MEMORY_ENTRY_SORTS`, `ERROR_CODES.MEMORY_*`(422), `KNOWN_ISSUE_CODES`의 `MEMORY_*`·`TOOLS_*`·`ARCHITECTURE_CONDITION_PATH_UNLISTED`.

## [0.9.0]
- 계약 v8(5.5R.3, design §5.5R.2.4). 사내 의존 범위를 `^0.9.0`으로 올린다. 하위 계약 버전 `runs`·`common` 1.4.0, 새 하위 경로 `@agent-console/contracts/architecture`(1.0.0).
- 새 타입(architecture): `ArchitectureSettings`·`ArchitectureProfile`·`ArchitectureCanvas`·`ArchitectureZone`·`ArchitectureCell`·`ArchitectureEdge`(`from` 키, `points: [number, number][]`)·`ArchitectureDrill`·`ArchitectureUnavailable`·`ArchitectureCoverage`·`ArchitectureOptions`, 투영 결과 `ArchitectureView`·`ArchitectureCellView`·`ArchitectureEdgeView`·`ArchitectureGroupView`·`ArchitectureGroupRest`·`ArchitectureUnassignedView`·`ArchitectureUnavailableView`·`ArchitectureSourceCount`·`ArchitectureNote`·`ArchitectureMetric`(`value: number | null` — null은 "수집 안 됨", 0으로 바꾸지 않는다)·`ArchitectureMetricDetail`·`ArchitectureSelector`·`ArchitectureDrillTarget`·`ArchitectureMembership`·`ArchitectureGroupRef`, REST `ArchitectureProfileInfo`·`ArchitectureProfileList`·`ArchitectureProfileDetail`·`ArchitectureProfileCheckRequest`·`ArchitectureProfileCheckResult`·`ArchitectureProjectRequest`·`ArchitectureScopeTooLargeDetails`.
- 새 타입(runs): `AgentContextPreparedEvent`·`AgentContextPreparedPayload`·`ContextResourceRef`. 새 필드(선택): `NodeStatusPayload.tool_use_id`, `AgentMessagePayload.duration_ms`, `AgentUsagePayload.duration_ms`. `KNOWN_RUN_EVENT_TYPES`에 `agent.context_prepared`.
- 새 상수: `ERROR_CODES.ARCHITECTURE_PROFILE_NOT_FOUND`(404)·`ARCHITECTURE_SCOPE_TOO_LARGE`(422). 스키마 `x-ui.widget` 키(화면 위젯 이름).

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
