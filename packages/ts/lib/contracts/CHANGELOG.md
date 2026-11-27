# Changelog: @agent-console/contracts

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). A change that breaks the version
range of an internal dependency bumps the other package's version and is recorded here.

## [0.16.1]
- Contracts 0.16.1 (additions only, the range `^0.16.0` still matches; packages that read the new fields use `^0.16.1`). `runs` 1.10.0, `common` 2.2.0, `i18n` 1.1.0, `logs` 2.1.0.
- New field `ModelInfo.sources?: ("config" | "discovered")[]` (type `ModelSource`): where a model entry comes from. Absent or empty = unknown (older servers).
- New field `BackendCapabilities.model_discovery?: boolean` (absent = `false`): the backend can list its account's models without a model call.
- New types `BackendModelCatalog` (`backend_id`, `models`, `discovery`) and `ModelDiscoveryInfo` (`state`, `fetched_at?`, `expires_at?`, `issues?`; `ModelDiscoveryState` = `"ok" | "stale" | "failed" | "disabled" | "unsupported"`) — the response of `GET /backends/{id}/model-catalog`.
- New constant `KNOWN_ISSUE_CODES.BACKEND_MODEL_DISCOVERY_FAILED` (`backend.model_discovery_failed`).
- New type `TextTemplate` (`@agent-console/contracts/common`): `{ template: string; params?: Record<string, string | number | boolean | TextTemplate | null> }` — the source template (the translation key, placeholders `{name}`) and values of one server sentence that mixes in values.
- New field `text_templates?: Record<string, TextTemplate[]>` on `BackendReadiness`, `BackendProbeResult`, `BackendLoginSession` and `BackendLogoutResult`: JSON Pointer of a text field in that response (`/detail`, `/checks/2/note`, `/message`, `/warnings/0`) → the sentences that made it. Filling them in order (nested templates first, a float with an integral value as an integer, `true`/`false`, `null` as empty, unknown names left as `{name}`) and joining with one space gives the field value. Absent or empty = fixed text only (older servers).
- New field `LogEvent.text_templates?: Record<string, TextTemplate[]>` (`logs` 2.1.0): source template + values of a log `title` or `summary` that mixes in values (`/title`, `/summary`). Absent = no template.
- New field `I18nInfo.source_language?: string | null`: the language of the server source text. Stop source-text lookups at this language; absent/`null` = unknown (older servers), use the whole fallback chain.

## [0.16.0]
- Contracts 0.16.0. Breaking change — internal dependency range `^0.16.0`. `common` 2.1.0, `i18n` 1.0.0 (new), `definitions` 3.0.0, `projects` 4.1.0, `sdd` 1.4.0. The unreleased 0.15.1 is folded into this release.
- Removed: `WorkspaceSettings.default_backend`. Use `agent_defaults.backend`.
- New subpath `@agent-console/contracts/i18n`: `I18nInfo` (`languages`, `default_language`, `fallback_language`), `LanguageInfo` (`code`, `sources`, `complete`, `missing?` — missing or empty messages compared with the fallback language, `null`/absent = not counted), `MessageCatalog` (`language`, `text`, `codes`, `ns`).
- New field `UiPreferences.language?: string | null` (screen language, `null` = follow the browser; widget `language`).
- New constants: `ERROR_CODES.I18N_UNKNOWN_LANGUAGE` (`i18n.unknown_language`, `HTTP_STATUS_BY_ERROR_CODE` 404), `KNOWN_ISSUE_CODES.I18N_CATALOG_UNREADABLE`, `I18N_CATALOG_INVALID`, `I18N_CATALOG_UNKNOWN_SECTION`, `I18N_ENTRY_INVALID`, `I18N_LANGUAGE_INVALID`, `I18N_LOCALES_MISSING`, `I18N_SOURCE_UNAVAILABLE`, `KNOWN_UI_WIDGETS.LANGUAGE` (`language`).
- New fields (from the unreleased 0.15.1): `CopyKindInfo.reserved_ids?: string[]` (reserved ids per kind, case-insensitive), `SddInfo.reserved_template_ids?: string[]` (reserved document template ids). Both absent = empty list (older servers do not send them).
- New field `CopyKindInfo.open_role?: string | null` (`projects` 4.1.0): the web route role of the screen that opens an item of that kind (same vocabulary as `FixTarget.role`). `null`/absent = no screen known (older servers do not send it); the web hides "Open" then, and also when it has no screen for that role.

### BREAKING CHANGE

`WorkspaceSettings.default_backend` is removed. Read and write `agent_defaults.backend` instead. Settings documents that still contain `default_backend` are read by the server and keep the key, but the value is not used (info issue `settings.ignored_key`, `details.replacement = "agent_defaults.backend"`).

