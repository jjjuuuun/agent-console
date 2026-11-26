# Architecture map

The architecture map is a picture that gathers log events into cells and edges. What to count and where to draw it are
all profile data. Profiles are added through user settings and plugins ([architecture-profile](#architecture-profile)),
and other modules contribute checks ([architecture-profile-check](#architecture-profile-check)). Interpreting drawing
names such as the color and shape of a cell (`tone`, `view`) is the job of web-side extensions.

## architecture-profile

**When to use**: when you want to view logs with a structure different from the default profiles (a different way of
building teams, the format of a new log source). For your own use, write it in your user settings. To ship a profile
for your own format together with, for example, a log source plugin, publish it through an entry point.

**Adding with data**: the `architecture` section of the workspace settings. For each profile id, write cells
(`cells`), edges (`edges`), and conditions (`when`). Conditions use the same syntax as the edge conditions of a team.

```yaml extdocs:validate=agent_console_contracts.architecture:ArchitectureSettings
include_defaults: true
default_profile: tool-flow
profiles:
  tool-flow:
    title: 도구 흐름
    cells:
      ask:
        label: 질문
        x: 100
        y: 60
        when: {all: [{path: /category, op: eq, value: input}]}
      work:
        label: 도구
        x: 400
        y: 60
        metrics: [count, errors, duration]
        group_by: /tool
        when: {all: [{path: /category, op: eq, value: tool}]}
    edges:
      - {id: hand, from: ask, to: work, kind: structural}
    error_when: {all: [{path: /status, op: eq, value: failed}]}
```

**Adding with a plugin**: the entry point value is a function without arguments that returns
`{profile id: profile data}`. The recommended way is to keep a data file inside the package and return what you read
from it. For a full example, see the [architecture map example](../../examples/extensions/agent-console-example-architecture/README.md).

**Rules**
- The merge order is package defaults (when `include_defaults` is set) → plugins → user settings. For the same id, the
  whole profile is replaced (cells are not merged one by one), and writing `null` in user settings turns that profile
  off.
- An edge is counted only when a single event that recorded that handoff matches the condition. An edge known only
  from order is written as `kind: structural` and has no metrics.
- Metrics that were not collected show as "Not collected", not as 0. Write the cells that each source kind fills in
  `coverage`.
- When several sources record the same occurrence, only the source that comes first in `source_priority` is counted
  (to avoid double counting).

**Common mistakes**: writing a condition path with a field that the list query does not have (inside `detail` or
`raw`; no event matches, so the cell stays empty and the check warns), and changing a cell id while leaving `from` and
`to` of the edges as they were (`architecture.unknown_cell`).

**Turning off and leftover data**: when you remove the plugin, its profiles disappear from the list. If
`default_profile` in the settings was one of those ids, another profile opens instead with an
`architecture.profile_fallback` notice. A profile with the same id written in user settings stays.

<!-- extdocs:facts architecture-profile -->
- Registration: Register in the entry point group `agent_console.architecture_profiles` (constant `agent_console_architecture:ARCHITECTURE_PROFILES_GROUP`). The registration name is the id.
- Interface:
  - `agent_console_architecture:ProfileSource` — The bundle of profiles one source provides.
  - `agent_console_contracts.architecture:ArchitectureProfile` — An architecture map profile: which cells and edges to draw where, and what to count.
- Settings: `architecture.profiles`, `architecture.include_defaults`
- Built-in implementations: —
- Examples:
  - package: [examples/extensions/agent-console-example-architecture](../../examples/extensions/agent-console-example-architecture/README.md)
  - snippet: Data in the user setting `architecture.profiles`
- Turning it off or removing it: Add the name to the setting `plugins.disabled`, or uninstall the package, then restart the server.
<!-- /extdocs:facts -->

## architecture-profile-check

**When to use**: to add warnings that only another feature knows about to the profile checks of the architecture map
module. For example, the link with the logs module warns about cells whose condition path uses a field that is not in
the log list body.

**Minimal shape**: an object with `check(profile, profile_id) -> list[Issue]`. `profile` is the contract
`ArchitectureProfile`, and `profile_id` is the saved id (for a check while editing, the requested id or `None`).
Provide it on the multi-provider port in the `build` of a link module. The reference implementation is the
[logs and architecture map link](../../packages/py/links/ac-link-logs-architecture/README.md).

```python
from agent_console_contracts import Issue


class NoEmptyCells:
    def check(self, profile, profile_id):
        return [
            Issue(severity="warning", code="example.cell_without_condition",
                  message=f"칸 {cell_id}에 조건이 없습니다", path=f"/cells/{cell_id}")
            for cell_id, cell in profile.cells.items()
            if cell.when is None
        ]
```

**Rules**
- It must be a pure function. The same profile gives the same result. The architecture map module calls it again only
  when the input changes.
- Issue codes use your own prefix. The severity is usually `warning`. It does not block saving and shows on the list
  and editor screens.
- An exception skips only that check. Do not modify the profile.

**Common mistakes**: reading a heavy store such as the log index on every check (the link fetches the values it needs
in advance).

**Turning off**: when you turn off the link module that provides it, only those warnings drop out.

<!-- extdocs:facts architecture-profile-check -->
- Registration: A server module provides the port `architecture.profile_checks` (symbol `agent_console_mod_architecture.ports:PROFILE_CHECKS`, multiple: yes).
- Interface:
  - `agent_console_mod_architecture.ports:ProfileCheck` — ``architecture.profile_checks`` port shape: an added profile check.
- Built-in implementations: `link-logs-architecture`
- Examples:
  - reference: [packages/py/links/ac-link-logs-architecture](../../packages/py/links/ac-link-logs-architecture/README.md)
- Turning it off or removing it: Turn off the providing module (`modules.<id>.enabled: false`); consumers turn off only the parts that use it.
<!-- /extdocs:facts -->
