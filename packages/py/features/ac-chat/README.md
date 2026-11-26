# agent-console-chat

The conversation (chat) service. It creates an ongoing conversation on one chosen team (graph), starts a turn (Run) for each message,
and assembles the turn list from Run records. It does not know the transport layer (HTTP, WS, CLI), the store, or the execution engine.

- **One conversation turn = one Run.** Messages are not stored separately. The user message = the Run input, the reply = `run.reply` events,
  questions, approvals, and reviews = that Run's interactions (`ChatTurn.interactions`).
- **New messages while running**: when the effective setting `chat.busy_policy` (common → team) is `queue`, the message is queued and runs after the previous turn ends;
  when it is `reject`, `ConversationBusyError` (409 `conversation_busy`). A turn waiting for a reply (`waiting`) counts as running.
  Cancel queued items with `cancel_queued`.
- **Session continuation**: when a turn ends, the last `agent.session_started` per node (`node_path == [node]`) is saved in the conversation's `sessions`
  and passed to the next turn as `TurnStart.sessions`. The node's `session` policy decides whether to use it.
  When the team changes (`update(graph_id=)`), sessions of nodes that are not in the new team are discarded. What is collected and how keys are
  built is decided by the `TurnSessions` rule (`collect`, `prune`). The default `RootRunSessions` is the rule above (the turn Run's own
  nodes, key = node id); to continue nested runs (child Runs) too, the assembly injects a rule (for example
  `LineageSessions` from `agent-console-link-chat-runs`, with path keys `"<team node>/<child node>"`).
