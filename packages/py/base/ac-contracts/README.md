# agent-console-contracts

Agent Console의 공용 타입·이벤트·DTO(Pydantic v2)와 JSON Schema 생성. 서버·엔진·CLI가 이 모델을 쓰고,
웹은 여기서 생성된 TS 타입(`@agent-console/contracts`)을 쓴다.

- 계약은 특정 노드 타입·엣지 타입·백엔드·모델 이름을 모른다. 노드 `config`, `attributes`, `backend_options`는 `dict[str, Any]`.
- 정의 모델(`Agent`, `Graph`, `NodeSpec`, `EdgeSpec`, `WorkspaceSettings` 등)은 모르는 필드를 보존하고, 그 밖의 모델은 무시한다.
- 시각은 모두 Unix epoch 초(`float`).

## 의존성

| 무엇을 | 왜 | 대안 |
| --- | --- | --- |
| `pydantic>=2.9` | 런타임 검증과 JSON Schema를 같은 모델에서 얻는다(계약 단일 소스, design §5.7) | msgspec(더 빠르지만 JSON Schema·FastAPI 통합이 약함), dataclasses + jsonschema 직접 작성 |

## 설치

```bash
uv sync --all-packages                        # 워크스페이스 안에서
uv pip install ./packages/py/base/ac-contracts     # 다른 프로젝트에서 단독으로
```

## 공개 API 요지

계약 버전 `CONTRACTS_VERSION` = 0.12.1(계약 v11 + 기록 공간·폴더 확인 보강, design §PI.4.6·§PI.16. 0.12.0은 §PI.10. v10(0.11.0)도 §PI.10, v9는 §5.7R.5, v8은 §5.5R.2.4, v7은 §5.2R.3, v6은 §5R.9, v5는 §4R.9, v4는 §3R.3, v3는 §2R.2, v2는 §R9.3).
모델은 기능별 하위 모듈 `common`·`resources`·`logs`·`definitions`·`runs`·`usage`·`projects`·`chat`·`exports`·`imports`·`architecture`·`memory`·`modules`
(`CONTRACT_SUBMODULES`, 버전 `CONTRACT_VERSIONS`)에 있고 루트가 전부를 다시 내보낸다. 기록은 `CHANGELOG.md`.

