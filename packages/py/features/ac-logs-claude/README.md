# agent-console-logs-claude

A plugin that reads Claude Code session records (including subagents) as normalized events of `agent-console-logs`.

- Source `claude-code-jsonl` (`ClaudeCodeJsonlSource`): finds session files in the Claude Code `projects` folder,
  `<session>/subagents/**/agent-*.jsonl`, and the meta files next to them (`.meta.json`), and reads them incrementally.
  **Off by default**: conversation text is copied into the index, so the user turns it on.
- Classifier `claude-code` (`ClaudeCodeClassifier`): **stateless per row**. Grouping responses, pairing calls, and
  durations are computed at query time from `message_id` and `call_id`.
- Row mappings such as delegation, file change, and document read tool names, document kinds, the MCP tool name pattern, category ids, tags, and hooks are
  **all settings data** (defaults in `data/classifier_config.schema.json`). There is no list of tool names in the code.
- Sources are **only read**. Files are opened only through the injected `open_read` (including meta files). `~` and `CLAUDE_CONFIG_DIR` are
  resolved only from the injected environment (`LogIngestor(environ=...)`); the process environment is never read behind your back.
- `thinking` bodies (and signatures) are never stored anywhere. Only an "internal reasoning body omitted" marker remains.
- Masking of suspected secret values is applied by the collector (`LogIngestor(redact=...)`) right before storing.
- Used without the server or the web app. `agent_console_logs.LogRegistries().load()` finds it through entry points.
- **In the app, only sessions of registered project folders are read** (the principle "features work only on projects the app created
  or registered"). When the collector passes `ProjectFolders` (current and registered project folders) with `LogIngestor(projects=...)`, this source's
  `in_scope` matches the key in `projects/<key>/…` against the project folder names (`project_key`) and skips units outside the scope (meta files are not
  read either). With no registered projects, nothing is read (no fallback that reads the whole home). The same filter applies even when you write `roots`
  yourself. Standalone use without `projects` reads the whole root as before.
- **By default it reads two places** ("one sign-in per app"): (a) CLI sessions in
  `~/.claude/projects` (or under `CLAUDE_CONFIG_DIR`, read-only; the only exception where the app reads from `~/.claude`), and (b) sessions the app
  ran, in `<app workspace>/.state/claude/projects` (under the app-only subscription credentials folder, `workspace_roots`). Both read only what passes the same scope
  filter (registered project folder keys). The app workspace comes in as the host path `LogIngestor(paths={"workspace": …})`.
  Nothing inside project folders is read.

## Installation

```bash
uv sync --all-packages                                  # inside the workspace
uv pip install ./packages/py/features/ac-logs-claude    # standalone (with logs and contracts)
```

| Dependency | What | Why | Alternatives |
| --- | --- | --- | --- |
| `agent-console-logs` | The source base class `JsonlFileSource`, drafts and convention tags, the collector | The core of the extension point | — |
| `agent-console-contracts` | Descriptors, `TokenSample`, `LogDocumentRef` | Single source of contracts | — |
| `agent-console-claude-format` | The folder key `project_key` (kept there and re-exported here) | One place for the same function as the execution backend's session storage | Copying the function (both places would need fixing when the rule changes) |

## Minimal usage

Create a fake Claude Code settings folder in a temporary folder (one response split across two rows) and collect it into an in-memory index.

```python
>>> import json, tempfile
>>> from pathlib import Path
>>> from agent_console_contracts.logs import LogSettings
>>> from agent_console_logs import LogFilter, LogIngestor, LogRegistries, query_context
>>> from agent_console_logs.testing import MemoryLogIndex

>>> config_dir = Path(tempfile.mkdtemp())                  # a fake CLAUDE_CONFIG_DIR
>>> session = config_dir / "projects" / "-work-demo" / "S1.jsonl"
>>> session.parent.mkdir(parents=True)
>>> def reply(text, output):
...     return {"type": "assistant", "sessionId": "S1", "cwd": "/work/demo",
...             "timestamp": "2026-10-01T00:00:01Z",
...             "message": {"id": "msg_1", "model": "m", "content": [{"type": "text", "text": text}],
...                         "usage": {"input_tokens": 10, "output_tokens": output}}}
>>> rows = [
...     {"type": "user", "sessionId": "S1", "cwd": "/work/demo", "parentUuid": None,
...      "timestamp": "2026-10-01T00:00:00Z", "message": {"content": "문서 정리해 줘"}},
...     reply("네,", 3),
...     reply("정리했습니다.", 8),
... ]
>>> _ = session.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), "utf-8")

>>> registries = LogRegistries()
>>> _ = registries.load()                                   # entry point: claude-code-jsonl, claude-code
>>> index = MemoryLogIndex()
>>> ingestor = LogIngestor(index, registries, environ={"CLAUDE_CONFIG_DIR": str(config_dir)})
>>> settings = LogSettings.model_validate({"sources": [{"id": "claude-code-jsonl", "enabled": True}]})
>>> ingestor.scan(settings).new_events
3
>>> [summary] = index.list_sessions(LogFilter(), query_context(settings))
>>> (summary.title, summary.cwd, summary.tokens.output)    # tokens of the same response msg_1 counted once
('문서 정리해 줘', '/work/demo', 8)

```

<!-- doctest: keep a blank line after the expected output (so the closing ``` line is not read as output). -->

## Source settings (`logs.sources[id=claude-code-jsonl].config`)

| Key | Default | Meaning |
| --- | --- | --- |
| `project_scope` | (none) | Not read (if present, info `logs.ignored_key`). The scope is always all registered projects (including subfolders) |
| `cwd_pointer` | `/cwd` | JSON pointer to the session's project folder. When a folder key equals a registered folder key or looks like one below it, this cwd decides whether it is inside the registered folder (the key is a lossy conversion) |
| `cwd_peek_bytes` | `262144` | Maximum bytes read from the start of the file to find the cwd |
| `workspace_roots` | `[".state/claude/projects"]` | Folders of sessions the app ran (relative to the app workspace, absolute paths allowed; under the app-only subscription credentials folder). Only when `roots` is empty. Change it together with the backend's `auth_dir.config_dir`. The old `project_roots` (paths relative to the project) remains in the schema only as `deprecated` and is not read (if it has a value, the app reports the info issue `logs.ignored_key`) |
| `project_key_keep`, `project_key_replacement` | `""`, `-` | The rule from a project folder to the folder name under `projects` (characters other than letters, digits, and kept characters become the replacement, for example `/work/demo` → `-work-demo`). Claude Code does not document this rule, so fix it if it changes |
| `roots` | `[]` | List of `projects` folders to read. When empty, the rule below (CLI sessions) + `workspace_roots` (sessions the app ran). The scope filter applies even when set |
| `config_dir_env`, `config_dir_subpath` | `CLAUDE_CONFIG_DIR`, `projects` | When the injected environment has this variable, the subpath under it |
| `default_root` | `~/.claude/projects` | When neither exists (`~` is the injected `HOME` or `USERPROFILE`) |
| `include` | `*/*.jsonl`, `*/*/subagents/**/agent-*.jsonl` | Globs relative to the root |
| `exclude` | `[]` | Example: leave out subagents with `*/*/subagents/**` |
| `subagents_dir`, `meta_suffix` | `subagents`, `.meta.json` | Subagent folder and meta file names |
| `meta_fields` | `role=/agentType`, `description=/description`, `tool_use_id=/toolUseId` | Values to take from the meta JSON (JSON pointers) |
| `max_meta_bytes` | 65536 | Meta files larger than this are not read |

When the scope changes and records outside it are already indexed, the collector clears this source's index (including cursors) at the next collection and reads only what is in scope
from the beginning (`LogIngestor.scope_purged`). The retention period (`retention_days`) keeps applying in later collection and cleanup cycles.
Credential files (`.credentials.json`) are outside the include pattern (`*.jsonl`), so they are never opened.

`SourceRef.meta` (classifier context): `kind` (`session`, `subagent`), `project`, `session`, `thread`; for subagents
`parent`, `role`, `description`, `tool_use_id`; for main sessions `subagents` (delegation call id → subagent thread).

## Classifier settings (`logs.sources[].config.classifier.config`)

| Key | Default (summary) | Meaning |
| --- | --- | --- |
| `categories` | input, llm, tool, mcp, handoff, merge, error, other | Category id per row kind |
| `tags` | `tool_call`, `tool_result`, `error`, `mcp`, `agent` | Extra tags per row kind (tool events always get the convention tag `tool`) |
| `delegation_tools` | `Agent`, `Task` (`/subagent_type`, via `Agent 도구`, `role:{value}` when there is no target) | Delegation tools |
| `delegation_result` | `/toolUseResult/agentId` | Pointer to find the subagent id in result rows |
| `subagent_thread_template` | `agent-{value}` | Subagent id → thread |
| `file_change_tools` | `Write` (created), `Edit`, `MultiEdit` (modified), `NotebookEdit` | Attach documents (path, action) to call events |
| `document_read_tools` | `Read` (`read_requested`) | Documents requested for reading |
| `document_kinds`, `default_document_kind` | `SPEC.md`→spec, `CLAUDE.md`, `CLAUDE.local.md`, `*/.claude/rules/*.md`→rules, `AGENTS.md`→agents_md, `SKILL.md`→skill / document | File names or path globs (`*` crosses `/` too) → document kind. File names first, then longer globs first. Instructions loaded automatically do not appear in session records, so only documents opened by tools are visible |
| `row_correlation` | `request_id` ← `/requestRef` | Correlation evidence to attach to every event of a row when the row has the value (the same evidence an event already has wins). Response rows are linked by explicit id to the `api-request` record of the same request (`request_id` ← `/id`) |
| `mcp_tool_pattern` | `mcp__{server}__{tool}` | A name template (not a regex): the placeholders `{server}` and `{tool}` once each + `*`. When the whole name matches, it is an MCP call. With an empty string, MCP is not treated separately |
| `session_title_skip_prefixes` | `<command-`, `<local-command-`, `Caveat:` | Inputs to leave out of session title candidates |
| `session_title_from_input` | `true` | When off, user input is not a session title candidate (only the `custom-title` and `ai-title` candidates of row rules remain) |
| `thinking_block_types`, `thinking_note` | `thinking`, `redacted_thinking` / the internal reasoning omitted note | Blocks whose bodies are not stored |
| `row_rules`, `extra_row_rules` | Table below | Declarative row mappings (the first matching rule wins; `extra_row_rules` comes first) |
| `summaries` | input and assistant_text → `/text`; tool_call → `/input/description`, `/input/command`, `/input/file_path`…; mcp_call → `{/server}/{/tool} · {/input/description}`…`{/server}/{/tool}`; tool_call last fallbacks `{/name} · {/input/id}`, `{/name}`; tool_result and delegation_result → `/output` → "{first block kind} block × N" → "no result"; thinking → `/note` | Locations of the plain-text list summary per row kind (see "Summary items" below; the first one that yields text wins). If none is found, the whole detail string. The raw data stays in detail and raw, and errors show as the status (`failed`) |

One row rule: `match` (JSON pointer → glob; with a list, any one; booleans and numbers are compared as `true` and `1`), `category`,
`title` (a `{/pointer}` template), `stage`, `status`, `fields` (category, stage, status, tool, via, model, message_id, turn_id, role
→ pointers), `value_maps` (field → {original value: replacement}; category changes only when it is in the mapping), `correlation` (evidence
→ pointer), `tags`, `detail` (a pointer; empty string = the whole row), `summary` (a list of list summary items, relative to detail),
`store_raw` (default `true`; with `false`, the raw data is not put into the index, and detail and raw become the `keep` pointer values + `omitted`{`bytes`, `sha256`};
size and hash are of the UTF-8 of JSON with sorted keys and no spaces, and search does not match the raw data either. Titles, fields, and evidence are read from the raw data,
so do not put body pointers into templates), `keep` (pointers of values to keep, at the same locations).

Summary items (`summaries`, row rule `summary`): a string starting with `/` and without `{/` is a JSON pointer (strings as is; content block
lists join their text blocks; numbers and objects are not plain text and are skipped). Anything else is a template. `{/pointer}` becomes that value (plain text, number,
boolean), `{/pointer|keys}` the object's key list (`, `), and `{/pointer|count}` the number of list or object items (including 0). If any placeholder is empty, that template is skipped.
A template without placeholders is literal text, so use it as the last fallback. Example: hook attachments
`["{/hookName} · {/content}", "{/hookName} · {/stdout}", …, "{/hookName} · {/type}"]` → `SessionStart:startup · ok`.

## Supported rows

Rows are split by `type` and content blocks. "Rule" means the `row_rules` defaults (data), and "code" means interpreting the record structure.
`thread` = the session id (main) or `agent-<id>` (subagent), `session` = the main session id; `cwd`, `turn_id` (`promptId`), and
`time` (`timestamp`) are common to every row. Default titles are the classifier's data values (shown in code format).

| Row | Handled by | Event |
| --- | --- | --- |
| `assistant` + `text` block | Code | `llm` `모델 응답` (model response), `message_id`, `model`. `usage` (TokenSample) on the first event |
| `assistant` + `thinking`, `redacted_thinking` | Code | `llm` `내부 추론` (internal reasoning; no body or signature) |
| `assistant` + `tool_use` | Code | `tool` (tags `tool` and `tool_call`, `call_id`, stage `start`). `handoff` (from, to, via) for delegation tools, `mcp` (detail `server` and `tool`, correlation `mcp_server`) for the MCP pattern, `documents` for file and document tools |
| `assistant` + `isApiErrorMessage` | Code | `error`, status `failed` |
| `user` + text (a string or `text` blocks) | Code | `input`. In main sessions, the tag `session_title` (title candidate); the first row of a subagent (`parentUuid: null`) is "delegated task received" (from the parent, to itself, correlation `tool_use_id`) |
| `user` + `tool_result` | Code | `tool` (tags `tool` and `tool_result`, stage `complete`; with `is_error`, status `failed` and tag `error`). With `toolUseResult.agentId`, `merge` (from the subagent, to itself) |
| `user` + images and other blocks | Code | Only the block kinds in the `input` detail (no body) |
| `user` + `isMeta: true` | Rule | `context` `메타 입력` (meta input) |
| `system` `compact_boundary`, `microcompact_boundary` | Rule | `context` `컨텍스트 압축` (context compaction) |
| `system` `stop_hook_summary` | Rule | `hook` "hook summary · N" (`hook 요약 · N개`), `preventedContinuation` → status blocked or completed, summary `stopReason` and the first hook command |
| `system` `api_error` | Rule | `error` |
| Other `system` | Rule | `system` `시스템 · {subtype}` (system) |
| `progress` `hook_progress` | Rule | `hook` `hook 실행 · {hookName}` (hook run; stage `start`, correlation `tool_use_id`, `parent_tool_use_id`, `hook_event`), summary "hook name · command" |
| `progress` `mcp_progress` | Rule | `mcp` "MCP progress · server/tool · status" (correlation `tool_use_id` = the parent call), summary "server/tool · status" |
| Other `progress` | Rule | `other` `진행 · {data.type}` (progress) |
| `attachment` `hook_*` | Rule | `hook` `hook · {hookName}`, status = kind mapping (`hook_success` completed, `hook_blocking_error` blocked, `hook_non_blocking_error` failed + category `error` …), summary "hook name · output (content, stdout, stderr; otherwise exit code and kind)" |
| `attachment` per subkind | Rule | `context` `첨부 맥락 · {attachment.type}` (attachment context). Summaries: `total_tokens_reminder`, `silent_turn_reminder` → `text`; `edited_text_file`, `compact_file_reference` → "kind · filename"; `deferred_tools_record` → "N deferred tools · N input copies"; `date` → "date …"; `language` → "language …"; `command_permissions` → "N allowed tools" |
| `attachment` `credential*`, `*secret*`, `*password*`, `*auth*` | Rule | The summary is only the kind ("… (value not included in the summary)"). Minimal exposure, separate from secret masking (the collector's `redact`) |
| Other `attachment` | Rule | `context` `첨부 맥락 · {attachment.type}`, summary = the kind name only (bodies of unknown attachments are never put into lists) |
| `summary` | Rule | `context` `요약 · …` (summary) |
| `custom-title`, `ai-title` | Rule | `custom-title` is `other`; `ai-title` is the hidden category `meta` (repeated automatic titles are timeline noise). Title = the `customTitle` or `aiTitle` value as is (no prefix, because it is used as the session list title), summary "session name (/rename)" or "session title (generated)", tag `session_title` + priority tags `session_title.renamed` and `session_title.generated` (priority below) |
| `agent-name` | Rule | `other` `에이전트 이름 · …` (agent name) |
| `permission-mode`, `mode` | Rule | `control` (agent control) `권한 모드 · {permissionMode}` (permission mode), `모드 · {mode}` (mode) |
| `atis-latch` | Rule | `meta`, summary "atis {value}" (only for scalars, otherwise the kind) |
| `queue-operation` | Rule | `meta` `입력 대기열 · {operation}` (input queue), summary "operation · content" |
| `last-prompt` | Rule | `other` `마지막 입력` (last input), summary `lastPrompt` |
| `file-history-*` | Rule | `meta` `파일 기록 · {type}` (file history), summary = `trackingPath` or the list of tracked file paths in the snapshot ("no tracked files" if none) |
| `cost-state`, `api-request*` | Rule | `meta` `비용 상태` (cost state), `API 요청 기록 · {type}` (API request record) |
| `api-request-blob` (request body) | Rule | `meta` `API 요청 기록 · api-request-blob`. **The raw data is not stored** (`store_raw: false`): detail and raw = `type`, `id`, `uuid`, `timestamp`, `sessionId`, `message.role` + `omitted` (size, sha256), summary "request body not stored · N bytes". To store it again, see "Storing request bodies" below |
| `api-request` (request metadata, Claude Code 2.1.30+) | Rule | `meta` `API 요청 · {model}` (API request), `model` ← `/params/model`, evidence `request_id` ← `/id`, detail = `/params` (request settings such as model, `max_tokens`, `thinking`; no body). Response rows of the same request have the same `request_id` through `requestRef` |
| Unknown rows | Code | `other` (title = the row `type`), raw data kept |
| Lines that are not JSON | Core | Diagnostic events (`source = diagnostic`) |

Format check (2026-10-17): checked against public material (community format notes, the Claude Code hooks documentation) and agent_bench
`claude_logs.py`. As instructed for the task, the real `~/.claude` was not read. What was confirmed: session paths,
`subagents/agent-<id>.jsonl` and `.meta.json` (`agentType`, `description`, `toolUseId`), `isSidechain` and `agentId` in subagent rows,
`data.type = hook_progress` in `progress` (`hookEvent`, `hookName`, `command`), and the hook summary in `system`
(`stop_hook_summary`). The `hook_*` kinds of `attachment` rows and the `mcp_progress` field
names could not be confirmed from public documentation, so these parts are default rule data rather than code. If the format
changes, fix `row_rules` or `extra_row_rules`; the code does not need changes. The fixtures (`tests/data/claude_config`) are
synthetic files without personal information.

Session title priority: this classifier only tags candidates, and the order is decided by the core's session title rule **data**
(`agent-console-logs` `data/default_session_title_rules.yaml`, module option `mod-logs.session_title_rules`).
The default is the last `session_title.renamed` (`custom-title`) > the last `session_title.generated` (`ai-title`) > the first
`session_title` (user input, excluding command markers and others in `session_title_skip_prefixes`). To leave inputs out of the candidates, set
`session_title_from_input: false`.

Hidden category `meta`: records internal to the format (repeated `ai-title`, `queue-operation`, `atis-latch`, `cost-state`, `api-request*`,
`file-history-*`) go to `meta`, which is `visible: false` in the default taxonomy, and are hidden from the timeline. They remain in lists, search, and
aggregates. To show them, set `logs.taxonomy.categories.meta.visible: true`; to change the category, edit `row_rules`.

The field names of `ai-title`, `custom-title`, `agent-name`, `permission-mode`, `mode`, `queue-operation`, `last-prompt`, and `file-history-*`
(`aiTitle`, `customTitle`, `agentName`, `permissionMode`, `mode`, `operation`, `content`, `lastPrompt`,
`trackingPath`, `snapshot.trackedFileBackups`) follow community format notes (checked 2026-10-18; no official documentation),
and the field names of the `mode` row could not be confirmed. So they are all default rule data, and if the format changes, only the data is fixed.

Storing request bodies: Claude Code `api-request-blob` rows contain the whole request body sent to the model (conversation, tool results, instructions).
So the same content does not pile up in the log index a second time, the default rule keeps only the size and hash. To index the raw data again,
put a rule matching the same rows into `extra_row_rules` (the first matching rule wins; the default of `store_raw` is `true`):

```yaml
logs:
  sources:
    - id: claude-code-jsonl
      config:
        classifier:
          config:
            extra_row_rules:
              - {match: {/type: api-request-blob}, category: meta, title: "API 요청 본문"}
```

Conversely, to turn off the raw data of other rows, give that row rule `store_raw: false` (and `keep` if needed).

Settings changes and already indexed events: classifier settings (`document_kinds`, `row_rules`, `store_raw`, and so on) apply **from the rows collected after the change**.
The index never rewrites the same event (same identity), so already indexed rows stay the same even when scanned again. For example,
to apply the document kind default (`CLAUDE.md` → `rules`) or the exclusion of `api-request-blob` raw data to old events,
clear (purge) the index for that scope and scan again. Until then, the raw data in the old index remains (it is deleted after the retention period
`mod-logs.retention_days`). When classification defaults change, purge and then rescan:

```bash
# on the server (dry_run is the default, so first see only how many rows would be deleted). The default category of request body rows is meta.
POST /api/v1/logs/index/purge  {"sources": ["claude-code-jsonl"], "categories": ["meta"]}
POST /api/v1/logs/index/purge  {"sources": ["claude-code-jsonl"], "categories": ["meta"], "dry_run": false}
POST /api/v1/logs/scan         {"source_ids": ["claude-code-jsonl"]}
# on the index file without the server (index_path from the settings → the server database). It deletes only with --yes.
agent-console logs purge --config agent-console.yaml --source claude-code-jsonl --category meta --yes
```

Category and source names are the values in the current settings (if you changed the category with `row_rules`, give that category). The cursors are deleted, so the next scan rereads
that source's files from the beginning. Events that were not deleted have the same identity and are not inserted again.

Known limitations (a consequence of being stateless per row):

- Tool result rows have no tool name. MCP results are in category `tool` and are paired with the MCP call (`start`) by the same `call_id`.
  The timeline `duration_ms` and the detail `related` are computed from this pairing too.
- The delegation target thread is found from meta files that already existed at collection time. If the meta file does not exist yet, `role:{subagent_type}`
  becomes the target. Delegation results (`merge`) are always exact through `toolUseResult.agentId`.
- File change documents are attached to call events (the requested change). Whether it actually succeeded is seen from the result status of the same `call_id`.

## Public API

| Name | Purpose |
| --- | --- |
| `ClaudeCodeJsonlSource` | The source (inherits `JsonlFileSource`; `default_roots`, `ref_meta`, scope `in_scope`, `allowed_keys`) |
| `project_key(folder, keep=, replacement=)` | Project folder → folder name under Claude Code `projects` |
| `ClaudeCodeClassifier` | The classifier |
| `source_config_schema()`, `classifier_config_schema()` | Settings schemas (with defaults, copies) |
| `compile_mcp_pattern(pattern)`, `McpPatternError` | MCP name template → matcher (with placeholder checks) |
| `summary_text(detail, items)` | Extracts the plain-text summary (the same rules as the `summaries` setting: a pointer or a template) |
| `summary_with_template(detail, items)` | The same summary plus its source template + values (`TextTemplate`) when a template mixed in values, otherwise `None` |
| `pointer_text_template(template, values, shown)` / `slot_name(pointer, mode)` | Turns a `{/pointer}` template and its filled values into a source template with `{name}` placeholders (what `LogEvent.text_templates` carries) |
| `omitted_row(row, keep)`, `OMITTED_KEY` | The value stored instead of the raw data (the same rule as the row rule `store_raw: false`: `keep` values + `omitted`{`bytes`, `sha256`}) |
| `CLAUDE_CODE_SOURCE_ID`, `CLAUDE_CODE_FORMAT`, `META_KIND_*`, `MCP_PATTERN_GROUPS` | Constants |

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes development dependencies (dev group)
uv run ruff check .
uv run mypy
uv run pytest          # includes the README.md doctests
```
