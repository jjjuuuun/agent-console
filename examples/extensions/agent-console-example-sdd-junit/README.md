# agent-console-example-sdd-junit

An example and writing guide that adds a verification result source, which puts **test results from elsewhere** into the spec (SDD) trace table,
with a single plugin package.
No engine, server, or web code changes. Once installed and turned on in the user settings, JUnit XML results appear in the verification column of the spec trace table (`GET …/{id}/trace` of the spec REST),
and they disappear when it is turned off or removed.

Verification result source `example.junit`
- Reads the JUnit XML files in the project folder (`paths` globs) and finds the requirement ids and task keys of each test case.
- Requirement ids are found with the `requirement_pattern` regular expression (named group `id`); when empty, the requirement ids in the spec's requirements document are
  found as words (`test_R1_login` → `R1`, but not the `R1` inside `R10` or `R1.2`). Task keys are found with `task_pattern` (group `task`),
  and keys that are not in the spec are dropped.
- Results are combined into one per requirement (or task): the value is the result, converted through `result_map`, that comes first in `status_priority`;
  the time is the latest test suite `timestamp`; and the evidence is the file where that result first appeared (`ref.path`).
- Files are read only through `ctx.spec.files`, which mod-sdd provides (only inside that project folder; links and the app config folder are rejected).
  When a file pattern points outside the folder (`..`, absolute paths, drives, backslashes), the whole options are rejected (no results).
- Regular expressions follow the `ac-safe-regex` rules (a length limit, rejection of dangerous nested repetition, a time limit per match `regex_timeout_ms`).
- XML with DTD or entity declarations is not read (standard library `xml.etree` + rejecting declarations; no new dependencies).
- Dependencies: the contract (`agent-console-contracts`), the spec library (`agent-console-sdd`, protocol and `SpecFiles`),
  `agent-console-safe-regex`, and `pydantic`. It does not import the server module (`mod-sdd`); only the tests use it.

This package is not a uv workspace member. When it is not installed, it changes nothing.

## How to build a source

A verification result source is an `id` attribute and a single `async collect(ctx) -> list[VerificationResult]` (`agent_console_sdd.VerificationSource`).

```python
from agent_console_contracts.sdd import VerificationResult
from agent_console_sdd import VerificationContext


class MySource:
    id = "example.my-ci"

    async def collect(self, ctx: VerificationContext) -> list[VerificationResult]:
        files = ctx.spec.files  # only inside that project folder; None for the standalone root or a space without file access
        if files is None:
            return []
        data = files.read(str(ctx.options.get("path", "ci.json")))  # options = user settings data
        ...
        return [VerificationResult(source=self.id, status="pass", requirement_ids=["R1"])]
```

Rules
1. **Options are data**: file locations, naming rules, and result names are not in code; they come through `ctx.options` (the user setting
   `sdd.verification_sources[].options`). When you need defaults, keep them as package data (here
   `data/defaults.json`).
2. **Files only through `ctx.spec.files`**: do not read them directly with `open()` or `Path`. Paths are POSIX paths relative to the project folder,
   and patterns given by the user are checked first (`check_file_pattern`).
3. **User regular expressions through `ac-safe-regex`**: `compile_user_regex(pattern, timeout=...)`; a match timeout
   (`RegexTimeoutError`) skips only that item.
4. **Result values are open strings**: the trace table treats `fail` and `failed` as failures (`verification_failed` gaps).
5. **Failures as exceptions**: when `collect` raises, mod-sdd skips only that source and uses the results of the other sources as they are.
   Do not put the raw results or secrets in the exception message.

