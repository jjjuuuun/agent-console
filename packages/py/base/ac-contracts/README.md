# agent-console-contracts

Shared types, events, and DTOs (Pydantic v2) of Agent Console, and JSON Schema generation. The server, engine, and CLI use these models,
and the web app uses the TS types generated from here (`@agent-console/contracts`).

- The contracts know no specific node type, edge type, backend, or model names. Node `config`, `attributes`, and `backend_options` are `dict[str, Any]`.
- Definition models (`Agent`, `Graph`, `NodeSpec`, `EdgeSpec`, `WorkspaceSettings`, and so on) preserve unknown fields; other models ignore them.
- All times are Unix epoch seconds (`float`).

## Dependencies

| What | Why | Alternatives |
| --- | --- | --- |
| `pydantic>=2.9` | Gets runtime validation and JSON Schema from the same models (single source of contracts) | msgspec (faster, but weaker JSON Schema and FastAPI integration), dataclasses + hand-written jsonschema |

## Installation

```bash
uv sync --all-packages                        # inside the workspace
uv pip install ./packages/py/base/ac-contracts     # standalone, from another project
```

## Public API in brief

Contract version `CONTRACTS_VERSION` = 0.16.0 (breaking: removed `WorkspaceSettings.default_backend`; use `agent_defaults.backend`. Added: the new submodule `i18n` 1.0.0 with the message catalog models `I18nInfo`, `LanguageInfo`, and `MessageCatalog`, `UiPreferences.language` (widget `language`), the error code `i18n.unknown_language` (404), the catalog loading issue codes `i18n.*`, per-kind reserved ids `CopyKindInfo.reserved_ids` and the screen role that opens an item `CopyKindInfo.open_role` (`projects` 4.1.0), and reserved document template ids `SddInfo.reserved_template_ids` (`sdd` 1.4.0). Submodules `common` 2.1.0, `definitions` 3.0.0. Internal dependency range `>=0.16,<0.17` (TS `^0.16.0`). Old `default_backend` keys are preserved as unknown keys and reported through `IGNORED_SETTINGS_KEYS`; no data migration is needed). 0.15.0 (breaking: removed the project scope APIs deprecated in 0.11 to 0.12, such as the move and delete plans `MovePlan` and `DeletePlan`, `WorkspaceSettings.projects`, `LogSettings.projects`, `LogSessionSummary.project`, and the scope issue codes and suggestion ids. Added: `MemoryChanged.space`, the error and issue code `project.memory_unavailable`, `WikiInfo.wiki_kind` and `reserved_page_names`, the full graph depth `WIKI_GRAPH_DEPTH_ALL` and `WikiGraph.depth`, and a narrowed `WikiRuleEntry.severity`. Submodules `common`, `logs`, and `definitions` 2.0.0, `projects` 4.0.0, `memory` and `wiki` 1.3.0. Internal dependency range `>=0.15,<0.16` (TS `^0.15.0`). There is no stored data migration; old keys are preserved as unknown keys and do not block reading or server start. Earlier versions are in `CHANGELOG.md`).
The models live in the feature submodules `common`, `resources`, `logs`, `i18n`, `definitions`, `runs`, `usage`, `projects`, `chat`, `exports`, `imports`, `architecture`, `memory`, `sdd`, `wiki`, `modules`
(`CONTRACT_SUBMODULES`, versions `CONTRACT_VERSIONS`), and the root re-exports all of them. The history is in `CHANGELOG.md`.