## [0.15.0]
- Contracts 0.15.0. Breaking change — internal dependency range `^0.15.0`. `common`, `logs` and `definitions` 2.0.0, `projects` 4.0.0, `memory` and `wiki` 1.3.0.
- Removed types and constants: `MovePlan`, `MovePlanRequest`, `DefinitionMove`, `DeletePlan`, `ProjectDeleteMode`, `ProjectPreferences`, `DefinitionScope`, `LogProjectSettings`, `LogProjectGroup`, `LogProjectRef` and `LogUngroupedPolicy`; the fields `WorkspaceSettings.projects`, `LogSettings.projects` and `LogSessionSummary.project`; `PROJECT_MEMORY_NETWORK_FS`, `PROJECT_SHARED_USES_PROJECT`, `PROJECT_CROSS_PROJECT` and `PROJECT_DEFINITIONS_UNAVAILABLE` in `KNOWN_ISSUE_CODES`; and `KNOWN_SUGGESTION_IDS.PROJECT_MOVE_TO_SHARED` (`KNOWN_SUGGESTION_IDS` = `{}`).
- New fields and constants: `MemoryChanged.space?`, `ERROR_CODES` and `KNOWN_ISSUE_CODES.PROJECT_MEMORY_UNAVAILABLE` (409), `WikiInfo.wiki_kind?` and `reserved_page_names?`, and `WIKI_GRAPH_DEPTH_ALL` (`"all"`) and `WikiGraph.depth?`. `WikiRuleEntry.severity` is `IssueSeverity | null`.

### BREAKING CHANGE

Contracts 0.15.0 removes the project-scope APIs that were deprecated in 0.11–0.12.
Stored data does not need a migration: old keys in `settings.yaml`, `project.yaml`,
and export bundles are still read (kept as unknown keys) and never stop the server
from starting.

**Removed models, fields, and constants**

| Removed | Use instead |
| --- | --- |
| `MovePlan`, `MovePlanRequest`, `DefinitionMove` | Definitions no longer belong to a project. To clean up old definitions that still have a `project` field, use the copy plan: `POST /api/v1/projects/{id}/legacy/plan`, then `POST /api/v1/projects/copy/apply`. |
| `DeletePlan`, `ProjectDeleteMode` | `DELETE /api/v1/projects/{id}` unregisters (archives) a project. It never deletes definitions and takes no `mode`. |
| `WorkspaceSettings.projects` (`ProjectPreferences`, `DefinitionScope`) | Nothing. A new definition is saved in the space where you create it (the shared library or a project). |
| `LogSettings.projects` (`LogProjectSettings`, `LogProjectGroup`) | Nothing. A log session belongs to the registered project whose folder contains its working directory. |
| `LogSessionSummary.project` (`LogProjectRef`) | `LogSessionSummary.project_id`. Get the display name from `GET /api/v1/projects`. |
| `KnownIssueCodes.PROJECT_MEMORY_NETWORK_FS` (`project.memory_network_fs`) | `KnownIssueCodes.PROJECT_NETWORK_FS` (`project.network_fs`). Servers have sent only the new code since 0.12.1. |
| `KnownIssueCodes.PROJECT_SHARED_USES_PROJECT`, `PROJECT_CROSS_PROJECT`, `PROJECT_DEFINITIONS_UNAVAILABLE`, `KnownSuggestionIds.PROJECT_MOVE_TO_SHARED` | Nothing. No server sends them. `KnownSuggestionIds` stays and is currently empty. |
| Python: `Project.working_directory`, `Project.log_projects` | `Project.folder`; `log_projects` was always empty. Files that still use `working_directory` are read as `folder`. |

**Removed REST endpoints**

`POST /api/v1/projects/move-plan`, `POST /api/v1/projects/move`, and
`POST /api/v1/projects/scope-issues` are gone. They now answer
`405 Method Not Allowed` because the path matches `/api/v1/projects/{id}`.

**Settings that are read and ignored**

If your workspace `settings.yaml` still has `projects` (for example
`projects.new_definition_scope`) or `logs.projects`, the server starts, ignores the
key, and reports an info issue `settings.ignored_key` with `details.key`. Remove the
key when convenient. Old project-file keys keep their behavior: `working_directory`
is read as `folder`; `log_projects`, `uses`, and `import_mode` are dropped on save.

**Dependency ranges**

0.x contract minors are not compatible with each other. Update plugins to
`agent-console-contracts>=0.15,<0.16` (Python) and `@agent-console/contracts@^0.15.0`
(TypeScript). A 0.15 web app connected to a 0.14 server, or the reverse, shows the
contract version warning.