| 묶음 | 모델 |
| --- | --- |
| 정의 | `Agent`(`AgentSettings` + 식별 필드·`role`), `Graph`(+ `settings: GraphSettings`), `NodeSpec`, `EdgeSpec`, `PortDef`, `PortSpec`, `Endpoint`, `Position`, `Limits`, `WorkspaceSettings` |
| 설정 층 | `AgentSettings`, `GraphSettings`, `ObserveSettings`, `ChatSettings`(+ `queue_after_restart`·`offer_resume`), `EditorSettings`, `DelegationSettings`(+ `max_nesting`, 기본 3), `FlowSettings`(`max_iterations`·`max_node_runs` 기본 200, `WorkspaceSettings.flow`·`GraphSettings.flow`), `InteractionSettings`, `UsageSettings`, `UsageSourceSetting`, `UiPreferences`(+ `notifications: NotificationSettings`), `SecretRuleSettings`(`WorkspaceSettings.secrets`), `ObserveSettings.collectors: {id: CollectorSetting}`·`hook_probe`, `EffectiveSettings`, `SettingsLayerInfo` |
| 리소스 | `Resource`, `ResourceAttachment`, `ResourceContentRef`, `ResourceBundle`, `BundleSource`, `ResourceSummary`, `ResourceFile`(여러 파일 본문) |
| 디스크립터 | `NodeTypeDescriptor`(+ `role`·`executable`·`binds`·`rerunnable`), `EdgeTypeDescriptor`(+ `scheduling`·`invocation`·`connects`·`interaction`·`default_ports`·`reply_fields: ReplyFields`·`cycle: CyclePolicy`·`handles_failure`), `BackendDescriptor`(`BackendCapabilities` + `subagents`·`resource_slots`·`interactions`·`host_tools`, `collectors: CollectorDescriptor[]`), `DelegationStrategyDescriptor`(+ `composable`), `ConditionOperatorDescriptor`(X22), `ResourceTypeDescriptor`(`ResourceContentSpec.multi_file`), `InteractionKindDescriptor`, `UsageSourceDescriptor`, `ModelInfo`, `UiHints` |
| 런타임 | `Run`(+ `conversation_id`·`resumed_from`·`parent_node_id`·`root_run_id`·`host_id`(0.12.1)), `NodeRun`(+ `call`·`invoked_by`), `RunSnapshot`(+ `children`), `WaitInfo`, `Usage`(+ `total_tokens`), `ErrorInfo`, `Issue`(+ `suggestions: IssueSuggestion[]`·`GraphPatch`, `blocks_run`) |
| 프로젝트(`projects`, 0.8.0 → 2.0.0 in 0.11.0 → 3.0.0 in 0.12.0 → 3.1.0 in 0.12.1) | 3.1(더하기만): 기록 DB 상태 `ProjectView{config_dir?, records_state, records_writable, records_issue?}`(`KnownProjectRecordsStates`)·`ProjectRecordsUnavailableDetails`(`KnownRecordsUnavailableReasons`)·옛 기록 옮기기 `RecordsMoveRequest`·`RecordsMoveResult`, 폴더 확인 `FolderCheck{existing?: ExistingProjectProbe, suggested_id?, config_dir?}`(`KnownExistingProjectStates`), 설정 파일 다시 만들기 `ManifestResetRequest`·`ManifestResetResult`.  3.0: 프로젝트 = 로컬 폴더 + 폴더 안 구성 사본. 앱 등록부 `ProjectRegistration{id, folder, archived, archived_at, labels}`, 폴더 매니페스트 `ProjectManifest{format, id, name, description, settings, attributes}`(둘 다 모르는 키 보존), 합친 보기 `Project{folder(필수 키, 옛 `working_directory`를 읽어 옮김, 옛 파일은 null), name, description, settings, archived, archived_at, labels, attributes}`(옛 `log_projects`·`uses`·`import_mode`는 읽고 버림 — `IGNORED_PROJECT_KEYS`·`ignored_project_keys`), `ProjectCreate{folder 필수, id·name 선택}`·`ProjectUpdate{folder·archived …}`, 상태 `ProjectView{project, status, status_detail?, version_hash?, config_writable, manifest_id?, kinds, issues}`(`KnownProjectStatuses`), 공간 사이 복사 `CopyPlanRequest{source, target: SpaceRef, items, include_references}`·`CopyPlan`·`CopyApplyRequest`·`CopyApplyResult`(`KnownCopyActions`·`KnownCopyTargetStates`·`KnownCopyStatuses`), 폴더 `FolderCheckRequest{path, create, exclude_project_id?}`·`FolderCheck{… nearest_existing?, problem, status, conflict?}`·`FolderListing`·`FolderEntry`·`FolderRoot`, 폴더 선택 `FolderCapabilities`·`FolderPickRequest`·`FolderPickResult`(`KnownFolderPickStatuses`), 오류 details `ProjectNotImportedDetails{…, in_library}`·`ProjectFolderConflictDetails`·`ProjectFolderUnavailableDetails`·`ProjectOutsideFolderDetails`, 이전 기록 `AssignProjectRequest`·`AssignProjectResult`·`ProjectCounts`, 키 `DefinitionKey`. (deprecated) 옮기기 `MovePlanRequest`·`MovePlan`·`DefinitionMove`(`from` 별칭), 삭제 `DeletePlan`·`ProjectDeleteMode`. 정의 범위는 `Agent`·`Graph`·`Resource.project`(생략 = 공용, 지정하지 않으면 전체 직렬화에도 없음), 새 정의 범위 설정 `ProjectPreferences`(`WorkspaceSettings.projects`, definitions), 실행·대화 `project_id`(불투명 문자열) |
| 구조도(`architecture`, 0.9.0) | 사용자 데이터(모르는 키 보존): 설정 섹션 `ArchitectureSettings{include_defaults, default_profile, profiles: {id: ArchitectureProfile \| null}}`, `ArchitectureProfile`(`canvas`·`zones: ArchitectureZone[]`·`cells: {id: ArchitectureCell}`·`edges: ArchitectureEdge[]`(`from` 별칭, `points`·`label_at`·`label_max_w`)·`coverage: {출처 종류: ArchitectureCoverage}`·`source_priority`·`error_when`·`group_limit`·`unassigned`·`options`), `ArchitectureDrill`, `ArchitectureUnavailable`. 투영 결과(그리기 완결형) `ArchitectureView`·`ArchitectureCellView`·`ArchitectureEdgeView`·`ArchitectureGroupView`·`ArchitectureMetric{status, value: null 가능, detail?}`(null은 0이 아님)·`ArchitectureSelector{arch, arch_group?, arch_sources?}`·`ArchitectureMembership`·`ArchitectureNote`. REST `ArchitectureProfileInfo`·`ArchitectureProfileList`·`ArchitectureProfileDetail`·`ArchitectureProfileCheckRequest`·`ArchitectureProfileCheckResult`·`ArchitectureProjectRequest`·`ArchitectureScopeTooLargeDetails`. 문서 상수 `KnownArchitectureMetrics`·`KnownArchitectureEdgeKinds`·`KnownArchitectureOrigins`·`KnownArchitectureTargets`·`KnownArchitectureNoteCodes`·`KnownArchitectureIssueCodes` |
| 공유 메모리(`memory`, 0.10.0, 1.1.0 in 0.12.0) | 사용자 데이터(모르는 키 보존): 설정 섹션 `MemorySettings{include_default_scope_kinds, scope_kinds: {id: MemoryScopeKindSpec \| null}, secrets, max_versions_per_entry, retention: MemoryRetentionSettings{rules: MemoryRetentionRule[]}}`, 리소스 종류 `memory`의 config `MemoryAccessConfig{scopes: MemoryScopeAccess[], default_scope, result_header, max_result_chars, tools: MemoryTools}`(도구 기본 이름·설명은 패키지 데이터 `memory_access_defaults()`). 항목 `MemoryEntry`·`MemoryEntrySummary`·`MemoryEntryPage`, 버전 `MemoryVersion`·`MemoryVersionSummary`, 범위 `MemoryScopeRef`(`<kind>:<id>`)·`MemoryScopeSummary`·`MemoryScopeKindInfo`·`MemoryScopeKindList`, 쓴 주체 `MemoryAuthor`, 맥락 `MemoryAccessContext`, REST `MemoryWriteRequest`·`MemoryUpdateRequest`·`MemoryMoveRequest`·`MemoryRetentionPlanRequest`·`MemoryRetentionPlan`·`MemoryRetentionResult`·`MemoryImportResult`·`MemoryTagList`·`MemorySecretRejectedDetails`, 이벤트 `MemoryEventPayload`(본문·검색어 원문 없음)·`KNOWN_MEMORY_EVENT_TYPES`(runs 목록 밖), WS `MemoryChanged`. 1.1.0: 공간 사이 복사 `MemoryCopyRequest{source, target: SpaceRef, filter: MemoryCopyFilter, on_conflict, remap: MemoryScopeRemap[]}`·`MemoryCopyResult{copied, skipped, conflicts: MemoryCopyConflict[], issues}`, REST 질의 `project=` |
| 오류 해결·사전 점검(0.8.0) | `Fix{actions}`·`FixAction{label, target, focus?}`·`FixTarget{role, id?, section?}`(`ErrorInfo.fix`·`Issue.fix`), `BackendUnresolvedDetails{nodes, options}`(`ErrorCodes.BACKEND_UNRESOLVED`, 422) |
| 스키마 확장 `x-ui`(0.8.0) | `x_ui(tier=, when=, example=, group=, group_title=, order=, unit=, enum_labels=, widget=)`(0.9.0 `widget`) → `Field(json_schema_extra=...)`, 키 `X_UI`·`XUiKeys`, `X_UI_TIERS`(basic·advanced) |
| 조건(0.7.0) | `ConditionSpec{all?, any?, negate?}`·`ConditionItem{path, op, value?}`(사용자 데이터, 모르는 키 보존), 판정 근거 `ConditionOutcome{result, combinator?, negate?, items?}`·`ConditionItemOutcome`, `ConditionMode`(all·any) |
| 상호작용 | `Interaction`(+ `node_label`·`root_run_id`), `InteractionStatus`, `InteractionGrant`, `RespondInteractionRequest`, `ReviewDecision`, `INTERACTION_CLOSED_STATUSES` |
| 채팅 | `Conversation`, `ConversationSummary`(+ `held`), 이어 가기 상태 `ConversationSessions{continuable, items: SessionStatus[]}`(`KnownSessionStates`, 0.12.1), `PostMessageRequest.on_missing_session`(0.12.1), `QueuedMessage.held_reason`(`KnownQueueHoldReasons`, 0.12.1), `ChatTurn`(+ `resumed_from`), `ChatReply`, `SessionRef`, `CreateConversationRequest`, `UpdateConversationRequest`, `PostMessageRequest`, `QueuedMessage`(+ `held`) |
| 관측 | `UsageWindowSnapshot`, `UsageReport`, `TokenRollupRow`, `UsageSourceInfo`, `Trace`, `TraceSpan`, `TraceLink`, `HandoffMatrix`, `HandoffCount` |
| 로그(`logs`, 0.6.0) | 이벤트 `LogEvent`(`from` 별칭)·`LogDocumentRef`·`LogEventPage`·`LogEventDetail`·`LogEvidenceLink`, 출처·분류기 `LogSourceDescriptor`·`LogClassifierDescriptor`·`LogSourceInfo`·`LogSourceStatus`, 수집 `LogScanReport`·`LogSourceScanResult`, 세션 `LogSessionSummary`(`tokens: LogTokenTotals`·`project: LogProjectRef`·`thread_count`)·`LogTimeline`(`lanes: LogLane[]`), 토큰 표본 `TokenSample`(`LogEventDetail.usage`), 집계 `LogAggregateRequest`·`LogAggregateRow`·`LogQuerySchema`(`LogDimensionInfo`·`LogMetricInfo`·`LogFilterFieldInfo`), 보관본 `LogArchive`(v1), 설정 `LogSettings`(`WorkspaceSettings.logs`: `LogSourceSetting`·`LogTaxonomy`·`LogCategory`·`LogProjectSettings`·`LogProjectGroup`·`LogDashboard`·`LogWidget`·`LogWidgetQuery`) |
| 이벤트 | `RunEvent`(일반형, 머리 `actor`), `KnownRunEvent`/`AnyKnownRunEvent`(판별 유니온), 타입별 `*Event`·`*Payload`(`run.reply`, `run.waiting`, `node.resumed`, `usage.rate_limit`, `interaction.requested·answered·closed`, 0.7.0 `edge.skipped`·`loop.iteration`·`loop.exhausted`·`run.child_started`·`run.child_finished` 포함, 0.9.0 `agent.context_prepared`(리소스 id·종류·크기·해시만, 본문 없음)·`node.*` `tool_use_id`·`agent.message`·`agent.usage` `duration_ms`, `edge.traversed`·`edge.skipped`의 `condition`), `parse_run_event()`, `KNOWN_RUN_EVENT_TYPES` |
| WS | `WsClientMessage`, `WsServerMessage`(run.event·conversation.updated·interaction.updated·logs.ingested·error), 토픽은 서버 모듈이 정한다(기본: `run:`·`conversation:`·`interactions`·`logs`) |
| REST | `ErrorResponse`, `BootstrapResponse`, `ResolvePortsRequest`, `CreateRunRequest`, `VersionedGraph`, `GraphSummary`, `DefinitionVersion`, `VersionConflictDetails`, `AppliedItemInfo`, `DefinitionReference`, `ServerInfo`, `PluginInfo`, `DuplicateGraphRequest`, `MergeStrategyInfo`(1R.14), v3: `GraphSummary.validation: GraphValidationSummary`, `ServerInfo.warnings`, `BundlePreview`, `TeamPlanSummary`·`EntrySlot`·`AnswerSlot`, `DraftGraphRequest`·`DraftNodeRequest`, `ResumeOptions`·`ResumeNodeOption`·`ResumeRunRequest`, `DefinitionDiff`·`DiffChange`·`ContentChange`·`RestoreVersionRequest` |
| 내보내기(X8) | `ExporterDescriptor`, `ExportSelection`, `ExportRequest`, `ExportFile`, `ExportPlan`, `ExportRootInfo`, `ExportWriteRequest`, `ExportResult` |
| 가져오기 | `ImportSourceDescriptor`, `ImportPreviewRequest`, `ImportPreview`, `ImportCandidate`, `ImportWarning`, `ImportRequest`, `ImportSelection`, `ImportResult` |
| 상수 | `CONTRACTS_VERSION`, `LOG_EVENT_ORDERS`(asc·desc), `LOG_PROJECT_UNGROUPED`(`~ungrouped`), `ErrorCodes`(+ `conversation_busy`·`interaction_closed` = 409), `HTTP_STATUS_BY_ERROR_CODE`, `RUN_ORIGINS`(+ `chat`, `resume`) |
| 문서 상수(Python 전용, 스키마·TS로 내보내지 않음) | `KnownResourceSlots`(알려진 실행 묶음 칸, + `RULES`), `KnownInteractionKinds`(기본 상호작용 종류 id), `KnownUsageTrust`, `KnownModuleStatus`, `KnownLogCategories`(기본 분류기 범주 id, 오류 판정용 아님), `KnownLogTones`(분류 체계 `tone`: 오류 표시는 `danger`만), `KnownLogDimensions`·`KnownLogMetrics`(기본 집계 차원·지표) |
| 문서 상수(이름 → 값 표로 `x-constants`에도, 여전히 열린 문자열) | `KnownIssueCodes` → `KNOWN_ISSUE_CODES`(`limits.not_enforced`·`resource.slot_unsupported`·`secret.plain_found`·`logs.*`, 0.7.0 `flow.*`·`condition.*`·`team.*`·`delegation.depth_exceeded`, 0.8.0 `backend.unresolved`·`project.*`), `KnownSuggestionIds` → `KNOWN_SUGGESTION_IDS`(`project.move_to_shared`). TS는 `@agent-console/contracts/constants`로 받는다 |
| 스키마 | `build_schema()`, `render_schema()`, `export_schemas(out_dir)`, `check_schemas(out_dir)`, `CONTRACT_MODELS` |

