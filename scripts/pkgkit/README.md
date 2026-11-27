# pkgkit

Package portability tools. The Python tools (.py) are described in their own section below.

## TS tools (.mjs)

They make sure a single package still installs, builds and tests after it is copied out of the repository, and check that it does. Node ^22.23.4 || ^24.22.1 || >=26.12.1 (the versions with the CVE-2026-111497 fix), no external dependencies (pure functions in `lib/`, input and output in each CLI).

| File | What it does |
| --- | --- |
| `pkg-lint.mjs` | `workspace:`, relative `extends`, paths and imports outside the package, `exports` rules (development→src, default→dist), scripts, required files, undeclared dependencies, direct references into another package's internals, and the README `ts readme` block matching its range in `test/readme.test.ts` |
| `pack-all.mjs` | `pnpm -r pack --pack-destination dist/npm` after `pnpm -r --if-present build` |
| `portability.mjs` | The targets are every pnpm workspace member except apps (`agentConsole.kind: "app"`), including the `examples/web/` examples (narrow them with `--under`). When a needed tarball is missing it runs `pack:all` first (always with `--pack`), then copies the package to a temporary folder, replaces internal dependencies with the `dist/npm` tarballs (`file:` plus `overrides`), runs `npm install`, then build, typecheck and test, and prints a result table |
| `new-package.mjs` | Creates a new package from the templates. Root files are not changed |
| `lib/*.mjs` | Pure functions: `lint-rules`, `readme-sync`, `plans`, `scaffold`, `template` and `workspace` (only `fsutil` reads files) |
| `templates/ts/` | `common/` plus a `lib/` or `config/` layer. Files are `.tmpl`, placeholders are `{{key}}`, and `package.patch.json` is merged into package.json |

Usage (from the repository root; the root `package.json` registers them as `pnpm pkg-lint`, `pnpm pack:all`, `pnpm portability` and `pnpm new-package`. `pkg-lint` is part of `pnpm check`, and `pack:all` builds and packs only `./packages/**`, leaving out the root and apps):

```sh
node scripts/pkgkit/pkg-lint.mjs [--package NAME] [--json]
node scripts/pkgkit/pack-all.mjs [--dry-run]
node scripts/pkgkit/portability.mjs [--package NAME] [--under PREFIX] [--pack] [--keep]   # runs pack-all first when tarballs are missing
node scripts/pkgkit/new-package.mjs --kind lib|config [--dom] [--scope @scope] NAME
```

`portability` sets `AGENT_CONSOLE_SKIP_PERF=1` when it runs the steps in the copy (`PORTABILITY_ENV` in `lib/plans.mjs`). Tests with timing assertions skip only the timing comparison under this value and keep their correctness assertions. You can use the same variable when running tests yourself.

README rule: the ` ```ts readme ` code block in the README must match the range between `// readme:start` and `// readme:end` in `test/readme.test.ts` (common indentation and trailing spaces are ignored). The template's `vitest.config.ts` aliases the package name to its source so the test can import it by package name.

Common options:
- `--prefix P` (repeatable): the name prefix of internal packages. The default is the scope of the root package.json name, otherwise the scope of the workspace packages, otherwise `@agent-console/`. Packages created with `--scope @acme` are checked with `--prefix @acme` (or the default guess).
- `--under PREFIX`: the folder prefix to look for packages in (default `packages/ts/`). When the folder does not exist, it ends with a readable error (exit code 2).
- The kind (`lib`|`config`) is decided by the `"agentConsole": {"kind": "..."}` marker in package.json (written by `new-package`). Only without the marker is it guessed from a `config` segment in the path.

`dist` assumes bundler consumers (`moduleResolution: Bundler`, extensionless relative imports). If a package ever needs Node to run its `dist` directly, switch only that package to NodeNext.

`pkg-lint` rules (rule id):
| id | Meaning |
| --- | --- |
| `required-file` | A required file for the kind is missing |
| `package-json` | JSON errors, name, semver version, `private: true`, license, `type: module` |
| `workspace-protocol` | `workspace:`, `link:` and `file:` dependencies outside the package, and the same syntax in overrides |
| `inhouse-range` | Internal dependencies use only `^x.y.z`, `~x.y.z` or `>=a <b` ranges |
| `scripts` / `external-path` | Required scripts (lib: build, typecheck, lint, test; config: lint, test), and paths outside the package in scripts and tsconfig |
| `tsconfig`, `tsconfig-extends` | tsconfig parsing, and relative `extends` pointing outside the package |
| `exports` | `main`/`types` point to src, the development→src, default→dist and types→dist rules, and dist in `files` |
| `escaping-import` / `deep-import` | Relative imports outside the package / direct imports of another internal package's `src`, `dist` or `test(s)` |
| `undeclared-dep` | Dependencies the source imports but package.json does not list (`@types/*` declarations count) |
| `readme-sync` | The README `ts readme` block does not match its range in `test/readme.test.ts` |

Tests: `pnpm exec vitest run scripts/pkgkit`

## Python tools (.py)

They use only the standard library (Python 3.12+, `tomllib`). Every value the tools know (prefixes, paths, internal dependency ranges, rule switches) is in `pkgkit_py.toml`, and the list of kinds is defined by the `templates/python/kinds/` folder. Every command takes `--root` (default: the current folder) and `--config`. Errors exit with code 2, violations and failures with 1.

