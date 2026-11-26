# @agent-console/projects

Reusable logic for projects (registered folders, status, copy plans). It draws no UI.

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
import { createCurrentProjectStore, spaceParam } from "@agent-console/projects";

const store = createCurrentProjectStore({ location: { getSearch: () => "?project=app", setSearch: () => {} } });

const current = store.get();
const query = spaceParam(current);
```


## Messages and language
The default messages are Korean (`src/locales/ko.json`, `DEFAULT_PROJECT_MESSAGES`), and an English bundle ships alongside. There is no dependency on i18next. Placeholders are `{name}` and `formatMessage` fills them.
`ko` and `en` have the same keys and placeholders (`test/locales.test.ts` checks this). In the JSON files, dotted keys are spread into a tree; when one key is the prefix of another, its value sits under `_`. `flattenMessageTree` turns a tree back into the dotted keys the helpers return (`MessageRef.key`).
To use English, pass the bundle as the overrides of `createProjectsText`:

```ts
import { createProjectsText } from "@agent-console/projects";
import en from "@agent-console/projects/locales/en";

const text = createProjectsText(en);
```
The Korean bundle is `@agent-console/projects/locales/ko`. Both files also export `tree` (the JSON as a tree) for code that takes tree bundles. For a new language, build an object with the same keys. The words that must not appear in UI text have an English list too (`RETIRED_TERMS_EN`, `PROJECT_CONTEXT_RETIRED_TERMS_EN`), and the English bundle is checked against it. The sources contain no Korean string literals (the same test checks this).

## Development and reuse
- `pnpm build` · `pnpm typecheck` · `pnpm lint` · `pnpm test` run on their own inside this folder.
- The public API is only the paths listed in `exports`. Other packages do not import `src/` or `dist/` directly.
- Check that it still works when copied out of the repository with `pnpm portability --package @agent-console/projects`.
