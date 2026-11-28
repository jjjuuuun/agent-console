# Changelog

## Unreleased

- Event titles and summaries that mix in values carry their source template + values in `LogEventDraft.text_templates`
  (`/title`, `/summary`), so the web app can translate them: row rule titles and summary templates (`{/pointer}`
  placeholders become `{name}` — the last pointer segment, `_count`/`_keys` for `|count`/`|keys`, no template when two
  placeholders would get the same name) and the code-built titles `응답 블록 · {kind}` and `서브에이전트 위임 · {value}`.
  Values read from the log (user text, tool output) have no template. New public function `summary_with_template`.
- Message catalog `en`: the fixed event titles the classifier builds, the default row rule titles and summaries, the
  default per-kind summaries and the default `thinking_note`.
- Message catalog `locales/en.json` is registered as the entry point `agent_console.message_catalogs`
  `ac-logs-claude`, so the web app can show the Claude Code log source and classifier settings in English (data only,
  no API change).
- The scope is the whole registered project. The setting `project_scope` is `deprecated` (not read, no default).
  Sessions in subfolders are included: a folder key that equals the registered key or starts with the key plus the
  replacement character is a candidate, and it is confirmed when the session cwd near the start of the file (new
  settings `cwd_pointer`, default `/cwd`, and `cwd_peek_bytes`, default 262144) is inside the registered folder (the
  key is a lossy conversion). Files without a cwd match only when the key is exactly equal, and files that have
  disappeared are decided by key alone (the index is kept). The same rule applies to both roots.

## 0.1.0

- First release (from the scripts/pkgkit template `feature`).
- Registered the log source `claude-code-jsonl` (finds session, subagent and meta files; off by default) and the
  classifier `claude-code` (stateless, row by row) as entry points. Special tool name handling, categories, tags,
  hooks and other row mappings are settings schema defaults (data).
- List summaries are plain text (setting `summaries` and the row rule `summary` = a pointer into detail; defaults are
  schema data). `summary_text` is public. The original stays in detail and raw.
- Rows and context are cleaned with `scrub_surrogates` before classification (lone surrogates become U+FFFD). Rows
  and subagent metadata that used to become diagnostic events because of model validation failures become normal
  events.
- Follow-up: the default `row_rules` gained `custom-title`, `ai-title` (tag `session_title`), `agent-name`,
  `permission-mode`, `mode` (category `control`), `queue-operation`, `last-prompt` and `file-history-*`. Summary items
  can use templates (`{/pointer}`, `{/pointer|keys}`; skipped when a placeholder is empty), and the default hook, MCP
  and file-history summaries are plain text. Added the setting `session_title_from_input` (default true).
- Second follow-up: summary rules per `attachment` subtype (total_tokens_reminder, deferred_tools_record, date,
  edited_text_file and others). Attachments that may hold secrets (credential* and similar) show only their kind in
  the summary, and unknown attachments are summarized by kind name. Added the `atis-latch` rule. Fallback items for
  tool result and call summaries (block count, no result, tool name). Added the summary template `{/pointer|count}`.
- Ranking tags `session_title.renamed` (custom-title) and `session_title.generated` (ai-title). Timeline noise rows
  (`ai-title`, `queue-operation`, `atis-latch`, `file-history-*`, `cost-state`, `api-request*`) go to the hidden
  category `meta` (rule data).
- Row rules `store_raw` (default `true`) and `keep`: with `false`, detail and raw hold the `keep` value plus `omitted`
  (size and sha256) instead of the original. The default rule `api-request-blob` (request bodies) does not store the
  original (turn it back on with the user setting `extra_row_rules`). `omitted_row` and `OMITTED_KEY` are public. The
  README explains that settings changes apply to rows collected after the change, and old index entries change only
  when the index is rebuilt.
- The README explains how to purge and rescan when the classification defaults change (and how to remove old
  `api-request-blob` originals).
