# @agent-console/eslint-config

The ESLint flat config shared by the Agent Console TS packages. A package copied out of the repository is linted with the same rules.

## Installation
Inside the repository, `pnpm install` links it. Outside the repository, install the tarball (`pnpm pack:all` → `dist/npm`) as a dev dependency,
together with the peers (`eslint`, `@eslint/js`, `typescript-eslint`, and `globals`). The React Hooks rules (`/react`) also need `eslint-plugin-react-hooks`.

## Minimal usage
The package's `eslint.config.js`:

```js
import config from "@agent-console/eslint-config";

export default config;
```

If you need options, use `createConfig`.

```ts readme
import { createConfig } from "@agent-console/eslint-config";

const config = createConfig({ ignores: ["**/generated/**"] });
```

A React package imports `createReactConfig` from `@agent-console/eslint-config/react`.

## Development and standalone reuse
- `pnpm lint` and `pnpm test` each run on their own inside this folder.
- Changing a rule affects every package, so record it in the `CHANGELOG`.