| Group | Models |
| --- | --- |
| Definitions | `Agent` (`AgentSettings` + identity fields and `role`), `Graph` (+ `settings: GraphSettings`), `NodeSpec`, `EdgeSpec`, `PortDef`, `PortSpec`, `Endpoint`, `Position`, `Limits`, `WorkspaceSettings` |
| Settings layers | `AgentSettings`, `GraphSettings`, `ObserveSettings`, `ChatSettings` (+ `queue_after_restart`, `offer_resume`), `EditorSettings`, `DelegationSettings` (+ `max_nesting`, default 3), `FlowSettings` (`max_iterations`, `max_node_runs` default 200, `WorkspaceSettings.flow`, `GraphSettings.flow`), `InteractionSettings`, `UsageSettings`, `UsageSourceSetting`, `UiPreferences` (+ `notifications: NotificationSettings`), `SecretRuleSettings` (`WorkspaceSettings.secrets`), `ObserveSettings.collectors: {id: CollectorSetting}` and `hook_probe`, `EffectiveSettings`, `SettingsLayerInfo` |
| Resources | `Resource`, `ResourceAttachment`, `ResourceContentRef`, `ResourceBundle`, `BundleSource`, `ResourceSummary`, `ResourceFile` (multi-file bodies) |
| Descriptors | `NodeTypeDescriptor` (+ `role`, `executable`, `binds`, `rerunnable`), `EdgeTypeDescriptor` (+ `scheduling`, `invocation`, `connects`, `interaction`, `default_ports`, `reply_fields: ReplyFields`, `cycle: CyclePolicy`, `handles_failure`), `BackendDescriptor` (`BackendCapabilities` + `subagents`, `resource_slots`, `interactions`, `host_tools`, `collectors: CollectorDescriptor[]`), `DelegationStrategyDescriptor` (+ `composable`), `ConditionOperatorDescriptor`, `ResourceTypeDescriptor` (`ResourceContentSpec.multi_file`), `InteractionKindDescriptor`, `UsageSourceDescriptor`, `ModelInfo`, `UiHints` |
| Runtime | `Run` (+ `conversation_id`, `resumed_from`, `parent_node_id`, `root_run_id`, `host_id` (0.12.1)), `NodeRun` (+ `call`, `invoked_by`), `RunSnapshot` (+ `children`), `WaitInfo`, `Usage` (+ `total_tokens`), `ErrorInfo`, `Issue` (+ `suggestions: IssueSuggestion[]`, `GraphPatch` (+ `unset_node_fields`, 0.12.2), `blocks_run`, `hint` and `group` (0.12.2)) |
| Projects (`projects`, 0.8.0 → 2.0.0 in 0.11.0 → 3.0.0 in 0.12.0 → 3.1.0 in 0.12.1 → 3.2.0 in 0.13.2 → 4.0.0 in 0.15.0 → 4.1.0 in 0.16.0) | 4.1 (additions only): `CopyKindInfo.reserved_ids` (from the kind data `DefinitionKind.reserved_ids`, case-insensitive) and `CopyKindInfo.open_role` (web route role of the screen that opens an item of that kind, from `DefinitionKind.open_role` or `KindContribution.open_role`; null = none). 4.0: removed the move and delete plans (`MovePlan`, `MovePlanRequest`, `DefinitionMove`, `DeletePlan`, `ProjectDeleteMode`) and the re-exported `ProjectPreferences` and `DefinitionScope` (cleaning up the old `project` field uses the copy plan). 3.2 (additions only): copy dialog metadata `CopyKindInfo{kind, library, portable}` and `CopyItem{kind, id, name, description, saved_at?}`. 3.1 (additions only): records database state `ProjectView{config_dir?, records_state, records_writable, records_issue?}` (`KnownProjectRecordsStates`), `ProjectRecordsUnavailableDetails` (`KnownRecordsUnavailableReasons`), moving old records `RecordsMoveRequest` and `RecordsMoveResult`, folder checks `FolderCheck{existing?: ExistingProjectProbe, suggested_id?, config_dir?}` (`KnownExistingProjectStates`), recreating the settings file `ManifestResetRequest` and `ManifestResetResult`. 3.0: project = a local folder + the configuration copies inside it. App registry `ProjectRegistration{id, folder, archived, archived_at, labels}`, folder manifest `ProjectManifest{format, id, name, description, settings, attributes}` (both preserve unknown keys), combined view `Project{folder (required key; reads and migrates the old `working_directory`; null in old files), name, description, settings, archived, archived_at, labels, attributes}` (the old `log_projects`, `uses`, and `import_mode` are read and dropped: `IGNORED_PROJECT_KEYS`, `ignored_project_keys`), `ProjectCreate{folder required, id and name optional}`, `ProjectUpdate{folder, archived …}`, status `ProjectView{project, status, status_detail?, version_hash?, config_writable, manifest_id?, kinds, issues}` (`KnownProjectStatuses`), copying between spaces `CopyPlanRequest{source, target: SpaceRef, items, include_references}`, `CopyPlan`, `CopyApplyRequest`, `CopyApplyResult` (`KnownCopyActions`, `KnownCopyTargetStates`, `KnownCopyStatuses`), folders `FolderCheckRequest{path, create, exclude_project_id?}`, `FolderCheck{… nearest_existing?, problem, status, conflict?}`, `FolderListing`, `FolderEntry`, `FolderRoot`, folder picking `FolderCapabilities`, `FolderPickRequest`, `FolderPickResult` (`KnownFolderPickStatuses`), error details `ProjectNotImportedDetails{…, in_library}`, `ProjectFolderConflictDetails`, `ProjectFolderUnavailableDetails`, `ProjectOutsideFolderDetails`, old records `AssignProjectRequest`, `AssignProjectResult`, `ProjectCounts`, key `DefinitionKey`. The definition scope is `Agent`, `Graph`, `Resource.project` (omitted = shared; when not set, absent even from full serialization), and run and conversation `project_id` (an opaque string) |
| Architecture map (`architecture`, 0.9.0) | User data (unknown keys preserved): the settings section `ArchitectureSettings{include_defaults, default_profile, profiles: {id: ArchitectureProfile \| null}}`, `ArchitectureProfile` (`canvas`, `zones: ArchitectureZone[]`, `cells: {id: ArchitectureCell}`, `edges: ArchitectureEdge[]` (`from` alias, `points`, `label_at`, `label_max_w`), `coverage: {source kind: ArchitectureCoverage}`, `source_priority`, `error_when`, `group_limit`, `unassigned`, `options`), `ArchitectureDrill`, `ArchitectureUnavailable`. Projection results (self-contained for drawing) `ArchitectureView`, `ArchitectureCellView`, `ArchitectureEdgeView`, `ArchitectureGroupView`, `ArchitectureMetric{status, value: may be null, detail?}` (null is not 0), `ArchitectureSelector{arch, arch_group?, arch_sources?}`, `ArchitectureMembership`, `ArchitectureNote`. REST `ArchitectureProfileInfo`, `ArchitectureProfileList`, `ArchitectureProfileDetail`, `ArchitectureProfileCheckRequest`, `ArchitectureProfileCheckResult`, `ArchitectureProjectRequest`, `ArchitectureScopeTooLargeDetails`. Documentation constants `KnownArchitectureMetrics`, `KnownArchitectureEdgeKinds`, `KnownArchitectureOrigins`, `KnownArchitectureTargets`, `KnownArchitectureNoteCodes`, `KnownArchitectureIssueCodes` |
| Shared memory (`memory`, 0.10.0, 1.1.0 in 0.12.0) | User data (unknown keys preserved): the settings section `MemorySettings{include_default_scope_kinds, scope_kinds: {id: MemoryScopeKindSpec \| null}, secrets, max_versions_per_entry, retention: MemoryRetentionSettings{rules: MemoryRetentionRule[]}}`, the config of the resource kind `memory` `MemoryAccessConfig{scopes: MemoryScopeAccess[], default_scope, result_header, max_result_chars, tools: MemoryTools}` (default tool names and descriptions are the package data `memory_access_defaults()`). Entries `MemoryEntry`, `MemoryEntrySummary`, `MemoryEntryPage`, versions `MemoryVersion`, `MemoryVersionSummary`, scopes `MemoryScopeRef` (`<kind>:<id>`), `MemoryScopeSummary`, `MemoryScopeKindInfo`, `MemoryScopeKindList`, author `MemoryAuthor`, context `MemoryAccessContext`, REST `MemoryWriteRequest`, `MemoryUpdateRequest`, `MemoryMoveRequest`, `MemoryRetentionPlanRequest`, `MemoryRetentionPlan`, `MemoryRetentionResult`, `MemoryImportResult`, `MemoryTagList`, `MemorySecretRejectedDetails`, events `MemoryEventPayload` (no body or raw query) and `KNOWN_MEMORY_EVENT_TYPES` (outside the runs list), WS `MemoryChanged`. 1.1.0: copying between spaces `MemoryCopyRequest{source, target: SpaceRef, filter: MemoryCopyFilter, on_conflict, remap: MemoryScopeRemap[]}`, `MemoryCopyResult{copied, skipped, conflicts: MemoryCopyConflict[], issues}`, the REST query `project=` |
| Specs (`sdd`, 0.13.0 → 1.1.0 in 0.13.2 → 1.4.0 in 0.16.0) | 1.4 (additions only): `SddInfo.reserved_template_ids` (reserved document template ids, server path vocabulary). 1.1 (additions only): `ImportFileListing.dirs: ImportDir[]`, `SpecTemplateCreateRequest`. 1.0: user data (unknown keys preserved): document templates `SpecTemplate` and specs `SpecDefinition` (`documents: SpecDocument[]`, `rules: SpecRules`), rules `SpecRules{syntax?, document_states?, initial_document_state?, transitions?, task_statuses?, gates?, run_profiles?, verification?, automation?}` (omitted = user settings → the default syntax), task syntax `SpecSyntax{task: TaskSyntax, requirement: RequirementSyntax, stage: StageSyntax}`, `TaskStatusSpec`, `DocumentStateSpec`, `StateTransition` (`from` alias), `SpecGate{require: ConditionSpec}`, `RunProfile{graph, when?, input, purpose?, status_on}`, `VerificationConfig`, `AutomationConfig`, the settings section `SddSettings`. Views `SpecSummary`, `SpecView` (resolved `task_statuses` and `document_states`, `automation_state?`), `SpecIndex`, `ParsedTask`, `EffectiveSyntax`, `TaskPlan`, `TraceMatrix`, `VerificationResult`, `SddInfo{limits, capabilities, label_display}`, `SpecTemplateSummary`, `TemplateVariable`, `ImportFileListing`, REST requests and results (`SpecCreateRequest`, `TaskPatch`, `TaskAction*`, `BulkActions*`, `BulkStart*`, `SaveAsTemplate*`, `SpecDocumentContent`, and so on), error details `SddGateBlockedDetails`, `SddTaskChangedDetails`, `SddDocumentMissingDetails`, WS `SddChanged`. Documentation constants `KnownDocumentRoles`, `KnownTaskFieldRoles`, `KnownGateTargets`, `KnownTransitionActors`, `KnownTraceGaps`, `KnownTaskLinkKinds`, `KnownAutomationStopReasons`, `KnownSyntaxSources`, `KnownTaskActionStatuses` (→ `x-constants`). Run labels `Run.labels` and `CreateRunRequest.labels` (`RUN_LABEL_LIMITS`, `run_label_problems`), pages `RunPage` and `ConversationPage{items, next_cursor, source: RecordSource}`, `ModuleInfo.description` and `label_display: LabelDisplay[]` (no web paths), `LogSourceInfo.default_effective`, `KnownUiWidgets` (`x-constants.KNOWN_UI_WIDGETS`), `x_ui(item_title=)` |
| Wiki (`wiki`, 0.14.0 → 1.3.0 in 0.15.0) | 1.3: `WikiInfo.wiki_kind` and `reserved_page_names`, graph `?depth=all` (`WIKI_GRAPH_DEPTH_ALL`) and `WikiGraph.depth`, `WikiRuleEntry.severity: IssueSeverity`. User data (unknown keys preserved): wikis `WikiDefinition{home?, rules}`, wiki rules `WikiRulesDefinition{instructions?, page_templates, write_rules: WikiWriteRule[], lint_rules: WikiLintRule[], syntax?}`, syntax `WikiSyntax` (every key None = inherit, `WikiLinkRule`, `WikiFrontMatter`, `WikiScheme`, `WikiLintDefaults`), the settings section `WikiSettings`, the config of the resource `wiki` `WikiAccessConfig` (default tool names and descriptions are the package data `wiki_access_defaults()`). Views `WikiInfo`, `WikiSummary`, `WikiView`, `WikiPageList`, `WikiPageView`, `WikiLink` (UTF-16 ranges), `WikiPageVersion`, `WikiAuthor`, `WikiChangePage`, `WikiSearchResult`, `WikiGraph`, `WikiLintReport`, `WikiIssue{page?, line?, rule_id?}`, `EffectiveWikiSyntax`, REST `WikiCreateRequest`, `WikiPageWrite`, `WikiMoveRequest`, `WikiMoveResult`, `WikiRestoreRequest`, `WikiScanResult`, `WikiImportResult`, `WikiRulesCheck*`, `WikiRuleRejectedDetails`, events `WikiEventPayload` (no body) and `KNOWN_WIKI_EVENT_TYPES`, WS `WikiChanged`. Documentation constants `KnownWiki*`, `WIKI_*_SUBJECT_PATHS` |
| Message catalogs (`i18n`, 0.16.0) | `I18nInfo{languages, default_language, fallback_language}` (`GET /i18n`), `LanguageInfo{code, sources, complete, missing?}` (`missing` = missing or empty messages compared with the fallback language, null = not counted), `MessageCatalog{language, text, codes, ns}` (`GET /i18n/{lang}`; an unknown language is 404 `i18n.unknown_language`). The contract has no language list. Uses only `common` |
| Error fixes and pre-checks (0.8.0) | `Fix{actions}`, `FixAction{label, target, focus?}`, `FixTarget{role, id?, section?}` (`ErrorInfo.fix`, `Issue.fix`), `BackendUnresolvedDetails{nodes, options}` (`ErrorCodes.BACKEND_UNRESOLVED`, 422) |
| Schema extension `x-ui` (0.8.0) | `x_ui(tier=, when=, example=, group=, group_title=, order=, unit=, enum_labels=, widget=)` (`widget` in 0.9.0) → `Field(json_schema_extra=...)`, keys `X_UI`, `XUiKeys`, `X_UI_TIERS` (basic, advanced) |
| Conditions (0.7.0) | `ConditionSpec{all?, any?, negate?}`, `ConditionItem{path, op, value?}` (user data, unknown keys preserved), evidence `ConditionOutcome{result, combinator?, negate?, items?}`, `ConditionItemOutcome`, `ConditionMode` (all, any) |
| Interactions | `Interaction` (+ `node_label`, `root_run_id`), `InteractionStatus`, `InteractionGrant`, `RespondInteractionRequest`, `ReviewDecision`, `INTERACTION_CLOSED_STATUSES` |
| Chat | `Conversation`, `ConversationSummary` (+ `held`), continuation status `ConversationSessions{continuable, items: SessionStatus[]}` (`KnownSessionStates`, 0.12.1), `PostMessageRequest.on_missing_session` (0.12.1), `QueuedMessage.held_reason` (`KnownQueueHoldReasons`, 0.12.1), `ChatTurn` (+ `resumed_from`), `ChatReply`, `SessionRef`, `CreateConversationRequest`, `UpdateConversationRequest`, `PostMessageRequest`, `QueuedMessage` (+ `held`) |
| Observation | `UsageWindowSnapshot`, `UsageReport`, `TokenRollupRow`, `UsageSourceInfo`, `Trace`, `TraceSpan`, `TraceLink`, `HandoffMatrix`, `HandoffCount` |
| Logs (`logs`, 0.6.0) | Events `LogEvent` (`from` alias), `LogDocumentRef`, `LogEventPage`, `LogEventDetail`, `LogEvidenceLink`; sources and classifiers `LogSourceDescriptor`, `LogClassifierDescriptor`, `LogSourceInfo`, `LogSourceStatus`; collection `LogScanReport`, `LogSourceScanResult`; sessions `LogSessionSummary` (`tokens: LogTokenTotals`, `project_id`, `thread_count`; `project` and `LogProjectRef` removed in 0.15.0), `LogTimeline` (`lanes: LogLane[]`); token samples `TokenSample` (`LogEventDetail.usage`); aggregation `LogAggregateRequest`, `LogAggregateRow`, `LogQuerySchema` (`LogDimensionInfo`, `LogMetricInfo`, `LogFilterFieldInfo`); archive `LogArchive` (v1); settings `LogSettings` (`WorkspaceSettings.logs`: `LogSourceSetting`, `LogTaxonomy`, `LogCategory`, `LogDashboard`, `LogWidget`, `LogWidgetQuery`) |
| Events | `RunEvent` (generic form, header `actor`), `KnownRunEvent`/`AnyKnownRunEvent` (discriminated union), per-type `*Event` and `*Payload` (`run.reply`, `run.waiting`, `node.resumed`, `usage.rate_limit`, `interaction.requested·answered·closed`, including in 0.7.0 `edge.skipped`, `loop.iteration`, `loop.exhausted`, `run.child_started`, `run.child_finished`; in 0.9.0 `agent.context_prepared` (resource ids, kinds, sizes, and hashes only, no bodies), `tool_use_id` of `node.*`, `duration_ms` of `agent.message` and `agent.usage`, and the `condition` of `edge.traversed` and `edge.skipped`), `parse_run_event()`, `KNOWN_RUN_EVENT_TYPES` |
| WS | `WsClientMessage`, `WsServerMessage` (run.event, conversation.updated, interaction.updated, logs.ingested, error); topics are decided by server modules (default: `run:`, `conversation:`, `interactions`, `logs`) |
| REST | `ErrorResponse`, `BootstrapResponse`, `ResolvePortsRequest`, `CreateRunRequest`, `VersionedGraph`, `GraphSummary`, `DefinitionVersion`, `VersionConflictDetails`, `AppliedItemInfo`, `DefinitionReference`, `ServerInfo`, `PluginInfo`, `DuplicateGraphRequest`, `MergeStrategyInfo`, v3: `GraphSummary.validation: GraphValidationSummary`, `ServerInfo.warnings`, `BundlePreview`, `TeamPlanSummary`·`EntrySlot`·`AnswerSlot`, `DraftGraphRequest`·`DraftNodeRequest`, `ResumeOptions`·`ResumeNodeOption`·`ResumeRunRequest`, `DefinitionDiff`·`DiffChange`·`ContentChange`·`RestoreVersionRequest` |
| Export | `ExporterDescriptor`, `ExportSelection`, `ExportRequest`, `ExportFile`, `ExportPlan`, `ExportRootInfo`, `ExportWriteRequest`, `ExportResult` |
| Import | `ImportSourceDescriptor`, `ImportPreviewRequest`, `ImportPreview`, `ImportCandidate`, `ImportWarning`, `ImportRequest`, `ImportSelection`, `ImportResult` |
| Constants | `CONTRACTS_VERSION`, `LOG_EVENT_ORDERS` (asc, desc), `LOG_PROJECT_UNGROUPED` (`~ungrouped`), `ErrorCodes` (+ `conversation_busy` and `interaction_closed` = 409), `HTTP_STATUS_BY_ERROR_CODE`, `RUN_ORIGINS` (+ `chat`, `resume`) |
| Documentation constants (Python only, not exported to the schema or TS) | `KnownResourceSlots` (known run bundle slots, + `RULES`), `KnownInteractionKinds` (default interaction kind ids), `KnownUsageTrust`, `KnownModuleStatus`, `KnownLogCategories` (default classifier category ids, not for error detection), `KnownLogTones` (taxonomy `tone`: only `danger` shows errors), `KnownLogDimensions`, `KnownLogMetrics` (default aggregation dimensions and metrics) |
| Documentation constants (also in `x-constants` as name → value tables; still open strings) | `KnownIssueCodes` → `KNOWN_ISSUE_CODES` (`limits.not_enforced`, `resource.slot_unsupported`, `secret.plain_found`, `logs.*`; in 0.7.0 `flow.*`, `condition.*`, `team.*`, `delegation.depth_exceeded`; in 0.8.0 `backend.unresolved`, `project.*`), `KnownSuggestionIds` → `KNOWN_SUGGESTION_IDS` (an empty table since 0.15.0). TS receives them from `@agent-console/contracts/constants` |
| Schema | `build_schema()`, `render_schema()`, `export_schemas(out_dir)`, `check_schemas(out_dir)`, `CONTRACT_MODELS` |

