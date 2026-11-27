# Changelog

## Unreleased

- Message catalog `locales/en.json` is registered as the entry point `agent_console.message_catalogs`
  `ac-link-chat-runs`, so the web app can show the link module description and settings in English (data only, no
  API change). Log lines are now in English.
- Provides the optional port `runs.move_hook` as `chat.move_hooks` (when a conversation moves to the project record
  database, its runs move with it).
- Resuming conversations and notifications use the optional conversation service method
  `for_project(run.project_id)`, and `RootInteractions.for_project`.
- `chat.interactions` = `RootInteractions` (turn interactions are based on the root run, including requests from child
  runs), and `ConversationNotifier` notifies the root conversation of child run events. The consumer port
  `interactions.port` has the shape `RootInteractionReader`.

## 0.1.0

- First release (from the scripts/pkgkit template `link`).
- Moved from the monolithic module in `apps/server`: starting conversation turns (`RuntimeTurnLauncher`), resuming
  turns (`ConversationResume`, `runs.resume_handlers`), notifications from the `runs.event` subscription, the restart
  queue policy and the shutdown order (hold the queue, then `runs.starter.shutdown()`, then clean up chat watchers).
