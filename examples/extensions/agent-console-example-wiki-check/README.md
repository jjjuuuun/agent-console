# agent-console-example-wiki-check

An example and writing guide that adds a **check that needs code** for writing wiki pages, with a single plugin package.
No engine, server, or web code changes. Once installed and turned on in the user settings, wiki writes (screen, REST, agent tools) get
warnings or rejections; when it is not turned on or is removed, there is no effect.

Write check `example.front-matter-keys`
- Checks that the front matter (`---` YAML) of the page after the write has all the keys of the option `keys`. Empty values (`null`, `""`, `[]`, `{}`)
  count as missing (with `allow_empty: true`, they count as present).
- The pages to check are chosen by page path globs (`paths`, relative to the wiki folder, without extensions; the same globs as the wiki write rule `applies_to`) and
  write actions (`ops`).
- When keys are missing, one issue (`details.missing` = the list of missing keys). Severity `error` = the write is rejected
  (`422 wiki.rule_rejected`; a tool error for agent tools); `warning` and `info` = saved, with a warning in the `X-Console-Issues` header.
- Key names, globs, severity, actions, issue code, and text are all option data (defaults in `data/defaults.json`; the default `keys` is an empty
  list = nothing is checked).
- Dependencies: the contract (`agent-console-contracts`, `WikiIssue`), the wiki library (`agent-console-wiki`, `glob_match` and
  `check_glob`), and `pydantic`. It does not import the server module (`mod-wiki`); only the tests use it.

This package is not a uv workspace member. When it is not installed, it changes nothing.

## How to build a check

A write check is an `id` attribute and a single `check(subject, text) -> list[WikiIssue]` (`agent_console_wiki.WikiWriteCheck`).
mod-wiki calls the enabled checks in turn after the write rules and the secret check of the wiki rules.

```python
from collections.abc import Mapping
from typing import Any

from agent_console_contracts.wiki import WikiIssue


class NoTodoInDecisions:
    id = "example.no-todo"

    def __init__(self, options: Mapping[str, Any]) -> None:  # options = user settings data
        self.word = str(options.get("word", "TODO"))

    def check(self, subject: Mapping[str, Any], text: str) -> list[WikiIssue]:
        if self.word not in text:
            return []
        return [
            WikiIssue(severity="warning", code="example.todo_left", message="할 일이 남았습니다")
        ]
```

- `subject` (what is judged) = `{change: {op, from?, to?}, author: {kind, agent_id?, run_id?, ...}, page: {path, title,
  tags, aliases, front_matter, bytes, links_out, broken_links}, before: <the page before the write, or null>}`
  (`agent_console_wiki.write_subject`). `text` = the new body (an empty string for deletes).
- For a delete (`op: delete`), `page` describes the page before the delete.

Rules
1. **Options are data**: key names, paths, and text are not in code; they come as constructor arguments (the user setting
   `wiki.write_checks[].options`). When you need defaults, keep them as package data.
2. **Wrong options raise in the constructor**: mod-wiki does not use that check and leaves the server warning `wiki.settings_invalid`
   (writes still work). When a pre-save check is needed, provide a function that returns a list of (location, reason), like `check_options`.
3. **Only `severity: "error"` rejects**: everything else is saved and shown as a warning. When the issue `rule_id` is empty, mod-wiki fills in the check
   `id`.
4. **An exception in `check` skips only that check**: mod-wiki leaves the warning `wiki.rule_warning`. Do not put page bodies or secret values in
   issue or exception messages.
5. **Do not read files or the network directly**: judge only from the subject and the body (it is called on every write, so keep it fast).

Using only the check, without a server:

