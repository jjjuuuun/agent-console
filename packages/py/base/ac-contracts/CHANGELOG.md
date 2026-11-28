# Changelog

## Unreleased

- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `ac-contracts`, so the web app can show contract schema titles, descriptions and
  `x-ui` hints (by source text) and the `ErrorCodes`, `KnownIssueCodes`, architecture and wiki codes (by code,
  placeholders = `details` keys) in English (data only, no API change).
- Follow-up: 796 more English `text` entries in `locales/en.json` (schema titles, descriptions and `x-ui` hints and
  examples of the models the web app renders; data only).
- Docs only: the `ArchitectureDrill` description no longer contains a stray `" "` (a string concatenation inside the
  docstring); the `en` key follows the fixed text.
- Docs only (`i18n`): `LanguageInfo.complete` and `missing` say that the source language (`I18nInfo.source_language`)
  and its subtags do not count the `text` section (its keys are the source text).

## 0.16.1

- Contracts 0.16.1 (additions only — the internal range stays `>=0.16,<0.17`, TS `^0.16.0`; consumers that
  read the new fields raise their lower bound to `>=0.16.1` / `^0.16.1`). Submodule versions: `runs` 1.10.0,
  `common` 2.2.0, `i18n` 1.1.0, `logs` 2.1.0.
- Added (`runs` 1.10.0): `ModelInfo.sources: list["config" | "discovered"]` (default empty = source unknown,
  for example an older server) — where a model entry comes from: the administrator's configured list, the
  backend account lookup, or both when the server merged them. Type alias `ModelSource`.
- Added (`runs` 1.10.0): `BackendCapabilities.model_discovery: bool = False` — the backend can list the
  models its account can use without calling a model (an optional capability and a new extension point).
- Added (`runs` 1.10.0): `BackendModelCatalog{backend_id, models, discovery}` and
  `ModelDiscoveryInfo{state, fetched_at, expires_at, issues}` (`state`: `ok`, `stale`, `failed`, `disabled`,
  `unsupported`; type alias `ModelDiscoveryState`) — the response of `GET /backends/{id}/model-catalog`. A
  failed lookup is not an error response: the configured list comes back with `state = failed` and a
  warning issue.
- Added (`common` 2.2.0): issue code `KnownIssueCodes.BACKEND_MODEL_DISCOVERY_FAILED`
  (`backend.model_discovery_failed`, warning, `details.backend_id`, `details.reason`), with `ko` and `en`
  messages in `locales/`.
- Added (`common` 2.2.0): `TextTemplate{template, params}` (type aliases `TextParam`, `TextTemplates`) — the
  source template and values of one server sentence that mixes in values. `template` is the server source
  text (the data text as written, placeholders `{name}` only) and is the screen translation key; a `params`
  value is a JSON scalar or a nested `TextTemplate` (a fixed word that is translated too).
- Added (`common` 2.2.0): pure functions `render_text_template(t) -> str` and `render_text_parts(parts) -> str`
  (standard library only). Nested templates are filled first, a float with an integral value is shown as an
  integer (`20.0` -> `20`, `1.5` stays), `true`/`false` for booleans, an empty string for null, a name that is
  not in `params` stays as `{name}`, otherwise Python `str.format` rules (a format spec the value does not
  accept leaves that placeholder as written; a template with unbalanced braces is returned as is).
  `render_text_parts` joins the filled sentences with one space.
- Added (`runs` 1.10.0): `text_templates: dict[str, list[TextTemplate]]` (default empty) on
  `BackendReadiness`, `BackendProbeResult`, `BackendLoginSession` and `BackendLogoutResult`. Key = JSON Pointer
  of a text field in that response (for example `/detail`, `/checks/2/note`, `/message`, `/warnings/0`),
  value = the sentences that made the field; filling them in order and joining with one space gives the field
  value. Fields with fixed text have no entry. String values go through the same secret masking as the field.
  An empty map = fixed text only or an older server.
