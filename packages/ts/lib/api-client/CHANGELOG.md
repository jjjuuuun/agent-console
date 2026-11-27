# Changelog: @agent-console/api-client

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). A change that breaks the version
range of an internal dependency bumps the other package's version and is recorded here.

## [Unreleased]
- Model catalog (contract 0.16.1): `getBackendModelCatalog(backendId, { refresh, signal })`
  (`GET /backends/{id}/model-catalog`, `?refresh=true` skips the server cache) returns the merged model list and the
  lookup state (`discovery.state`; a failed lookup is still a 200). When the path is missing (404, older server) it
  falls back to `listBackendModels` and returns `discovery: null`. Types `BackendModelCatalogResult`,
  `ModelCatalogOptions`. Contract range raised to `^0.16.1`. Patch (0.2.1).
- Message catalog client (contract `i18n` 1.0.0): subpath `i18n` (`createI18nClient`, `I18nClient`) with
  `getI18nInfo()` (`GET /i18n`) and `getI18nCatalog(language, { signal })` (`GET /i18n/{lang}`; returns `null` instead
  of a 404 when that language has no catalog). Merged into `createRestClient`. A new feature, so minor (0.2.0).
- App database record counts: `getRunProjectCounts(params?)` and `getConversationProjectCounts(params?)` take
  `ProjectCountsParams{source?: "app"}` (`?source=app` = only records in the app database; omitted means the app
  database plus project record databases, as now). Type `ProjectCountsParams`.
- Run locating (contract `runs` 1.9.0, 0.14.8): `RunsClient.locateRun(id)` (`GET /runs/{id}/locate` returns
  `RunLocation{project_id}`; 404 when not found, 409 `run.ambiguous` when in several record spaces). The record space
  of per-run calls: `getRun(id, project?)`, `ListRunEventsParams.project` and `listRunInteractions(runId, project?)`
  (`?project=`; omitted leaves the URL as is). Type `RunSpace`.
- Conversation locating (contract `chat` 1.4.0, 0.14.7): `ChatClient.locateConversation(id)`
  (`GET /conversations/{id}/locate` returns `ConversationLocation{project_id}`). 404 when not found, 409
  `conversation.ambiguous` when in several record spaces.
- Wiki client (contract `wiki` 1.0.0): subpath `wiki` (`createWikiClient`, `WikiClient`) with wiki list, view, save
  and delete; page list, view, write (`If-Match`, `If-None-Match: *`), preview, rename (`dry_run`) and delete; history
  (list, version content as text, revert); link insertion text and page templates; search, graph, checks, recent
  changes, effective syntax and rescan; zip export (POST) and import (zip body, `policy`, `dry_run`); and wiki rule
  list, single item, save, delete and check. Spaces (`?project=`) are bound with `withSpace`. WS `subscribeWiki`
  (topic `wiki.changed`).
- Single document template REST (contract `sdd` 1.1.0): `SddClient` gained `createSpecTemplate`, `getSpecTemplate`,
  `putSpecTemplate` (`If-Match`), `deleteSpecTemplate`, `listSpecTemplateVariables`, and the skeleton file calls
  `listSpecTemplateFiles`, `readSpecTemplateFile`, `putSpecTemplateFile` and `deleteSpecTemplateFile`. For version
  history, pass the path `/sdd/templates/{id}` to the existing `versions` client.
- Copy kinds and items (contract `projects` 3.2.0): `projects` gained `listCopyKinds(project)`
  (`GET /projects/copy/kinds`, `CopyKindInfo{kind, library, portable}`) and `listCopyItems(project, kind?)`
  (`GET /projects/copy/items`, `CopyItem`).
- Specs (SDD) client (contract `sdd` 1.0.0): subpath `sdd` (`createSddClient`, `SddClient`) with spec list, view, save
  and delete; document content (`If-Match`, `If-None-Match: *`) and state transitions; task filtering and line edits;
  plan, trace and syntax; task actions and batch start; auto-advance; rule checks; import and export; and document
  template list and save as template. Spaces (`?project=`) are bound with `withSpace`. WS `subscribeSdd` (topic
  `sdd.changed`).
- Cursor pages for lists: `runsPage` (`GET /runs/page`, `RunsPageParams`), `conversationsPage`
  (`GET /conversations/page`, `ConversationsPageParams`) and the event query `listRunEvents(id, { node })`. `query()`
  sends array values as a repeated key (`status=a&status=b`).
- `previewImport` and `importResources` take the optional argument `ImportScope{project, target}`, and `planExport`,
  `downloadExportArchive` and `writeExport` take `ExportScope{project, source}`, passed as query parameters. Omitted
  leaves the URL as is.
- `projects` gained `resetProjectManifest` (`POST /projects/{id}/manifest/reset`) and `appendProjectGitignore`
  (`POST /projects/{id}/gitignore/append`).
- Projects (contract 0.12.0): subpath `projects` (`createProjectsClient`) with register, read, update and unregister;
  folder check, create, list, picker methods and the OS picker dialog (`AbortSignal` of `pickFolder`); copy plan and
  apply; and the old records plan. `RestIo.request` and `requestVersioned` take `signal`. `memory` gained
  `copyMemory`, and `runs` and `chat` gained per-project counts and moving into a project
  (`get…ProjectCounts`, `assign…ToProject`) and the list queries `project` and `source`.
- Space argument: `withSpace(io, project)` builds a transport that adds `?project=<id>` to every request (for the
  shared library it returns `io` as is, so URLs are unchanged). `createSpaceRestClient(options, project)` binds the
  definitions, versions and memory clients to one space.
- Split REST into per-feature clients (`clients/*`). Subpath exports: `core`, `catalog`, `agents`, `graphs`, `runs`,
  `chat`, `interactions`, `usage`, `resources`, `imports`, `exports`, `settings` and `versions`; the transport is `io`
  (types and tools) and `transport` (`createRestIo`). Feature clients do not import each other. `createRestClient`
  (the client combining all features) and the root export are unchanged.
- Removed the presets client (subpath `presets`, `listPresets`, `applyPreset`) together with the presets feature.
- Added `listModules()` (`GET /modules`).
- Subpath `logs`: the logs REST client (`createLogsClient`, `logQuery`) and WS `subscribeLogs` (topic `logs`).

## [0.1.0]
- First release.
