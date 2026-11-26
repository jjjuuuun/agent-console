# @agent-console/api-client

A pure TypeScript client that wraps the server's REST (`/api/v1`) and WebSocket (`/ws`) with `@agent-console/contracts` types.
It does not depend on React or app code. The server address, token, `fetch`, and `WebSocket` implementation are all taken as arguments.

## Minimal usage
This block matches `test/readme.test.ts`, and the test actually runs it (`pnpm pkg-lint` checks that they match).

```ts readme
import { createRestClient } from "@agent-console/api-client";

// fetch is injected, so this runs without a server (in real use you rely on the global fetch or a server address).
const fakeFetch = async () =>
  new Response(JSON.stringify({ token: "t", server_version: "0.0.0", contracts_version: "0.4.0" }), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
const rest = createRestClient({ baseUrl: "http://127.0.0.1:8765", fetch: fakeFetch });
const boot = await rest.getBootstrap();
```

## Installation
Inside the repository, `pnpm install` links the package. Outside the repository, install the tarball (`pnpm pack:all` → `dist/npm`): `npm install ./agent-console-<name>-<version>.tgz`

## Usage example
```ts
import { createClient, ApiError } from "@agent-console/api-client";
import { isKnownRunEvent } from "@agent-console/contracts";

// 1) Get a token from bootstrap (GET /bootstrap needs no token).
const baseUrl = "http://127.0.0.1:8765";
const boot = await createClient({ baseUrl }).rest.getBootstrap();
const { rest, ws } = createClient({ baseUrl, token: boot.token });

// 2) REST: a save sends the last received version_hash as If-Match.
const { graph, version_hash } = await rest.getGraph("main");
try {
  await rest.updateGraph("main", { ...graph, name: "New name" }, version_hash);
} catch (e) {
  if (e instanceof ApiError && e.versionConflict) {
    // 412 version_conflict: draw the conflict screen from e.versionConflict.current_version_hash and so on.
  } else throw e; // 428 version_required, 404 not_found, and so on come through e.status / e.code
}

// 3) Run events: after a reconnect, it resumes from the sequence after the last seq (no duplicates).
const run = await rest.createRun({ graph_id: "main", input: {}, origin: "web" });
const snap = await rest.getRun(run.id); // a snapshot + later increments
const sub = ws.subscribeRun(run.id, (event) => {
  if (isKnownRunEvent(event)) { /* narrow by event.type and use it */ } else { /* an ordinary row */ }
}, { sinceSeq: snap.last_seq });
sub.unsubscribe();
```

## Per-feature subpaths
The full client (`createRestClient`) is a convenience assembly that combines the feature clients. To use only one feature, use its subpath and the transport (`createRestIo`) separately.
Feature clients do not import one another (enforced by dependency-cruiser); the only thing they share is `io` (the transport contract and helpers).

```ts
import { createRestIo } from "@agent-console/api-client/transport";
import { createChatClient } from "@agent-console/api-client/chat";

const chat = createChatClient(createRestIo({ baseUrl: "http://127.0.0.1:8765", token: "t" }));
const conversations = await chat.listConversations({ archived: false });
```

Subpaths: `core` (bootstrap, server info, and the module list `listModules`), `catalog` (the kind list), `agents`, `graphs`, `runs`, `chat`, `interactions`, `usage`, `resources`, `imports`, `exports`, `settings`, `i18n`, `versions`, `logs`, `memory`, `projects`, `architecture`, and `io` and `transport`.

