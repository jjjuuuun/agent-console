# agent-console-example-log-source

An example that adds a new **log source** and **log classifier** with a single plugin package.
No engine, server, or web code changes. Once installed, they appear in the log source list (`GET /api/v1/logs/sources`) and the classifier list,
and they disappear when removed.

Source and classifier `example.text_log` (text log)
- Format: one line per entry, `<ISO 8601 time> <level> [<thread>] <message>` (`[thread]` is optional).
- The source subclasses `JsonlFileSource` and changes only `parse_line`. Incremental reads (byte offset cursor), holding back unfinished lines,
  file rotation detection, and read-only opening are done by the base class. Lines with a wrong format are not dropped; they become diagnostic events.
- The classifier is stateless, row by row. The level → category mapping is settings data (`level_categories`, default `ERROR` and `FATAL` → `error`,
  everything else `default_category` = `system`), so you change it without changing code. Session = file, status = the level in lowercase.
- The original files are only read (the tests check this with `no_writes_under` and `tree_digest`).

This package is not a uv workspace member. When it is not installed, it changes nothing.

## Minimal code

A source needs only `parse_line` (line → value), and a classifier only `classify` (value → normalized event drafts).

```python
>>> from typing import ClassVar
>>> from agent_console_contracts.logs import LogClassifierDescriptor, LogSourceDescriptor
>>> from agent_console_logs import JSONL_CONFIG_SCHEMA, JsonlFileSource, LogEventDraft

>>> class TinySource(JsonlFileSource):
...     descriptor: ClassVar[LogSourceDescriptor] = LogSourceDescriptor(
...         id="tiny", title="한 줄 텍스트", format="tiny", config_schema=JSONL_CONFIG_SCHEMA
...     )
...     def parse_line(self, line):
...         level, _, message = line.decode("utf-8").partition(" ")
...         return {"level": level, "message": message}

>>> class TinyClassifier:
...     descriptor = LogClassifierDescriptor(id="tiny", formats=["tiny"], title="한 줄 텍스트")
...     def classify(self, record, ctx):
...         row = record.data
...         category = "error" if row["level"] == "ERROR" else "system"
...         return [LogEventDraft(category=category, title=row["message"], session=ctx.ref.ref)]

```

The real implementation is `src/agent_console_example_log_source/text_log.py` (time parsing, the pure function `parse_text_line`,
and the level → category mapping through the settings schema). Below, that implementation is loaded as if it were registered as an entry point, and logs are collected.

```python
>>> import tempfile
>>> from importlib.metadata import EntryPoint
>>> from pathlib import Path
>>> from agent_console_contracts.logs import LogSettings
>>> from agent_console_logs import (
...     LOG_CLASSIFIERS_GROUP, LOG_SOURCES_GROUP, LogFilter, LogIngestor, LogRegistries, query_context,
... )
>>> from agent_console_logs.testing import MemoryLogIndex

>>> value = "agent_console_example_log_source:"
>>> eps = [
...     EntryPoint("example.text_log", value + "TextLogSource", LOG_SOURCES_GROUP),
...     EntryPoint("example.text_log", value + "TextLogClassifier", LOG_CLASSIFIERS_GROUP),
... ]
>>> registries = LogRegistries()
>>> _ = registries.load(entry_points=eps)        # when installed, call only load()
>>> [d.id for d in registries.source_descriptors()]
['example.text_log']

>>> folder = Path(tempfile.mkdtemp())
>>> _ = (folder / "app.log").write_text(
...     "2026-10-17T09:00:00Z INFO [worker] 작업 시작\n"
...     "2026-10-17T09:00:02Z ERROR [worker] 연결 실패\n",
...     encoding="utf-8",
... )
>>> index = MemoryLogIndex()
>>> ingestor = LogIngestor(index, registries)
>>> settings = LogSettings.model_validate(
...     {"sources": [{"id": "example.text_log", "enabled": True, "config": {"roots": [str(folder)]}}]}
... )
>>> ingestor.scan(settings).new_events
2
>>> [(e.category, e.title, e.status) for e in index.query_events(LogFilter(), query_context(settings)).items]
[('system', '작업 시작', 'info'), ('error', '연결 실패', 'error')]

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

## Registration and settings

```toml
[project.entry-points."agent_console.log_sources"]       # agent_console_logs.LOG_SOURCES_GROUP
"example.text_log" = "agent_console_example_log_source:TextLogSource"

[project.entry-points."agent_console.log_classifiers"]   # agent_console_logs.LOG_CLASSIFIERS_GROUP
"example.text_log" = "agent_console_example_log_source:TextLogClassifier"
```

The `format` of the source descriptor is the default classifier id. The setting `logs.sources[].config.classifier.id` chooses another classifier, and `classifier.config` passes the classifier settings.
Modules that are not installed are read with `LogRegistries.load(source_modules=["example.text_log=agent_console_example_log_source:TextLogSource"],
classifier_modules=[...])` (they go through the same checker).

Workspace settings (the settings screen or `settings.yaml`). You have to set the roots, so it is off by default.

```yaml
logs:
  sources:
    - id: example.text_log
      enabled: true
      config:
        roots: ["~/my-app/logs"]           # default include pattern **/*.log
        classifier:                        # {id?, config?}; when id is empty, the source's format
          config:
            level_categories: {ERROR: error, WARN: error}
            default_category: system
```

## Install and remove

Run these from the repository root. Install into the same Python environment as the server. When the server runs in a different virtual environment,
add `--python <path to that virtual environment>` (for example, when you set it with `UV_PROJECT_ENVIRONMENT`, `--python "$UV_PROJECT_ENVIRONMENT"`).

```bash
uv pip install -e examples/extensions/agent-console-example-log-source   # install
uv pip uninstall agent-console-example-log-source                        # remove
```

**Restart the server** after installing or removing.
- Install: `GET /api/v1/logs/sources` lists `example.text_log` (turned off). With the settings above, collecting shows one session per file in the session list.
- Remove: it disappears from the source list. The `logs.sources` entry in the settings and the events already indexed remain, but nothing new is collected.
- Turn off while installed: set `enabled: false` in the settings entry, or remove it from the server setting `plugins.enabled` (allow list).

Note: `uv sync` removes packages that are not in the lock file. To sync with the example installed, use `uv sync --all-packages --inexact`.

## Test

```bash
cd examples/extensions/agent-console-example-log-source
uv run --project ../../.. python -m pytest
```

The tests run without installing (`pythonpath = ["src"]`). The `examples` step of the root `uv run poe check` runs mypy and pytest with this folder's settings (`uv run poe examples`).
