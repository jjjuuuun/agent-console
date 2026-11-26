# @agent-console/projects

Reusable logic for projects (registered folders, status, copy plans). It draws no UI.

- Log filter: `logFilterFor` (project id to the log filter `project=<id>`, based on `LogSessionSummary.project_id`)
- Current project: `createCurrentProjectStore` (the `?project=` address and browser storage; the storage and address are injected)
- Project helpers: status text and tone `statusInfo`; what each status allows and why something is blocked, `projectAbilities` (the table is data); space chip and query `spaceLabel`·`spaceParam`; copy-plan helpers (`initialSelections`·`canSubmit`·`skipWarnings`·`buildApplyRequest`·`summarizeResult` …); folder-picker adapters (`folderCheckOutcome`·`folderPickOutcome`: contract to the shape `@agent-console/folder-picker` accepts); the message table `DEFAULT_PROJECT_MESSAGES`·`createProjectsText`; and the words that must not appear in UI text, `RETIRED_TERMS` (including `PROJECT_CONTEXT_RETIRED_TERMS`, the words blocked only in project text; both are data)

Project REST calls use `rest` from `@agent-console/api-client`. The only dependency is `@agent-console/contracts` (its types, and for values only the status and copy-action constants from the constants entry `@agent-console/contracts/constants`). Kind names, project lists, and messages are not fixed in code.

## Install
Inside the repository, `pnpm install` links the local package. Outside it, install the tarball (`pnpm pack:all` → `dist/npm`).

```sh
npm install ./agent-console-projects-0.3.0.tgz
```

## Minimal usage
```ts readme
import { createCurrentProjectStore, logFilterFor, spaceParam } from "@agent-console/projects";

const store = createCurrentProjectStore({ location: { getSearch: () => "?project=app", setSearch: () => {} } });

const current = store.get();
const logFilter = logFilterFor(current).filter;
const query = spaceParam(current);
```

`current` is `"app"`, `logFilter` is `{ project: "app" }`, and `query` is `"app"`. This block must match `test/readme.test.ts`.

## Development and reuse
- `pnpm build` · `pnpm typecheck` · `pnpm lint` · `pnpm test` run on their own inside this folder.
- The public API is only the paths listed in `exports`. Other packages do not import `src/` or `dist/` directly.
- Check that it still works when copied out of the repository with `pnpm portability --package @agent-console/projects`.