Using only the core function, without a server (this package's `collect_results`):

```python
>>> from agent_console_contracts.sdd import ParsedRequirement, SpecIndex
>>> from agent_console_sdd.testing import MemorySpecFiles
>>> from agent_console_example_sdd_junit import collect_results
>>> xml = (
...     '<testsuite name="unit" timestamp="2026-11-05T09:00:00">'
...     '<testcase classname="tests.login" name="test_R1_login"/>'
...     '<testcase classname="tests.login" name="test_R1_logout"><failure/></testcase>'
...     "</testsuite>"
... )
>>> files = MemorySpecFiles({"reports/unit/junit.xml": xml})
>>> index = SpecIndex(requirements=[ParsedRequirement(id="R1", document="req", line=3)])
>>> report = collect_results(files, index, {"paths": ["reports/**/*.xml"]})
>>> [(r.requirement_ids, r.status, r.detail, r.ref.path) for r in report.results]
[(['R1'], 'fail', 'fail 1, pass 1', 'reports/unit/junit.xml')]
>>> collect_results(files, index, {"paths": ["../outside.xml"]})
Traceback (most recent call last):
  ...
agent_console_example_sdd_junit._options.JUnitOptionsError: /paths/0: 파일 패턴은 프로젝트 폴더 밖이나 빈 구성요소를 가리킬 수 없습니다

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

## Registration

One entry point in `pyproject.toml`. Group = `agent_console_mod_sdd.plugins.VERIFICATION_SOURCES_GROUP`
(`agent_console.sdd_verification_sources`); name = source id. The value is a source object or a class or function called without arguments.

```toml
[project.entry-points."agent_console.sdd_verification_sources"]
"example.junit" = "agent_console_example_sdd_junit:JUnitVerificationSource"
```

At server startup, the host plugin loader (`agent_console.host_plugin_loaders: sdd` of `mod-sdd`) reads this group.
**Installing alone does not use it**: it goes into the trace table only when the user settings list it with `enabled: true` (unlike the
default source `runs`, which a link module provides through a port). To use the same class with another id, register a function that returns
`JUnitVerificationSource("ci")` as the entry point.

## Settings example

`sdd.verification_sources` in the workspace settings (`settings.yaml`, the *Specs* section of the settings screen):

```yaml
sdd:
  verification_sources:
    - id: example.junit
      enabled: true
      options:
        paths: ["reports/**/*.xml", "build/test-results/**/TEST-*.xml"]
        # when empty (null), the requirement ids of the spec's requirements document are found as words
        requirement_pattern: "\\[(?P<id>[A-Z]+\\d+(?:\\.\\d+)*)\\]"
        task_pattern: "task_(?P<task>\\d+_\\d+)"   # task keys that are not in the spec are dropped
        match_fields: [classname, name]
        result_map: {passed: pass, failed: fail, error: fail, skipped: skipped}
        status_priority: [fail, skipped, pass]
        label: CI
```

| Option | Default (`data/defaults.json`) | Meaning |
| --- | --- | --- |
| `paths` | `[]` (reads nothing) | JUnit file globs (relative to the project folder). `*`, `?`, `[..]`; `**` = zero or more folders (hidden folders are not entered) |
| `requirement_pattern` | `null` | Requirement id regular expression (group `id` or the whole match). `null` = find the spec's requirement ids as words |
| `task_pattern` | `null` | Task key regular expression (group `task` or the whole match). `null` = do not attach to tasks |
| `match_fields` | `[classname, name]` | The `<testcase>` attributes to look at |
| `result_map` | `passed→pass`, `failed→fail`, `error→fail`, `skipped→skipped` | Test result → trace table value |
| `status_priority` | `[fail, skipped, pass]` | The order to choose in when several tests attach to one requirement (values not in the list go last) |
| `label` | `JUnit` | Prefix of the result label (`JUnit (3)`) |
| `max_files`, `max_file_bytes`, `max_dirs`, `max_testcases` | 50, 5MB, 2000, 20000 | Read limits (reading stops when exceeded) |
| `regex_timeout_ms` | 50 | Time limit for one regular expression match |

Unknown keys, wrong values, patterns outside the folder, and dangerous regular expressions reject the whole options (no results from that source). Before saving,
`check_options(options)` returns a list of (location, reason).
Task keys are compared exactly as the spec syntax defines them. When test names cannot contain `.`, use `_` as in the example above, and when the key shape
differs, capture only the matching part with `task_pattern` (the example does not rewrite keys; change the source if you need that).

## Install and remove

Run these from the repository root. Install into the same Python environment as the server. When the server runs in a different virtual environment,
add `--python <path to that virtual environment>` (for example, when you set it with `UV_PROJECT_ENVIRONMENT`, `--python "$UV_PROJECT_ENVIRONMENT"`).

```bash
uv pip install -e examples/extensions/agent-console-example-sdd-junit   # install
uv pip uninstall agent-console-example-sdd-junit                        # remove
```

Entry points are read at server startup, so **restart the server** after installing or removing.
- Installed and turned on in the settings: `capabilities.verification` of `GET /api/v1/sdd/info?project=<id>` is true, and `source: example.junit` results appear in the verification column of the trace table.
- Removed or `enabled: false`: those results disappear from the trace table. The settings entry is not deleted.
- Keep it installed but not loaded: remove `example.junit` from the server setting `plugins.enabled` (allow list).

Note: `uv sync` removes packages that are not in the lock file. To sync with the example installed, use `uv sync --all-packages --inexact`.

## Test

The tests run without installing (pytest setting `pythonpath = ["src"]`). The `examples` step of the root `uv run poe check` runs mypy and pytest
with this folder's settings (`uv run poe examples`). Outside the repository, copy only this folder, run `uv sync --find-links <wheelhouse>`
(`uv run poe wheels` in the repository), and then `uv run pytest`.

```bash
cd examples/extensions/agent-console-example-sdd-junit
uv run --project ../../.. python -m pytest
```

- `tests/test_agent_console_example_sdd_junit.py`: the entry point declaration, options (defaults, rejection of 10 kinds of patterns outside the folder, dangerous
  regular expressions, unknown keys), reading JUnit (four kinds of results, nested suites, times, DTD rejection), globs (`**`, hidden folders, links not followed: nothing is read even when a real folder
  symbolic link points outside), finding requirement ids, combining per requirement and task, result name data, and limits.
- `tests/test_mod_sdd_assembly.py`: assembles a test host + `mod-sdd` + one project space and loads the entry point with the
  mod-sdd loader. When turned on in the settings, the trace table shows `R1 pass` and `R2 fail` (+ `verification_failed`); when not turned on, there are no
  results; with a pattern outside the folder, there are no results.

Test your own source the same way: for unit tests, provide files with `agent_console_sdd.testing.MemorySpecFiles`, and build the
assembly with `agent_console_mod_sdd.testing` (`static_settings_module`, `spaces_module`, `SimpleSpace`).
