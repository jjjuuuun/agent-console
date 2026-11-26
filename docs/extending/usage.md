# Usage

The usage screen gathers and shows the usage rate and reset time of the windows that sources provide (the 5-hour
window, the weekly window, and so on). The service knows neither source names nor window names. Values a source does
not provide are left empty (`None`), never made up. There are two ways to add a source.

| Way | When |
| --- | --- |
| A plugin source ([usage-source](#usage-source)) | When the source can get the values on its own (a file, an external API, values written in settings) |
| A source provided by a module ([runtime-usage-source](#runtime-usage-source)) | When getting the values needs the data of another server feature (the log index, run history) |

Either way, users turn sources on and off and give them values with the same settings. The `id` of an entry in the
workspace setting `usage.sources` is the source id.

```yaml extdocs:validate=agent_console_contracts:WorkspaceSettings
usage:
  sources:
    - id: acme.gateway
      enabled: true
      config:
        endpoint_env: ACME_USAGE_URL
    - id: statusline-file
      enabled: false
  window_labels:
    five_hour: 5시간
```

A source that is not in the settings is on only when its descriptor `auto_enable` is true. The setting `config` is
validated against the source descriptor's `config_schema`, and when it is wrong, the pre-save check blocks it with
the error `usage.source_config_invalid` (the value is not put in the text).

## runtime-usage-source

**When to use**: when computing usage values needs the data of another server feature. The built-in implementation
is `local-logs` (it estimates window usage from the token samples of the log index), provided by the logs and usage
link. If the source package imported that feature, feature independence would break, so a link module takes the
public ports of both features, builds the source object, and puts it on the usage module's port.

**Minimal shape**: put `provides=[USAGE_SOURCES]` (port name `usage.sources`, multi-provider) in the link module's
descriptor and call `ctx.provide(USAGE_SOURCES, source)` in `build`. The source object is the same `UsageSource` as
in [usage-source](#usage-source). For the port key, do not import the usage module; declare a `PortKey` with the same
name in your own package ([Link modules](links.md#only-public-ports)).

**Rules**

- Keep the source id from colliding with entry point sources. On a collision, only one of them shows in the usage
  list.
- If you can tell when the data changes (for example, by subscribing to log index notifications), drop the cache at
  that moment. Do not reread everything every time `snapshot` is called.
- Report the trust level (`trust`) honestly. Values guessed from other data are `estimated`.

**Common mistakes**: not considering environments where the usage module is off. Without a required port, the link
is turned off as `unsatisfied` and the server must still start. Do not look up other modules directly in the link's
`build`.

**Data left after removal**: when the link is turned off (the link itself, or any module that provides a required
port) or removed, the source disappears from the source list. The entry in the setting `usage.sources` stays, but
there is no registered source, so it is ignored without an issue.

<!-- extdocs:facts runtime-usage-source -->
- Registration: A server module provides the port `usage.sources` (symbol `agent_console_mod_usage:USAGE_SOURCES`, multiple: yes).
- Interface:
  - `agent_console_usage:UsageSource` — Usage source. Register it through entry point `agent_console.usage_sources`.
- Built-in implementations: `link-logs-usage`
- Examples:
  - reference: [packages/py/links/ac-link-logs-usage](../../packages/py/links/ac-link-logs-usage/README.md)
- Turning it off or removing it: Turn off the providing module (`modules.<id>.enabled: false`); consumers turn off only the parts that use it.
<!-- /extdocs:facts -->

## usage-source

**When to use**: when there is usage that the built-in sources (run event tokens, the Claude Code status line file,
a fake for tests) cannot show. Examples are in-house gateway quotas, another tool's usage API, and a shared team limit
that users write themselves.

**Minimal shape**: `descriptor` (`UsageSourceDescriptor`: `id`, `title`, `trust`, and optionally `config_schema`,
`auto_enable`, `setup_help`) and one method, `async snapshot(ctx) -> list[UsageWindowSnapshot]`. `ctx`
(`UsageSourceContext`) holds the current settings (`config`) and the injected clock value (`now`).

**Rules**

- **Do not make up values.** Leave usage rates, reset times, and states the source does not know as `None`. The
  screen does not fill empty values with numbers. When there is nothing to observe, return an empty list.
- Window ids (`five_hour` and so on) are strings the source defines. The user setting `usage.window_labels` changes
  their display names.
- The trust level `trust` is an open string. Values outside the known ones (`official`, `observed`, `estimated`,
  `unofficial`) are allowed, and the screen shows them with the default badge.
- Use `ctx.now` for times (so tests can change it). If there are external calls, finish within the time limit. If the
  source does not answer in time, the service marks only that source as `usage_source_timeout` and the other sources
  still show. A read failure reported as an exception becomes `usage_source_failed`.
- Do not take secrets (API tokens) as values in `config`. Take an environment variable name or a `secret://`
  reference.
- For a source that works only with settings, turn off `auto_enable` and write one paragraph in `setup_help` on what
  to fill in.

**Common mistakes**: dropping the reset time and emitting only the usage rate. The service removes windows whose
reset time has passed from the current values; without the time, old values look current.

**Data left after removal**: the source disappears from the source list and the window cards. Its entry in the
setting `usage.sources` stays, but there is no registered source, so it is ignored without an issue. When you install
it again, it shows again with the same settings.

<!-- extdocs:facts usage-source -->
- Registration: Register in the entry point group `agent_console.usage_sources` (constant `agent_console_usage:USAGE_SOURCES_GROUP`). The registration name is the id.
- Interface:
  - `agent_console_usage:UsageSource` — Usage source. Register it through entry point `agent_console.usage_sources`.
  - `agent_console_usage:UsageSourceContext` — Context passed to `UsageSource.snapshot` (read-only).
  - `agent_console_usage:UsageRecord` — One usage record (aggregation input). Unknown dimensions are `None`.
- Settings: `usage.sources`
- Built-in implementations: `fake (agent-console-usage)`, `run-events (agent-console-usage)`, `statusline-file (agent-console-usage)`
- Examples:
  - package: [examples/extensions/agent-console-example-usage](../../examples/extensions/agent-console-example-usage/README.md)
- Turning it off or removing it: Add the name to the setting `plugins.disabled`, or uninstall the package, then restart the server.
<!-- /extdocs:facts -->