### 설정 층: "생략 = 상속"

`AgentSettings`와 그 하위 묶음의 필드는 모두 선택이다. 생략하면 위 층 값을 쓰고, 값이 있으면(null·빈 목록 포함)
그 층에서 정한 것이다. 이 구분은 `model_fields_set`에 남으므로 **저장·전송은 `model_dump(exclude_unset=True)`**로 한다
(기본 `model_dump()`는 생략한 필드를 null로 써서 "이 층에서 null로 지정"이 되어 버린다).
필드별 병합 규칙 기본값은 스키마 주석 `x-merge`(예: `limits` = `replace`, `resources` = `keyed_attachments`),
넓힘 경고 규칙은 `Limits` 필드의 `x-widen`이다. 해석은 `ac-settings`가 한다.

### 로그 설정: "생략 = 상속"

`WorkspaceSettings.logs`(`LogSettings`)와 `ObserveSettings.collectors`·`hook_probe`도 같은 규칙이다. 생략한 출처는
디스크립터 `default_enabled`, 생략한 분류 체계는 기본 분류 체계를 따른다. 범주·위젯 종류·차원·지표·출처 id는
열린 문자열이다(스키마에 enum 없음). 고정 어휘는 묶음 밖 경로 처리 `LogUngroupedPolicy`(`cwd`·`repo_root`·`none`)뿐이다.