- **Turn completion order**: reply (`run.reply`, which the engine stores before the Run's final status) → session record → publish the finished status
  → notify (`listener`). Even after the Run ends, until the session is recorded, `turns()`, `turn()`, and the summary `last_status` show that turn
  as `running` (no end time). So a turn that shows a finished status has all its replies.
- **Conversation title**: when the setting `chat.title` is `first_message`, the first `ChatOptions.title_chars` (default 40) characters of the first message; when it is `manual`, left empty.
- **Summary**: `ConversationSummary.last_status`, `queued`, `pending_interactions`. `listener` is called on every change (the server sends it as WS
  `conversation.updated`). When an interaction's status changes, the app calls `notify(conversation_id)`.
- **Queue storage**: the queue lives in the injected `QueueStore` (default `MemoryQueue`; the server passes in
  the queue store (SQLite) of `agent_console_mod_chat.storage`). The running indicator lives in process memory.
  - After a restart, `await apply_restart_policy()` (once at startup): when the effective setting `chat.queue_after_restart` is
    `ask` (default), every item is held (`held`, reason `restart`); `run` runs them in order; `drop` deletes them.
  - A held first item blocks the items behind it (order is preserved). Release it with `await release_queued(conversation, item)`
    and delete it with `cancel_queued`. If the conversation is idle but the queue is not empty, new messages under the `queue` policy line up behind it.
  - Just before shutdown, `stop_dispatch()` (before stopping the engine): nothing more is taken from the queue after an interrupted turn. `aclose()` does not
    delete the queue.
- **Resuming interrupted turns**: `await resume_turn(run_id, graph=, seed=)` → a new turn in the same conversation (Run, `origin =
  ChatOptions.resume_origin` (default `resume`), `resumed_from`, with the same input as the original turn). While running,
  `ConversationBusyError`; if it is not the conversation's last turn, `TurnNotResumableError` (409 `run_not_resumable`).
  Which nodes may run again is checked by the caller (`ac-runtime.ResumeService`). `ChatTurn.resumed_from`.

## Injected protocols

`ChatService(conversations, graphs, *, launcher=None, runs=None, events=None, interactions=None, settings=, listener=, clock=, ids=, options=, queue=)`.
Only the conversation store and the team lookup are required. The **run connection** (`launcher`, `runs`, `events`, `interactions`) is optional.

| Protocol | Methods | What you usually pass | Without it |
| --- | --- | --- | --- |
| `ConversationRepository` (required) | `get`, `save`, `delete`, `list(graph_id=, archived=)` | The store's conversation repository | — |
| `GraphLookup` (required) | `get_graph(graph_id)` | One function over the definition store | — |
| `ProjectGraphLookup` (optional capability) | `get_project_graph(project_id, graph_id)` | When present, the team of a conversation with a `project_id` is looked up only in that project (fake `testing.MemoryProjectGraphs`) | Every conversation uses `get_graph` |
| `TurnLauncher` | `async start_turn(TurnStart) -> TurnHandle`, `cancel(run_id, reason)` | A thin adapter around `GraphRuntime` (`TurnStart.sessions` to the node services, `conversation_id` and `origin` to the Run) | Sending and resuming raise `ChatFeatureUnavailableError`; the queue is kept, not taken |
| `TurnHandle` | `run_id`, `run`, `async wait()` | The `RunHandle` of `GraphRuntime.start()` as is | — |
| `RunReader` | `get`, `list(conversation_id=, limit=)` (newest first) | The store's Run repository | The turn list is empty and the last status is null |
| `EventReader` | `list(run_id, since_seq=, limit=)` | The store's event repository | Replies and sessions are not read |
| `InteractionReader` | `list(run_id=, conversation_id=, status=)` | The store's interaction repository | Turn interactions are empty and the waiting count is 0 |
| `TurnSessions` | `collect(run)`, `prune(sessions, node_ids)` | The session rule that the runs integration provides | The default `RootRunSessions(events)` |
| `ChatSettingsResolver` | `(graph) -> ChatSettings` | `layered_chat_settings(lambda: workspace.chat)` |
| `QueueStore` (optional) | `enqueue`, `get`, `list`, `remove`, `hold_all`, `release`, `pop_next`, `counts`, `clear` | The queue store of `mod-chat` (`MemoryQueue` if absent) |

`agent_console_chat.testing` has in-memory example implementations of these protocols and a fake launcher (`FakeLauncher`).
An assembler (server module) that has to create the service first and learns about the run connection later calls
`connect(launcher=, runs=, events=, interactions=, sessions=)` once before starting turns (`can_send` tells whether sending is possible).

Optional connection `SessionContinuity` (`state`, `prepare`): when given, `ChatService.session_states(id)` shows the continuation state per node
(`ConversationSessions`), and if a node has no record before sending, `SessionUnavailableError` (409 `chat.session_unavailable`,
`details{conversation_id, node_ids}`); with `on_missing_session: "fresh"`, only that node starts a new session. Nodes restored from an archived copy or an old location
are reported to the launcher through `TurnStart.session_notes` (`archived`, `relocatable`, `fresh`). Example implementation: `testing.MemoryContinuity`.

## Installation

```bash
uv sync --all-packages                   # inside the workspace
uv pip install ./packages/py/features/ac-chat     # standalone, from another project (needs ac-contracts)
```

## Minimal usage

```python
>>> import asyncio
>>> from agent_console_chat import ChatService, layered_chat_settings
>>> from agent_console_chat.testing import (
...     FakeLauncher,
...     MemoryConversations,
...     MemoryEvents,
...     MemoryGraphs,
...     MemoryInteractions,
...     MemoryRuns,
... )
>>> from agent_console_contracts import CreateConversationRequest, Graph, NodeSpec, PostMessageRequest

>>> async def main():
...     runs, events = MemoryRuns(), MemoryEvents()
...     launcher = FakeLauncher(runs, events)  # in real use, an engine (GraphRuntime) adapter
...     chat = ChatService(
...         MemoryConversations(),
...         MemoryGraphs([Graph(id="team", name="팀", nodes=[NodeSpec(id="pl", type="agent")])]),
...         launcher=launcher,
...         runs=runs,
...         events=events,
...         interactions=MemoryInteractions(),
...         settings=layered_chat_settings(),
...     )
...     conv = chat.create(CreateConversationRequest(graph_id="team"))
...     run = await chat.post_message(conv.id, PostMessageRequest(text="로그인 화면 만들어 줘"))
...     queued = await chat.post_message(conv.id, PostMessageRequest(text="그리고 테스트도"))
...     print(type(run).__name__, type(queued).__name__, queued.position)  # queued while a turn is running
...     launcher.finish(run.id)  # in real use the engine finishes it → the next queued message starts automatically
...     second = await launcher.wait_started(2)
...     launcher.finish(second.run_id)
...     await chat.wait_idle(conv.id)
...     for turn in chat.turns(conv.id):  # ChatTurn[] (oldest first)
...         print(turn.run_id, turn.user_text, turn.status)
>>> asyncio.run(main())
Run QueuedMessage 1
run-1 로그인 화면 만들어 줘 completed
run-2 그리고 테스트도 completed

```

Conversations and the queue work even without a run connection. Only sending raises `ChatFeatureUnavailableError` (`code = feature_unavailable`).

```python
>>> from agent_console_chat import ChatFeatureUnavailableError
>>> chat = ChatService(MemoryConversations(), MemoryGraphs([Graph(id="team", name="팀")]))
>>> conv = chat.create(CreateConversationRequest(graph_id="team"))
>>> [c.id for c in chat.list()] == [conv.id], chat.turns(conv.id), chat.can_send
(True, [], False)
>>> try:
...     asyncio.run(chat.post_message(conv.id, PostMessageRequest(text="안녕")))
... except ChatFeatureUnavailableError as exc:
...     print(exc.code, exc.details)
feature_unavailable {'dependency': 'launcher'}

```

## Errors

All are subclasses of `ChatError` (`code` = contract `ErrorCodes`, `details`).
`ConversationNotFoundError`·`GraphNotFoundError`·`QueuedMessageNotFoundError`·`TurnNotFoundError`(not_found),
`ConversationBusyError`(conversation_busy), `TurnNotResumableError`(run_not_resumable),
`InvalidMessageError`(bad_request), `ChatFeatureUnavailableError`(feature_unavailable, `details.dependency` =
`launcher` or `runs`: there is no run connection).
Errors where the execution engine refused to start (for example, graph validation failure) are raised as is, unchanged.

## Development and standalone reuse

This folder is a standalone project. Copy only this folder and the commands below still work. Internal dependencies
are declared as a name plus a version range, so outside the repository pass the wheelhouse (`uv run poe wheels` in the repository → `dist/wheelhouse`)
as a find-links path (`uv sync --find-links <wheelhouse>`). Check inside the repository: `uv run poe portability --package ac-chat`.

```bash
uv sync                  # includes the dev group (pytest, mypy, ruff, internal packages the tests use)
uv run ruff check . && uv run mypy && uv run pytest
```

## Testing

```bash
uv run pytest packages/py/features/ac-chat
```