| File | What it does |
| --- | --- |
| `pkg_lint.py` | Static checks. Rules: `layout` (outside the kind folder), `workspace-source` (package `[tool.uv.sources]`), `outside-path` (relative paths outside the package in pyproject values), `root-lookup` (`Path(__file__).parents[N]` or `.parent` chains above the package root), `foreign-tests-import` (imports of another package's `tests/` modules or `*.tests`), `required-files` (common plus per kind), `tool-config` (pytest, mypy and ruff tables and the dev group against the template), `internal-dep-range` (missing internal dependency ranges), `readme-doctest` (a violation when the README "Minimal usage" section has no doctest `>>>` or the section is missing; only that section is counted. The candidate section headings are `[pkg_lint] readme_doctest_headings` in `pkgkit_py.toml`: the first candidate is the name shown in messages, and aliases can follow. The default is only "Minimal usage"), and the repository rules `template-root-drift` (template against the root tool settings), `root-source` (whether the root `[tool.uv.sources]` links every internal workspace project with `workspace = true`, and entries for packages that do not exist) and `importlinter-drift` |
| `importlinter_sync.py` | From `importlinter.rules.toml` (groups `@all`, `@packages`, `@app` and `@<kind>`, exclusions `!name` and `!@group`, user `[groups]`) to the `[tool.importlinter]` region of the root `pyproject.toml` (between marker lines). `--check` reports only semantic differences, and `--init` moves the current contracts into the rules file |
| `wheels.py` | `uv build --all-packages --wheel -o dist/wheelhouse` (a thin wrapper with `--clean`, `--package` and `--dry-run`) |
| `mypy_conftests.py` | The second step of `poe typecheck`. Package `tests/` folders have no `__init__.py`, so every `conftest.py` has the same module name; the root `[tool.mypy] exclude` leaves them out of the combined run, and this script checks each `conftest.py` under `[tool.mypy] files` one file at a time with the root settings. No effect on standalone package mypy runs |
| `portability.py` | Copies the package folder to `$TMPDIR`, runs `uv venv`, then `uv sync` (a flat index of the wheelhouse is added only to the copy, so internal packages come from the wheelhouse), then `ruff check`, `ruff format --check`, `mypy` and `pytest` (including README doctests), then `python -m <import> --check` for the `module` and `link` kinds, and prints a result table. `UV_PROJECT_ENVIRONMENT`, `VIRTUAL_ENV`, `PYTHONPATH` and `MYPY_CACHE_DIR` are not passed through (the mypy cache is created inside the temporary copy and removed with the session). `--wheels` rebuilds the wheelhouse and by default uses a temporary `UV_CACHE_DIR` for the session (so the uv cache does not reuse old contents for internal wheels rebuilt with the same version; turn it off with `--reuse-uv-cache`, or set the location with `--uv-cache-dir`). Without `--wheels`, it warns when a wheel is older than the package source (`pyproject.toml`, `README.md`, `src/`). `--package` also selects extension examples from `[examples] roots` (they are not workspace members). Without `--package`, whether examples are included is decided by `[examples] portability_default` (included by default) and overridden by `--examples` and `--no-examples` (examples have no `run-check`) |
| `examples_check.py` | `poe examples`. Finds every folder with a `pyproject.toml` under the `[examples] roots` globs of `pkgkit_py.toml` (default `examples/extensions/*`) as an example, and runs the `[examples] steps` (default `mypy` and `pytest -q`) in each folder (without installing, using the folder's own settings). The example list is not written by hand. A folder matched by the glob without a `pyproject.toml` is reported as a failure (exit code 1). When a step fails, the rest still run and a result table is printed at the end |
| `new_package.py` | `--kind {base,feature,kit,module,link} NAME` creates `packages/py/<kind folder>/NAME`, adds it to the workspace `members` if missing, adds `<distribution name> = { workspace = true }` to the root `[tool.uv.sources]`, and updates import-linter when the rules file exists |
| `pkgkit_common.py`, `pkgkit_template.py` | Pure functions: settings, finding packages, naming rules and TOML writing / template rendering. `with_range` adds the configured range to internal dependencies without one and keeps extras (for example `agent-console-modkit[host]`) |
| `templates/python/` | `common.toml` (common required files and dev tools) plus `common/**.tmpl` plus `kinds/<kind>/kind.toml` (folder, dependencies, required files, standalone run, entry points) plus `kinds/<kind>/files/**.tmpl` |

They are registered as poe tasks in the root `pyproject.toml`: `uv run poe pkg-lint` (part of `poe check`), `poe importlinter-sync`, `poe wheels`, `poe portability`, `poe new-package`, `poe examples` (part of `poe check`) and `poe pkgkit-test`. Arguments go after the poe task as is (for example `uv run poe portability --package ac-chat`). Direct runs:

```sh
python scripts/pkgkit/pkg_lint.py [--package NAME] [--path DIR] [--rule ID] [--json] [--list-rules]
python scripts/pkgkit/importlinter_sync.py [--check | --init [--force]]
python scripts/pkgkit/wheels.py [--clean] [--package DIST]
python scripts/pkgkit/examples_check.py [--package NAME] [--list] [--dry-run]
python scripts/pkgkit/portability.py [--package NAME] [--[no-]examples] [--wheels] [--no-index] [--reuse-uv-cache | --uv-cache-dir DIR] [--keep] [--dry-run]
python scripts/pkgkit/new_package.py --kind KIND NAME [--dep D] [--dev-dep D] [--id MODULE_ID] [--dry-run]
```

README doctests need a blank line after the expected output (otherwise the closing ```` ``` ```` line is read as output).

The internal dependency range `"from-package"` (`[python.internal_ranges]` in `pkgkit_py.toml`) resolves only when that package is in the workspace. When you use `new_package.py` or `pkg_lint.py` outside the repository (where that package is not in the workspace), write the range directly instead of `"from-package"` (for example `agent-console-contracts = ">=0.5,<0.6"`).

Tests: `uv run pytest scripts/pkgkit` (uses this folder's `pytest.ini`) · `uv run mypy scripts/pkgkit` · `uv run ruff check scripts/pkgkit`