### R0: 이름 없는 계약

연결 종류·리소스 종류·상호작용 종류·위임 방식·사용량 출처·창 이름·가져오기 출처는 모두 문자열 id다.
계약 스키마에 이 이름들이 고정 값(enum/const/default)으로 나오지 않음을 테스트한다. 고정 어휘는 엔진 의미
(`EdgeScheduling` 4값, 상태 값, 첨부 방식 등)뿐이다. v3에서 더한 동작 모드(`ChatSettings.queue_after_restart`,
`ExportFile.action`, `ExportWriteRequest.on_conflict`, `DiffChange.op`)도 종류 id가 아니라 고정 어휘다.
답변 연결이 config의 어디에 답변 속성을 두는지(`EdgeTypeDescriptor.reply_fields`), 다시 실행 가능 여부(`rerunnable`),
내보내기 형식(`ExporterDescriptor`)은 플러그인이 선언하며 계약에 키 이름·형식 이름 기본값이 없다.

### 옛 데이터 읽기

`DefinitionModel`은 모르는 필드를 지우지 않으므로 기존 `settings.yaml`에 남은 `console`·`default_entry` 같은 키는
그대로 보존된다. 저장된 `route.decided` 이벤트는 일반형 `RunEvent`로 읽힌다.
`WorkspaceSettings.default_backend`는 읽기 호환용이며 `agent_defaults.backend`를 쓴다. `Graph.limits`는 Phase 1 형식이며
새 데이터는 `settings.limits`를 쓴다.

