# @agent-console/tsconfig

The tsconfig shared by the Agent Console TS packages. A package copied out of the repository is type-checked and built with the same settings.

| File | Purpose |
| --- | --- |
| `base.json` | Strict common options (bundler resolution, `noEmit`) |
| `library.json` | `base.json` + declaration files and source maps. Library packages `extends` it |

## Installation
Inside the repository, `pnpm install` links it. Outside the repository, install the tarball (`pnpm pack:all` → `dist/npm`) as a dev dependency.

## Minimal usage
The package's `tsconfig.json`:

```json
{ "extends": "@agent-console/tsconfig/library.json", "include": ["src"] }
```

If you need a file path in code:

```ts readme
import { configPath } from "@agent-console/tsconfig";

const path = configPath("library");
```

## Development and standalone reuse
- `pnpm lint` and `pnpm test` each run on their own inside this folder.
- Changing an option affects every package, so record it in the `CHANGELOG` and raise the version if you break compatibility.