**Also in 0.15.0 (additive)**

- `MemoryChanged.space`: the memory space of the change (`null` = shared library).
- Error and issue code `project.memory_unavailable` (409): a project's memory
  database cannot be opened. It replaces `feature_unavailable` for that case.
- `WikiInfo.wiki_kind` and `WikiInfo.reserved_page_names`.
- Wiki graph: `GET …/graph?depth=all` (constant `WIKI_GRAPH_DEPTH_ALL`) and
  `WikiGraph.depth`. Omitting `depth` still means 1.
- `WikiRuleEntry.severity` is now `"error" | "warning" | "info" | null`.
- `LOG_PROJECT_UNGROUPED` (`~ungrouped`) is no longer deprecated. It is the log filter
  value for sessions outside every registered project folder.

## [0.14.12]
- Contracts 0.14.12. Additions only. The internal dependency range stays `^0.14.0`. `modules` 1.7.0.
- New type: `PluginOptionsView{extension, name, settings_key, schema?, values?, configured?, yaml_snippet?}` — a read-only view of the options of plugins that declare settings (secret value providers and others). `ServerInfo.plugin_options?: PluginOptionsView[]` (omitted = empty list).

## [0.14.11]
- Contracts 0.14.11. Additions only. The internal dependency range stays `^0.14.0`. `common` 1.16.0.
- New constants: `KNOWN_ISSUE_CODES.WIKI_UNKNOWN_TITLE_SOURCE` (`wiki.unknown_title_source`) and `WIKI_REDACTED_CONTENT` (`wiki.redacted_content`). The wiki event status `WikiEventStatus` is unchanged (refusing masked content = `secret_rejected` + a reason code).

## [0.14.10]
- Contracts 0.14.10. Additions only. The internal dependency range stays `^0.14.0`. `projects` 3.7.0.
- New type: `CopyItemReferences{items?: CopyItem[], checked?: boolean, warnings?: Issue[]}` — the response of `GET /projects/copy/items/{kind}/{id}/references` (definitions in the same space that use this item).

## [0.14.9]
- Contracts 0.14.9. Additions only. The internal dependency range stays `^0.14.0`. `sdd` 1.3.0, `memory` 1.2.0, `common` 1.15.0.
- New optional fields: `TaskSyntax.status_pattern?`, `status_format?` and `field_format?: string | null`, `RunProfile.document_state_on?: Record<string, DocumentStateOnRun>` (new type `DocumentStateOnRun{document, to}`), and `MemoryRetentionSettings.auto?: MemoryRetentionAuto` (`library?` and `projects?: boolean`, `exclude_projects?: string[]`).
- New constants: `KNOWN_ISSUE_CODES.SDD_STATUS_PATTERN_IGNORED` (`sdd.status_pattern_ignored`) and `KNOWN_ISSUE_CODES.SDD_DOCUMENT_STATE_NOT_APPLIED` (`sdd.document_state_not_applied`).

## [0.14.4]
- Contracts 0.14.4. Additions only. The internal dependency range stays `^0.14.0`. `projects` 3.4.0.
- New optional fields: `CopyPlanItem.blocked?: boolean` (an item that cannot be applied; when true, `default_action` = skip) and `CopyPlanItem.issues?: Issue[]` (item issues, for example the error `secret.plain_found`, without the value).

## [0.14.3]
- Contracts 0.14.3 (follow-up to `plugins.disabled`). Additions only. The internal dependency range stays `^0.14.0`. `modules` 1.6.0.
- New optional field: `PluginInfo.reason?: string | null` (why a skipped or disabled plugin is off). The `status` description mentions `plugins.disabled`.

## [0.14.2]
- Contracts 0.14.2. Additions only. The internal dependency range stays `^0.14.0`. `wiki` 1.2.0, `common` 1.12.0.
- New optional fields: `WikiInfo.rules_kind?: string | null`, `WikiRuleEntry.applies_to?`, `path?` and `title?`, `WikiLintReport.partial?`, `skipped?` and `enabled_checks?`, and `WikiGraphNode.scheme_target?: LabelDisplayTarget | null`.
- New constants: `KNOWN_ISSUE_CODES.WIKI_LINT_FAILED` (`wiki.lint_failed`) and `KNOWN_WIKI_LINT_CHECKS` (generated names follow the generator).

