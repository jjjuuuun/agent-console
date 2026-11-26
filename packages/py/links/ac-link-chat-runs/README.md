# agent-console-link-chat-runs

Chat and runs link module. It connects chat (`mod-chat`) to runs (`mod-runs`).

- **Starting a turn**: `chat.turn_launcher` = `runs.starter.start_run(conversation_id=…)`. The backend sessions a conversation continues are passed only to that run, through the node service `SESSIONS` (`ac-nodes-core`).
- **Queries**: `chat.runs` and `chat.run_events` (the received run ports as they are), and `chat.interactions` (`RootInteractions`, which collects a turn's interactions by root run, so requests opened inside a child run of a nested team appear in the same turn; it is not provided when there is no interactions port).
- **Continuing sessions**: `chat.turn_sessions` (`LineageSessions`) collects the node sessions of the turn run and the child runs below it (`list(root_run_id=)` on `runs.reader`). Child run nodes are recorded under the path key `"<team node>/<child node>"` (`session_path_key`; grandchildren append to the path) following the `parent_node_id` lineage, so on the next turn the node passes them to its child run by the same rule (`child_sessions`). When the team changes, only keys whose first segment is a node id that still exists are kept. Node type names are not inspected (only the run lineage).
- **Resume**: a conversation turn handler in `runs.resume_handlers` (`ConversationResume` → `ChatService.resume_turn`).
- **Notifications**: subscribes to `runs.event`. Interaction (`interaction.*`) and waiting (`run.waiting`, `run.resumed`) events that belong to a conversation turn go to `chat.notify`. Events of a child run (no `conversation_id`) are reported to the conversation of the root run (`root_run_id`).
- **Start**: processes the saved queue according to `chat.queue_after_restart` (`apply_restart_policy`). In assembly order it starts after the runs module (which cleans up unfinished runs) and the chat module.
- **Stop** (assembly order is reversed, so this runs before the chat and runs modules): stops taking items from the queue (`stop_dispatch`), then waits for the run cleanup (`runs.starter.shutdown()`). After that the chat module cleans up its watchers. No queued item is taken after a turn is cut off.
- When this link is off, conversations, records, and the queue still work; only sending returns 409 `feature_unavailable` (web role `conversations:runs`).

## Install

```bash
pip install agent-console-link-chat-runs
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-link-chat-runs
```

## Minimal usage

Assemble it with the test conversation module and the fake run starter (`testing`). A message goes to the run start port.

```python
>>> import asyncio
>>> from agent_console_contracts import CreateConversationRequest, Graph, PostMessageRequest
>>> from agent_console_modkit import assemble
>>> from agent_console_link_chat_runs import CHAT_CONVERSATIONS, module
>>> from agent_console_link_chat_runs.testing import (
...     LocalRunStarter, local_chat_module, local_runs_module,
... )
>>> starter = LocalRunStarter()
>>> assembly = assemble([
...     module,
...     local_chat_module(graphs=[Graph(id="team", name="팀")]),
...     local_runs_module(starter=starter),
... ])
>>> assembly.order
['local-chat', 'local-runs', 'link-chat-runs']
>>> chat = assembly.port(CHAT_CONVERSATIONS)
>>> async def main():
...     await assembly.start()
...     conv = chat.create(CreateConversationRequest(graph_id="team"))
...     run = await chat.post_message(conv.id, PostMessageRequest(text="안녕"))
...     print(starter.calls[0]["conversation_id"] == conv.id, starter.calls[0]["origin"])
...     await assembly.stop()  # stop the queue -> clean up runs -> clean up conversation watchers
...     print(starter.current_run(run.id).status)
>>> asyncio.run(main())
True chat
interrupted

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

## Ports

| Direction | Port | Shape |
| --- | --- | --- |
| Required | `chat.conversations` | `ChatLike` (`notify`, `resume_turn`, `apply_restart_policy`, `stop_dispatch`) |
| Required | `runs.starter` | `RunStarter` (`start_run`, `cancel`, `current_run`, `shutdown`) |
| Required | `runs.reader` / `runs.events` | `LineageRunReader` (`get`, `list(…, root_run_id=)`) / event queries |
| Optional | `interactions.port` | `RootInteractionReader` (`list(…, root_run_id=)`) |
| Subscribes | `runs.event` | `RunEvent` |
| Provides | `chat.turn_launcher` | `RuntimeTurnLauncher` |
| Provides | `chat.runs` / `chat.run_events` | the received ports as they are |
| Provides | `chat.interactions` | `RootInteractions` (by root run) |
| Provides | `chat.turn_sessions` | `LineageSessions` (child run sessions = path keys) |
| Provides (multi) | `runs.resume_handlers` | `ConversationResume` |
| Optional → provides (multi) | `runs.move_hook` → `chat.move_hooks` | the received hook as it is: when an old conversation is moved, its runs move with it |

## Standalone run

```bash
python -m agent_console_link_chat_runs [--with ID] [--config PATH] [--port 0] [--check]
```

Without `--with`, it attaches `testing.standalone_modules` (an in-memory conversation service and a fake run starter). With the real modules: `--with mod-chat --with mod-runs --with mod-definitions`.

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes the dev dependency group
uv run ruff check .
uv run mypy
uv run pytest          # includes the doctests in README.md
```
