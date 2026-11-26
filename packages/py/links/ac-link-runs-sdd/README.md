# agent-console-link-runs-sdd

A link module (`link-runs-sdd`) that connects specs (`mod-sdd`) to run history (`mod-runs`).
It runs the tasks of a spec task document with run profiles (a team + an input template) and reflects the run results in the task markers and the trace
table.

| What it does | How |
| --- | --- |
| Task actions (`sdd.integrations`, integration id default `runs`) | One action per spec rule `run_profiles`. Not offered for tasks that `when` does not match. When the `run` gate blocks, `disabled` (`sdd.gate_blocked`) |
| Run | `when` → `run` gate → input template substitution → secret scan (`sdd.secret_scan`) → label limit → `runs.starter.start_graph(graph, input, origin="sdd", project_id=space name, labels)` |
| Run labels | `<prefix>spec`, `<prefix>task`, `<prefix>profile`, `<prefix>purpose` (prefix = `mod-sdd.run_label_prefix`, default `sdd.`) |
| Result reflection | `runs.event` status events → when the run profile has `status_on[result name]`, only the task header line is changed (`by: run`). When that line changed during the run, or the `task_status` gate blocks, nothing is changed and the info issue `sdd.status_not_applied` is raised (`details.reason`, `gate_id`) |
| Document state reflection | On the same event, when the run profile has `document_state_on[result name]` (`{document, to}`), `change_document_state(by="run", run_id=<root run>)` runs with the transition rules and the `document_state` gate as they are. Independent of the task line reflection (when one is blocked, the other is still tried). When the document is already in that state, it stays. When the transition is rejected, a gate blocks, the document does not exist, or it is not writable, nothing is changed and the info issue `sdd.document_state_not_applied` is raised (`details{document_id, to, reason, gate_id?}`). When empty, nothing changes. REST state requests are always `by: human` (the `by` in the body is not accepted) |
| Run links | `runs.reader.page(labels={<prefix>spec: id}, root_only=True)` up to the limit → `TaskLink{kind: run}` (status, time, token total) |
| Verification source (`sdd.verification_sources`, id default `runs`) | Runs with a `verification.purposes` purpose → `VerificationResult` converted through `result_map` |
| Profile check | When that space has no such team, `sdd.profile_graph_missing` (`details.in_library`) |

The run status → result name table (the names used by `status_on` and `result_map`), the event types to reflect, the integration and source names,
`origin`, and the read limits are the administrator options `modules.options.link-runs-sdd`, and the defaults are the package data
`data/defaults.json` (`running → started`, `completed → succeeded`, and so on). Run status names (`completed`) written directly in `status_on`,
`document_state_on`, and `result_map` also match.

When this link or `mod-runs` is off, `capabilities.runs=false`, and there are no run buttons, run chips, or verification column.
Documents, tasks, plans, and traces (requirements ↔ tasks) keep working.

## Auto-advance (optional, off by default)

`SpecAutomation` acts only on specs whose spec rule `rules.automation{enabled, profile, max_parallel, max_failures, scope}` is on.
When it is off, no run is started.

- Every time a run finishes (and on [Restart], when a spec is viewed, and when the app starts), it starts `ready` tasks in document order
  up to `max_parallel` with `RunsTaskIntegration.start`. Without `profile`, it uses the first profile that matches the task.
  Tasks that are running, skipped, or settled (finished with a result that is neither a failure nor a restart, with the line unchanged) are left out.
- When the result name is in `automation_failure_outcomes` (default `failed`), the consecutive failure count goes up by one; when it reaches `max_failures`,
  the task is skipped and the info issue `sdd.automation_skipped` is raised. `automation_retry_outcomes` (default `interrupted`) are not
  counted and the task is started again. Tasks blocked by a gate are not counted as failures; they wait.
- Stop reason `stopped_reason`: `user`, `spec_done`, `stage_done` (`scope: stage`), or `failures`. Stopping only prevents new
  runs. [Restart] clears the failure count and the skipped tasks.
- The state (`AutomationState`) is kept only in memory and is exposed through `RunsTaskIntegration.automation_state` and `control`
  (`AutomationControl`). Every change calls `sdd.service.notify(…, automation=True)`.
- After a restart: the first time a spec is viewed, it picks only the runs of **its own app** from run history (the optional method
  `host_id(project_id)` of `runs.starter`), restores the consecutive failure count and the settled tasks, and continues as configured.

## Install

```bash
pip install agent-console-link-runs-sdd
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-link-runs-sdd
```

## Minimal usage

Collect a label query to the last page (`labeled_runs`) and turn a run start exception into an error issue
(`start_issue`). The fake runs module (`testing.FakeRuns`) provides the same shape without a server.

```python
>>> import asyncio
>>> from agent_console_link_runs_sdd import labeled_runs, start_issue
>>> from agent_console_link_runs_sdd.testing import FakeRuns
>>> runs = FakeRuns(graphs={None: {"team"}}, library={"shared"})
>>> for key in ("1.1", "1.2", "1.3"):
...     _ = asyncio.run(runs.start_graph("team", {}, labels={"sdd.spec": "s", "sdd.task": key}))
>>> [r.labels["sdd.task"] for r in labeled_runs(
...     runs, project_id=None, labels={"sdd.spec": "s"}, limit=10, page_size=2)]
['1.3', '1.2', '1.1']
>>> try:
...     asyncio.run(runs.start_graph("shared", {}, project_id="p1"))
... except Exception as exc:
...     issue = start_issue(exc)
>>> issue.code, issue.details["in_library"]
('project.not_imported', True)

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

In a server assembly it turns on as `link-runs-sdd` of the entry point group `agent_console.server_modules` (required ports
`runs.starter`, `runs.reader`, and `sdd.service`).

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes the dev dependency group
uv run ruff check .
uv run mypy
uv run pytest          # includes the doctests in README.md
AGENT_CONSOLE_PERF=strict uv run pytest -k perf   # wall-clock assertions (on an idle machine)
```