### Settings layers: "omitted = inherit"

All fields of `AgentSettings` and its sub-groups are optional. When omitted, the upper layer's value is used; when present (including null and empty lists),
it is set at that layer. This distinction is kept in `model_fields_set`, so **store and send with `model_dump(exclude_unset=True)`**
(the default `model_dump()` writes omitted fields as null, which turns into "set to null at this layer").
The default merge rules per field are the schema annotation `x-merge` (for example `limits` = `replace`, `resources` = `keyed_attachments`),
and the widening warning rules are `x-widen` on `Limits` fields. `ac-settings` interprets them.

### Log settings: "omitted = inherit"

`WorkspaceSettings.logs` (`LogSettings`) and `ObserveSettings.collectors` and `hook_probe` follow the same rule. Omitted sources follow
the descriptor's `default_enabled`, and an omitted taxonomy follows the default taxonomy. Category, widget kind, dimension, metric, and source ids are
open strings (no enums in the schema). The old project grouping `logs.projects` (including the fixed vocabulary `LogUngroupedPolicy`) was removed in 0.15.0.

### Contracts without names

Edge types, resource kinds, interaction kinds, delegation strategies, usage sources, window names, and import sources are all string ids.
Tests check that these names do not appear as fixed values (enum/const/default) in the contract schema. The only fixed vocabularies are engine semantics
(the 4 values of `EdgeScheduling`, status values, attachment modes, and so on). The behavior modes added in v3 (`ChatSettings.queue_after_restart`,
`ExportFile.action`, `ExportWriteRequest.on_conflict`, `DiffChange.op`) are also fixed vocabularies, not kind ids.
Where reply edges keep reply attributes in their config (`EdgeTypeDescriptor.reply_fields`), whether a node can run again (`rerunnable`),
and export formats (`ExporterDescriptor`) are declared by plugins, and the contracts have no default key names or format names for them.