### 비밀 의심 판정 규칙(옮김)

v3(2R.4)부터 비밀 의심 판정은 계약 패키지가 아니라 `ac-secret-rules`(`agent_console_secret_rules`)에 있다.
계약에는 사용자 규칙 설정 모델 `SecretRuleSettings`(`WorkspaceSettings.secrets`)만 남는다.

## 최소 사용 예

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_contracts import Graph, export_schemas, parse_run_event

>>> graph = Graph.model_validate({"id": "g", "name": "예", "nodes": [{"id": "n1", "type": "my-type"}]})
>>> graph.nodes[0].type  # 노드 종류는 열린 문자열(레지스트리가 해석)
'my-type'
>>> event = parse_run_event(
...     {
...         "event_id": "e",
...         "run_id": "r",
...         "seq": 1,
...         "ts": 0.0,
...         "node_path": [],
...         "type": "agent.text_delta",
...         "payload": {"text": "안녕"},
...     }
... )
>>> type(event).__name__, event.payload.text
('AgentTextDeltaEvent', '안녕')
>>> with tempfile.TemporaryDirectory() as out:
...     [p.name for p in export_schemas(Path(out) / "schema")]
['agent-console.schema.json']
>>> from agent_console_contracts import LogEvent, WorkspaceSettings
>>> log = LogEvent.model_validate(
...     {"uid": "u1", "seq": 1, "source": "my-source", "observed_at": 0.0,
...      "category": "my-category", "from": ["main"], "to": ["helper"]}
... )
>>> log.from_, log.model_dump(exclude_unset=True)["from"]  # `from`은 별칭
(['main'], ['main'])
>>> WorkspaceSettings.model_validate({}).model_dump(exclude_unset=True)  # 생략 = 상속
{}
>>> from agent_console_contracts import Agent, x_ui
>>> "project" in Agent.model_validate({"id": "a", "name": "A"}).model_dump()  # 생략 = 공용
False
>>> x_ui(tier="advanced", unit="초")
{'x-ui': {'tier': 'advanced', 'unit': '초'}}

