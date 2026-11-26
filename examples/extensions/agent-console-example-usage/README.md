# agent-console-example-usage

An example that adds a new **usage source** with a single plugin package.
No engine, server, or web code changes. Once installed, it appears in the source list and the window cards of the usage screen, and it disappears when removed.

Usage source `example.manual_count` (manually entered usage)
- For tools without official usage values (an in-house gateway, a team's shared quota, and so on), the user writes the values in the settings directly.
- Settings: `windows: [{window, used, limit, status?}]` → `used_ratio = used / limit` per window. Values that are not written (`status`, `resets_at`) are `None` (nothing is made up).
- Trust level `trust = "manual"`: an example showing that values outside the known levels (`official`, `observed`, `estimated`, `unofficial`) work too. The screen shows it with the default badge.
- The observation time comes from the injected clock (`ctx.now`). There are no external calls.

This package is not a uv workspace member. When it is not installed, it changes nothing.

## Minimal code

```python
from agent_console_contracts import UsageSourceDescriptor, UsageWindowSnapshot
from agent_console_usage import UsageSourceContext


class ManualCountSource:
    descriptor = UsageSourceDescriptor(
        id="example.manual_count",
        title="직접 적은 사용량",
        trust="manual",
        config_schema={"type": "object", "properties": {"windows": {"type": "array"}}},
    )

    async def snapshot(self, ctx: UsageSourceContext) -> list[UsageWindowSnapshot]:
        return [
            UsageWindowSnapshot(
                source=ctx.source_id,
                window=w["window"],
                used_ratio=w["used"] / w["limit"],
                observed_at=ctx.now,
            )
            for w in ctx.config.get("windows", [])
        ]
```

The real implementation is `src/agent_console_example_usage/manual_count.py` (split into the pure function `windows_from_config`; wrong items are skipped).
The server validates `usage.sources[].config` against `config_schema` before passing it on (when wrong, only that source shows an error).

## Registration and settings

```toml
[project.entry-points."agent_console.usage_sources"]   # agent_console_usage.USAGE_SOURCES_GROUP
"example.manual_count" = "agent_console_example_usage:ManualCountSource"
```

Workspace settings (the settings screen or `settings.yaml`):

```yaml
usage:
  sources:
    - id: example.manual_count
      config:
        windows:
          - {window: team_weekly, used: 120, limit: 500}
  window_labels: {team_weekly: "Team weekly quota"}
```

## Install and remove

Run these from the repository root. Install into the same Python environment as the server. When the server runs in a different virtual environment,
add `--python <path to that virtual environment>` (for example, when you set it with `UV_PROJECT_ENVIRONMENT`, `--python "$UV_PROJECT_ENVIRONMENT"`).

```bash
uv pip install -e examples/extensions/agent-console-example-usage   # install
uv pip uninstall agent-console-example-usage                        # remove
```

**Restart the server** after installing or removing.
- Install: it appears in `GET /api/v1/usage/sources`, and with the settings above the usage rate shows up in `GET /api/v1/usage` and the window cards of the usage screen.
- Remove: it disappears from the source list and the window cards. The `usage.sources` entry in the settings remains, but it is ignored because no source is registered.
- Turn off while installed: set `enabled: false` in the settings entry, or remove it from the server setting `plugins.enabled` (allow list).

Note: `uv sync` removes packages that are not in the lock file. To sync with the example installed, use `uv sync --all-packages --inexact`.

## Test

```bash
cd examples/extensions/agent-console-example-usage
uv run --project ../../.. python -m pytest
```

The tests run without installing (`pythonpath = ["src"]`). The `examples` step of the root `uv run poe check` runs mypy and pytest with this folder's settings (`uv run poe examples`).
E2E: the usage source scenario of `apps/web/e2e/08-extension.spec.ts` installs this package into a temporary folder and uses it.
