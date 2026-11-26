# agent-console-mod-chat

Chat feature module. It plugs the conversation service (`ac-chat`) into the server.

- Routes: `GET/POST /conversations`, `GET/PATCH/DELETE /conversations/{id}`, `GET /conversations/{id}/turns`, `POST /conversations/{id}/messages`, and the queue (`GET …/queue`, `DELETE …/queue/{queued_id}`, `POST …/queue/{queued_id}/release`).
- WS topic: `conversation:<id>` (the current summary right after subscribing, then `conversation.updated` on every change).
- Running turns, reading runs, and interactions come through **optional ports** (usually provided by `link-chat-runs`). Without them, conversations, records, and the queue work, and only sending a message returns 409 `feature_unavailable{module: mod-chat, port: chat.turn_launcher}`. Without definition reading (`definitions.lookup`), creating a conversation and changing its team return 409.
- Storage: this module owns conversations and the queue (`conversations`, `chat_queue`) (`agent_console_mod_chat.storage`). They are built on the engine of the host database handle (`BaseServices.database`, for example `agent_console_store.SqliteDatabase`), and the migration lineage `chat` (package data `storage/migrations/versions`) is applied only when the module is on. The tables are exactly the ones legacy 0002 and 0003 created (no changes). Deleting a conversation deletes its queue in the same transaction. Without a database, memory is used (warning `chat.storage_memory`). **Legacy is never downgraded**: to roll back, roll back only the `chat` lineage.

### Conversation list page query (`GET /conversations/page`)

Sorted by `updated_at` and `id` in descending order. Pass `next_cursor` as `cursor=` in the next request to continue with the same conditions. In an assembly with record spaces, `?project=` reads the folder records to the end and then continues with the old records in the app database; both sources are filtered with the same conditions.

| Query | Meaning |
| --- | --- |
| `cursor` | `next_cursor` of the previous response (opaque; 400 `bad_request` when wrong) |
| `limit` | 1 to 1000 (default 50) |
| `project` · `source` | Conversations of that project · record source (`project` by default; `app` = old records in the app database) |
| `graph_id` · `archived` | Equality |
| `q` | Partial match on the title (up to 200 characters, 422 when longer; leading and trailing spaces are removed, ignored when empty, case-insensitive with `casefold`). Conversations with an empty title do not match |

### Conversation counts per project (`GET /conversations/project-counts`)

`ProjectCounts` (total, without a project, and per project). In an assembly with record spaces, it counts the app database together with the record databases of registered projects that are not unregistered. With `?source=app`, only the app database is counted (for showing the records left in the app).

## Install

```bash
pip install agent-console-mod-chat
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-mod-chat
```

## Minimal usage

With only definition reading attached, you can create conversations and list them. There is no turn launcher, so sending returns `feature_unavailable`.

```python
>>> import asyncio
>>> from types import SimpleNamespace
>>> from agent_console_chat import ChatFeatureUnavailableError
>>> from agent_console_contracts import CreateConversationRequest, PostMessageRequest
>>> from agent_console_modkit import assemble
>>> from agent_console_modkit.testing import fake_module
>>> from agent_console_mod_chat import CHAT_CONVERSATIONS, DEFINITIONS_LOOKUP, module
>>> class Graphs:  # the shape of definitions.lookup: get(kind, id).document
...     def get(self, kind, id):
...         return SimpleNamespace(document={"id": id, "name": "팀"})
>>> definitions = fake_module(
...     "my-definitions", provides=[DEFINITIONS_LOOKUP],
...     on_build=lambda ctx: ctx.provide(DEFINITIONS_LOOKUP, Graphs()),
... )
>>> assembly = assemble([module, definitions])
>>> [(r.id, r.state.value) for r in assembly.report]
[('mod-chat', 'active'), ('my-definitions', 'active')]
>>> chat = assembly.port(CHAT_CONVERSATIONS)
>>> async def main():
...     await assembly.start()
...     conv = chat.create(CreateConversationRequest(graph_id="team"))
...     print([c.id for c in chat.list()] == [conv.id], chat.can_send)
...     try:
...         await chat.post_message(conv.id, PostMessageRequest(text="안녕"))
...     except ChatFeatureUnavailableError as exc:
...         print(exc.code)
...     await assembly.stop()
>>> asyncio.run(main())
True False
feature_unavailable

```

Attach a module that provides the run connection (here the fake test module `fake_turns_module`) and a message becomes a turn (a run).

```python
>>> from agent_console_mod_chat.testing import fake_turns_module
>>> assembly = assemble([module, definitions, fake_turns_module()])
>>> chat = assembly.port(CHAT_CONVERSATIONS)
>>> async def main():
...     await assembly.start()
...     conv = chat.create(CreateConversationRequest(graph_id="team"))
...     run = await chat.post_message(conv.id, PostMessageRequest(text="안녕"))
...     print(run.conversation_id == conv.id, run.status, chat.summary(conv.id).last_status)
...     await assembly.stop()
>>> asyncio.run(main())
True running running

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

## Ports

| Direction | Port | Shape |
| --- | --- | --- |
| Provides | `chat.conversations` | `ChatService` (conversations, queue, turn assembly; `notify`, `resume_turn`, `apply_restart_policy`, `stop_dispatch`, `connect`) |
| Provides (multi) | `server.warnings` | `chat.storage_memory` when there is no database |
| Topic | `conversations.updated` | `ConversationSummary` |
| Optional | `chat.turn_launcher` | `TurnLauncher` (`start_turn`, `cancel`); without it, sending and resuming return 409 |
| Optional | `chat.runs` / `chat.run_events` / `chat.interactions` | `RunReader` / `EventReader` / `InteractionReader`; without them, the turn list is empty and the waiting count is 0 |
| Optional | `chat.turn_sessions` | `TurnSessions` (`collect`, `prune`); without it, the default rule (only the turn run's own nodes, key = node id) |
| Optional | `definitions.lookup` | `get(kind, id).document`; without it, creating a conversation returns 409 |
| Optional | `definitions.spaces` | `open(project_id).get(kind, id).document`; when present, the team of a project conversation is read only from that space (404 when missing); otherwise `definitions.lookup` |
| Optional | `workspace.settings` | `() -> WorkspaceSettings` (`chat.*`); without it, the schema defaults |
| Optional (multi) | `chat.move_hooks` | `MoveHook` (`busy`, `prepare`, optional `after_move`): dependent records bound into the same operation when an old conversation in the app database is moved with `POST /conversations/move-to-project` (for example the runs of that conversation). Without it, only the conversation and its queue are moved |

The run connection is read when this module starts (`ChatService.connect`), because the connecting module requires `chat.conversations` and is therefore built after this module in assembly order. The queue policy after a restart (`chat.queue_after_restart`) is applied when the link module that provides the turn launcher starts (without a launcher, the queue is left as it is).

Optional port `records.sessions`: `GET /conversations/{id}/sessions` (`ConversationSessions`) and the send-time 409
`chat.session_unavailable`. Without it, every session is `not_applicable` (the current behavior).

## Standalone run

```bash
python -m agent_console_mod_chat [--with ID] [--config PATH] [--port 0] [--check]
```

Without `--with`, it attaches `testing.local_definitions_module` (a file store in the workspace). Conversations are in `<state>/console.sqlite3`. To run turns too: `--with mod-definitions --with mod-runs --with link-chat-runs`.

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes the dev dependency group
uv run ruff check .
uv run mypy
uv run pytest          # includes the doctests in README.md
```