## [0.14.1]
- Contracts 0.14.1. Additions and a default change. The internal dependency range stays `^0.14.0`. `wiki` 1.1.0, `common` 1.11.0.
- **Default change (stronger security)**: the default of the schema `WikiSettings.secret_scan` gained `system: "reject"` (`{user: warn, agent: reject, system: reject}`). The default shown in the web settings form changes.
- New optional field: `WikiInfo.writable?: boolean | null` (false = a read-only space, null or omitted = older server).
- New constant: `KNOWN_ISSUE_CODES.WIKI_UPDATE_UNAVAILABLE` (`wiki.update_unavailable`).

## [0.14.0]
- Contracts 0.14.0. Internal dependency range `^0.14.0` (a minor bump: raise the range in consumer package.json files too). New subpath **`@agent-console/contracts/wiki`** (1.0.0). `common` 1.10.0, `projects` 3.3.0, `sdd` 1.2.0, `modules` 1.5.0.
- New types: all of `wiki` (`WikiDefinition`, `WikiRulesDefinition`, `WikiSyntax`, `WikiSettings`, `WikiAccessConfig`, `WikiInfo`, `WikiPageView`, `WikiLink`, `WikiPageVersion`, `WikiGraph`, `WikiSearchResult`, `WikiLintReport`, `WikiMoveResult`, `WikiEventPayload`, `WikiChanged` and others), and `WikiChangedMessage` (modules, added to the `WsServerMessage` union).
- Design decisions applied: `WikiPagePreview`, `WikiLinkText`, `WikiTemplateRender`, `WikiRulesListItem`, `WikiRulesView`, `WikiHistoryPage`, `WikiImportItem`, `WikiPageNotFoundDetails`, `WikiTextRange` and others; `WikiLink.status`, `label`, `outside` and `suggested_path`; `WikiImportResult` has a single `items` list (no four lists). Schema `x-ui.variables` and `x-ui.enum_tones`, and the widget `wiki-rule-refs`.
- New optional fields: `CopyKindInfo.title?` and `SpecTemplateSummary.kind?`.
- New constants: `KNOWN_UI_WIDGETS.WIKI_REF` and `GLOB`, `ERROR_CODES.WIKI_*`, `KNOWN_ISSUE_CODES.WIKI_*` and `TOOLS_INSTRUCTIONS_UNSUPPORTED`, `KNOWN_WIKI_*`, `WIKI_ACCESS_OPS`, `WIKI_WRITE_SUBJECT_PATHS` and `WIKI_LINT_SUBJECT_PATHS`, and `KNOWN_WIKI_EVENT_TYPES`.

## [0.13.2]
- Contracts 0.13.2. Additions only (new fields are optional). The internal dependency range stays `^0.13.0`. `runs` 1.8.0, `definitions` 1.7.0.
- New optional field: `Run.has_children?: boolean | null` (whether there is a direct child run; filled on `GET /runs/page` rows; null or omitted = the server did not fill it).
- New optional field (`definitions` 1.7.0): `GraphSummary.session_summary?: GraphSessionSummary | null` (the session summary `{nodes, delegated: {session value: count}}` of `GET /graphs` rows; null or omitted = not computed, or no edge has a session value). New type `GraphSessionSummary`.
- New optional field (`sdd` 1.1.0): `ImportFileListing.dirs?: ImportDir[]` (the subfolders of the import folder; omitted = older server). New types `ImportDir` and `SpecTemplateCreateRequest`.
- New types (`projects` 3.2.0): `CopyKindInfo` and `CopyItem` (`GET /projects/copy/kinds` and `/projects/copy/items`).

## [0.13.1]
- Contracts 0.13.1 (contract follow-up). Additions only (all new fields are optional). The internal dependency range stays `^0.13.0`. `common` 1.9.0, `definitions` 1.6.0, `sdd` 1.0.1.
- New optional field: `SecretRuleSettings.weak_key_names?: string[] | null` (null or omitted = default data, an empty list = off).
- New constants: `ERROR_CODES.FAKE_SESSION_MISSING` (`fake.session_missing`), and `KNOWN_ISSUE_CODES.RECORDS_SESSION_ARCHIVE_FAILED` (`records.session_archive_failed`) and `RUN_MOVE_BUSY` (`run.move_busy`). `SDD_AUTOMATION_SKIPPED` has existed since 0.13.0.
- Description only: `ParsedTask.issues` (it also holds the issues from the optional method `task_issues` of a task integration).

