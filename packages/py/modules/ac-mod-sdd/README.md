# agent-console-mod-sdd

Agent Console specs (SDD) server module (`mod-sdd`). It attaches `ac-sdd` (task syntax, parsing, plans, traces,
spec store) to the server. It does not know about runs or projects; link modules attach both through ports.

- REST `/sdd/*` (spec list, create, view, save, delete; document bodies and states; tasks and fixes; plans, traces, input variables, and
  the effective syntax; task integration actions, starting several at once, and auto-advance; save as template; import from and export to folders; and screen information
  `GET /sdd/info`). Every route accepts `?project=<space name>`.
- A single document template (`template_routes`): `POST /sdd/templates` (an empty template), `GET·PUT·DELETE /sdd/templates/{id}`
  (`ETag` and `If-Match` = the definition version), skeleton files `…/files[/{path}]`, versions `…/versions…` and `…/restore`, and version comparison `…/versions/{a}/diff[/{b}]` (`DefinitionDiff`; suspected secret
  locations are `***`). The store is the same as for the template
  list (the library, or the standalone root when there is none; `?project=` = that space). `variables` and `check` cannot be used as template ids.
- `GET /sdd/import/files?path=`: the markdown files of that folder and its direct subfolders (`dirs`, excluding hidden, linked, and reserved ones).
- WS topic `sdd.changed` (no content; the screen reads again).
- Definition kind contributions (`definitions.kind_contributions`): document templates (library and project, with reference extraction for the teams of
  run profiles) and specs (`library=False`). Kind names and folder names are administrator options (the defaults are the package data
  `data/defaults.json`).
- User settings section `sdd` (`include_default_syntax`, `syntax`, `secret_scan`, `verification_sources`).
  Unknown keys are kept, and only the broken parts are left out and reported in `server.warnings` as `sdd.settings_invalid`.
- Spaces: `sdd.spaces` (optional, provided by `link-projects-sdd`). Requests without a space name use the standalone root
  (`standalone_root`, by default `sdd/` inside the workspace). When a name is given but the link is missing, 409
  `sdd.spaces_unavailable` (nothing is created in the app workspace instead). Document template requests without a space name read the app
  library (`definitions.store`), or the templates of the standalone root when there is no library.
- Extension points: task integrations (`sdd.integrations`, several providers) and verification result sources
  (the `sdd.verification_sources` port + the entry point `agent_console.sdd_verification_sources`; plugin
  sources are turned on in the user settings). The screen capabilities `SddInfo.capabilities` are computed from which ports exist.
- Run label display rule: the administrator prefix (`run_label_prefix`, default `sdd.`) is added and
  exposed as `ModuleParts.label_display` → `label_display` of `GET /modules`.
- A parse cache (space, spec, definition version, body hash, effective syntax key; LRU) and the secret check of document bodies (`secret_scan`:
  off, warn, reject).

## Dependencies: what, why, alternatives

- In-house: `agent-console-sdd` (SDD core), `agent-console-store` (definition store, versions), `agent-console-conditions`
  (gate operator registry), `agent-console-registry` (verification source plugins), `agent-console-secret-rules`
  (secret checks of bodies), and `agent-console-modkit[host]` (module, host). No new external dependencies (FastAPI and pydantic are
  the same as other modules).

## Install

```bash
pip install agent-console-mod-sdd
# outside the repository, with in-house dependencies: pip install --find-links <wheelhouse> agent-console-mod-sdd
```

## Minimal usage (one module + the standalone root)

```python
>>> import tempfile
>>> from pathlib import Path
>>> from fastapi.testclient import TestClient
>>> from agent_console_mod_sdd import module
>>> from agent_console_modkit import BaseServices, Paths, assemble
>>> from agent_console_modkit.host import SecurityPolicy, create_host_app

>>> tmp = Path(tempfile.mkdtemp())
>>> base = BaseServices(paths=Paths(base_dir=tmp, workspace=tmp / "ws", state=tmp / "state"))
>>> assembly = assemble([module], base=base)
>>> policy = SecurityPolicy.for_bind("127.0.0.1", 0, token="t" * 32, allowed_hosts=["testserver"])
>>> client = TestClient(create_host_app(assembly, policy=policy))
>>> client.headers["X-Console-Token"] = "t" * 32
>>> with client:
...     print(client.get("/api/v1/sdd/specs").json())
...     made = client.post("/api/v1/sdd/specs", json={"name": "Demo"}).json()
...     print(made["spec"]["id"], made["directory"])
[]
demo specs/demo

```

<!-- doctest: keep a blank line after expected output so the closing fence is not read as output. -->

Standalone run: `python -m agent_console_mod_sdd [--with ID] [--config PATH] [--port 0] [--check]`. User
settings go in the `sdd` section of the workspace `settings.yaml`.

## Ports

| Port | Direction | Shape |
| --- | --- | --- |
| `sdd.service` | Provides | `SddServicePort`: `label_key(name)`, `secret_findings(text)`, `secret_mode()`, `notify(space, spec_id)` (+ `scope(space)` and `context(scope, loaded)` of the implementation `SddService`) |
| `definitions.kind_contributions` | Provides (several) | Two `KindContribution(DefinitionKind, references, title, delete)` (`delete` does the same as the module's own delete route; the common delete for all kinds calls it) |
| `server.warnings` | Provides (several) | User settings format problems |
| `sdd.spaces` | Optional | `SddSpaces.open(name) -> SddSpace{store, files, config_writable, config_dir?, max_content_bytes?}` |
| `sdd.integrations` | Optional (several) | `agent_console_sdd.TaskIntegration` (+ the optional attribute `link_kinds`, capabilities `ProfileChecker` and `AutomationControl`) |
| `sdd.verification_sources` | Optional (several) | `agent_console_sdd.VerificationSource` |
| `workspace.settings`, `secrets.rules`, `definitions.store` | Optional | User settings, secret rules, library store |

- When the `link_kinds` of an integration (for example `("run",)`) contain `run`, `capabilities.runs=true`. Auto-advance exists only when
  an integration implements `AutomationControl` (`capabilities.automation`; the routes `…/automation/{stop|
  resume}` return 404 otherwise).
- Fakes for tests and other apps: `agent_console_mod_sdd.testing` (`SimpleSpace`, `spaces_module`,
  `integration_module`, `verification_module`, `library_module`, `static_settings_module`).

## Development and reuse

This folder is a standalone project. Copy only this folder and the commands below still work.

```bash
uv sync                # includes the dev dependency group
uv run ruff check .
uv run mypy
uv run pytest          # includes the doctests in README.md
```
