# Contributing to Agent Console

Thanks for your interest in improving Agent Console. This guide covers the development setup, the checks to run
before you open a pull request, how the code is organized, and the commit message format.

## Development setup

You need the tools listed in the [README](README.md#requirements): Python 3.12+, uv, Node.js and pnpm.

```bash
uv sync --all-packages   # Python: uv workspace (server, CLI and all Python packages)
pnpm install             # TypeScript: pnpm workspace (web app and all TS packages)
```

CI installs with the lock files as they are: `uv sync --all-packages --locked` and `pnpm install --frozen-lockfile`.
If you change dependencies, commit the updated `uv.lock` or `pnpm-lock.yaml`.

Run the app while you work:

| What | Command |
| --- | --- |
| Server and web preview together | `pnpm app` (see `pnpm app --help`) |
| Server only (API and WebSocket) | `uv run agent-console serve` (default `127.0.0.1:8765`) |
| Web dev server with hot reload | `pnpm --filter @agent-console/web dev` (proxies `/api` and `/ws` to the server) |
| Web build / preview of the build | `pnpm --filter @agent-console/web build` / `pnpm --filter @agent-console/web preview` |

If the web app runs on a different origin than the server, add that origin to `security.allowed_origins` in
`agent-console.yaml` (the example settings file already lists the dev server and preview origins).

## Repository layout

| Path | Contents |
| --- | --- |
| `packages/py/base/` | Base Python packages: contracts, registries, graph model, settings layers |
| `packages/py/features/` | Feature libraries: run engine, backends, storage, usage, logs, import and export, ... Usable without the server |
| `packages/py/kit/` | Toolkit for building server modules (module descriptors, ports, assembly) |
| `packages/py/modules/` | Server feature modules (`mod-*`). Each exposes one feature over REST and WebSocket and can be turned off |
| `packages/py/links/` | Link modules (`link-*`). Each connects two features and turns itself off if either side is missing |
| `packages/ts/lib/`, `packages/ts/config/` | TypeScript packages (contract types, API client, UI, graph editor, chat, ...) and shared tsconfig and ESLint settings |
| `apps/server`, `apps/cli`, `apps/web` | Thin apps that only assemble packages: the server, the `agent-console` command, and the web app |
| `examples/` | Example plugins (`examples/extensions/`) and a web extension example (`examples/web/`) |
| `docs/extending/` | Extension guide |
| `tests/integration/` | Tests that combine several packages |
| `scripts/` | Development scripts: `pnpm app`, `pnpm check`, package tooling, extension guide tooling |

## Checks

Run these before opening a pull request. CI runs the same commands.

| Command | What it runs |
| --- | --- |
| `uv run poe check` | Python: ruff (lint and format check), mypy, import-linter, package portability lint, settings schema help lint, extension point check, extension guide drift check, pytest, example plugin checks |
| `pnpm check` | TypeScript: ESLint, package portability lint, tsc, Vitest, dependency-cruiser, TS extension point check. Arguments after `--` go to Vitest only |
| `uv run poe contracts-check` | Regenerates the contract schemas and TS types and fails if they differ from the committed files |
| `pnpm --filter @agent-console/web build` | Web production build |

Helpers:

- `uv run poe fmt`: auto-fix with ruff (`ruff check --fix` and `ruff format`)
- `uv run poe mypy-package <package folder>`: mypy for one package with its own settings
- `uv run poe portability [--package NAME] [--wheels]` and `pnpm portability [--package NAME]`: copy packages out of
  the repository, install them there and run their checks
- `uv run poe wheels` and `pnpm pack:all`: build wheels into `dist/wheelhouse` and tarballs into `dist/npm`

## How the code is organized

These rules keep every feature reusable on its own. Reviews check them.

- **No hard-coded lists.** Agents, teams, roles, categories, node types, models, tools, log sources and wiki rules are
  user data. Examples in docs are examples, not built-in data. The app has to work with an empty workspace. Defaults
  a feature needs (for example log classification rules) can ship as package data, but users must be able to change
  or turn them off.
- **New kinds come in through extension points.** Things that grow in number (node types, backends, log sources,
  exporters, ...) sit on a shared base and a registry, and plugins add to them through Python entry points. See the
  [extension guide](docs/extending/README.md).
- **One package, one job.** Each feature is its own package with a public API (Python `__init__.py`, TS `src/index.ts`)
  and internal modules (`_`-prefixed in Python). Do not import another package's internals or tests.
- **Features stand alone.** Chat, runs, usage, logs, settings, resources, import and export each work without the
  server, the web app or other features. Features connect only through injected interfaces (ports), and when a
  connection is missing only that part turns off.
- **Apps are thin.** `apps/server`, `apps/cli` and `apps/web` only assemble packages. Business logic lives in packages.
- **Inject external dependencies.** File system, database, model APIs, SDKs, time and environment variables are passed
  in, not created or read from globals. Paths, ports, model names and URLs come from arguments or settings.
- **Portable packages.** A package folder copied out of the repository must still install, test and run. Do not rely
  on workspace-only paths or root settings. TS packages depend on each other with normal `^x.y.z` ranges, not the
  `workspace:` protocol.
- **Dependency direction is checked.** Python rules live in `importlinter.rules.toml` (apply changes with
  `uv run poe importlinter-sync`). TypeScript rules live in `.dependency-cruiser.cjs`. Cycles between packages are not
  allowed.
- **Every package has a README and tests.** The README says what it does, how to install it, and shows a minimal
  example. When you add a dependency, note what it is for, why, and the alternatives in the package README.
- **Prefer existing libraries.** Look for a maintained library with a compatible license before writing your own,
  and keep it behind an adapter so it can be replaced.

Names: Python import `agent_console_*`, distribution `agent-console-*`, TypeScript `@agent-console/*`.

### Contracts

Shared types between Python and TypeScript are defined once, as Pydantic models in `agent_console_contracts`. JSON
Schema and the TS types in `@agent-console/contracts` are generated from them, and the generated files are committed.
After changing a contract, run `uv run poe contracts` and commit the result.

### Extension points

A package that defines an extension point declares it in its own `pyproject.toml` under
`[tool.agent-console.extension-points.<slug>]` (TS packages use `package.json`). `uv run poe extpoints-check` compares
the declarations with the code. After adding or changing an extension point, regenerate the guide's reference tables
with `uv run poe extdocs` and check them with `uv run poe extdocs-check`.

## Creating a package

Use the generators. They create the folder from a template and register the package with the workspace and the
import rules.

```bash
uv run poe new-package --kind {base,feature,kit,module,link} NAME
uv run poe new-package --kind module ac-mod-notes --id mod-notes             # server module
uv run poe new-package --kind link ac-link-notes-runs --id link-notes-runs   # link module
pnpm new-package --kind lib NAME                                             # add --dom for React components
pnpm new-package --kind config NAME
```

`--dry-run` (Python) shows the files without writing them. See [Creating packages](docs/extending/packages.md) for
details.

## Commit messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

<body: why the change was made and what changed, 1-5 bullet lines>

Refs: <issue>
```

| Type | Use for |
| --- | --- |
| `feat` | A new feature or behavior users can use |
| `add` | New files, examples, data or scripts with no behavior change |
| `fix` | A bug fix, including security fixes |
| `refactor` | Code cleanup with no behavior change |
| `perf` | Performance improvement |
| `test` | Tests only |
| `docs` | Documentation and READMEs |
| `style` | Formatting or lint only |
| `build` | Build settings, dependencies, lock files |
| `ci` | CI settings |
| `chore` | Other tooling and maintenance |

- **scope**: the package or area that changed (for example `contracts`, `ac-store`, `web/wiki`). Use the most central
  one if several changed. Leave it out if the change is very broad.
- **subject**: one short line (about 40 characters) without a trailing period. Say what you did. Reasons and details
  go in the body.
- **footer**: `Refs:` for related issues. Breaking changes add `BREAKING CHANGE: <what breaks>`.
- One logical change per commit. Do not rewrite commits that are already pushed.

## Security and data

- Never commit secrets. Put them in environment variables and refer to them as `secret://<name>` in settings and
  definitions.
- Do not commit runtime data: the workspace (`.agent-console/`, `.state/`), SQLite databases, or your
  `agent-console.yaml`.
- The server binds to `127.0.0.1` by default. Keep it that way unless the user explicitly turns on remote access.
- The app reads files under `~/.claude` but never writes to them.

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