### Reading old data

`DefinitionModel` does not drop unknown fields, so keys left in an existing `settings.yaml` such as `console` and `default_entry`
are preserved as is. Stored `route.decided` events are read as the generic `RunEvent`.
Keys removed in 0.15.0 and 0.16.0 (`projects`, `logs.projects`, and `default_backend` in `settings.yaml`, `working_directory` and `log_projects` in project files) also
do not make reading fail: common settings preserve them as unknown keys and write them back (reported through `IGNORED_SETTINGS_KEYS` and `ignored_settings_keys`),
and the project registry reads `working_directory` as `folder`. No data migration is needed.
`WorkspaceSettings.default_backend` was removed in 0.16.0 and its value is no longer used; put the same value in `agent_defaults.backend`. `Graph.limits` is the old format;
new data uses `settings.limits`.

### Secret suspicion rules (moved)

Since v3, secret suspicion judgement lives in `ac-secret-rules` (`agent_console_secret_rules`), not in the contracts package.
Only the user rule settings model `SecretRuleSettings` (`WorkspaceSettings.secrets`) remains in the contracts.

## Minimal usage

```python
>>> import tempfile
>>> from pathlib import Path
>>> from agent_console_contracts import Graph, export_schemas, parse_run_event

>>> graph = Graph.model_validate({"id": "g", "name": "예", "nodes": [{"id": "n1", "type": "my-type"}]})
>>> graph.nodes[0].type  # node types are open strings (the registry interprets them)
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
>>> log.from_, log.model_dump(exclude_unset=True)["from"]  # `from` is an alias
(['main'], ['main'])
>>> WorkspaceSettings.model_validate({}).model_dump(exclude_unset=True)  # omitted = inherit
{}
>>> from agent_console_contracts import Agent, x_ui
>>> "project" in Agent.model_validate({"id": "a", "name": "A"}).model_dump()  # omitted = shared
False
>>> x_ui(tier="advanced", unit="초")
{'x-ui': {'tier': 'advanced', 'unit': '초'}}
>>> from agent_console_contracts import TextTemplate, render_text_template
>>> note = TextTemplate(template="{seconds}초 안에 응답이 없었습니다.", params={"seconds": 20.0})
>>> render_text_template(note)  # a sentence with values: source template (translation key) + values
'20초 안에 응답이 없었습니다.'

```

