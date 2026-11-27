# Changelog

## Unreleased

- Internal log messages are now in English.

## 0.1.0

- `ChatService.page(after, limit, graph_id, archived, project_id) -> (summaries, next cursor)`: sorted by
  `updated_at` and `id` descending, and summaries are computed only for that page. The caller decides the cursor
  string.
- `ChatService(busy_elsewhere=)`: turns running outside this process also count as running (none by default).
- The run connection is optional: `ChatService(conversations, graphs, *, launcher=None, runs=None, events=None,
  interactions=None, ...)`. **The constructor argument order changed** (keyword-only). Without a launcher, sending and
  resuming raise `ChatFeatureUnavailableError` (`feature_unavailable`, `details.dependency`), while conversations and
  the queue keep working and the queue is not drained until a launcher appears. Late connection with `connect(...)`,
  `can_send`. Constants `LAUNCHER_DEPENDENCY` and `RUNS_DEPENDENCY`.
- Set up as a standalone project: internal dependencies are declared by name and version range, with per-package
  pytest, mypy and ruff settings, a `dev` dependency group, LICENSE and CHANGELOG. No behavior changes.
