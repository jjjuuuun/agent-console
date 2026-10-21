# @agent-console/projects

프로젝트(정의·대화·실행의 범위)를 다루는 재사용 로직. 화면을 그리지 않는다.

- 보기 규칙: `isVisible`·`filterByScope`·`groupByScope`(공용 + 이 프로젝트 / 이 프로젝트만 / 공용만)
- 새 정의의 기본 범위: `defaultScopeFor`(서버 설정 `projects.new_definition_scope` 데이터를 받는다)
- 범위 배지: `scopeBadge`(문구 키와 톤만 돌려준다), 기본 문구 `DEFAULT_BADGE_MESSAGES`
- 로그 필터: `logFilterFor`(프로젝트의 `log_projects` → 로그 필터 `project`)
- 현재 프로젝트: `createCurrentProjectStore`(주소 `?project=`와 브라우저 저장, 저장소·주소는 주입)
- 옮기기 계획: `mergeMovePlans`·`selectMoves`·`moveTargetOfIssue`
- REST: `createProjectsClient`(전송은 주입, `@agent-console/api-client`의 `RestIo`가 맞는다)

의존은 `@agent-console/contracts`뿐이다(타입과, 값은 상수 진입점 `@agent-console/contracts/constants`의 이슈 코드·제안 id만). 종류 이름·프로젝트 목록·문구를 코드에 고정하지 않는다.

## 설치
저장소 안에서는 `pnpm install`이 로컬 패키지를 연결한다. 저장소 밖에서는 tarball(`pnpm pack:all` → `dist/npm`)을 설치한다.

```sh
npm install ./agent-console-projects-0.1.0.tgz
```

## 최소 사용
```ts readme
import { createCurrentProjectStore, defaultScopeFor, filterByScope, scopeBadge, badgeLabel } from "@agent-console/projects";

const store = createCurrentProjectStore({ location: { getSearch: () => "?project=app", setSearch: () => {} } });
const items = [{ id: "a", project: "app" }, { id: "b", project: null }, { id: "c", project: "other" }];

const current = store.get();
const visible = filterByScope(items, current).map((x) => x.id);
const scopeForNew = defaultScopeFor("resource", current, { new_definition_scope: { agent: "shared" } });
const badge = badgeLabel(scopeBadge("other", current)!);
```

`current`는 `"app"`, `visible`은 `["a", "b"]`, `scopeForNew`는 `"app"`, `badge`는 `"다른 프로젝트: other"`이다. 이 블록은 `test/readme.test.ts`와 같아야 한다.

## 개발·재사용
- `pnpm build` · `pnpm typecheck` · `pnpm lint` · `pnpm test`는 이 폴더 안에서 단독으로 돈다.
- 공개 API는 `exports`에 적힌 경로뿐이다. 다른 패키지는 `src/`·`dist/`를 직접 import하지 않는다.
- 저장소 밖으로 복사해도 되는지는 `pnpm portability --package @agent-console/projects`로 확인한다.