A server text field that mixes in values is sent with `text_templates` (JSON Pointer of the field → the
`TextTemplate` sentences that made it). The template is the translation key, so text an installer changes is
not translated unless a catalog has that template.

Command line: `python -m agent_console_contracts export <dir>` / `check <dir>` (exit 1 when different).

## Forbidden patterns in user-facing text

Design document citations, section numbers, requirement numbers (of the form `R<number>.<number>`), and internal node ids (of the form `'n1'`) must not appear in user-facing text.
The rules live in one place, the package data `data/user_text_rules.json`, and TS tests read the same values through the generated constant `USER_TEXT_RULES`.
The scopes (`scopes`) are `description` (contract and descriptor descriptions) and `messages` (server and web user-facing text).

```python
>>> from agent_console_contracts.user_text import find_forbidden_text
>>> [v.rule for v in find_forbidden_text("자세한 것은 R3.1 참고", scope="description")]
['requirement-id']
>>> find_forbidden_text("'안내원'을(를) 실행할 백엔드가 정해지지 않았습니다.", scope="messages")
[]

```

## Writing settings form help (a guide for plugin authors)

Settings forms are drawn from schemas, not code. If the `config_schema` of node and edge types, resource kinds, usage sources, execution backend options,
and delegation strategies follows the same rules as the contract models, it shows up in the same shape (basic/advanced, descriptions, examples, units).

