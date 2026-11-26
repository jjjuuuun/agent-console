# Wiki

The source of a wiki is markdown files. The rules for reading links and front matter ([wiki-syntax](#wiki-syntax))
and the agent instructions, write rules, and check rules ([wiki-rules](#wiki-rules)) are data. The search index
([wiki-search-index](#wiki-search-index)) and write checks ([wiki-write-check](#wiki-write-check)) are replaced with
plugins, and the page history store ([wiki-history](#wiki-history)) by injection.

## wiki-history

**When to use**: to keep page history (versions, authors, revert sources) in another store. This is for using the
wiki library without the server while recording history in your own DB.

**Minimal shape**: implement the `WikiHistory` protocol (`record`, `list`, `get`, `read`, `latest`, `summaries`,
`changes`, `prune`) and pass it to `WikiRepository(..., history=...)`. The in-memory implementation
`InMemoryWikiHistory` and the SQLite implementation (`agent_console_wiki.sqlite.SqliteWikiHistory`) are models to
follow.

```python
from agent_console_wiki.testing import WikiHistoryContractTests


class TestMyHistory(WikiHistoryContractTests):
    def make_history(self, tmp_path):
        return MyHistory(tmp_path / "history.db")
```

**Rules**
- Methods are synchronous and must be safe to call from threads.
- Versions start at 1 per page and go up. The wiki repository decides what to record and when, and the history store
  records what it receives as it is.
- The repository enforces the retention limit (`max_versions_per_page`) by calling `prune`.
- Check that the meaning is the same with the contract test suite `WikiHistoryContractTests`
  ([Testing](testing.md#3-contract-test-suites)).

**Common mistakes**: keeping only a hash of the content and dropping the content (revert and compare read the
content with `read`), and dropping one of the two records of a move (`move_out`, `move_in`).

**In the server**: the wiki module uses the host DB for a standalone space and the folder's record DB for a project
space. If the record DB cannot be opened, the wiki works without history and the history screen shows
`wiki.history_unavailable`.

<!-- extdocs:facts wiki-history -->
- Registration: Inject an implementation through a constructor or an argument (an object that follows the interface).
- Interface:
  - `agent_console_wiki:WikiHistory` — Page history store. Methods are synchronous and must be thread-safe.
- Built-in implementations: —
- Examples:
  - contract-tests: `agent_console_wiki.testing:WikiHistoryContractTests`
- Turning it off or removing it: Without an injected implementation, the default implementation is used.
<!-- /extdocs:facts -->

## wiki-rules

**When to use**: to bundle the instructions for agents that write to a wiki, what must not be written (write rules),
what to show on the checks tab (check rules), the skeletons of new pages (page templates), and syntax specific to
that wiki. A wiki definition uses several rule sets in order through a list of rule ids (`rules`). The app ships no
rules at all.

**Minimal shape**: one document of the definition kind `wiki-rules`. Keep the instruction body and the page template
files in the body folder next to the definition.

```yaml extdocs:validate=agent_console_contracts.wiki:WikiRulesDefinition
kind: wiki-rules
id: decisions
name: 결정 기록
instructions: {file: instructions.md}
page_templates:
  - {id: decision, title: 결정, file: templates/decision.md, path: "decisions/{slug}"}
write_rules:
  - id: no-temp-notes
    applies_to: ["decisions/**"]
    deny_patterns: ['(?i)\bTODO\b']
    action: reject
    message: 결정 페이지에 임시 메모를 남기지 않습니다
  - id: agent-needs-source
    when: {all: [{path: /author/kind, op: eq, value: agent}]}
    require: {all: [{path: /page/front_matter/source, op: exists}]}
    action: warn
    message: 에이전트가 쓴 페이지에는 근거(source)를 적습니다
lint_rules:
  - id: stale
    when: {all: [{path: /idle_days, op: gte, value: 90}]}
    severity: info
    message: 90일 넘게 고치지 않은 페이지
```

**Rules**
- With several rule sets, the instruction bodies are joined in order, and the write rules, check rules, and page
  templates are joined too. For the same id, the earlier one wins and `wiki.duplicate_rule_id` is attached.
- Write rules are all evaluated from the top: `applies_to` (path globs) → `when` (must be true for the rule to apply)
  → `require` (acts when false) and `deny_patterns` (acts when a line matches). If any `reject` matches, the write
  does not happen. An unknown action is read as `warn` and `wiki.unknown_action` is attached.
- Write rules apply to writes from the screens, REST, and agent tools. Files edited directly are recorded as external
  changes at the next read and show as `wiki.rule_violation` in the checks.
- The pre-save check looks at regular expressions, globs, conditions, and template variables. A rule that always
  rejects is `wiki.always_rejects`.

**Common mistakes**: writing a condition path outside the write decision subject (it is always false, so the rule
never applies; the available paths are in the suggestion list of the editor), and listing instruction or template
files in the definition without creating them in the body folder (`wiki.template_missing`).

**Turning off and leftover data**: when you remove a rule set from `rules` of the wiki definition, its rules no longer
apply. A wiki that points to a deleted rule set shows `wiki.rules_missing` and works with the remaining rules.

<!-- extdocs:facts wiki-rules -->
- Registration: Registration kind `definition`.
- Interface:
  - `agent_console_contracts.wiki:WikiRulesDefinition` — 위키 규칙입니다. 에이전트 지침, 쓰기·점검 규칙, 페이지 틀, 문법을 담습니다.
- Built-in implementations: —
- Examples:
  - snippet: Wiki rules definition data
<!-- /extdocs:facts -->

## wiki-search-index

**When to use**: to replace wiki search with another index (an in-house search engine, morphological analysis,
another storage method). The index is a cache that can be rebuilt from the page files at any time.

**Minimal shape (a factory)**: what you register is not an index but a **factory** `(root, options) -> WikiSearchIndex`.
The entry point value is a function without arguments that returns this factory.

- `root`: the location of the index files (`Path`) or `None`. The wiki module gives one per wiki: under the space's
  index folder for a project space, or under the state folder for a standalone space. It may also call the factory
  with `None` to check capabilities. Indexes that do not write files ignore it.
- `options`: values from the administrator settings. On top of `tokenizer` and the keys written under
  `search.index_options.<method>` for that method name (the index defines what the keys mean, for example
  `token_pattern`), the wiki module passes, overriding them, `case_insensitive` (from the wiki syntax), `max_results`
  (the search result limit), `redact` (the masking function of the current secret suspicion rules, including user
  rules; call it before putting titles and content into the index), and `redact_signature` (the signature text of
  those rules; when it changes, rebuild the file index). Without `redact`, mask with the default secret rules. Turn
  unknown values back to the defaults.
- The factory is called again for each wiki (and space), and whenever the settings change. If the factory raises,
  that wiki works without an index.

```python
>>> from agent_console_wiki import ScanSearchIndex, WikiSearchDocument
>>> def index_factory():                  # entry point value
...     def make(root, options):          # factory
...         return ScanSearchIndex(case_insensitive=bool(options.get("case_insensitive", True)),
...                                redact=options.get("redact"))
...     return make
>>> index = index_factory()(None, {"tokenizer": "trigram", "case_insensitive": True, "max_results": 50})
>>> index.update([WikiSearchDocument(path="guide/intro", title="소개", text="이 위키는 팀의 약속을 적는다.",
...                                  content_hash="h1")])
1
>>> [hit.path for hit in index.search("위키").items]
['guide/intro']

```

```toml
[project.entry-points."agent_console.wiki_search_indexes"]
"my-index" = "my_package:index_factory"
```

The index itself follows the `WikiSearchIndex` protocol (`id`, `degraded`, `hashes`, `update`, `remove`, `rebuild`,
`search`, `close`). An in-memory inverted index that takes its word splitting as option data is in the
[wiki search example](../../examples/extensions/agent-console-example-wiki-search/README.md).

**Choosing it**: installing it is not enough. The first installed name in the order user setting
`wiki.search_backend` → administrator `modules.options.mod-wiki.search.backend` → `search.fallback` is used.

```yaml extdocs:validate=agent_console_contracts.wiki:WikiSettings
search_backend: my-index
```

**Rules**
- The contract suite `WikiSearchContractTests` defines the meaning. A page matches when every word appears somewhere
  in its path, title, tags, aliases, or content, and the scoring rules and order must equal those of the default
  index.
- Mask secrets before putting text into the index. Snippets (`snippet`) and highlight ranges (`marks`) are based on
  the masked content, and `marks` are UTF-16 ranges within the snippet.
- `update` skips documents whose `content_hash` is unchanged and returns the number actually written.
- It is safe to call from threads, and `close` may be called more than once.
- When the index cannot use the method it wanted and runs a slower one, set `degraded` to true. The wiki information
  shows `wiki.search_degraded`.

**Common mistakes**: publishing an index object instead of a factory as the entry point (each wiki needs its own
index), trying to create files when `root` is `None`, and counting `marks` in code points.

**Turning off and leftover data**: when you remove the name from the settings or uninstall the package, the method
next in order is used. If the chosen name is not installed, the fallback method is used and `wiki.search_degraded`
shows. The index files stay, but they are a rebuildable cache, so you can delete them.

<!-- extdocs:facts wiki-search-index -->
- Registration: Register in the entry point group `agent_console.wiki_search_indexes` (constant `agent_console_wiki:SEARCH_INDEX_GROUP`). The registration name is the id.
- Interface:
  - `agent_console_wiki:WikiSearchIndex` — Wiki search index. Must be safe to call from threads.
- Settings: `wiki.search_backend`, `mod-wiki.search.backend`
- Built-in implementations: —
- Examples:
  - package: [examples/extensions/agent-console-example-wiki-search](../../examples/extensions/agent-console-example-wiki-search/README.md)
  - contract-tests: `agent_console_wiki.testing:WikiSearchContractTests`
- Turning it off or removing it: Add the name to the setting `plugins.disabled`, or uninstall the package, then restart the server.
<!-- /extdocs:facts -->

## wiki-syntax

**When to use**: when you want to open a wiki folder made by another tool as it is. Change the link shape (other
brackets instead of `[[target|label]]`), front matter key names (for example `제목` instead of `title`), where titles
are read from, page extensions, case sensitivity, the link scheme that leads to app screens, and the severity of the
default checks.

**Minimal shape**: `syntax` in the `wiki` section of the workspace settings (all wikis) or `syntax` in wiki rules (the
wikis that use those rules).

```yaml extdocs:validate=agent_console_contracts.wiki:WikiSettings
include_default_syntax: true
syntax:
  links:
    - id: double-paren
      kind: pattern
      pattern: '\(\((?P<target>[^)|]+)(?:\|(?P<label>[^)]+))?\)\)'
      insert: "(({target}|{label}))"
      resolve: [path, title, alias]
    - {id: markdown, kind: markdown, resolve: [relative_path, path]}
  front_matter:
    roles: {title: 제목, tags: 분류, aliases: 별칭}
  page_extensions: [.md]
  lint:
    builtin: {orphan: null, broken_link: warning}
```

**Rules**
- The merge order is package defaults → user setting `wiki.syntax` → wiki rules `syntax` (in rule order). `null`
  inherits, and an empty list means "none in this layer". `front_matter` and `lint` are merged key by key inside
  them, and everything else is replaced entirely. Each value records which layer it came from.
- The only things the code understands are the front matter roles (`title`, `tags`, `aliases`), the default checks
  (`broken_link`, `orphan`, `duplicate_title`), and target resolution (`path`, `title`, `alias`, `relative_path`).
  Patterns, key names, and order are data.
- Patterns use the named groups `target` (required), `label`, and `anchor`. Links inside code blocks and inline code
  are not links.
- Renaming changes only the link target text. Links resolved through titles or aliases are not changed (they stay
  connected after a move).

**Common mistakes**: listing only one rule in `links`, which removes the default markdown link reading (the list is
replaced entirely), patterns without a `target` group (`wiki.link_pattern_invalid`), and slow regular expressions in
wikis with many pages (`wiki.parse_timeout`).

**Turning off**: with `include_default_syntax: false`, the default syntax drops out. If there is no other syntax
either, there are zero links and `wiki.syntax_missing` is attached. If part of the settings is broken, only that part
is left out and reported with `wiki.settings_invalid`.

<!-- extdocs:facts wiki-syntax -->
- Registration: Uses the package data `data/default_syntax.yaml`; the settings `wiki.syntax` override it.
- Interface:
  - `agent_console_contracts.wiki:WikiSyntax` — 링크·머리말·제목을 페이지에서 읽는 규칙입니다.
  - `agent_console_wiki:load_default_syntax` — Read the package default wiki syntax (`data/default_syntax.yaml`).
- Built-in implementations: —
- Examples:
  - snippet: Data in the user setting `wiki.syntax`
- Turning it off or removing it: Keys that turn it off: `wiki.include_default_syntax`.
<!-- /extdocs:facts -->

## wiki-write-check

**When to use**: to add checks to wiki writes that data rules cannot express. Examples: checking combinations of
front matter keys, and comparing against an outside list. Checks that regular expressions and conditions can do are
covered by the write rules of wiki rules ([wiki-rules](#wiki-rules)).

**Minimal shape**: `id` and `check(subject, text) -> list[WikiIssue]`. The entry point value is the check object, or
a factory that takes options (the user setting `options`) and builds the check.

```python
>>> from agent_console_contracts.wiki import WikiIssue
>>> from agent_console_wiki import run_write_checks
>>> class NoTodo:
...     id = "example.no-todo"
...     def __init__(self, options):
...         self.word = str(options.get("word", "TODO"))
...     def check(self, subject, text):
...         if self.word not in text:
...             return []
...         return [WikiIssue(severity="error", code="example.todo_left", message="할 일이 남았습니다")]
>>> decision = run_write_checks([NoTodo({})], {"page": {"path": "a"}}, "TODO 나중에")
>>> [(i.code, i.rule_id) for i in decision.issues]
[('example.todo_left', 'example.no-todo')]

```

Turn it on in the user settings. Checks that link modules provide through a port are always on and are turned off
with `enabled: false`.

```yaml extdocs:validate=agent_console_contracts.wiki:WikiSettings
write_checks:
  - id: example.front-matter-keys
    enabled: true
    options: {keys: [owner, source], paths: ["decisions/**"]}
```

**Rules**
- Checks are called in order after the write rules of wiki rules and the secret check. `subject` is the write
  decision subject (the action, the author, the page after the write, the page before the write), and `text` is the
  new content (an empty string for a delete).
- Only `severity: error` rejects the write. Everything else is saved and shown as a warning. When an issue's `rule_id`
  is empty, the check `id` is filled in.
- When the options are wrong, raise in the constructor. The wiki module then does not use that check and records
  `wiki.settings_invalid` (writes still go through).
- If `check` raises, only that check is skipped and a `wiki.rule_warning` warning is attached. Do not put content or
  secret values in issue text or exception text.

**Common mistakes**: keeping key names, paths, or text in code (take them as option data), and deciding on a delete
(`op: delete`) by reading `text` (the facts before the delete are in `subject.page`).

**Turning off and leftover data**: setting `enabled: false` in the settings or uninstalling the package removes the
check. If a check that is not installed is left on, a `wiki.settings_invalid` warning is attached and other writes
go through as usual.

<!-- extdocs:facts wiki-write-check -->
- Registration: Register in the entry point group `agent_console.wiki_write_checks` (constant `agent_console_mod_wiki:WRITE_CHECKS_GROUP`). The registration name is the id.
- Interface:
  - `agent_console_wiki:WikiWriteCheck` — Added wiki write check. Called in order after the write rules and the secret check.
- Settings: `wiki.write_checks`
- Built-in implementations: —
- Examples:
  - package: [examples/extensions/agent-console-example-wiki-check](../../examples/extensions/agent-console-example-wiki-check/README.md)
- Turning it off or removing it: Add the name to the setting `plugins.disabled`, or uninstall the package, then restart the server.
<!-- /extdocs:facts -->
