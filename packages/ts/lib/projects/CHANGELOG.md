# Changelog: @agent-console/projects

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). A change that breaks the version
range of an internal dependency bumps the other package's version and is recorded here.

## [Unreleased]

## [0.3.0]
- Messages (folded into 0.3.0): moved `DEFAULT_PROJECT_MESSAGES` to `src/locales/ko.json` (still the Korean default) and added `en.json`. New subpath exports `./locales/ko` and `./locales/en` (`createProjectsText(en)`), `flattenMessageTree`, the `MessageTree` and `ProjectMessages` types, and the English retired-word lists `RETIRED_TERMS_EN` and `PROJECT_CONTEXT_RETIRED_TERMS_EN` (the Korean lists moved to `locales/retired.json`, same values). The error `buildApplyRequest` throws is now English. Added tests for matching keys and placeholders and for no Korean string literals in the source.
- **BREAKING CHANGE**: removed the log filter helpers `applyLogFilter` and `logFilterFor` and the types `LogProjectRef` and `ProjectLogFilter` (`logs.ts`), which had no web consumers. Build the log query filter `project=<id>` directly instead (based on `LogSessionSummary.project_id`).
- Added (minor): the third argument of `validateNewId(newId, taken, reserved?)` (reserved words from the server, case-insensitive) and the problem kind `reserved` (the `NewIdProblem` union widens), the fourth argument of `canSubmit` (reserved words per kind), `reservedIdsByKind` (`CopyKindInfo.reserved_ids` → a table per kind) and `reservedIdsForPlan` (the kind info first, then the plan warning `details.reserved`), and the message key `copy.plan.new_id_reserved`.

## [0.2.0]
- **BREAKING CHANGE**: removed the project-only scope exports (deprecated in 0.11–0.12), because definitions no longer have a project-only scope.
  - View rules and default scope (`scope.ts`): `DEFAULT_SCOPE_VIEW_MODE`, `SCOPE_GROUP_ORDER`, `SCOPE_VIEW_MODES`, `defaultScopeFor`, `filterByScope`, `groupByScope`, `groupOf`, `isShared`, `isVisible`, `normalizeScope` and `withScope`, and the types `NewScopePreferences`, `Scope`, `ScopeGroup`, `ScopeViewMode` and `VisibilityOptions`. The `CurrentProject` type stays and is exported under the same name from `current.ts`.
  - Scope badges (`badge.ts`): `DEFAULT_BADGE_MESSAGES`, `SCOPE_BADGE_KEYS`, `badgeLabel` and `scopeBadge`, and the types `ScopeBadge`, `ScopeBadgeKind`, `ScopeBadgeOptions` and `ScopeBadgeTone`.
  - Move plans (`moves.ts`): `MOVE_TO_SHARED_SUGGESTION_ID`, `SCOPE_ISSUE_CODES`, `isRequiredMove`, `mergeMovePlans`, `moveKey`, `moveTargetOfIssue` and `selectMoves`.
  - REST client (`client.ts`): `createProjectsClient` and the types `ProjectsClient`, `ProjectsIo` and `ProjectsVersioned`. Use the project REST client of `@agent-console/api-client` instead.
  - `configDirLabel` and the message key `projects.dir_fallback`. Use the paired `*_unknown` sentences instead.
- Where a new definition is saved is decided by the space it is created in (`spaceParam`, `spaceQuery`). Cleaning up the old `project` field is handled by the copy plan (`copy.ts`).
- Contract types come from `@agent-console/contracts` `^0.14.0` (a later release raises this to `^0.15.0`).
- Added the retired-word data `PROJECT_CONTEXT_RETIRED_TERMS` (words in `RETIRED_TERMS` that are retired only in project texts). The app message table check does not apply these words to the texts of other features.
- Marked `configDirLabel` and the message `projects.dir_fallback` deprecated (no uses). They are removed together in the next major; use the paired `*_unknown` sentences instead.
- Added the keys of the copy plan dialog and space chips to the message table (`copy.import.*`, `copy.plan.*`, `copy.result.*`, `copy.submit.*`, `space.view_*`). The helper functions are unchanged.
- `folderCheckData` maps `FolderCheck.existing` (found, invalid) to the folder-picker `manifest{name,count,valid}`.
- Projects, second round (contract 0.12.0): status display and the ability table (`statusInfo`, `projectAbilities`, data table `ABILITY_TABLE`), space display and query arguments (`spaceLabel`, `spaceParam`), copy plan helpers (`copy.ts`: default actions, choices, checks, apply requests and result summaries), the folder picking adapter (`folders.ts`, contract → folder-picker shape), and the message table (`DEFAULT_PROJECT_MESSAGES`, `createProjectsText`).
- `logFilterFor` and `applyLogFilter` build `project=<id>` from a single project id (or project object). Removed `LegacyLogProjectsHolder` and `ProjectLogFilter.groups/linked` (a breaking change; the only consumer was the web log link UI, which is removed later).
- No logic for `uses` and `import_mode` was built (the fields are gone in 0.12.0).
- The view scope functions (`scope`, `badge`, `moves`) and the old REST client (`createProjectsClient`) stay (deprecated) until the switch to cleanup through the copy plan is finished. New REST code uses the `projects` client of `@agent-console/api-client`.

## [0.1.0]
- First release: view rules, the default scope, scope badges, log filters, the current project store, move plan helpers and a REST client. The only dependency is the contract types.
- Follow-up: the values of `SCOPE_ISSUE_CODES` and `MOVE_TO_SHARED_SUGGESTION_ID` come from the generated contract constants (`KNOWN_ISSUE_CODES` and `KNOWN_SUGGESTION_IDS` of `@agent-console/contracts/constants`) instead of hand copies. Value imports from contracts are allowed only through this constants entry point (dependency-cruiser `projects-contracts-types-only`).
