# Changelog

## Unreleased

- Message catalog `locales/en.json` is registered as the entry point `agent_console.message_catalogs`
  `ac-link-runs-sdd`, so the web app can show the link module description and settings in English (data only, no API
  change). Log lines are now in English.

## 0.1.0

- First release (from the scripts/pkgkit template `link`).
- Task integration `runs` (run profile actions, gates, input substitution, secret checks, run labels, start), run
  results applied to `status_on` (line hash conflict rules, `sdd.status_not_applied`), run links (`TaskLink`), the
  verification source `runs`, profile graph checks, and a fake runs and in-memory spec service (`testing`).
- Auto-advance `SpecAutomation` (spec rule `automation`, off by default: each time a run finishes it starts `ready`
  tasks up to `max_parallel`, skips after consecutive failures with `sdd.automation_skipped`, stops at the end of a
  phase with `scope: stage`, `stopped_reason` user, spec_done, stage_done or failures, and after a restart revives only
  runs with its own `host_id` from the run history). `RunsTaskIntegration.automation_state` and `control`
  (`AutomationControl`). Server administrator options `automation_failure_outcomes` and
  `automation_retry_outcomes`. `FakeRuns.host` and `host_id`.
- Contract follow-up: `AUTOMATION_SKIPPED` uses the contract document constant `KnownIssueCodes.SDD_AUTOMATION_SKIPPED`
  (same value).
- Changing document states from run results: when the profile has `document_state_on` (contract 0.14.9), the same event
  as `status_on` calls `change_document_state(by="run", run_id=…)`, and when blocked an info issue
  `sdd.document_state_not_applied` is reported (`reason` = `transition_denied`, `gate_blocked`, `document_not_found`
  or `error`). Independent of applying task lines. Constants `REASON_TRANSITION_DENIED`,
  `REASON_DOCUMENT_NOT_FOUND`, `ISSUE_STATUS` and `ISSUE_DOCUMENT`.
- Performance (the `trace` target of one second): the verification source `runs` builds the task key to task table
  once (it used to scan the task list for every verification run; about 0.2 seconds with 5,000 tasks and 20,000
  links). Link path performance test `test_agent_console_link_runs_sdd_perf.py` (default = a small workload,
  `AGENT_CONSOLE_PERF=strict` = wall-clock time at the reference scale).