What to put on each field:

| Key | What | Rule |
| --- | --- | --- |
| `title` | The label (2 to 12 characters) | Required |
| `description` | One sentence on what it does and why you would change it | Required, at most 100 characters, not the same sentence as the label. No internal names (descriptor, registry, `config_schema`, design document numbers). Difficult terms (references to upper layers, SDK, hook, MCP, and so on) are written as their real names or with an explanation, such as "hook (a command that runs before and after tool runs)" (a warning without an explanation) |
| `x-ui.tier` | `basic` (on top) · `advanced` (collapsed) | Required. Only what must be set or is changed often is `basic` |
| `x-ui.when` | One sentence on when to change it ("Change this when …") | Required for `basic` fields (bundled = error, external = warning), recommended for frequently touched advanced fields |
| `x-ui.example` | An example value (filled in when the empty field is clicked) | Required for strings and numbers that can be empty and have no default. For values chosen from a list, state "no example" with `None` |
| `x-ui.group`, `group_title` | Subheading in the advanced area | Optional |
| `x-ui.unit` | Unit (seconds, items, MB) | Optional |

For Pydantic models, put `x_ui()` into `json_schema_extra`; for hand-written schemas, spread it with `**x_ui(...)`.
You can check your own schema with `agent_console_contracts.schema_help.lint_schema_help` (rule data
`data/schema_help_rules.json`). The repository's `uv run poe schema-help-lint` shows violations in contracts and bundled plugins as errors and
violations in external plugins as warnings.

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

## Contract generation pipeline

`uv run poe contracts`: this package → `packages/ts/lib/contracts/schema/agent-console.schema.json` → `packages/ts/lib/contracts/src/generated/contracts.generated.ts`.
`uv run poe contracts-check`: checks that both generated files equal the result of regenerating them from the current code (exit 1 when different). The generated files are committed.

## Development and standalone reuse

This folder is a standalone project. Copy only this folder and the commands below still work. Internal dependencies
are declared as a name plus a version range, so outside the repository pass the wheelhouse (`uv run poe wheels` in the repository → `dist/wheelhouse`)
as a find-links path (`uv sync --find-links <wheelhouse>`). Check inside the repository: `uv run poe portability --package ac-contracts`.

```bash
uv sync                  # includes the dev group (pytest, mypy, ruff, internal packages the tests use)
uv run ruff check . && uv run mypy && uv run pytest
```

## Testing

```bash
uv run pytest packages/py/base/ac-contracts/tests
```