## [0.13.0]
- Contracts 0.13.0. Internal dependency range `^0.13.0`. New subpath **`@agent-console/contracts/sdd`** (1.0.0). `common` 1.8.0, `logs` 1.2.0, `runs` 1.7.0, `chat` 1.3.0, `modules` 1.4.0.
- New types: all of `sdd` (`SpecTemplate`, `SpecDefinition`, `SpecRules`, `SpecView`, `ParsedTask`, `TaskPlan`, `TraceMatrix`, `SddInfo` and others), `LabelDisplay`, `LabelDisplayTarget` and `RecordSource` (common), `RunPage` (runs), `ConversationPage` (chat), and `SddChangedMessage` (modules, added to the `WsServerMessage` union). New optional fields: `Run.labels`, `CreateRunRequest.labels`, `ModuleInfo.description` and `label_display`, and `LogSourceInfo.default_effective`.
- New constants: `RUN_LABEL_LIMITS`, `RECORD_SOURCES`, `KNOWN_UI_WIDGETS`, `KNOWN_DOCUMENT_ROLES`, `KNOWN_TASK_FIELD_ROLES`, `KNOWN_GATE_TARGETS`, `KNOWN_TRANSITION_ACTORS`, `KNOWN_TRACE_GAPS`, `KNOWN_TASK_LINK_KINDS`, `KNOWN_AUTOMATION_STOP_REASONS`, `KNOWN_SYNTAX_SOURCES` and `KNOWN_TASK_ACTION_STATUSES`, `sdd` in `RUN_ORIGINS`, and the `sdd.*` error and issue codes.
- Request change: the server rejects unknown keys in `CreateConversationRequest` with 422.

## [0.12.2]
- Contracts 0.12.2. Additions only (all new fields are optional). The internal dependency range stays `^0.12.0`. `runs` 1.6.0, `definitions` 1.5.0.
- New optional fields: `DelegationStrategyDescriptor.session`, `backend` and `nestable` (the server fills `session` from `shares_session` and `nestable` from `max_depth`), `EdgeTypeDescriptor.session`, `NodeTypeDescriptor.opens_session` (default true), `Issue.hint` and `group: IssueGroup{key, message}`, and `GraphPatch.unset_node_fields: NodeFieldRef{node_id, path}[]`.
- New constants: `KNOWN_DELEGATION_SESSIONS` (same, separate) and `KNOWN_DELEGATION_BACKENDS` (delegator, target).

## [0.12.1]
- Contracts 0.12.1. Additions only (all new fields are optional). The internal dependency range stays `^0.12.0`. `@agent-console/contracts/projects` 3.1.0, `runs` 1.5.0, `chat` 1.2.0, `common` 1.7.0.
- New types: `ExistingProjectProbe`, `ManifestResetRequest`, `ManifestResetResult`, `RecordsMoveRequest`, `RecordsMoveResult`, `RecordsMoveSelect` and `ProjectRecordsUnavailableDetails` (projects), and `SessionStatus`, `ConversationSessions` and `MissingSessionPolicy` (chat). New optional fields: `ProjectView.config_dir`, `records_state`, `records_writable` and `records_issue`, `FolderCheck.existing`, `suggested_id` and `config_dir`, `Run.host_id`, `PostMessageRequest.on_missing_session`, and `QueuedMessage.held_reason`.
- New constants: `KNOWN_PROJECT_RECORDS_STATES`, `KNOWN_RECORDS_UNAVAILABLE_REASONS`, `KNOWN_EXISTING_PROJECT_STATES`, `KNOWN_SESSION_STATES` and `KNOWN_QUEUE_HOLD_REASONS`; `PROJECT_RECORDS_UNAVAILABLE` and `CHAT_SESSION_UNAVAILABLE` (409) in `ERROR_CODES` and `KNOWN_ISSUE_CODES`; and `PROJECT_NETWORK_FS`, `PROJECT_GITIGNORE_OUTDATED` and `RUN_OTHER_HOST` in `KNOWN_ISSUE_CODES` (info issues only). `PROJECT_MEMORY_NETWORK_FS` is a deprecated alias.