## Public API
- `createClient(opts)` → `{ rest, ws }` (the same `baseUrl` and `token`)
- `createRestClient({ baseUrl, token?, fetch? })` → all of the Phase 1 REST (bootstrap, node and edge types, port resolution, backends and models, agent CRUD, team graph CRUD, validate, and versions, run creation, lookup, and cancel, and settings)
- Nested teams and conditions: `listConditionOperators` (`GET /condition-operators`), `listRuns({root})` (every child run under a root; an empty list for an unknown id), `listInteractions({root})` (the interactions of the root and its child runs; the response routes each by its `Interaction.run_id`), and `children` in `getRun` (the direct child runs).
- v2 REST: chat (`listConversations`, `createConversation`, `updateConversation` (rename, archive, and switching `graph_id`), `listTurns`, `postMessage` → `{run}` or `{queued}`, and `cancelQueuedMessage`), interactions (`listInteractionKinds`, `listInteractions`, `listRunInteractions`, and `respondInteraction`), runs (`getRunTrace`, `listRunEvents`, `getHandoffs`, and the extended `listRuns` filters), agents (`listAgentUsages`, `getAgentEffectiveSettings`, and `getAgentActivity`), teams (`duplicateGraph`, `getNodeEffectiveSettings`, `getNodeBundlePreview` → `BundlePreview{bundle, warnings}`, contract v3's `getGraphPlan`, `planDraftGraph` (`TeamPlanSummary`), `previewDraftEffectiveSettings`, and `previewDraftBundle` (previews of an unsaved draft), and `listGraphs({validate:false})`), delegation strategy and resource kind descriptors, usage (`getUsage` and `listUsageSources`), and resources (CRUD, content, and usages, and `.claude` import with `listImportSources`, `previewImport`, and `importResources`). The definition save family uses `Versioned<T>{value, version_hash}` (the ETag) and an optional `If-Match` argument.
- Logs (`logs`): sources and collection (`listLogSources` and `scanLogs`), sessions, timeline, events, aggregation, handoff, the taxonomy, dashboard templates, `getLogSchema`, the archive (`downloadLogArchive` → a Blob plus a file name), `getLogSessionTrace`, `listRunLogs`, and the architecture map (`getLogArchitecture` (a log filter plus `profile` → `ArchitectureView`) and `getLogEventArchitecture` (uid → `ArchitectureMembership`); the profile list is `listArchitectureProfiles` in `architecture`). A filter is `LogQueryParams` (a name → a value or a list of values, with repeated keys), and the server decides whether a name is valid. The WS `subscribeLogs(h)` delivers `logs.ingested` on the topic `logs` (it re-subscribes automatically on reconnect).
- Shared memory (`memory`): scope kinds, scope summaries, and tags (`listMemoryScopeKinds`, `listMemoryScopes`, and `listMemoryTags`), entry lists and search (`listMemoryEntries`; the scope is passed as a `MemoryScopeRef` and goes out as a repeated `<kind>:<id>` key, with the server sorting `sort` and `order`, and cursor paging), create, read, and update (`updateMemoryEntry(id, body, version)` requires `If-Match`, and a 412 gives the current version through `memoryConflictVersion(error)`), mark-delete, permanent delete (`purgeMemoryEntry`, 204), move, archive, revert (`restoreMemoryEntry`), the version list and content, cleanup preview and apply (`planMemoryRetention` and `applyMemoryRetention`), the settings check (`checkMemorySettings`), export (`exportMemory` → a Blob plus a file name) and import (`importMemory(zip bytes, {policy, dryRun})`; the body is the zip bytes, not multipart), and clearing the log index (`purgeLogIndex`; to actually delete without a scope, pass `all: true`, otherwise 422, and 400 `logs.purge_unsupported` when unsupported). The WS `subscribeMemory(h)` delivers change notices (with no body) on the topic `memory.changed` (nothing is sent right after subscribing, and it re-subscribes automatically on reconnect). Scope kinds, tags, and key names are not in the code.
- `getServerInfo()` → `GET /server-info` (the server info in Settings, read-only).
- Screen text catalogs (`i18n`): `getI18nInfo()` → `GET /i18n` (languages and the default language) and `getI18nCatalog(language, { signal })` → `GET /i18n/{lang}` (the server's catalog for one language; `null` instead of an error when the server has none for it, a 404).
- `getAgentVersioned(id)` and `updateAgentVersioned(id, agent, versionHash?)`: read an agent together with its `ETag` (`version_hash`) and save it with `If-Match` (a conflict is a 412 `ApiError.versionConflict`). The existing `getAgent` and `updateAgent` are unchanged.
- `ApiError { status, code, message, details, versionConflict? }`: every REST failure. A network failure is `status 0` with `code "network_error"`. An unknown `code` is exposed as it is. `isInteractionClosed` (409 `interaction_closed`: a request that was already answered) and `isConversationBusy` (409 `conversation_busy`) tell the same 409 apart.
- `createWsClient({ baseUrl, token?, webSocket?, backoff?, timers?, random?, nextId?, onError? })` → `connect / close / status / onStatus / subscribe / subscribeRun / subscribeConversation(id, h) / subscribeInteractions(h) / onMessage`. The `conversation:<id>` and `interactions` topics are re-subscribed automatically on reconnect (no replay; for `interactions` the server sends the waiting list again).
- The constants `WS_CLOSE_UNAUTHORIZED` (4401), `WS_CLOSE_FORBIDDEN` (4403), and `WS_AUTH_CLOSE_CODES`: the default of `noReconnectCloseCodes` (`createClient` accepts this option too; the values are re-exported as they are from the constants in `@agent-console/contracts`).
- Injected types: `FetchLike`, `WebSocketFactory`, `WebSocketLike`, and `TimerApi`. `token` is a string or a function read on every call (it is read again on reconnect as well).

## Behavior
- Reconnect: exponential backoff `min(maxMs, initialMs * factor^n) * (1 - jitter * random())` (by default 500 ms ×2, at most 10 s, jitter 0.2). It resets once the connection opens. Calling `close()` stops it.
- Run events: it remembers the last seq per topic, sends `subscribe {since_seq}` on reconnect, and drops events with `seq <=` the last.
- A seq that has already passed (an event or line that arrived late because of reordering) is dropped.
- The `sinceSeq` and `onError` passed by a second or later subscription to the same topic are ignored (the first subscription's values are used).
- The backoff resets only after the connection has opened and either received a first message or held for `stableMs` (default 10 seconds). For a server that closes immediately after opening, the interval keeps growing.
- A close code listed in `noReconnectCloseCodes` (default `WS_AUTH_CLOSE_CODES`) does not reconnect and leaves the state as `closed` (the authentication failure codes are `WS_AUTH_CLOSE_CODES`).
- An exception thrown by a handler is isolated and reported through `onError({code: "handler_error"})`, and the other handlers are still called.
- Subscribing to the same topic several times uses a single socket subscription, and a late subscriber receives events from then on.
- There is no dedicated handler for the `graph:<id>` topic. Receive the raw message through `onMessage`.

## Dependencies
| What | Why | Alternatives |
| --- | --- | --- |
| `@agent-console/contracts` (workspace) | Reuses the generated contract types and `ERROR_CODES` | None (the only dependency) |
| No external library | `fetch` and `WebSocket` are standards, and the reconnect and seq replay rules are tied to this project's contract | `reconnecting-websocket` (the since_seq replay and the console's duplicate removal would need to be written anyway), `openapi-fetch` (the schema is a single JSON Schema file, so the OpenAPI path is deferred) |

## Multi-file resources and resuming
- `listResourceFiles`, `readResourceFile`, `putResourceFile`, and `deleteResourceFile` (`If-Match` = the definition's `version_hash`, and the response = the definition plus the new ETag), `getResumeOptions`, `resumeRun`, and `releaseQueuedMessage`.

## Testing
`pnpm test` (from the package folder or the repository root; Vitest). With a fake `fetch`, `WebSocket`, and timers, it verifies REST success, errors, and 412, reconnect backoff, `since_seq` replay, and the console's seq de-duplication.

## Projects and spaces
- The `projects` client (`createProjectsClient`, also merged into `createRestClient`): `listProjects`, `getProject`, `createProject`, `updateProject`, and `unregisterProject` (DELETE = the server archives it), the settings file `resetProjectManifest` (only when `status == manifest_invalid`, with the backup path `backup_path`) and `appendProjectGitignore`, folders `checkFolder`, `createFolder`, `listFolders`, `getFolderCapabilities`, and `pickFolder(request, {signal})` (aborting makes the server close the window), copying between spaces with `planCopy` and `applyCopy`, reverse references before deletion with `listCopyItemReferences(project|null, kind, id)` (with `checked === false` there is no way to check), and old records with `planLegacyCopy`. Record counts and assigning records to a project are in `runs` (`getRunProjectCounts` and `assignRunsToProject`) and `chat`, and copying memory is in `memory` (`copyMemory`) (features do not import one another).
- Run delegation flow and handoffs: `getRunTrace(id, { project })` and `getHandoffs({ project })` attach an optional `project` (`?project=`; an unknown project is a 404 `project.not_found`). When omitted, they read the shared records as before.
- The space argument: the definition and memory REST calls pick the project folder's copy store with `?project=<id>` (the shared library when omitted). Feature clients do not know about spaces; wrap the transport with `withSpace(io, "payments")`, or get the definition, version, and memory bundle with `createSpaceRestClient(options, "payments")`. With `null` or when omitted, the request address does not change.
