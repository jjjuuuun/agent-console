# Distribution

This page explains how to let other people install your plugin or module package on their servers. The server reads
entry points at startup, so "install, then restart" is all it takes. The server packages are not on PyPI, so provide
a wheelhouse along with the install.

## Build

### Python wheels

```bash
# in your plugin folder
uv build --wheel                         # → dist/<name>-<version>-py3-none-any.whl

# in the source repository: the server and all built-in packages
uv run poe wheels                        # → dist/wheelhouse
```

A wheel contains the packages under `src/` and the data files inside them. Keep data such as default values, text,
and mapping tables in `data/` inside the package and read it with `importlib.resources`. Do not read paths outside the
package (the repository root, the home folder).

### TypeScript tarballs

```bash
pnpm pack:all                            # build each package → dist/npm/*.tgz
```

Web extensions are not installed at runtime. They are included when you rebuild the web app. See [Web](web.md).

## Install

Install into the Python environment the server runs in.

```bash
uv pip install --find-links <wheelhouse> ./dist/my_console_ops-0.1.0-py3-none-any.whl
uv pip install --python <server virtual environment> --find-links <wheelhouse> my-console-ops   # when the environment differs
```

- Restart the server after installing. To check: `plugins` of `GET /api/v1/server-info` (plugins) and
  `GET /api/v1/modules` (server modules).
- During development, install with `uv pip install -e <folder>` (editable mode) so that code changes apply at the next
  restart.
- If you rebuild a wheel with the same name and version and install it, uv may install the old wheel left in its
  cache. Raise the version, or install with `uv pip install --reinstall …` or a new cache folder
  (`UV_CACHE_DIR=<empty folder>`).
- If a server module declares command-line options, they appear in `agent-console serve --help` after installing.

### Environments that use `uv sync`

If you run the server from a uv project (for example, a checkout of the source repository), `uv sync` **removes**
packages that are not in the lock file. To keep plugins you installed separately:

```bash
uv sync --all-packages --inexact
```

If you want to pin the plugin as a project dependency, it is better to add it to the lock file with `uv add`.

## Remove

```bash
uv pip uninstall my-console-ops
```

- Restart the server. Data that used the plugin's names stays, and the checks report warnings or errors
  ([Plugin basics](plugins.md#data-left-after-removal)).
- When you remove a server module, its paths disappear and **its DB tables and files stay**. To remove the tables as
  well, downgrade that module's migration branch before removing it. Leftover settings in `modules.options.<id>` only
  produce a warning, and the server starts.
- To turn something off for a while without removing it, use `plugins.disabled` for plugins and `modules.disabled`
  for modules.

## Version compatibility

| Situation | Result | What to do |
| --- | --- | --- |
| The server's contract minor moves past the plugin's range (for example, 0.16 → 0.17) | Dependency resolution fails at install or upgrade time | Test with the new contract and release a new version with a raised range |
| A patch within the same minor | Works as before | — |
| Outside the range of a feature library the plugin uses (`agent-console-runtime` and others) | Resolution fails | Same as above |

- The server's contract version is `contracts_version` in `GET /api/v1/server-info`. The submodule versions are in
  [contract submodule versions](reference.md#contract-submodule-versions).
- Do not leave the range open (`>=0.16`). In 0.x, shapes can change when the minor changes, and a resolution failure
  is easier to notice than an error during a run.
- When you change your own data (settings keys, event types, issue codes), do not silently rewrite old values when you
  read them. For a server module, point to the new location with `RemovedSetting` in `settings_compat`. For a plugin,
  write it in the CHANGELOG.

## Before publishing

Check these before you push to a public repository or a package index.

- **Secrets**: keys, tokens, and session values are not in the code, test data, README examples, or default value
  files. Examples use only `secret://name` references.
- **Local paths**: your home folder, drive paths, and user name are not in settings examples, expected test values, or
  log examples. Keep paths as settings values or relative paths.
- **Personal information**: email addresses, real names, and internal addresses are not in examples or tests.
- **Portability**: copy only the plugin folder into a new folder and check that `uv sync --find-links <wheelhouse>`
  and then `uv run pytest` pass.

You can scan default values and example data with the server's secret suspicion rules package
(`agent-console-secret-rules`). Its results contain only the location and the reason, never the value.

```python
>>> from agent_console_secret_rules import SecretRules
>>> defaults = {"endpoint": "https://example.org", "headers": {"Authorization": "Bearer abc123456"}}
>>> [(f.path, f.reason) for f in SecretRules().find_suspected(defaults, path="/defaults")]
[('/defaults/headers/Authorization', 'key_name')]

```

For documents inside the source repository, `uv run poe extdocs-check` runs the same kind of checks (internal paths,
email addresses, and so on) on the docs and example READMEs.