```

명령행: `python -m agent_console_contracts export <dir>` / `check <dir>`(다르면 exit 1).

## 사용자 문구 금지 패턴(5.2R.5)

설계 문서 번호(`design §`·`§숫자`·`R숫자.숫자`)와 내부 노드 id(`'n1'` 꼴)는 사용자 문구에 넣지 않는다.
규칙은 패키지 데이터 `data/user_text_rules.json` 한 곳이고, 생성 상수 `USER_TEXT_RULES`로 TS 테스트도 같은 값을
읽는다. 범위(`scopes`)는 `description`(계약·디스크립터 설명)과 `messages`(서버·웹 사용자 문구)다.

```python
>>> from agent_console_contracts.user_text import find_forbidden_text
>>> [v.rule for v in find_forbidden_text("자세한 것은 design §5 참고", scope="description")]
['design-ref', 'section-number']
>>> find_forbidden_text("'안내원'을(를) 실행할 백엔드가 정해지지 않았습니다.", scope="messages")
[]

```

## 설정 폼 도움말 쓰기(플러그인 작성 가이드)

설정 폼은 코드가 아니라 스키마에서 그린다. 노드·연결 종류, 리소스 종류, 사용량 출처, 실행 백엔드 옵션,
위임 방식의 `config_schema`도 계약 모델과 같은 규칙을 따르면 같은 모양(기본/고급, 설명, 예시, 단위)으로 나온다.

필드마다 넣을 것:

| 키 | 무엇 | 규칙 |
| --- | --- | --- |
| `title` | 라벨(2~12자) | 필수 |
| `description` | 무엇을 하는지, 왜 바꾸는지 한 문장 | 필수, 100자 이하, 라벨과 같은 문장 금지. 내부 이름(디스크립터·레지스트리·`config_schema`·설계 문서 번호) 금지. 어려운 용어("위 층", SDK, hook, MCP 등)는 실제 이름으로 쓰거나 "hook(도구 실행 전후에 도는 명령)"처럼 풀이를 붙인다(풀이가 없으면 경고) |
| `x-ui.tier` | `basic`(위쪽) · `advanced`(접힘) | 필수. 꼭 정해야 하거나 자주 바꾸는 것만 `basic` |
| `x-ui.when` | 언제 바꾸는지 한 문장("~할 때 바꾸세요") | `basic` 필드는 필수(번들 = 오류, 외부 = 경고), 자주 만지는 고급 필드에 권장 |
| `x-ui.example` | 예시 값(빈 칸을 누르면 채워짐) | 비워 둘 수 있는 문자열·숫자에 기본값이 없으면 필수. 목록에서 고르는 값이면 `None`으로 "예시 없음"을 명시 |
| `x-ui.group`·`group_title` | 고급 영역 소제목 | 선택 |
| `x-ui.unit` | 단위(초, 개, MB) | 선택 |

Pydantic 모델이면 `x_ui()`를 `json_schema_extra`에 넣고, 손으로 쓴 스키마면 `**x_ui(...)`로 펼친다.
`agent_console_contracts.schema_help.lint_schema_help`로 자기 스키마를 검사할 수 있다(규칙 데이터
`data/schema_help_rules.json`). 저장소의 `uv run poe schema-help-lint`는 계약·번들 플러그인 위반을 오류로,
외부 플러그인 위반을 경고로 보인다.

```python
>>> from pydantic import BaseModel, Field
>>> from agent_console_contracts import x_ui
>>> from agent_console_contracts.schema_help import lint_schema_help
>>> class MyNodeConfig(BaseModel):
...     greeting: str | None = Field(
...         default=None,
...         title="인사말",
...         description="대화를 시작할 때 보낼 첫 문장입니다. 비우면 보내지 않습니다.",
...         json_schema_extra=x_ui(
...             tier="basic", example="안녕하세요", when="첫인사를 바꾸고 싶을 때 바꾸세요."
...         ),
...     )
...     retries: int = Field(
...         default=2,
...         title="재시도",
...         description="실패했을 때 다시 시도할 횟수입니다.",
...         json_schema_extra=x_ui(tier="advanced", when="응답이 자주 끊길 때 늘립니다.", unit="회"),
...     )
>>> lint_schema_help(MyNodeConfig.model_json_schema())
[]
>>> raw = {"type": "object", "properties": {"path": {"type": "string", "title": "경로"}}}
>>> sorted(i.rule for i in lint_schema_help(raw))
['missing-description', 'missing-example', 'missing-tier']

```

## 계약 생성 파이프라인

`uv run poe contracts`: 이 패키지 → `packages/ts/lib/contracts/schema/agent-console.schema.json` → `packages/ts/lib/contracts/src/generated/contracts.generated.ts`.
`uv run poe contracts-check`: 두 생성물이 지금 코드로 다시 만든 결과와 같은지 검사(다르면 exit 1). 생성물은 커밋한다.

## 개발·재사용(단독)

이 폴더는 독립 프로젝트다(design §3R.2). 폴더만 복사해도 아래 명령이 그대로 돈다. 사내 의존은 이름 + 버전
범위로 선언돼 있으므로, 저장소 밖에서는 휠 모음(저장소에서 `uv run poe wheels` → `dist/wheelhouse`)을
찾기 경로로 준다(`uv sync --find-links <wheelhouse>`). 저장소 안 검사: `uv run poe portability --package ac-contracts`.

```bash
uv sync                  # dev 그룹(pytest·mypy·ruff, 테스트가 쓰는 사내 패키지) 포함
uv run ruff check . && uv run mypy && uv run pytest
```

## 테스트

```bash
uv run pytest packages/py/base/ac-contracts/tests
```