## [0.12.0]
- Contract v11. Raises the internal dependency range to `^0.12.0`. `@agent-console/contracts/projects` 3.0.0, `memory` 1.1.0, `common` 1.6.0.
- Breaking change (projects 3.0): removed `ProjectUse`, `ProjectUseMode`, `ProjectImportMode`, `ProjectUsesUpdate`, `UseCopyRequest`, `UseCopyResult`, `DefinitionCopy`, `LegacyUse`, `LegacyUsesPlan`, `LegacyUsesApplyRequest`, `LegacyUseResult` and `LegacyUsesApplyResult`; removed `uses` and `import_mode` from `Project`, `ProjectCreate` and `ProjectUpdate`; and `reason` and `import_mode` of `ProjectNotImportedDetails` → `in_library`.
- New types: `ProjectRegistration` and `ProjectManifest`, `SpaceRef` (common), `CopyPlanRequest`, `CopyPlan`, `CopyPlanItem`, `CopyApplyRequest`, `CopyApplyItem`, `CopyApplyResult` and `CopyApplyItemResult`, `FolderCapabilities`, `FolderPickRequest` and `FolderPickResult`, and `MemoryCopyRequest`, `MemoryCopyFilter`, `MemoryScopeRemap`, `MemoryCopyResult` and `MemoryCopyConflict`. New optional fields `ProjectView.config_writable`, `manifest_id`, `kinds` and `issues`.
- New constants: `KNOWN_COPY_ACTIONS`, `KNOWN_COPY_TARGET_STATES`, `KNOWN_COPY_STATUSES`, `KNOWN_FOLDER_PICK_STATUSES` and `PROJECT_MANIFEST_FORMAT`; `KNOWN_PROJECT_STATUSES.MANIFEST_INVALID`; `PROJECT_NOT_FOUND`, `PROJECT_MANIFEST_INVALID`, `PROJECT_CONFIG_READONLY`, `PROJECT_COPY_CONFLICT`, `FOLDERS_DIALOG_UNAVAILABLE`, `FOLDERS_DIALOG_BUSY` and `FOLDERS_DIALOG_TIMEOUT` in `ERROR_CODES` and `KNOWN_ISSUE_CODES`; and `KNOWN_ISSUE_CODES.PROJECT_MEMORY_NETWORK_FS` (info issue only).

## [0.11.0]
- Contract v10. Raises the internal dependency range to `^0.11.0`. `@agent-console/contracts/projects` 2.0.0, `common` 1.5.0, `definitions` 1.4.0, `logs` 1.1.0.
- Breaking change (projects 2.0): removed `Project.working_directory` and `log_projects` → `Project.folder: string | null` (a required key); `ProjectCreate.folder` is required (`id` and `name` optional); `ProjectUpdate` lost `working_directory` and `log_projects` and gained `folder`, `uses`, `import_mode` and `archived`.
- New types: `ProjectUse`, `ProjectImportMode`, `ProjectUseMode`, `ProjectStatus`, `ProjectView`, `ProjectUsesUpdate`, `UseCopyRequest`, `UseCopyResult`, `DefinitionCopy`, `FolderCheckRequest`, `FolderCheck`, `FolderConflict`, `FolderListing`, `FolderEntry`, `FolderRoot`, `ProjectNotImportedDetails`, `ProjectFolderConflictDetails`, `ProjectFolderUnavailableDetails`, `ProjectOutsideFolderDetails`, `OutsideFolderPath`, `AssignProjectRequest`, `AssignProjectResult`, `AssignProjectSkip`, `ProjectCounts`, `LegacyUse`, `LegacyUsesPlan`, `LegacyUsesApplyRequest`, `LegacyUseResult` and `LegacyUsesApplyResult`, and `LogSessionSummary.project_id`.
- New constants: `X_PATH`, `X_PATH_KINDS`, `KNOWN_PROJECT_STATUSES`, `KNOWN_FOLDER_CHECK_STATUSES` and `KNOWN_FOLDER_CONFLICT_RELATIONS`, and `PROJECT_*`, `FOLDERS_*`, `SETTINGS_IGNORED_KEY` and `LOGS_NO_PROJECTS` in `ERROR_CODES` and `KNOWN_ISSUE_CODES`.
- `@deprecated`: `LogSettings.projects`, `WorkspaceSettings.projects` and `LogSessionSummary.project`.

## [0.10.0]
- Contract v9. Raises the internal dependency range to `^0.10.0`. New subpath `@agent-console/contracts/memory` (1.0.0), and `modules` 1.3.0 (`memory.changed` in `WsServerMessage`).
- New types (memory): `MemorySettings`, `MemoryScopeKindSpec`, `MemoryRetentionSettings`, `MemoryRetentionRule`, `MemoryAccessConfig`, `MemoryScopeAccess`, `MemoryTools` and `MemoryToolText`; `MemoryScopeRef`, `MemoryAuthor`, `MemoryEntry`, `MemoryEntrySummary`, `MemoryEntryPage`, `MemoryVersion`, `MemoryVersionSummary`, `MemoryScopeSummary`, `MemoryScopeKindInfo` and `MemoryScopeKindList`; REST `MemoryWriteRequest`, `MemoryUpdateRequest`, `MemoryMoveRequest`, `MemoryRetentionPlanRequest`, `MemoryRetentionPlan`, `MemoryRetentionPlanItem`, `MemoryRetentionResult`, `MemoryImportResult`, `MemoryImportProblem`, `MemoryTagList`, `MemoryTagCount` and `MemorySecretRejectedDetails`; the event `MemoryEventPayload` (no content or search text); and WS `MemoryChanged` and `MemoryChangedMessage`.
- New constants: `KNOWN_MEMORY_EVENT_TYPES`, `MEMORY_ACCESS_OPS`, `MEMORY_CONTEXT_FIELDS`, `KNOWN_MEMORY_CONTEXT_FIELDS`, `MEMORY_SCOPE_SEPARATOR` and `MEMORY_ENTRY_SORTS`, `ERROR_CODES.MEMORY_*` (422), and `MEMORY_*`, `TOOLS_*` and `ARCHITECTURE_CONDITION_PATH_UNLISTED` in `KNOWN_ISSUE_CODES`.

