# @agent-console/contracts

TS types and constants **generated** from the Python `agent_console_contracts` (Pydantic), plus the contract JSON Schema. It does not depend on other TS packages.

- `schema/agent-console.schema.json` — the generated JSON Schema (2020-12, every model under `$defs`).
- `src/generated/contracts.generated.ts` — the types and constants generated from that schema. **Do not edit by hand.**
- `src/index.ts` — the public API: every generated type, the constants (`CONTRACTS_VERSION`, `CONTRACT_VERSIONS`, `KNOWN_RUN_EVENT_TYPES`, `RUN_ORIGINS`, `USAGE_REPORT_PARTS`, `ERROR_CODES`, `HTTP_STATUS_BY_ERROR_CODE`, `X_UI` and `X_UI_TIERS` (schema extension keys, 0.8.0)), `contractsSchema`, `getContractSchema(name)`, `isKnownRunEvent()`, and `RunEventOf<T>`.
- `src/generated/<submodule>.ts` — per-feature subpaths `@agent-console/contracts/<submodule>` (common, resources, logs, i18n, definitions, runs, usage, projects, chat, exports, imports, architecture, memory, sdd, wiki, modules). Each exports only the types defined in that submodule plus `CONTRACT_MODULE` and `CONTRACT_VERSION`. A package that uses a single feature uses the subpath (for example, `import type { Conversation } from "@agent-console/contracts/chat"`). **Generated; do not edit by hand.**
- `src/generated/constants.ts` — a constants-only subpath, `@agent-console/contracts/constants`. It re-exports only the values of the schema's `x-constants` (`ERROR_CODES`, `KNOWN_ISSUE_CODES`, `KNOWN_SUGGESTION_IDS`, and so on). The root entry point carries the whole schema JSON, so a package that needs only value constants uses this path. **Generated; do not edit by hand.**

## Minimal usage
This block matches `test/readme.test.ts`, and the test actually runs it (`pnpm pkg-lint` checks that they match).

```ts readme
import { CONTRACTS_VERSION, getContractSchema } from "@agent-console/contracts";

const schema = getContractSchema("WorkspaceSettings"); // pass it straight to SchemaForm
const version = CONTRACTS_VERSION;
```

## Dependencies

| What | Why | Alternatives |
| --- | --- | --- |
| `json-schema-to-typescript` (dev) | Generates TS types from the JSON Schema. It turns discriminated unions and `$defs` into types as they are | openapi-typescript (worth considering for REST path types once an OpenAPI document exists), quicktype |

## Generation

```bash
uv run poe contracts         # Python models → schema → TS (from the repository root)
uv run poe contracts-check   # compare the regenerated output with the committed output; exit 1 if they differ
pnpm --filter @agent-console/contracts generate   # the schema → TS step only
```

## Another usage example

```ts
import { getContractSchema, isKnownRunEvent, type RunEvent } from "@agent-console/contracts";

const settingsSchema = getContractSchema("WorkspaceSettings"); // straight to SchemaForm
function onEvent(ev: RunEvent) {
  if (isKnownRunEvent(ev) && ev.type === "agent.usage") console.log(ev.payload.usage.input_tokens);
}
```

## Testing
`pnpm test` (from the package folder or the repository root; Vitest)

## Generator notes
- Sibling keys next to a `$ref` (such as descriptions) are removed before generation. If they stay, json-schema-to-typescript duplicates the same model as something like `AgentSettings1`.