- Added (`i18n` 1.1.0): `I18nInfo.source_language: str | None` (default null) — the language of the server
  source text (setting `mod-i18n.source_language`). The screen stops source-text lookups at this language
  (that language's catalog included); null = unknown (older server), the whole fallback chain is used.
- Added (`logs` 2.1.0): `LogEvent.text_templates: dict[str, list[TextTemplate]]` (default empty) — source template +
  values of a `title` or `summary` that mixes in values (`/title`, `/summary`), masked like the field. Empty = no
  template (the source gave none, or an event indexed before).

## 0.16.0

- Contracts 0.16.0 (breaking change — internal dependency range `>=0.16,<0.17`, TS `^0.16.0`). Submodule
  versions: `common` 2.1.0, `i18n` 1.0.0 (new), `definitions` 3.0.0, `projects` 4.1.0, `sdd` 1.4.0. The
  unreleased 0.15.1 (reserved ids) is folded into this release.
- Removed (`definitions` 3.0.0): `WorkspaceSettings.default_backend`. The common default execution backend
  is `agent_defaults.backend`. `IGNORED_SETTINGS_KEYS` now also lists `default_backend`, so
  `ignored_settings_keys()` reports it whether or not the model still has the field.
- Added (`i18n` 1.0.0, new submodule on the same layer as `resources` and `logs`, uses only `common`):
  `I18nInfo{languages, default_language, fallback_language}`, `LanguageInfo{code, sources, complete,
  missing?}` (`missing` = number of missing or empty messages compared with the fallback language,
  null = not counted), `MessageCatalog{language, text, codes, ns}` — the merged message catalog a server
  returns from `GET /api/v1/i18n/{lang}`. TS subpath `@agent-console/contracts/i18n`.
- Added (`definitions` 3.0.0): `UiPreferences.language: str | None` (screen language code, null = follow
  the browser; widget `language`, tier basic). The contract has no language list.
- Added (`common` 2.1.0): error code `ErrorCodes.I18N_UNKNOWN_LANGUAGE` (`i18n.unknown_language`, 404,
  `details.language`, `details.available`), catalog loading issue codes `KnownIssueCodes.I18N_*`
  (`i18n.catalog_unreadable`, `i18n.catalog_invalid`, `i18n.catalog_unknown_section`,
  `i18n.entry_invalid`, `i18n.language_invalid`, `i18n.locales_missing`, `i18n.source_unavailable`),
  widget name `KnownUiWidgets.LANGUAGE` (`language`).
- Added (`projects` 4.1.0): `CopyKindInfo.reserved_ids: list[str]` (default empty) — words that must not be
  used as an id of that kind (case-insensitive, compared with `casefold` on the server). It is the
  definition kind data `DefinitionKind.reserved_ids`, contributed kinds included. The copy dialog uses it
  to warn in the new-name field before applying (applying still returns 422 `project.copy_reserved_id`).
- Added (`projects` 4.1.0): `CopyKindInfo.open_role: str | None` (default null) — the web route role of the
  screen that opens an item of that kind (the same open vocabulary as `FixTarget.role`). The server does not
  know web paths: the kind data (`DefinitionKind.open_role`) or the module that contributes the kind
  (`KindContribution.open_role`) supplies it. Null (no such screen, or an older server) or a role the web
  does not know = no "Open" action in the copy list.
- Added (`sdd` 1.4.0): `SddInfo.reserved_template_ids: list[str]` (default empty) — ids a document template
  cannot use (server route words). Creating a template or "save as template" with one of these ids returns
  422 `validation_failed` (`details.reserved`). Works with the SDD screen alone, without the projects
  module.
- Docs only: the first docstring line of `ArchitectureProfile`, `SpecSyntax`, `SpecTemplate`,
  `WikiSyntax`, `WikiRulesDefinition`, `Run`, and `x_path` is English (the generated extension guide reads
  it). The JSON Schema descriptions shown on screen stay the same Korean text; only the `Run` description
  in the schema and the generated TS comment changes.

### BREAKING CHANGE

Contracts 0.16.0 removes `WorkspaceSettings.default_backend`, which was deprecated and only read as a
fallback. Use `agent_defaults.backend` (the execution backend in the common agent settings) instead.

Stored data does not need a migration. A `settings.yaml` or export bundle that still has
`default_backend` is read as before (the key is kept as an unknown key) and the server starts. Since
1.1.0 the server no longer uses the value: it reports an info issue `settings.ignored_key`
(`details.key = "default_backend"`, `details.replacement = "agent_defaults.backend"`). If no other layer
sets a backend, the pre-run check reports `backend.unresolved` with a fix button.

| Removed | Use instead |
| --- | --- |
| `WorkspaceSettings.default_backend` | `WorkspaceSettings.agent_defaults.backend` |

Plugins and API clients must move to contracts 0.16: `agent-console-contracts>=0.16,<0.17` (Python) and
`@agent-console/contracts@^0.16.0` (TypeScript).

## 0.15.0

- Contracts 0.15.0 (breaking change — internal dependency range `>=0.15,<0.16`, TS `^0.15.0`). Submodule
  versions: `common` 2.0.0, `logs` 2.0.0, `definitions` 2.0.0, `projects` 4.0.0, `memory` 1.3.0, `wiki` 1.3.0.
- Removed: `MovePlan`, `MovePlanRequest`, `DefinitionMove`, `DeletePlan` and `ProjectDeleteMode` (projects);
  `WorkspaceSettings.projects`, `ProjectPreferences` and `DefinitionScope` (definitions); `LogSettings.projects`,
  `LogProjectSettings`, `LogProjectGroup` and `LogUngroupedPolicy` (a fixed vocabulary used only by the old grouping
  rules), `LogSessionSummary.project` and `LogProjectRef` (logs); `KnownIssueCodes.PROJECT_MEMORY_NETWORK_FS`,
  `PROJECT_SHARED_USES_PROJECT`, `PROJECT_CROSS_PROJECT` and `PROJECT_DEFINITIONS_UNAVAILABLE`; and
  `KnownSuggestionIds.PROJECT_MOVE_TO_SHARED` (the table stays, empty: `x-constants.KNOWN_SUGGESTION_IDS` = `{}`).
- Added: `MemoryChanged.space`, `ErrorCodes` and `KnownIssueCodes.PROJECT_MEMORY_UNAVAILABLE`
  (`project.memory_unavailable`, 409, `details.project_id` and `details.reason`), `WikiInfo.wiki_kind` and
  `reserved_page_names`, and the constant `WIKI_GRAPH_DEPTH_ALL` (`all`, `x-constants`) and `WikiGraph.depth`.
  Narrowed: `WikiRuleEntry.severity: IssueSeverity | None`. `LOG_PROJECT_UNGROUPED` is no longer deprecated, and its
  description now says "logs that belong to no registered project folder".
- Python only, no schema change: the old common settings keys that are read and ignored, `IGNORED_SETTINGS_KEYS`
  (`("projects", "logs.projects")`), and `ignored_settings_keys(settings, *, section=None)`, which accepts models and
  dicts and gives the same answer whether the field is still on the model (0.14) or removed (0.15). Reading modules
  use this function instead of attribute access to report the info issue `settings.ignored_key`.
- Breaking change, Python only: removed the compatibility attributes `Project.working_directory` and
  `Project.log_projects` (and the same field group on `ProjectManifest` and `ProjectCreate`). Use `folder` instead.
  The `working_directory` of an old file is still read as `folder`, and `log_projects`, `uses` and `import_mode` are
  read and dropped (`IGNORED_PROJECT_KEYS`).

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

## 0.14.12

- Contracts 0.14.12. Additions only, so a patch; the internal dependency range stays `>=0.14,<0.15` (TS `^0.14.0`).
  Submodule versions: `modules` 1.7.0.
- New model (`modules` 1.7.0): `PluginOptionsView{extension, name, settings_key, schema, values, configured,
  yaml_snippet}` — a read-only view of the options of plugins the host sets up directly (secret value providers): the
  schema the plugin declares, the current values with defaults filled in and masked, and the place in the settings
  file. `ServerInfo.plugin_options: list[PluginOptionsView]` (default empty list, so older responses are read as is).

## 0.14.11

- Contracts 0.14.11. Additions only, so a patch; the internal dependency range stays `>=0.14,<0.15` (TS `^0.14.0`).
  Submodule versions: `common` 1.16.0.
- New documented constants (`common` 1.16.0): `KnownIssueCodes.WIKI_UNKNOWN_TITLE_SOURCE` =
  `wiki.unknown_title_source` (warning: an unknown value in the wiki syntax `title_sources` is skipped,
  `Issue.path` = `/title_sources/<i>`, `details.value`) and `KnownIssueCodes.WIKI_REDACTED_CONTENT` =
  `wiki.redacted_content` (the reason for refusing to write content that contains the secret placeholders masked on
  read, `details.lines`). The event status `WikiEventStatus` is not widened: this refusal is `secret_rejected` plus
  a reason code. Both also appear in the schema `x-constants.KNOWN_ISSUE_CODES` (TS `KNOWN_ISSUE_CODES`).

## 0.14.10

- Contracts 0.14.10. Additions only, so a patch; the internal dependency range stays `>=0.14,<0.15` (TS `^0.14.0`).
  Submodule versions: `projects` 3.7.0.
- New model (`projects` 3.7.0): `CopyItemReferences{items: CopyItem[], checked, warnings}` — the response of the
  kind-wide reverse reference route `GET /projects/copy/items/{kind}/{id}/references` (definitions in the same space
  that use this item). The server does not know kind names or reference fields; it uses the registered reference
  extraction (the `references` of kind contributions). `checked` false = no way to check (info
  `project.references_unavailable`).

## 0.14.9

- Contracts 0.14.9. Additions only, so a patch; the internal dependency range stays `>=0.14,<0.15` (TS
  `^0.14.0`). All new fields are optional and omitting them keeps the current behavior (0.14.8 documents are read
  as is). Submodule versions: `sdd` 1.3.0, `memory` 1.2.0, `common` 1.15.0.
- Task syntax (`sdd` 1.3.0): `TaskSyntax.status_pattern` (reading the status from a word at the start of a line,
  named group `status`), `status_format` (the shape inserted into a line without a status) and `field_format` (the
  shape for appending fields). The behavior is implemented in the SDD package.
- Run profile (`sdd` 1.3.0): `RunProfile.document_state_on: dict[run status, DocumentStateOnRun{document, to}]` —
  changing a document state from a run result (implemented in the SDD package). It is not named
  `DocumentStateChange` because the document state transition REST request already uses that name (it pairs with
  `DocumentStateOnEdit`).
- Memory settings (`memory` 1.2.0): `MemoryRetentionSettings.auto` = `MemoryRetentionAuto{library: true,
  projects: true, exclude_projects: []}` — the targets of automatic server cleanup (implemented in the memory
  module).
- New documented constants (`common` 1.15.0): `KnownIssueCodes.SDD_STATUS_PATTERN_IGNORED`
  (`sdd.status_pattern_ignored`, a syntax check warning: no `status` group, or used together with checkboxes) and
  `KnownIssueCodes.SDD_DOCUMENT_STATE_NOT_APPLIED` (`sdd.document_state_not_applied`, info). The
  `SDD_UNKNOWN_STATUS_MARKER` description now mentions words at the start of a line.

## 0.14.8

- Contracts 0.14.8 (run locating). Additions only, so a patch; the internal dependency range stays `>=0.14,<0.15`
  (TS `^0.14.0`). Submodule versions: `runs` 1.9.0, `common` 1.14.0.
- New model (`runs` 1.9.0): `RunLocation{project_id}` — the response of `GET /runs/{id}/locate` (the record space
  that holds the run, null = app records). Used to find the `?project=` of a run detail opened directly by address.
  It has the same shape as `ConversationLocation` of chat but is kept separate so that submodules do not depend on
  each other.
- New error code (`common` 1.14.0): `ErrorCodes.RUN_AMBIGUOUS` (`run.ambiguous`, 409, `details.project_ids`) — the
  same run id is in several record spaces.

## 0.14.7

- Contracts 0.14.7 (conversation locating). Additions only, so a patch; the internal dependency range stays
  `>=0.14,<0.15` (TS `^0.14.0`). Submodule versions: `chat` 1.4.0, `common` 1.13.0.
- New model (`chat` 1.4.0): `ConversationLocation{project_id}` — the response of `GET /conversations/{id}/locate`
  (the record space that holds the conversation, null = app records). Used to find the `?project=` of a
  conversation opened directly by address.
- New error code (`common` 1.13.0): `ErrorCodes.CONVERSATION_AMBIGUOUS` (`conversation.ambiguous`, 409,
  `details.project_ids`) — the same conversation id is in several record spaces.

## 0.14.6

- Contracts 0.14.6 (`If-Match` for kind-wide deletion). Additions only, so a patch; the internal dependency range
  stays `>=0.14,<0.15` (TS `^0.14.0`). Submodule versions: `projects` 3.6.0.
- New optional field (`projects` 3.6.0): `CopyItem.version` (the current version of the item = the version hash in
  that space's definition store, used as is in the `If-Match` of the kind-wide deletion
  `DELETE /projects/copy/items/{kind}/{id}?project=`; null = unknown or an older server).

## 0.14.5

- Contracts 0.14.5 (kind-wide item deletion). Additions only, so a patch; the internal dependency range stays
  `>=0.14,<0.15` (TS `^0.14.0`). Submodule versions: `projects` 3.5.0.
- New optional field (`projects` 3.5.0): `CopyKindInfo.deletable` (items can be deleted in that space through the
  kind-wide deletion route `DELETE /projects/copy/items/{kind}/{id}?project=`; default false = no way to delete, or
  an older server).

## 0.14.4

- Contracts 0.14.4 (early notice of copies blocked by plain-text secrets). Additions only, so a patch; the internal
  dependency range stays `>=0.14,<0.15` (TS `^0.14.0`). Submodule versions: `projects` 3.4.0.
- New optional fields (`projects` 3.4.0): `CopyPlanItem.blocked` (an item that cannot be applied; when true,
  `default_action` is skip) and `CopyPlanItem.issues` (item issues, for example the error `secret.plain_found`
  `details{kind, id, path, reason}`, without the value). The 422 on apply stays.

## 0.14.3

- Contracts 0.14.3 (follow-up to `plugins.disabled`). Additions only, so a patch; the internal dependency range
  stays `>=0.14,<0.15` (TS `^0.14.0`). Submodule versions: `modules` 1.6.0.
- New optional field (`modules` 1.6.0): `PluginInfo.reason` (why a skipped or disabled plugin is off, a sentence for
  people; null = no reason or an older server). The `PluginInfo.status` description now mentions
  `plugins.disabled`.

## 0.14.2

- Contracts 0.14.2. Additions only, so a patch; the internal dependency range stays `>=0.14,<0.15` (TS
  `^0.14.0`). Submodule versions: `common` 1.12.0, `wiki` 1.2.0.
- New optional fields (`wiki` 1.2.0): `WikiInfo.rules_kind` (the definition kind name of wiki rules, null = older
  server), `WikiRuleEntry.applies_to` (write rule glob), `path` (the page template path template) and `title` (the
  source text of the page template display name), `WikiLintReport.partial`, `skipped` (pages that could not be
  checked) and `enabled_checks` (names of enabled checks, null = older server), and `WikiGraphNode.scheme_target`
  (the screen a scheme target opens, the same shape as `WikiLink.scheme_target`).
- New documented constants: `KnownIssueCodes.WIKI_LINT_FAILED` (`wiki.lint_failed`, `common` 1.12.0) and
  `KnownWikiLintChecks` (`lint_rules`, `write_rules`: the names in `enabled_checks` outside the default checks).

## 0.14.1

- Contracts 0.14.1. Additions and a default change, so a patch; the internal dependency range stays
  `>=0.14,<0.15` (TS `^0.14.0`). Submodule versions: `common` 1.11.0, `wiki` 1.1.0.
- **Default change (stronger security)**: the default of `WikiSettings.secret_scan` changed from
  `{user: warn, agent: reject}` to `{user: warn, agent: reject, system: reject}`. Previously there was no `system`
  key, so it followed the `user` value (warn), and agent output moved through the wiki update node (`wiki-update`,
  author system) was saved more loosely than when the agent wrote directly (reject). Now, with the default settings,
  system writes of content with suspected secrets give 422 `wiki.secret_rejected` (the node fails). A workspace that
  sets `secret_scan` itself keeps its values (a missing key still follows the `user` value).
- New optional field (`wiki` 1.1.0): `WikiInfo.writable: bool | None` (the space's `config_writable`, null = older
  server or unknown).
- New documented constant (`common` 1.11.0): `KnownIssueCodes.WIKI_UPDATE_UNAVAILABLE` (`wiki.update_unavailable`,
  no wiki service for the wiki update node).
- Root public alias `Slug` (`from agent_console_contracts import Slug`, the shape of definition ids). The shape is
  unchanged.

## 0.14.0

- Contracts 0.14.0. A new submodule raises the minor version (as with 0.10.0 `memory` and 0.13.0 `sdd`). Internal
  dependency range `>=0.14,<0.15` (TS `^0.14.0`). Submodule versions: **`wiki` 1.0.0** (new), `common` 1.10.0,
  `projects` 3.3.0, `sdd` 1.2.0, `modules` 1.5.0. All fields added to existing models are optional, so 0.13
  responses are read as is.
- `wiki` 1.0.0: user data (unknown keys kept) `WikiDefinition{name, description, home?, rules, attributes}`,
  `WikiRulesDefinition{instructions?, page_templates, write_rules, lint_rules, syntax?}`, `WikiPageTemplate`,
  `WikiWriteRule{applies_to, when?, require?, deny_patterns, action (an open string), message}`, `WikiLintRule`, the
  conditions `WikiWriteCondition` and `WikiLintCondition` (suggested subject paths `WIKI_WRITE_SUBJECT_PATHS` and
  `WIKI_LINT_SUBJECT_PATHS`), the syntax `WikiSyntax{links?, front_matter?, title_sources?, page_extensions?,
  case_insensitive?, schemes?, lint?}` (every key None = inherit), `WikiLinkRule`, `WikiFrontMatter`, `WikiScheme`,
  `WikiSchemeTarget` (a form model with the same shape as `LabelDisplayTarget`) and `WikiLintDefaults`, the settings
  sections `WikiSettings` and `WikiWriteCheckSetting`, and the `wiki` resource config
  `WikiAccessConfig{wikis: WikiAccessEntry[], default_wiki?, include_rules_instructions, path_hint, result_header,
  max_result_chars, tools: WikiToolNames}` (default tool names, descriptions and texts come from the package data
  `data/wiki_access_defaults.json` → schema defaults, `wiki_access_defaults()`). Views `WikiInfo`,
  `WikiCapabilities`, `WikiLimits`, `WikiSummary`, `WikiView`, `WikiRulesSummary`, `WikiRuleRef`, `WikiPageList`,
  `WikiPageSummary`, `WikiPageView`, `WikiLink` (UTF-16 ranges), `WikiBacklink`, `WikiHeading`, `WikiPageVersion`
  (alias `from`), `WikiAuthor`, `WikiChange`, `WikiChangePage`, `WikiSearchResult`, `WikiSearchHit`, `WikiGraph`
  (`total`), `WikiGraphNode`, `WikiGraphEdge` (alias `from`), `WikiIssue(Issue){page?, line?, rule_id?}`,
  `WikiLintReport`, `EffectiveWikiSyntax` and `WikiPageTemplateInfo`. Requests and results `WikiCreateRequest`,
  `WikiPageWrite`, `WikiMoveRequest`, `WikiMoveResult`, `WikiRewrittenPage`, `WikiRestoreRequest`,
  `WikiScanResult`, `WikiImportResult`, `WikiRulesCheckRequest`, `WikiRulesCheckResult` and
  `WikiRuleRejectedDetails`; the run event `WikiEventPayload` (no content or search text), `KNOWN_WIKI_EVENT_TYPES`
  and `WIKI_ACCESS_OPS`; and WS `WikiChanged`. Documented constants `KnownWikiLinkKinds`, `KnownWikiResolvers`,
  `KnownWikiAuthorKinds`, `KnownWikiVersionOps`, `KnownWikiChangeOps`, `KnownWikiLintCodes`,
  `KnownWikiFrontMatterRoles`, `KnownWikiTitleSources`, `KnownWikiWriteActions` and `KnownWikiSyntaxSources`
  (→ `x-constants`). Layer: imports only `common`, `definitions` and `runs` (it does not know `memory` or `sdd`).
- `wiki` 1.0.0, design decisions applied: the pre-save test `WikiPagePreviewRequest`, `WikiPagePreview` and
  `WikiRuleResult`; link insertion `WikiLinkRule.insert`, `WikiLinkTextRequest` and `WikiLinkText`; `WikiLink.label`
  (always filled), `outside`, `suggested_path` and `status` (`KnownWikiLinkStatuses`); `WikiSummary.rules:
  WikiRuleRef[]`, `lint_counts`, `orphans` and `updated_by`; `WikiRulesSummary.entries: WikiRuleEntry[]`
  (`KnownWikiRuleEntryKinds`); the rule list `WikiRulesListItem{counts: WikiRuleCounts, has_instructions, used_by:
  WikiRef[]}` and the single item `WikiRulesView`; `WikiGraphNode.home` and `depth`; the template variables
  `WikiTemplateVariable`, `WikiPageTemplate.variables`, `WikiPageTemplateInfo.variables`,
  `WikiTemplateRenderRequest` and `WikiTemplateRender`; `WikiChange.wiki`; `WikiPageNotFoundDetails{path,
  has_history}`; `WikiPageList.total`; `WikiPageSummary.orphan` and `home`; `WikiSearchHit.marks: WikiTextRange[]`;
  `WikiLintReport.generated_at` and `counts`; `WikiLintDefaults.write_rules`; `WikiImportResult.items:
  WikiImportItem[]` (`KnownWikiImportStatuses`, the four lists removed); `WikiHistoryPage{items, pruned}`; and
  `WikiAuthor.label` = the name at the time of recording. Constants `WIKI_LINK_INSERT_VARIABLES`,
  `WIKI_TEMPLATE_BUILTIN_VARIABLES`, `WIKI_PATH_HINT_VARIABLES` and `WIKI_RESULT_HEADER_VARIABLES`.
- `common` 1.10.0: `XUiKeys.VARIABLES` (`variables`), `ENUM_TONES` (`enum_tones`) and `x_ui(variables=,
  enum_tones=)`, `KnownUiWidgets.WIKI_RULE_REFS` (`wiki-rule-refs`), and the issue codes
  `wiki.link_insert_unavailable` (422), `wiki.home_missing`, `wiki.rule_violation` and `wiki.version_not_found`
  (404). `KnownUiWidgets.WIKI_REF` (`wiki-ref`) and `GLOB` (`glob`). Nine `wiki.*` error codes (HTTP table:
  not_found, page_not_found and version_not_found 404; page_exists, spaces_unavailable, history_unavailable and
  config_readonly 409; rule_rejected, secret_rejected, too_large and link_insert_unavailable 422), `wiki.*` issue
  codes (tool reasons, parsing, checks and rule checks), and `tools.instructions_unsupported`
  (`ToolProvision.instructions`). `sdd.automation_skipped` has existed since 0.13.0.
- `projects` 3.3.0: `CopyKindInfo.title?` (the kind display name, null = the kind name as is).
- `sdd` 1.2.0: `SpecTemplateSummary.kind?` (the definition kind name of the document template, null = not filled).
- `modules` 1.5.0: WS `WikiChangedMessage` (`wiki.changed`).

## 0.13.2

- Contracts 0.13.2. **Additions only**: new fields are optional, so 0.13.1 responses are read as is. The internal
  dependency range stays `>=0.13,<0.14` (TS `^0.13.0`). Submodule versions: `runs` 1.8.0, `definitions` 1.7.0, `sdd`
  1.1.0, `projects` 3.2.0.
- `sdd` 1.1.0: `ImportFileListing.dirs: list[ImportDir] = []` (the immediate subfolders of `GET /sdd/import/files`,
  sorted by name, without hidden, linked or reserved folders; `truncated` is true when either files or folders exceed
  the limit) and the new `ImportDir{name}`. `SpecTemplateCreateRequest{id?, name, description}` (`POST
  /sdd/templates` creates an empty document template, response `SpecTemplate`).
- `projects` 3.2.0: `CopyKindInfo{kind, library, portable}` (`GET /projects/copy/kinds`) and `CopyItem{kind, id,
  name, description, saved_at?}` (`GET /projects/copy/items`) — the copy dialog reads the definition kinds the server
  knows (defaults plus contributed kinds) and their items without a table of kind names.
- `runs` 1.8.0: `Run.has_children: bool | None = None` (whether there is a direct child run, one whose
  `parent_run_id` is this run). `GET /runs/page` fills it by counting the page rows at once (no N+1). null = the
  server did not fill it (the old `GET /runs`, `GET /runs/{id}` and others). It is a read-only display value, not a
  stored one.
- `definitions` 1.7.0: `GraphSummary.session_summary: GraphSessionSummary | None = None` (a session summary for rows
  of the `GET /graphs` list). `GraphSessionSummary{nodes, delegated: {session value: count}}`: session values are
  open strings counted per value (the contract and server do not fix names such as same or separate). null = not
  computed, or no edge has a session value.

## 0.13.1

- Contracts 0.13.1 (contract follow-up). **Additions only**: new fields are optional, so 0.13.0 responses and
  settings are read as is. The internal dependency range stays `>=0.13,<0.14` (TS `^0.13.0`). Submodule versions:
  `common` 1.9.0, `definitions` 1.6.0, `sdd` 1.0.1.
- `definitions` 1.6.0: `SecretRuleSettings.weak_key_names: list[str] | None = None` (key names with a broad
  meaning; null = the package default data `DEFAULT_WEAK_KEY_NAMES`, an empty list = off, a given list replaces it).
  `x-ui` tier advanced.
- `common` 1.9.0 (documented constants): `ErrorCodes.FAKE_SESSION_MISSING` (`fake.session_missing`, a run failure
  `ErrorInfo`, not in the HTTP table), `KnownIssueCodes.RECORDS_SESSION_ARCHIVE_FAILED`
  (`records.session_archive_failed`, info) and `RUN_MOVE_BUSY` (`run.move_busy`, a `failed` item of moving
  records). `SDD_AUTOMATION_SKIPPED` already exists in 0.13.0.
- `sdd` 1.0.1 (description only): `ParsedTask.issues` = parsing issues plus the issues from the optional method
  `task_issues` of a task integration. The protocol is `agent_console_sdd.TaskIssueSource`.

## 0.13.0

- Contracts 0.13.0. A new submodule raises the minor version (as with 0.10.0 `memory`). Internal dependency range
  `>=0.13,<0.14` (TS `^0.13.0`). Submodule versions: **`sdd` 1.0.0** (new), `common` 1.8.0, `logs` 1.2.0, `runs`
  1.7.0, `chat` 1.3.0, `modules` 1.4.0.
- `sdd` 1.0.0: document templates, specs, rules, task syntax and the settings section (unknown keys kept, rule forms
  with `x-ui` that pass `schema-help-lint`); parsing, plan, trace and screen info views; REST requests and results;
  error details; the WS payload `SddChanged`; and nine documented constants (`x-constants`). Status labels have only
  `label` (no `label_key`); the views (`TaskStatusInfo`, `DocumentStateInfo`) always fill it.
- `common` 1.8.0: `LabelDisplay{key, title, target?: LabelDisplayTarget{role, id_from, query?}, group?, order?}` (no
  web paths), `RecordSource` (project, app) and `RECORD_SOURCES`, the documented constant `KnownUiWidgets` (the
  existing 5 plus 8 new: condition, regex, template-text, graph-ref, profile-ref, state-ref, status-ref and tone),
  `XUiKeys.ITEM_TITLE` (`itemTitle`) and `x_ui(item_title=)`, and `UiHints` descriptions in user language. Ten
  `sdd.*` error codes (HTTP table), `sdd.*` issue codes, and `sdd` in `RUN_ORIGINS`.
- `runs` 1.7.0: `Run.labels` (default {}) and `CreateRunRequest.labels` (limits `RUN_LABEL_LIMITS`: 16 keys, 64
  characters per key, 256 characters per value; beyond that a validation error), `run_label_problems()`, and
  `RunPage{items, next_cursor?, source}`.
- `chat` 1.3.0: `ConversationPage{items: ConversationSummary[], next_cursor?, source}`. `CreateConversationRequest`
  rejects unknown keys (`extra=forbid`, 422); the keys sent by the web app, e2e tests and tests (`graph_id`, `title`,
  `project_id`) were checked first.
- `logs` 1.2.0: `LogSourceInfo.default_effective?` (the enabled value without settings).
- `modules` 1.4.0: `ModuleInfo.description?` and `label_display: LabelDisplay[]`, and WS `SddChangedMessage`
  (`sdd.changed`).
- 0.12 responses (without the new fields) are read as is (all fields added to existing models are optional).

## 0.12.2

- Contracts 0.12.2. **Additions only**: all new fields are optional, so 0.12.1 responses are read as is. The
  internal dependency range stays `>=0.12,<0.13` (TS `^0.12.0`). Submodule versions: `runs` 1.6.0, `definitions`
  1.5.0.
- `runs` 1.6.0: descriptor attributes for the screen. `DelegationStrategyDescriptor.session` (an open string; when
  omitted it is filled as same or separate from `shares_session`), `backend` (an open string, delegator or target)
  and `nestable` (when omitted, true when `max_depth` is null or 2 or more). Filled values do not count as set fields
  (`exclude_unset` serialization unchanged). A known value that disagrees with the engine attributes is a validation
  error. `EdgeTypeDescriptor.session` (edge types that are not delegation) and `NodeTypeDescriptor.opens_session`
  (default true). Documented constants `KnownDelegationSessions` and `KnownDelegationBackends` (schema
  `x-constants.KNOWN_DELEGATION_SESSIONS` and `KNOWN_DELEGATION_BACKENDS`).
- `definitions` 1.5.0: `Issue.hint` and `Issue.group: IssueGroup{key, message}` (serialized only when set), and
  `GraphPatch.unset_node_fields: NodeFieldRef{node_id, path}[]` (a JSON Pointer relative to the node config,
  serialized only when set).

## 0.12.1

- Contracts 0.12.1. **Additions only**: all new fields are optional, so 0.12.0 responses are read as is. The
  internal dependency range stays `>=0.12,<0.13` (TS `^0.12.0`). Submodule versions: `projects` 3.1.0, `runs` 1.5.0,
  `chat` 1.2.0, `common` 1.7.0 (error and issue codes).
- `projects` 3.1.0: `ProjectView.config_dir?`, `records_state` (default `ready`, documented constant
  `KnownProjectRecordsStates`), `records_writable` (default true) and `records_issue?`;
  `FolderCheck.existing?: ExistingProjectProbe{state, id?, name?, description?, definitions, issue?}`
  (`KnownExistingProjectStates` found and invalid), `suggested_id?` and `config_dir?`;
  `ManifestResetRequest{name, description?}` and `ManifestResetResult{project, backup_path}`;
  `RecordsMoveRequest{project_id, select: project|null|ids, ids?, remove_source=true}` (ids only, and required, when
  select is ids) and `RecordsMoveResult{moved, skipped, failed: Issue[]}`; and
  `ProjectRecordsUnavailableDetails{project_id, reason, backup_path?}` (`KnownRecordsUnavailableReasons`).
- `runs` 1.5.0: `Run.host_id?`.
- `chat` 1.2.0: `SessionStatus{node_id, backend, session_id?, state}` (`KnownSessionStates`) and
  `ConversationSessions{conversation_id, continuable, items}`, `PostMessageRequest.on_missing_session`
  (`MissingSessionPolicy` fail or fresh, default fail), and `QueuedMessage.held_reason?` (`KnownQueueHoldReasons`
  restart and other_host: values already in the table, now exposed in the contract).
- Error codes (409): `project.records_unavailable` and `chat.session_unavailable`. Info issues (not error codes):
  `project.network_fs` (shared by the memory and record databases, `details.files`), `project.gitignore_outdated` and
  `run.other_host`. `project.memory_network_fs` stays as a deprecated alias (the server sends only the new name).
- `x-constants`: `KNOWN_PROJECT_RECORDS_STATES`, `KNOWN_RECORDS_UNAVAILABLE_REASONS`, `KNOWN_EXISTING_PROJECT_STATES`,
  `KNOWN_SESSION_STATES` and `KNOWN_QUEUE_HOLD_REASONS`.

## 0.12.0

- Contract v11 (project configuration = copies inside the project folder). The internal dependency range is
  `>=0.12,<0.13` (TS `^0.12.0`). Submodule versions: `projects` 2.0.0 → **3.0.0**, `memory` 1.1.0, `common` 1.6.0.
- Removed (no consumers): `ProjectUse`, `ProjectUseMode` and `ProjectImportMode`; `uses` and `import_mode` of
  `Project`, `ProjectCreate` and `ProjectUpdate`; `ProjectUsesUpdate`; `UseCopyRequest`, `UseCopyResult` and
  `DefinitionCopy`; `LegacyUse`, `LegacyUsesPlan`, `LegacyUsesApplyRequest`, `LegacyUseResult` and
  `LegacyUsesApplyResult`; and `ProjectNotImportedDetails.reason` and `import_mode`. The `uses` and `import_mode` (and
  `log_projects`) of old YAML are read and dropped (left out on save). With `IGNORED_PROJECT_KEYS` and
  `ignored_project_keys(doc)`, readers can report a `settings.ignored_key` issue.
- Added (`projects`): `ProjectRegistration{kind, id, folder, archived, archived_at, labels}` (the app registry,
  unknown keys kept), `ProjectManifest{format, id, name, description, settings, attributes}` (the folder manifest,
  unknown keys kept, `PROJECT_MANIFEST_FORMAT` = 1), `ProjectView.config_writable` (default true), `manifest_id`,
  `kinds` and `issues`, the status `manifest_invalid`, copying with `CopyPlanRequest`, `CopyPlan`, `CopyPlanItem`,
  `CopyApplyRequest`, `CopyApplyItem` (`new_id` required for rename), `CopyApplyResult` and `CopyApplyItemResult`,
  folder picking with `FolderCapabilities`, `FolderPickRequest` and `FolderPickResult`, and
  `ProjectNotImportedDetails.in_library`. Documented constants `KnownCopyActions`, `KnownCopyTargetStates`,
  `KnownCopyStatuses` and `KnownFolderPickStatuses` (→ `x-constants`). `DefinitionKey` moved out of the deprecated
  group.
- Added (`common` 1.6.0): `SpaceRef{project_id?}` (null = the shared library).
- Added (`memory` 1.1.0): `MemoryCopyRequest{source, target, filter: MemoryCopyFilter, on_conflict, remap:
  MemoryScopeRemap[]}` (`remap` item key `from`) and `MemoryCopyResult{copied, skipped, conflicts:
  MemoryCopyConflict[], issues}`.
- Error and issue codes: `project.not_found` (404), `project.manifest_invalid` (409), `project.config_readonly`
  (409), `project.copy_conflict` (409, usually an item issue), `folders.dialog_unavailable`, `folders.dialog_busy`
  and `folders.dialog_timeout` (409), and the info issue `project.memory_network_fs` (not an error code).
- Unchanged: the items deprecated in 0.11 (`MovePlan`, `MovePlanRequest`, `DefinitionMove`, `DeletePlan`,
  `ProjectDeleteMode` and others).

## 0.11.0

- Contract v10 (project isolation and the shared library). The internal dependency range is `>=0.11,<0.12` (TS
  `^0.11.0`). Submodule versions: `projects` 1.0.0 → **2.0.0**, `common` 1.5.0 (`x-path`), `definitions` 1.4.0
  (`x-path` annotations, the `projects` section deprecated), `logs` 1.1.0 (`LogSessionSummary.project_id`, grouping
  settings deprecated).
- `projects` 2.0.0 (project = local folder): `Project.folder` (a required key; on read the old `working_directory` is
  moved into it, and old files without a folder get null = status `folder_unset`), `log_projects` removed (read and
  dropped), and the new fields `uses: ProjectUse[]` (`kind` an open string, `mode` ref or pin, pin requires
  `version`, `enabled`, duplicate `(kind, id)` rejected), `import_mode` (explicit by default, or all), `archived` and
  `archived_at`. `ProjectCreate` requires `folder`, with `id` and `name` optional. `ProjectUpdate` gained `folder`
  (change path), `uses`, `import_mode` and `archived` (register again), and lost `working_directory` and
  `log_projects`. The read-only attributes `Project.working_directory` (= folder) and `Project.log_projects` (always an
  empty list), kept for Python consumers, are outside the schema and are to be removed in a later release.
- New DTOs: `ProjectView` (computed status values, documented constant `KnownProjectStatuses`),
  `ProjectUsesUpdate`, `UseCopyRequest`, `UseCopyResult` and `DefinitionCopy`; folders with
  `FolderCheckRequest{path, create, exclude_project_id?}`, `FolderCheck` (the ac-local-folders result plus the
  registry `status` and `conflict: FolderConflict`, `nearest_existing`, no path suggestion fields; paths of other
  operating systems are `invalid` + `foreign_path`), `FolderListing`, `FolderEntry{… project_id?}` and `FolderRoot`;
  error details `ProjectNotImportedDetails{reason?}`, `ProjectFolderConflictDetails`,
  `ProjectFolderUnavailableDetails`, `ProjectOutsideFolderDetails` and `OutsideFolderPath`; moving earlier records with
  `AssignProjectRequest{to, ids | from_null}`, `AssignProjectResult`, `AssignProjectSkip` and `ProjectCounts`; and old
  definition cleanup with `LegacyUse`, `LegacyUsesPlan`, `LegacyUsesApplyRequest`, `LegacyUseResult` and
  `LegacyUsesApplyResult`.
- Deprecated (to be removed in the next major): `MovePlan`, `MovePlanRequest`, `DefinitionMove`, `DeletePlan` and
  `ProjectDeleteMode`, `WorkspaceSettings.projects` (`ProjectPreferences`), `LogSettings.projects`
  (`LogProjectSettings`, `LogProjectGroup`), `LogSessionSummary.project` (`LogProjectRef`) and
  `LOG_PROJECT_UNGROUPED`. Schema `deprecated: true`; reading still works.
- Error codes: `project.required` (422), `project.not_imported` (422), `project.folder_missing` (409),
  `project.folder_taken` (409), `project.folder_overlaps` (409), `project.outside_folder` (422) and
  `folders.remote_disabled` (403), and folder operation failures `folders.<ac-local-folders code>` (not_found 404,
  outside_roots 403, exists 409, io_error 500, the rest 422). `KnownIssueCodes` has the same 7 plus
  `settings.ignored_key` and `logs.no_projects`.
- Schema annotation `x-path` (`X_PATH`, `X_PATH_KINDS`, `x_path()`): `AgentSettings.working_directory` and
  `Limits.directories`.
- `x-constants`: `X_PATH`, `X_PATH_KINDS`, `KNOWN_PROJECT_STATUSES`, `KNOWN_FOLDER_CHECK_STATUSES` and
  `KNOWN_FOLDER_CONFLICT_RELATIONS`.

## 0.10.0

- Contract v9 (shared memory). The internal dependency range is `>=0.10,<0.11` (TS `^0.10.0`). Submodule versions:
  the new `memory` 1.0.0, and `modules` 1.2.0 → 1.3.0 (WS `memory.changed`). The `runs`, `logs` and `definitions`
  models are unchanged, and so is `KNOWN_RUN_EVENT_TYPES`.
- New submodule `memory` (the same layer as `chat`, `exports`, `imports` and `architecture`; uses `common`, `runs`
  (`ConditionSpec`) and `definitions` (`Issue`)).
  - User data (`DefinitionModel`, unknown keys kept, full settings form help): `MemorySettings` (the workspace
    settings section `memory`, owned by the memory module, with no field in the common settings model),
    `MemoryScopeKindSpec` (a scope kind: name, description and id template), `MemoryRetentionSettings` and
    `MemoryRetentionRule` (`when: ConditionSpec`, `action: archive|delete`), and the config `MemoryAccessConfig` of
    the resource kind `memory` (`scopes: MemoryScopeAccess[]`, `default_scope`, `result_header`, `max_result_chars`,
    `tools: MemoryTools`). Default tool names, descriptions and result header lines come from the package data
    `data/memory_access_defaults.json` (`memory_access_defaults()`). The contract has no scope kind names.
  - Entries, versions and scopes: `MemoryScopeRef{kind, id}` (`to_text`, `parse`, `<kind>:<id>`), `MemoryAuthor`
    (`kind` an open string, `KnownMemoryAuthorKinds`), `MemoryEntry`, `MemoryEntrySummary` (`preview`) and
    `MemoryEntryPage`, `MemoryVersion` and `MemoryVersionSummary`, `MemoryScopeSummary`, and `MemoryAccessContext`
    (the context read by scope id templates, `MEMORY_CONTEXT_FIELDS`).
  - REST DTOs: `MemoryScopeKindInfo` and `MemoryScopeKindList`, `MemoryWriteRequest`, `MemoryUpdateRequest` and
    `MemoryMoveRequest`, `MemoryRetentionPlanRequest`, `MemoryRetentionPlan`, `MemoryRetentionPlanItem` and
    `MemoryRetentionResult`, `MemoryImportResult` (`dry_run`) and `MemoryImportProblem`, `MemoryTagList` and
    `MemoryTagCount`, `MemorySecretRejectedDetails{field, rules}` (no values), and the sort values
    `MEMORY_ENTRY_SORTS`.
  - Events: `MemoryEventPayload` (RunEvent `memory.<op>`, **no content or search text**, only sizes and hashes), the
    documented constant `KNOWN_MEMORY_EVENT_TYPES` (not added to the known event list of `runs`), and the WS payload
    `MemoryChanged` (+ `modules.MemoryChangedMessage`).
- Constants: `ErrorCodes.MEMORY_INVALID_KEY`, `MEMORY_TOO_LARGE` and `MEMORY_SECRET_REJECTED` (422); in
  `KnownIssueCodes`, `MEMORY_*` (tool reason codes, `memory.unknown_scope_kind`, `settings_invalid`, `storage_memory`
  and `search_fallback`), `TOOLS_*` (`tools.provider_failed`, `duplicate_name` and `backend_capability_missing`) and
  `ARCHITECTURE_CONDITION_PATH_UNLISTED`. In `x-constants`: `KNOWN_MEMORY_EVENT_TYPES`, `MEMORY_ACCESS_OPS`,
  `MEMORY_CONTEXT_FIELDS`, `KNOWN_MEMORY_CONTEXT_FIELDS`, `MEMORY_SCOPE_SEPARATOR` and `MEMORY_ENTRY_SORTS`.

## 0.9.0

- Contract v8 (architecture map). The internal dependency range is `>=0.9,<0.10` (TS `^0.9.0`). Submodule versions:
  the new `architecture` 1.0.0, `runs` 1.3.0 → 1.4.0 and `common` 1.3.0 → 1.4.0. All new fields are optional, so old
  data is read as is.
- New submodule `architecture` (the same layer as `chat`, `exports` and `imports`; uses `common`, `logs`,
  `definitions` and `runs`).
  - User data (`DefinitionModel`, unknown keys kept at every level): `ArchitectureSettings` (the workspace settings
    section `architecture`, owned by the architecture map module; the common settings model has no field for it and
    it round-trips as an unknown key), `ArchitectureProfile`, `ArchitectureCanvas`, `ArchitectureZone`,
    `ArchitectureCell`, `ArchitectureEdge` (alias `from`), `ArchitectureDrill`, `ArchitectureUnavailable`,
    `ArchitectureCoverage` and `ArchitectureOptions`. Cell and edge kinds, metrics, colors and shape names are open
    strings, and the profile check validates the values. Full settings form help (labels, descriptions and `x-ui`).
  - The zone `description` and the edge `label_max_w` from the screen design are **formal fields** (they are also in
    the projection result).
  - Projection results (complete for drawing): `ArchitectureView`, `ArchitectureCellView`, `ArchitectureEdgeView`,
    `ArchitectureGroupView`, `ArchitectureGroupRest`, `ArchitectureUnassignedView`, `ArchitectureUnavailableView`,
    `ArchitectureSourceCount` and `ArchitectureNote`; metrics `ArchitectureMetric{status:
    observed|inferred|not_collected, value: number|null, detail?}` and `ArchitectureMetricDetail` (null is not 0);
    cell and edge states `observed|partial|not_collected`; the click filter `ArchitectureSelector{arch, arch_group?,
    arch_sources?}`; `ArchitectureDrillTarget`; and event membership `ArchitectureMembership` and
    `ArchitectureGroupRef`.
  - REST: `ArchitectureProfileInfo` (`origin`, `overrides`, `disabled`, `issues`, and the counts of `cells` and
    `edges`), `ArchitectureProfileList`, `ArchitectureProfileDetail`, `ArchitectureProfileCheckRequest` (also accepts
    malformed bodies), `ArchitectureProfileCheckResult`, `ArchitectureProjectRequest` and
    `ArchitectureScopeTooLargeDetails`.
  - Documented constants: `KnownArchitectureMetrics`, `KnownArchitectureEdgeKinds`, `KnownArchitectureOrigins`,
    `KnownArchitectureTargets`, `KnownArchitectureNoteCodes` and `KnownArchitectureIssueCodes`.
- Error codes: `architecture.profile_not_found` (404) and `architecture.scope_too_large` (422, `details` =
  `{events, limit}`).
- `runs` 1.4.0: the new known event `agent.context_prepared` (`AgentContextPreparedPayload{resources:
  ContextResourceRef{id, kind, bytes?, sha256?}[], fragments?}`, **no content**), `NodeStatusPayload.tool_use_id`
  (the delegation tool call id), and `AgentMessagePayload.duration_ms` and `AgentUsagePayload.duration_ms` (ms, null
  when unknown).
- `common` 1.4.0: the `x-ui` key `widget` (`XUiKeys.WIDGET`, `x_ui(widget=)`): a widget name registered by the
  screen; unknown names fall back to the default form.
- Backward compatibility: rereading the events of the 0.6.0 and 0.7.0 reference files only adds `tool_use_id` and
  `duration_ms` as null (they are in the "new keys" list of the reference comparison test). The v7 version test now
  checks "0.8.0 or later", and the v8 test pins the exact value.
- Test-only dependency `ruamel-yaml` (dev group): for round-trip tests of the architecture profile YAML examples.
  PyYAML was the alternative, but no other package in the project uses it, so an existing dependency was reused. The
  runtime dependency is still only `pydantic`.

## 0.8.0

- Subscription sign-in: `BackendCapabilities.login` and `logout` (default false),
  `BackendDescriptor.login_methods: LoginMethodInfo[]` (`id`, `label`, `description`, `notice`, `writes`,
  `needs_browser`), `BackendReadiness.actions: ReadinessAction[]` (`kind` an open vocabulary of login and logout,
  `method_id`, `label`, `primary`), the new models `BackendLoginStartRequest`, `BackendLoginSession` (`phase` the
  closed list `BackendLoginPhase`), `BackendLoginInput` (`text` is `writeOnly` and `x-secret`, at most 2048
  characters, one of `text` and `key`) and `BackendLogoutResult`, and the constant `BACKEND_LOGIN_TEXT_MAX_CHARS`.
  Error codes `backend.login_unsupported`, `backend.login_busy`, `backend.logout_unsupported` and
  `backend.subscription_auth_disabled` (409), and `backend.login_session_not_found` (404). All new fields are
  optional, so this is backward compatible.
- Follow-up: the descriptions of `BackendCapabilities.login` and `logout` now add "when the backend gives a refusal
  reason, that code (for example `backend.subscription_auth_disabled`)" (`ac-runtime` `LoginRefusalAware`). Only the
  text changed; the format is the same.
- Removed the presets feature: `PresetSummary`, `ApplyPresetRequest` and `ApplyPresetResult` and the routes
  `GET /presets` and `POST /presets/{id}/apply`. They are also gone from the generated TS types and JSON Schema.
  Import still uses `AppliedItemInfo` and `ConflictPolicy`. 0.8.0 is not released yet, so the submodule version
  (`definitions` 1.3.0) stays. Removed the samples of the two models from the 0.7.0 reference file (the other samples
  stay).
- Cleanup: moved the README section about removals in 0.4.0 into the 0.4.0 entry of this changelog; the README keeps
  only the explanation of reading old data. No code change.
- List summaries `GraphSummary.attributes` and `ResourceSummary.attributes` (`JsonObject`, default `{}`, optional).
  They are the original `attributes` as is, used for web list folders (`ui.folder`) and grouping by any key. The edit
  time is still the existing `saved_at` (epoch seconds, optional). The new fields are optional, so this is backward
  compatible.
- Follow-up: the documented issue code constants `KnownIssueCodes.PROJECT_REFERENCES_UNAVAILABLE`
  (`project.references_unavailable`) and `PROJECT_DEFINITIONS_UNAVAILABLE` (`project.definitions_unavailable`), and
  the new documented constant `KnownSuggestionIds.PROJECT_MOVE_TO_SHARED` (`project.move_to_shared`). Both are
  exported as name → value tables in `x-constants` (`KNOWN_ISSUE_CODES`, `KNOWN_SUGGESTION_IDS`). Issue codes and
  suggestion ids are still open strings (format unchanged).
- Forbidden user text pattern data `data/user_text_rules.json` and `agent_console_contracts.user_text`
  (`find_forbidden_text`, `scan_forbidden_text`), and the generated constant `USER_TEXT_RULES`. Removed internal
  document references from contract descriptions (format unchanged).
- Contract v7. The internal dependency range is `>=0.8,<0.9` (TS `^0.8.0`). Submodule versions: `common` 1.2.0 →
  1.3.0, `definitions` 1.2.0 → 1.3.0, `runs` 1.2.0 → 1.3.0, `usage` and `chat` 1.0.0 → 1.1.0, `resources` and
  `imports` 1.0.0 → 1.1.0 (`Resource.project`, `ResourceSummary.project`, `ImportRequest.project`), `modules` 1.1.0 →
  1.2.0 (`ModuleOptionsView`), and the new `projects` 1.0.0. All new fields are optional.
- New submodule `projects` (the same layer as `runs` and `usage`, uses up to `definitions`): `Project`,
  `ProjectCreate`, `ProjectUpdate`, `DefinitionKey`, `DefinitionMove` (alias `from`), `MovePlanRequest`, `MovePlan`,
  `DeletePlan` and `ProjectDeleteMode`. `ProjectPreferences{new_definition_scope, fallback}` and `DefinitionScope`
  are in `definitions` because they are a common settings section (`projects` uses `AgentSettings` and `Issue`, so
  this avoids an import in the opposite direction). `projects` re-exports them.
- Definition scope: `Agent`, `Graph` and `Resource.project: Slug | None` (omitted = shared; **when not set it is also
  left out of full serialization**, through the internal base `OmitWhenUnsetModel`, which moves the existing rule of
  `GraphSettings`). `GraphSummary` and `ResourceSummary.project`, `WorkspaceSettings.projects`, and
  `ApplyPresetRequest.project` and `ImportRequest.project`.
- Runs and conversations: `project_id` (an opaque string) on `Run`, `CreateRunRequest`, `Conversation`,
  `ConversationSummary` and `CreateConversationRequest`. The list queries `GET /runs?project=&root_only=` and
  `GET /conversations?project=` are documented on the models.
- Error resolution data: `Fix`, `FixAction` and `FixTarget` (common), `ErrorInfo.fix` and `Issue.fix`. The backend
  pre-check `ErrorCodes.BACKEND_UNRESOLVED` (`backend.unresolved`, 422) and `BackendUnresolvedDetails{nodes:
  UnresolvedBackendNode[], options: BackendDescriptor[]}`. `BackendDescriptor.cost_note` and `ui_hints`, and
  `UiHints.badge`.
- Editor: `EditorSettings.auto_connect_io` (omitted = on), and the `default_edge_shape` description "empty means an
  automatic path". In the team layer they are serialized only when set (`GraphSettings._OMIT_WHEN_UNSET`).
- Usage: **the default of `UsageIndicatorSettings.value_mode` changed from `remaining` to `used`** (the only change
  in meaning; settings that set a value keep it). `UsageSourceDescriptor.auto_enable`, `needs_setup`, `test_only`,
  `setup_snippets: UsageSetupSnippet[]` and `windows: UsageWindowInfo[]`, and `UsageSourceInfo.last_received_at`.
- Preset summaries `PresetSummary.badges`, `featured` and `start_graph`. The delegation strategy
  `DelegationStrategyDescriptor.shares_session` (default true). The read-only module options response
  `ModuleOptionsView{module_id, schema, values, yaml_snippet}`.
- `x-ui` helpers `x_ui(...)`, `X_UI`, `XUiKeys` and `X_UI_TIERS` (also in the schema `x-constants`). The content is
  filled by the next item.
- Settings form help (schema metadata only, no format or serialization change): every field of the definition models
  (models that inherit `DefinitionModel` and the models they reference, `PortDef`, `Endpoint`, `Position` and
  `ResourceContentRef`, plus `UiHints` and `ReviewDecision` used by plugins) has `title`, `description` (100
  characters or less, in user language) and `x-ui.tier` (+ `when`, `example`, `group`, `unit`). The classification
  follows the settings form classification table, and the team layer (`GraphSettings`) shows all inherited agent
  settings in the advanced "Agent defaults" group (model `json_schema_extra`). Developer descriptions (descriptor ids,
  `config_schema`, JSON Pointer and so on) were rewritten as user text.
- New submodule `agent_console_contracts.schema_help`: `lint_schema_help`, `lint_contract_help`,
  `contract_form_roots` and `HelpIssue`, and the rule data `data/schema_help_rules.json` (common forbidden patterns
  also use `user_text_rules.json`). `x-ui.example: null` means "no example (choose from the list)".
- More help: filled `x-ui.when` ("change this when …") for every basic (`basic`) field and for frequently edited
  advanced fields (limits, permissions, backend options, chat, interactions, team settings groups). "Upper layer /
  lower layer" became "common, team and agent settings", and hook, MCP and SDK got short explanations. Added the lint
  rules `missing-when` (basic fields, error) and `hard-term` (difficult terms, warning), `HelpIssue.severity`, and the
  rule data `when_required_tiers`, `hard_terms` (explanation pattern `explained`) and `severity`.
- Tier rebalancing: the new model `AgentDefaults(AgentSettings)` (the same fields, title "Agent defaults") is the type
  of `WorkspaceSettings.agent_defaults`. Through a schema hook only the execution backend is `basic` (+ when). The
  execution backend in agent and team forms stays advanced. It also accepts `AgentSettings` instances (only the set
  fields are moved). The serialization format is the same.
- Documented issue code constants: `backend.unresolved`, `project.shared_uses_project`, `project.cross_project` and
  `project.unknown`.
- Backward compatibility: compared with the 0.7.0 reference file (`tests/fixtures/phase5r_reference.json`).
  Definitions (graphs, agents, resources and team layers) are the same down to full serialization and hashes. Other
  models only gain new fields with defaults, and only a `value_mode` that was not set is read as `used`. The graph
  version hash (`ac-graph`) leaves out `project`.

## 0.7.0

- Contract v6. The internal dependency range is `>=0.7,<0.8` (TS `^0.7.0`). Submodule versions: `common` 1.1.0 →
  1.2.0 (documented issue code constants), `definitions` 1.1.0 → 1.2.0 and `runs` 1.1.0 → 1.2.0. All new fields are
  optional.
- Edge types `EdgeTypeDescriptor.cycle: CyclePolicy{max_iterations ≥ 1, title?}` and `handles_failure`. The
  delegation strategy `DelegationStrategyDescriptor.composable`, and the backend capability
  `BackendCapabilities.host_tools`.
- Run history: `NodeRun.call` (the call count, default 0) and `invoked_by` (the delegator node path),
  `Run.root_run_id` (with descriptions for the existing `parent_run_id` and `parent_node_id`),
  `RunSnapshot.children: Run[] | null` (null = the server did not fill it), and `Interaction.root_run_id`. The
  `RunSummary` and `RunDetail` of earlier drafts are the current list and detail response models `Run` and
  `RunSnapshot`.
- Events (known shapes): `loop.iteration{edge_id, iteration, nodes}`, `loop.exhausted{edge_id, iteration,
  max_iterations?}`, `run.child_started{child_run_id, node_id, graph_id?}` (no status),
  `run.child_finished{child_run_id, node_id, status}` (`status` = the child run status) and `edge.skipped{edge_id,
  source, target, kind?, reason?, condition?}`. `edge.traversed.condition`, and `call` in `node.*` payloads.
- Conditions: `ConditionSpec{all?, any?, negate?}` and `ConditionItem{path (JSON Pointer), op (an open string),
  value?}` (definition data, unknown keys kept), the decision evidence `ConditionOutcome{result, combinator?, negate?,
  items?[{path, op, value?, actual?, result, mode?, reason?}]}`, and `ConditionOperatorDescriptor{id, title,
  description, value_schema, applies_to?, ui_hints?}` (`GET /condition-operators`).
- Trace: `TraceSpan.iteration`, `call` and `run_id`, and `TraceLink.run_id`.
- Settings: `FlowSettings{max_iterations?, max_node_runs? (default 200)}` (`WorkspaceSettings.flow`,
  `GraphSettings.flow`) and `DelegationSettings.max_nesting` (default 3, null = no limit). All are "omitted =
  inherit".
- Documented issue code constants: `flow.max_iterations_invalid`, `flow.max_node_runs_exceeded`,
  `condition.unknown_operator`, `condition.invalid_value`, `team.mixed_strategies`, `team.recursive`,
  `team.nesting_exceeded`, `team.team_not_found`, `team.child_no_entry` and `delegation.depth_exceeded`.
- Backward compatibility: compared with a reference file read and written with the 0.6.0 contract
  (`tests/fixtures/phase4r_reference.json`). Definitions (graphs and agents) are the same down to full serialization
  and hashes, because `GraphSettings` does not serialize `flow` and `delegation.max_nesting` when they are not set
  (the graph version hash is computed from full serialization). Full serialization of run history, descriptors and
  `WorkspaceSettings` gains the new fields with defaults (the `exclude_unset` storage format and hashes are
  unchanged), and events from 0.6.0 are read in the same shape.

## 0.6.0

- Contract v5. The internal dependency range is `>=0.6,<0.7` (TS `^0.6.0`). Submodule versions: the new `logs`
  1.0.0, `definitions` 1.0.0 → 1.1.0, `runs` 1.0.0 → 1.1.0 and `modules` 1.0.1 → 1.1.0.
- New submodule `logs` (the same layer as `resources`; uses only `common` and is used by `definitions`): `LogEvent`
  (alias `from`; `detail` and `raw` are null in lists), `LogDocumentRef`, `LogEventPage`, `LogEventDetail`,
  `LogEvidenceLink`, `LogSourceDescriptor`, `LogClassifierDescriptor`, `LogSourceInfo` and `LogSourceStatus`,
  `LogScanReport` and `LogSourceScanResult`, `LogSessionSummary` (`tokens`, `project`, `thread_count`, `models`),
  `LogTimeline` (`lanes: LogLane[]`, `total`, `truncated`), `TokenSample`, `LogTokenTotals`, `LogProjectRef`,
  `LogAggregateRequest`, `LogAggregateRow` and `LogArchive` (v1); the settings `LogSettings`, `LogSourceSetting`,
  `LogTaxonomy`, `LogCategory`, `LogProjectSettings`, `LogProjectGroup`, `LogDashboard`, `LogWidget` and
  `LogWidgetQuery`; the fixed vocabulary `LogUngroupedPolicy`; and the documented constant `KnownLogCategories`.
- `WorkspaceSettings.logs` (default an empty `LogSettings`; every field inside is omitted = inherit).
- Field additions: `LogCategory.tone` (documented constant `KnownLogTones`; only `danger` marks errors),
  `LogEventDetail.usage: TokenSample` and `detail_truncated` (separate from the evidence limit `truncated`),
  `LogEvent.duration_ms`, `LogScanReport.new_events` and `sources[{source_id, new_events, error_code?, message?}]`,
  the cell shape `from`, `to` and `via` on `HandoffCount` (filled together with the old `source`, `target` and
  `kind`, backward compatible for `runs`), the constants `LOG_EVENT_ORDERS` (asc, desc) and `LOG_PROJECT_UNGROUPED`
  (`~ungrouped`), the reserved keys `w` and `h` of `LogWidget.options`, and `LogQuerySchema{dimensions, metrics,
  filters[{id, title?, multi?}]}` (`GET /logs/schema`) with the documented constants `KnownLogDimensions` and
  `KnownLogMetrics`.
- `ObserveSettings.collectors: {id: CollectorSetting{enabled?, config?}}` and `hook_probe` (omitted = inherit). The
  old keys `hooks`, `mcp` and `hook_events` are still read (the backend interprets them).
- `CollectorDescriptor` and `BackendDescriptor.collectors` (default empty list).
- `EdgeTraversedPayload.kind` (the edge type id, optional, included in `runs` 1.1.0).
- WS `logs.ingested{source_ids, count, max_seq}` (topic `logs`).
- The documented constant `KnownIssueCodes` gained `logs.source_failed`, `logs.redaction_unavailable`,
  `logs.storage_memory` and `logs.unknown_classifier`.
- Existing YAML and run snapshots are read as is. Hash impact: `WorkspaceSettings` gains one field with a default, so
  the result of `model_dump()` (without exclude_unset) has a `logs` key. Definition hashes use the exclude_unset
  canonical document, so they do not change.

## 0.5.1

- Removed the monolithic module. Submodule versions: `common` 1.0.0 → 1.1.0, `modules` 1.0.0 → 1.0.1.
- `ErrorCodes.NOT_READY` (`not_ready`, HTTP 503): `GET /health` before the module start hooks finish and during
  shutdown. The meaning of the readiness signal is unchanged (`/health` 200 = ready).
- Removed `graph:<id>` from the `SubscribePayload.topic` description (a topic with no messages to send; the
  monolithic module that received it was removed). Topics are decided by the enabled server modules, and subscribing
  to an unknown topic gives `error`. The format (a string) is unchanged.

## 0.5.0

- Contract v4. The internal dependency range is `>=0.5,<0.6`.
- Fixed per-feature submodules: `common`, `resources`, `definitions`, `runs`, `usage`, `chat`, `exports`, `imports`
  and `modules` (`CONTRACT_SUBMODULES`). Per-submodule versions `CONTRACT_VERSIONS`, and import rules between
  submodules (only upper layers import lower layers; import-linter layers plus package tests). The old file module
  paths `api`, `descriptors`, `events`, `interactions`, `trace` and `ws` are gone (the root exports are unchanged).
  `Issue`, `IssueSuggestion`, `GraphPatch` and `IssueSeverity` are in `definitions`.
- New models: `ModuleInfo`, `ModuleStatus` and `FeatureUnavailableDetails`, `NodeLayout`, `EdgeLayout` and
  `GraphUiLayout`, and `VersionUiSettings`. New fields: `NodeSpec.layout` and `EdgeSpec.layout`,
  `EditorSettings.default_direction` and `default_edge_shape`, `UiHints.direction` and `edge_shape`, and
  `UiPreferences.versions`.
- `ErrorCodes.FEATURE_UNAVAILABLE` (409), the documented constant `KnownModuleStatus`, and the constant
  `USAGE_REPORT_PARTS`. `UsageReport.windows` and `rollups` are null for parts that were not requested.
- The schema root has `x-modules` (submodule → model names), and `x-constants` has `CONTRACT_VERSIONS` and
  `USAGE_REPORT_PARTS`.
- Hash impact: `EditorSettings` gains two fields with defaults, so the canonical document hash of existing graphs
  with `settings.editor` changes once after the upgrade (the store records one external change version row, which
  trips the resume hash comparison of runs from before the upgrade). `layout` is left out of the hash, so graphs that
  differ only in layout keep their hash.

## 0.4.0

- Removed the router (`RoutingDecision`, `RouteVerdict`, the `route.decided` event) and the console
  (`ConsoleSettings`, the `console.*` WS messages, `ConsoleStyle` and `CONSOLE_STYLES`,
  `WorkspaceSettings.default_entry` and `console`, and `console` in `RUN_ORIGINS`).
- Set up as a standalone project: internal dependencies are declared by name and version range, with per-package
  pytest, mypy and ruff settings, a `dev` dependency group, LICENSE and CHANGELOG. No behavior change.
