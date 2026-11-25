# @agent-console/projects

프로젝트(등록된 폴더, 상태, 복사 계획)를 다루는 재사용 로직. 화면을 그리지 않는다.

- 로그 필터: `logFilterFor`(프로젝트 id → 로그 필터 `project=<id>`, `LogSessionSummary.project_id` 기준)
- 현재 프로젝트: `createCurrentProjectStore`(주소 `?project=`와 브라우저 저장, 저장소·주소는 주입)
- 프로젝트 2: 상태 문구·색조 `statusInfo`, 상태별 할 수 있는 일과 막힌 이유 `projectAbilities`(표는 데이터), 공간 칩·질의 `spaceLabel`·`spaceParam`, 복사 계획 도우미(`initialSelections`·`canSubmit`·`skipWarnings`·`buildApplyRequest`·`summarizeResult` …), 폴더 선택 어댑터(`folderCheckOutcome`·`folderPickOutcome`: 계약 → `@agent-console/folder-picker`가 받는 모양), 문구 표 `DEFAULT_PROJECT_MESSAGES`·`createProjectsText`, 화면 문구에 쓰지 않는 말 `RETIRED_TERMS`(그중 프로젝트 문구에서만 막는 말 `PROJECT_CONTEXT_RETIRED_TERMS`, 둘 다 데이터)

프로젝트 REST는 `@agent-console/api-client`의 `rest`를 쓴다. 의존은 `@agent-console/contracts`뿐이다(타입과, 값은 상수 진입점 `@agent-console/contracts/constants`의 상태·복사 동작 상수만). 종류 이름·프로젝트 목록·문구를 코드에 고정하지 않는다.

## 설치
저장소 안에서는 `pnpm install`이 로컬 패키지를 연결한다. 저장소 밖에서는 tarball(`pnpm pack:all` → `dist/npm`)을 설치한다.

```sh
npm install ./agent-console-projects-0.2.0.tgz
```

## 최소 사용
```ts readme
import { createCurrentProjectStore, logFilterFor, spaceParam } from "@agent-console/projects";

const store = createCurrentProjectStore({ location: { getSearch: () => "?project=app", setSearch: () => {} } });

const current = store.get();
const logFilter = logFilterFor(current).filter;
const query = spaceParam(current);
```

`current`는 `"app"`, `logFilter`는 `{ project: "app" }`, `query`는 `"app"`이다. 이 블록은 `test/readme.test.ts`와 같아야 한다.

## 개발·재사용
- `pnpm build` · `pnpm typecheck` · `pnpm lint` · `pnpm test`는 이 폴더 안에서 단독으로 돈다.
- 공개 API는 `exports`에 적힌 경로뿐이다. 다른 패키지는 `src/`·`dist/`를 직접 import하지 않는다.
- 저장소 밖으로 복사해도 되는지는 `pnpm portability --package @agent-console/projects`로 확인한다.