```python
>>> from agent_console_contracts.wiki import WikiAuthor
>>> from agent_console_wiki import write_subject
>>> from agent_console_example_wiki_check import FrontMatterKeysCheck, check_options
>>> check = FrontMatterKeysCheck({"keys": ["source", "owner"], "paths": ["decisions/**"]})
>>> subject = write_subject(
...     op="create",
...     author=WikiAuthor(kind="agent"),
...     page={"path": "decisions/db", "front_matter": {"owner": "kim"}},
... )
>>> [(i.severity, i.message, i.details) for i in check.check(subject, "")]
[('error', '머리말에 필요한 키가 없습니다: source', {'missing': ['source']})]
>>> check_options({"keys": ["source"], "severity": "fatal"})[0][0]
'/severity'

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

## Registration

One entry point in `pyproject.toml`. Group = `agent_console_mod_wiki.plugins.WRITE_CHECKS_GROUP`
(`agent_console.wiki_write_checks`); name = check id (= the setting `wiki.write_checks[].id`). The value is a check object (that takes no
options) or a function or class that receives one options mapping and builds a check.

```toml
[project.entry-points."agent_console.wiki_write_checks"]
"example.front-matter-keys" = "agent_console_example_wiki_check:FrontMatterKeysCheck"
```

At server startup, the host plugin loader (`agent_console.host_plugin_loaders: wiki` of `mod-wiki`) reads this group.
**Installing alone does not use it**: it takes part in write decisions only when it is listed in the user settings (checks that other modules provide through the port `wiki.write_checks`
are always on and are turned off with `enabled: false`). To use the same class with another id, register a function such as
`lambda options: FrontMatterKeysCheck(options, check_id="team.status")` as an entry point with that name.

## Settings example

`wiki.write_checks` in the workspace settings (`settings.yaml`, the *Wiki* section of the settings screen):

```yaml
wiki:
  write_checks:
    - id: example.front-matter-keys
      enabled: true          # true when omitted
      options:
        keys: [source, owner]
        paths: ["decisions/**", "meetings/*"]
        severity: error      # error = reject; warning and info = save with a warning
        ops: [create, update, move]
        message: "Decision documents need the keys {missing}"
```

| Option | Default (`data/defaults.json`) | Meaning |
| --- | --- | --- |
| `keys` | `[]` (no check) | Keys that must be in the front matter (duplicates are merged) |
| `paths` | `["**"]` | Page path globs to check. `*` and `?` do not cross `/`, `**/` = zero or more folders, a trailing `/**` = that folder and below. A leading `/`, backslashes, and control characters are rejected |
| `severity` | `error` | `error`, `warning`, or `info` |
| `ops` | `[create, update, move]` | Write actions to check (open strings; with `delete`, the page before the delete is checked) |
| `allow_empty` | `false` | Whether empty values count as present |
| `code` | `example.front_matter_missing` | Issue code |
| `message` | `머리말에 필요한 키가 없습니다: {missing}` | Issue message (`{missing}` = the missing keys joined with commas) |

With unknown keys, wrong values, or wrong globs, the check is not built: writes still work, and a server warning remains (`wiki.settings_invalid` in the
`warnings` of `GET /api/v1/server-info`, location `/wiki/write_checks/<n>`). An id that is turned on but not installed gives the same warning.

## Install and remove

Run these from the repository root. Install into the same Python environment as the server. When the server runs in a different virtual environment,
add `--python <path to that virtual environment>` (for example, when you set it with `UV_PROJECT_ENVIRONMENT`, `--python "$UV_PROJECT_ENVIRONMENT"`).

```bash
uv pip install -e examples/extensions/agent-console-example-wiki-check   # install
uv pip uninstall agent-console-example-wiki-check                        # remove
```

Entry points are read at server startup, so **restart the server** after installing or removing.
- Installed and turned on in the settings: writes of pages with missing front matter keys are rejected (`422`, `error.details.rule_id` =
  `example.front-matter-keys`) or saved with a warning.
- Remove: when the settings entry that turned it on remains, writes still work and a server warning about a write check that is not installed remains. The settings entry is
  not deleted.
- Keep it installed but not loaded: remove `example.front-matter-keys` from the server setting `plugins.enabled` (allow list).

Note: `uv sync` removes packages that are not in the lock file. To sync with the example installed, use `uv sync --all-packages --inexact`.

## Test

The tests run without installing (pytest setting `pythonpath = ["src"]`). The `examples` step of the root `uv run poe check` runs mypy and pytest
with this folder's settings (`uv run poe examples`). Outside the repository, copy only this folder, run `uv sync --find-links <wheelhouse>`
(`uv run poe wheels` in the repository), and then `uv run pytest`.

```bash
cd examples/extensions/agent-console-example-wiki-check
uv run --project ../../.. python -m pytest
```

- `tests/test_agent_console_example_wiki_check.py`: the entry point declaration, defaults (no check), missing key issues and empty values,
  the glob, action, severity, code, and message options, rejection of wrong options (unknown keys, severity, empty keys, globs), and agreement with the mod-wiki registry checker.
- `tests/test_mod_wiki_assembly.py`: assembles a test host + `mod-wiki` and loads the entry point with the mod-wiki loader. Turned on with
  `error`, writes return `422` (no page is created) and `201` once the keys are added; with `warning`, the page is saved + `X-Console-Issues`, and pages outside the glob are not
  checked; not turned on or `enabled: false` has no effect; wrong options give no check and one `wiki.settings_invalid` warning.

Test your own check the same way: for unit tests, build the subject with `agent_console_wiki.write_subject`, and build the
assembly with `agent_console_mod_wiki.testing.static_settings_module` and `load_write_check_plugins(entry_points=[...])`.
