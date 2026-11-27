# Changelog

## Unreleased

- The conversation locator log label is in English (`conversation`).
- Message catalogs `locales/en.json` and `locales/ko.json` are registered as the entry point
  `agent_console.message_catalogs` `ac-mod-chat`, so the web app can show the module description, chat settings and
  the `chat.storage_memory` warning in English (data only, no API change).
- Fixed: for an unregistered project (an unknown record space), checking for turns running elsewhere
  (`busy_elsewhere`) and applying the restart queue policy did not catch `UnknownSpace` and leaked exception logs.
  Spaces that cannot be read are now quietly treated as "none" with the same policy as `mod-runs`
  (`RecordsUnavailable`, `UnknownSpace`, `LookupError`).

## 0.1.0

- `GET /conversations/project-counts?source=app`: counts only conversations in the app (host) database (project record
  databases are not read). Omitted means the app database plus the record databases of registered projects that are
  not archived, as now. Other values give 422. No contract changes.
- The candidate and memory policy of conversation locating (`SpacedChatService.locate`) moved to
  `agent_console_store.SpaceLocator` (shared with run locating). Behavior, settings and the name
  `DEFAULT_LOCATE_LIMIT` are the same.
- `GET /conversations/{id}/locate` (`ConversationLocation`, contract 0.14.7): conversation id to the record space
  that holds it (spaces opened in this process plus, read only, the record databases of registered projects from the
  optional port `projects.lookup` up to the limit `locate_max_projects`, default 200; app records = null). 404 when not
  found, 409 `conversation.ambiguous` (`ConversationAmbiguousError`) when found in several places. The detail
  `GET /conversations/{id}` is unchanged (it does not read another space in place of a missing `?project=`). WS
  `conversation:<id>` also finds conversations in project record databases that are not open yet through
  `service_of` to `locate` (on a worker thread). New module setting `locate_max_projects`.
- `GET /conversations/page` (`ConversationPage`, `cursor`, `limit`, `graph_id`, `archived`, `project` and `source`;
  after the folder records end it continues with `source=app`), the old `GET /conversations` is marked deprecated in
  OpenAPI, and `InvalidCursor` gives 400 `bad_request`.
- `POST /conversations/move-to-project` (old conversations and queue items in the app database to the project record
  database, `ConversationMover`), the optional port `chat.move_hooks` (`MoveHook`: moves dependent records and runs
  after-move hooks), and `SqliteChatStorage.engine`. No table changes.
- Optional port `records.spaces`: project conversations and queues go to that record database
  (`SpacedChatService.for_project`), queue `host_id` (items of another app are `other_host`), routes with `?project=`
  and lists with `?source=app`, and the module setting `records_space_prefix` (new settings schema).
- Lineage `chat` gained `chat_0003` (`chat_queue.host_id`), and the descriptor has `scopes=("app","project")`.
- First release (from the scripts/pkgkit template `module`).
- Moved the conversation assembly of `apps/server` (conversation, turn, message and queue routes, WS
  `conversation:`). Running turns, reading runs and interactions come through the optional ports `chat.turn_launcher`,
  `chat.runs`, `chat.run_events` and `chat.interactions` (without them, sending gives 409 `feature_unavailable`).
- Brought the conversation and queue stores (SQLite and in memory) into `storage/` (removed from `ac-store`). Migration
  lineage `chat` (the first revision is a baseline; tables stay as legacy 0002 and 0003). Deleting a conversation
  deletes its queue in the same transaction.
