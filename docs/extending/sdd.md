# Specs (SDD)

The specs (SDD) feature reads tasks, requirements, and phases from markdown documents and builds a plan and a trace
table. The rules for reading documents are data ([sdd-syntax](#sdd-syntax)), and the skeleton of a new spec is a
definition the user creates ([spec-template](#spec-template)). Verification results
([sdd-verification-source](#sdd-verification-source)) and task actions ([sdd-task-integration](#sdd-task-integration))
are attached with plugins and link modules.

## sdd-syntax

**When to use**: when you want to read documents in a format different from the default task syntax (checkbox list
lines, `[key: value]` fields, `~` ranges). Change the status markers your team uses (`[~]` for in progress, and so
on), the shape of requirement ids, and the heading levels treated as phases.

**Minimal shape**: `syntax` in the `sdd` section of the workspace settings (all specs), or the spec rule
`rules.syntax` (that spec only). Empty items follow the layer below.

```yaml extdocs:validate=agent_console_contracts.sdd:SddSettings
include_default_syntax: true
syntax:
  task:
    statuses:
      - {id: todo, label: 할 일, marker: " "}
      - {id: doing, label: 진행 중, marker: "~", tone: info}
      - {id: done, label: 완료, marker: [x, X], done: true}
    roles: {after: dependencies, req: requirements, who: assignee}
  requirement:
    patterns: ['^#{2,6}\s+(?P<id>REQ-\d+)\b']
  stage:
    heading_levels: [2]
```

**Rules**
- The merge order is package defaults → user setting `sdd.syntax` → spec `rules.syntax` (+ `rules.task_statuses`).
  The first level (`task`, `requirement`, `stage`) is merged key by key, and the lists below it and `roles` are
  replaced entirely. `null` inherits, and an empty list means "none in this layer".
- The only field roles the code understands are `dependencies`, `requirements`, and `assignee` (+ the optional
  `weight`). `roles` decides which field name plays each role.
- Regular expressions use named groups (`id`, `key`, `value`). They have length and time limits, and dangerous nested
  repetition is rejected (`sdd.invalid_pattern`).
- Changing a status changes only the checkbox character and field values on that task's head line. Every other byte
  stays the same.

**Common mistakes**: listing only one status in `statuses`, which removes the default statuses (the list is replaced
entirely), giving the same marker character to two statuses (`sdd.duplicate_status_marker`), and changing `roles`
while leaving the field names in existing documents as they were (dependencies show as empty).

**Turning off**: with `include_default_syntax: false`, the default syntax drops out. If there is no user syntax
either, there are zero tasks and `sdd.syntax_missing` is attached. If part of the settings is broken, only that part
is left out and reported with `sdd.settings_invalid`.

<!-- extdocs:facts sdd-syntax -->
- Registration: Uses the package data `data/default_syntax.yaml`; the settings `sdd.syntax` override it.
- Interface:
  - `agent_console_contracts.sdd:SpecSyntax` — 작업·요구·단계를 문서에서 읽는 규칙입니다. 비운 항목은 앱 설정이나 기본 규칙을 따릅니다.
  - `agent_console_sdd:load_default_syntax` — Read the package default task syntax (`data/default_syntax.yaml`).
- Built-in implementations: —
- Examples:
  - snippet: Data in the user setting `sdd.syntax`
- Turning it off or removing it: Keys that turn it off: `sdd.include_default_syntax`.
<!-- /extdocs:facts -->

## sdd-task-integration

**When to use**: to attach actions, links, issues, and auto-advance to spec tasks. Examples: running a team from a
task and changing the status from the run result, and showing the items of an outside issue tracker next to tasks.
This connects to other features, so link modules provide it.

**Minimal shape**: `id` and three asynchronous methods. The reference implementation is the
[runs and SDD link](../../packages/py/links/ac-link-runs-sdd/README.md).

```python
class TrackerLinks:
    id = "example.tracker"
    link_kinds = ("issue",)

    async def actions(self, ctx, task):      # -> list[TaskAction]
        return []                            # the actions available on this task

    async def invoke(self, ctx, task, action, args):   # -> TaskActionResult
        raise NotImplementedError            # never called if it offers no actions

    async def links(self, ctx, tasks):       # -> list[TaskLink], all tasks at once
        return []
```

**Optional capabilities**: `check_profile(ctx, profile)` (checking run profiles, for example
`sdd.profile_graph_missing`), `task_issues(ctx, tasks)` (adds issues per task, synchronous), and `automation_state`
and `control(op)` (auto-advance). If no link has the auto-advance capability, the screens do not show auto-advance.

**Rules**
- It is a multi-provider port. The actions and links of all links are collected.
- `links` receives the task list at once. Do not call outside systems separately for each task.
- If you need to read files, use the spec file access that `ctx` provides (only inside that space's folder).
- When `link_kinds` contains `run`, the screens turn on the run capability. Capabilities are computed from the
  presence of ports, so the web does not need to know module ids.

**Common mistakes**: editing task documents directly in `invoke` (change statuses through the SDD module's edit
path), and letting outside call failures escape as exceptions, which blocks the whole list (return them as issues).

**Turning off**: when you turn off the providing link, only its actions and links drop out. Documents and task
statuses stay as they are.

<!-- extdocs:facts sdd-task-integration -->
- Registration: A server module provides the port `sdd.integrations` (symbol `agent_console_mod_sdd.ports:SDD_INTEGRATIONS`, multiple: yes).
- Interface:
  - `agent_console_sdd:TaskIntegration` — Task integration (multi port `sdd.integrations`). Default implementation: link-runs-sdd.
  - `agent_console_sdd:ProfileChecker` — Optional capability: run profile check (e.g. team missing → `sdd.profile_graph_missing`).
  - `agent_console_sdd:TaskIssueSource` — Optional capability: task issues.
  - `agent_console_sdd:AutomationControl` — Optional capability: auto-advance status, pause, and resume (`capabilities.automation`).
- Built-in implementations: `link-runs-sdd`
- Examples:
  - reference: [packages/py/links/ac-link-runs-sdd](../../packages/py/links/ac-link-runs-sdd/README.md)
- Turning it off or removing it: Turn off the providing module (`modules.<id>.enabled: false`); consumers turn off only the parts that use it.
<!-- /extdocs:facts -->

## sdd-verification-source

**When to use**: to put results from elsewhere (test reports, CI results) into the verification column of the trace
table. There is one source per result file format.

**Minimal shape**: `id` and `async collect(ctx) -> list[VerificationResult]`. The entry point value is the source
object, or a class that creates the source when called without arguments. For a full example, see the
[JUnit example](../../examples/extensions/agent-console-example-sdd-junit/README.md).

```toml
[project.entry-points."agent_console.sdd_verification_sources"]
"example.junit" = "agent_console_example_sdd_junit:JUnitVerificationSource"
```

Installing it is not enough. Turn it on in the user settings and give it options.

```yaml extdocs:validate=agent_console_contracts.sdd:SddSettings
verification_sources:
  - id: example.junit
    enabled: true
    options: {paths: ["reports/**/*.xml"]}
```

**Rules**
- Read files only through `ctx.spec.files` (only inside that space's folder; links and the app configuration folder
  are rejected). Reject option paths that point outside the folder.
- Attach results to requirement ids or task keys. Keys that are not in the spec are dropped.
- Sources that link modules provide through a port are used without settings and are turned off by writing
  `enabled: false` in the settings. Plugin sources are on only when written in the settings.
- The source defines its option values. Return no results for wrong options, and do not put secret values or file
  contents in result text.

**Common mistakes**: taking result files as absolute paths, and reading XML entity declarations as they are (external
entity attacks).

**Turning off and leftover data**: when you turn it off in the settings or remove the package, that source's results
drop out of the verification column. Entries left in the settings are currently ignored without a warning.

<!-- extdocs:facts sdd-verification-source -->
- Registration: Register in the entry point group `agent_console.sdd_verification_sources` (constant `agent_console_mod_sdd:VERIFICATION_SOURCES_GROUP`). The registration name is the id.
- Interface:
  - `agent_console_sdd:VerificationSource` — Verification result source, plugged in by entry point or multi port.
- Built-in implementations: —
- Examples:
  - package: [examples/extensions/agent-console-example-sdd-junit](../../examples/extensions/agent-console-example-sdd-junit/README.md)
  - reference: [packages/py/links/ac-link-runs-sdd](../../packages/py/links/ac-link-runs-sdd/README.md)
- Turning it off or removing it: Add the name to the setting `plugins.disabled`, or uninstall the package, then restart the server.
<!-- /extdocs:facts -->

## spec-template

**When to use**: to prepare the document skeletons (requirements, design, and task documents) and rules (task
statuses, document statuses, gates, run profiles) to copy when a new spec is created. The app ships no templates at
all. Users create them on screens, in files, or by importing.

**Minimal shape**: one document of the definition kind `spec-template`. For each document, write the file name and
its roles (`tasks`, `requirements`). The skeleton bodies are files in the body folder next to the definition (write
them with the template editor on screen or through the SDD module's template file path).

```yaml extdocs:validate=agent_console_contracts.sdd:SpecTemplate
kind: spec-template
id: feature
name: 기능 개발
description: 요구 → 작업 두 문서
documents:
  - {id: requirements, title: 요구사항, file: requirements.md, roles: [requirements]}
  - {id: tasks, title: 작업, file: tasks.md, roles: [tasks]}
rules:
  task_statuses:
    - {id: todo, label: 할 일, marker: " "}
    - {id: done, label: 완료, marker: x, done: true}
```

**Rules**
- When a spec is created, the template's `documents` and `rules` and the skeleton files are copied. After that, the
  spec is independent of the template. Editing the template does not change specs already created.
- Only documents with the roles `tasks` or `requirements` are read for tasks and requirements. For documents without
  a role, only their existence and hash are checked.
- Templates can live in both the library and project spaces, and can be copied to projects. The teams that run
  profiles point to come along when you copy.
- The kind name (`spec-template`) is the default in the SDD module's administrator data. If the administrator changes
  it, the `kind` value is that name too.

**Common mistakes**: giving the same `file` to two documents, and copying a template to a project while the teams of
its run profiles exist only in the library (the copy plan brings them along, but if you skip them, you get
`sdd.profile_graph_missing`).

**Turning off**: deleting a template does not delete the specs created from it.

<!-- extdocs:facts spec-template -->
- Registration: Registration kind `definition`.
- Interface:
  - `agent_console_contracts.sdd:SpecTemplate` — 문서 틀입니다. 스펙을 만들 때 문서 뼈대와 규칙을 그대로 복사합니다.
- Built-in implementations: —
- Examples:
  - snippet: Document template definition data
<!-- /extdocs:facts -->