## [0.9.0]
- Contract v8. Raises the internal dependency range to `^0.9.0`. Submodule versions `runs` and `common` 1.4.0, and the new subpath `@agent-console/contracts/architecture` (1.0.0).
- New types (architecture): `ArchitectureSettings`, `ArchitectureProfile`, `ArchitectureCanvas`, `ArchitectureZone`, `ArchitectureCell`, `ArchitectureEdge` (key `from`, `points: [number, number][]`), `ArchitectureDrill`, `ArchitectureUnavailable`, `ArchitectureCoverage` and `ArchitectureOptions`; the projection results `ArchitectureView`, `ArchitectureCellView`, `ArchitectureEdgeView`, `ArchitectureGroupView`, `ArchitectureGroupRest`, `ArchitectureUnassignedView`, `ArchitectureUnavailableView`, `ArchitectureSourceCount`, `ArchitectureNote`, `ArchitectureMetric` (`value: number | null`: null means "not collected" and is not turned into 0), `ArchitectureMetricDetail`, `ArchitectureSelector`, `ArchitectureDrillTarget`, `ArchitectureMembership` and `ArchitectureGroupRef`; and REST `ArchitectureProfileInfo`, `ArchitectureProfileList`, `ArchitectureProfileDetail`, `ArchitectureProfileCheckRequest`, `ArchitectureProfileCheckResult`, `ArchitectureProjectRequest` and `ArchitectureScopeTooLargeDetails`.
- New types (runs): `AgentContextPreparedEvent`, `AgentContextPreparedPayload` and `ContextResourceRef`. New fields (optional): `NodeStatusPayload.tool_use_id`, `AgentMessagePayload.duration_ms` and `AgentUsagePayload.duration_ms`. `agent.context_prepared` in `KNOWN_RUN_EVENT_TYPES`.
- New constants: `ERROR_CODES.ARCHITECTURE_PROFILE_NOT_FOUND` (404) and `ARCHITECTURE_SCOPE_TOO_LARGE` (422). The schema key `x-ui.widget` (a screen widget name).

## [0.8.0]
- Contract v7. Raises the internal dependency range to `^0.8.0`. Submodule versions `common`, `definitions` and `runs` 1.3.0, `resources`, `usage`, `chat` and `imports` 1.1.0, `modules` 1.2.0, and the new subpath `@agent-console/contracts/projects` (1.0.0).
- New types: `Project`, `ProjectCreate`, `ProjectUpdate`, `DefinitionKey`, `DefinitionMove` (key `from`), `MovePlan`, `MovePlanRequest`, `DeletePlan` and `ProjectDeleteMode` (projects), `ProjectPreferences` and `DefinitionScope` (definitions), `Fix`, `FixAction` and `FixTarget` (common), `BackendUnresolvedDetails` and `UnresolvedBackendNode` (runs), `UsageSetupSnippet` and `UsageWindowInfo` (usage), and `ModuleOptionsView` (modules).
- New fields (all optional): `Agent`, `Graph` and `Resource.project`, `GraphSummary` and `ResourceSummary.project`, `WorkspaceSettings.projects`, `ApplyPresetRequest.project`, `ImportRequest.project`, `project_id` on `Run`, `CreateRunRequest`, `Conversation`, `ConversationSummary` and `CreateConversationRequest`, `ErrorInfo.fix` and `Issue.fix`, `UiHints.badge`, `BackendDescriptor.cost_note` and `ui_hints`, `EditorSettings.auto_connect_io`, `UsageSourceDescriptor.auto_enable`, `needs_setup`, `test_only`, `setup_snippets` and `windows`, `UsageSourceInfo.last_received_at`, `PresetSummary.badges`, `featured` and `start_graph`, and `DelegationStrategyDescriptor.shares_session` (default true).
- New constants: `ERROR_CODES.BACKEND_UNRESOLVED` (`backend.unresolved`, 422), and `X_UI` (`"x-ui"`) and `X_UI_TIERS`.
- Follow-up: the known issue code and suggestion id tables `KNOWN_ISSUE_CODES` and `KNOWN_SUGGESTION_IDS` (name → open string, including `project.references_unavailable`, `project.definitions_unavailable` and `project.move_to_shared`). The constants-only subpath `@agent-console/contracts/constants` (only the x-constants values, without the schema JSON).
- **Default change**: the default of `UsageIndicatorSettings.value_mode` changed from `remaining` to `used`. Settings that set a value keep it.

## [0.7.0]
- Contract v6. Raises the internal dependency range to `^0.7.0`. Submodule versions `common`, `definitions` and `runs` 1.2.0.
- New types: `CyclePolicy`, `FlowSettings`, `ConditionSpec`, `ConditionItem`, `ConditionOutcome`, `ConditionItemOutcome` and `ConditionMode`, `ConditionOperatorDescriptor`, and the events `EdgeSkippedEvent`, `LoopIterationEvent`, `LoopExhaustedEvent`, `RunChildStartedEvent` and `RunChildFinishedEvent` (with their payloads).
- New fields (all optional): `EdgeTypeDescriptor.cycle` and `handles_failure`, `DelegationStrategyDescriptor.composable`, `BackendCapabilities.host_tools`, `NodeRun.call` and `invoked_by`, `Run.root_run_id`, `RunSnapshot.children`, `Interaction.root_run_id`, `EdgeTraversedPayload.condition`, `NodeStatusPayload.call`, `TraceSpan.iteration`, `call` and `run_id`, `TraceLink.run_id`, `WorkspaceSettings.flow` and `GraphSettings.flow`, and `DelegationSettings.max_nesting`.
- Note: `run.child_started` and `run.child_finished` have the `run.` prefix but are not status events of the parent run (`run.child_finished.status` is the child's status). Code that reads `run.*` as status must leave these two out.

## [0.6.0]
- Contract v5. Raises the internal dependency range to `^0.6.0`.
- Subpath `@agent-console/contracts/logs` (1.0.0): `LogEvent`, `LogEventPage`, `LogEventDetail`, `LogSourceInfo`, `LogScanReport`, `LogSessionSummary`, `LogTimeline`, `LogAggregateRequest`, `LogAggregateRow`, `LogArchive`, `LogSettings`, `LogTaxonomy`, `LogDashboard`, `LogWidget` and others. Submodule versions `definitions` 1.1.0, `runs` 1.1.0, `modules` 1.1.0.
- New fields: `WorkspaceSettings.logs`, `ObserveSettings.collectors` and `hook_probe` (`CollectorSetting`), and `BackendDescriptor.collectors` (`CollectorDescriptor`). WS `logs.ingested` in `WsServerMessage` (`LogsIngestedMessage`).
- `EdgeTraversedPayload.kind` (the edge type id, optional).
- Field additions: `LogCategory.tone`, `LogLane`, `LogTimeline.total` and `truncated`, `LogEventDetail.usage` (`TokenSample`) and `detail_truncated`, `LogSessionSummary.tokens`, `project` and `thread_count`, `LogScanReport.new_events` and `sources[].source_id`, `HandoffCount.from`, `to` and `via`, `LogQuerySchema` (`GET /logs/schema`), and the constants `LOG_EVENT_ORDERS` and `LOG_PROJECT_UNGROUPED`.

## [0.5.1]
- `ERROR_CODES.NOT_READY` (`not_ready`, 503: `GET /health` before the modules start and during shutdown). The meaning of the readiness signal is unchanged (200 = ready).
- Submodule versions `common` 1.1.0, `modules` 1.0.1. Removed `graph:<id>` from the `SubscribePayload.topic` description (the format is still a string).

## [0.5.0]
- Contract v4. Raises the internal dependency range to `^0.5.0`.
- Subpaths `@agent-console/contracts/<submodule>` (common, resources, definitions, runs, usage, chat, exports, imports, modules): the types of that submodule plus `CONTRACT_MODULE` and `CONTRACT_VERSION`. The root still exports everything.
- New types: `ModuleInfo`, `ModuleStatus` and `FeatureUnavailableDetails`, `NodeLayout`, `EdgeLayout` and `GraphUiLayout`, and `VersionUiSettings`. New fields: `NodeSpec.layout` and `EdgeSpec.layout`, `EditorSettings.default_direction` and `default_edge_shape`, `UiHints.direction` and `edge_shape`, and `UiPreferences.versions`.
- `UsageReport.windows` and `rollups` can be `null` (= parts that were not requested, `GET /usage?parts=`).
- New constants: `CONTRACT_VERSIONS`, `USAGE_REPORT_PARTS` and `ERROR_CODES.FEATURE_UNAVAILABLE` (409).

## [0.4.0]
- First release.
