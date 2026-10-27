/**
 * design.md §6.2: packages/ts/lib/* 끼리는 서로 의존 금지. 예외는 contracts(다른 패키지가 의존 가능).
 * 조립은 apps/web만 한다. packages/ts는 apps를 import할 수 없다.
 */
module.exports = {
  forbidden: [
    {
      name: "no-cross-package-deps",
      comment: "packages/ts/* 패키지는 자기 자신과 contracts 외의 형제 패키지를 import하지 않는다.",
      severity: "error",
      from: { path: "^packages/ts/lib/([^/]+)/", pathNot: "^packages/ts/lib/memory-view/" },
      to: {
        path: "^packages/ts/lib/([^/]+)/",
        pathNot: ["^packages/ts/lib/$1/", "^packages/ts/lib/contracts/"],
      },
    },
    {
      name: "memory-view-allowed-deps",
      comment: "memory-view(공유 메모리 표현)는 사내 패키지 중 contracts(타입만)와 text-editor(편집기·비교, design §5.7R.2 표)만 import한다. api-client·log-view·ui 등은 import하지 않고 연결은 props로 받는다(5.7R.17). 위 no-cross-package-deps에서 이 패키지만 빼고 여기서 대신 허용 범위를 정한다.",
      severity: "error",
      from: { path: "^packages/ts/lib/memory-view/src/" },
      to: {
        path: "^packages/ts/(lib|config)/",
        pathNot: ["^packages/ts/lib/memory-view/", "^packages/ts/lib/text-editor/", "^packages/ts/lib/contracts/"],
      },
    },
    {
      name: "memory-view-contracts-types-only",
      comment: "memory-view는 contracts에서 타입만 가져온다(`import type`). 값 import는 계약 런타임을 번들에 끌어온다(arch-view와 같은 이유).",
      severity: "error",
      from: { path: "^packages/ts/lib/memory-view/src/" },
      to: { path: "^packages/ts/lib/contracts/", dependencyTypesNot: ["type-only"] },
    },
    {
      name: "log-view-contracts-only",
      comment: "log-view는 사내 패키지 중 contracts(타입)만 import한다. ui·trace-view·schema-form·text-editor는 슬롯 props로 받는다(design §4R.1, F-19).",
      severity: "error",
      from: { path: "^packages/ts/lib/log-view/src/" },
      to: { path: "^packages/ts/(lib|config)/", pathNot: ["^packages/ts/lib/log-view/", "^packages/ts/lib/contracts/"] },
    },
    {
      name: "log-view-contracts-types-only",
      comment: "log-view는 contracts에서 타입만 가져온다(`import type`). 값 import는 번들에 계약 런타임을 끌어오고 패키지 단독 이식을 해친다(5R.21, phase4r-review H8).",
      severity: "error",
      from: { path: "^packages/ts/lib/log-view/src/" },
      to: { path: "^packages/ts/lib/contracts/", dependencyTypesNot: ["type-only"] },
    },
    {
      name: "arch-view-contracts-types-only",
      comment: "arch-view(구조도 표현)는 사내 패키지 중 contracts의 타입만 import한다(`import type`). ui·log-view·api-client를 import하지 않고 문구·확장은 props로 받는다(design §5.5R.3, 5.5R.14). 위 no-cross-package-deps가 형제 패키지를 막고, 이 규칙은 contracts 값 import까지 막는다.",
      severity: "error",
      from: { path: "^packages/ts/lib/arch-view/src/" },
      to: {
        path: "^packages/ts/(lib|config)/",
        pathNot: "^packages/ts/lib/arch-view/",
        dependencyTypesNot: ["type-only"],
      },
    },
    {
      name: "projects-contracts-types-only",
      comment: "projects는 사내 패키지 중 contracts의 타입만 import한다(`import type`). 전송(api-client)은 props로 주입한다(5.2R.35). 값은 상수 전용 진입점 `@agent-console/contracts/constants`(생성 상수만, 스키마 JSON 없음)에서만 가져온다(5.2R.3 후속: 이슈 코드를 손으로 복사하지 않기 위해).",
      severity: "error",
      from: { path: "^packages/ts/lib/projects/src/" },
      to: {
        path: "^packages/ts/(lib|config)/",
        pathNot: ["^packages/ts/lib/projects/", "^packages/ts/lib/contracts/src/generated/constants\\.ts$"],
        dependencyTypesNot: ["type-only"],
      },
    },
    {
      name: "list-arrange-pure",
      comment: "list-arrange는 순수 함수 패키지다. 사내 패키지(contracts 포함)와 React·DOM 계열을 import하지 않는다. 그리는 쪽(ui ListPane groups)과는 앱이 props로 잇는다(5.2R.61).",
      severity: "error",
      from: { path: "^packages/ts/lib/list-arrange/src/" },
      to: { path: ["^packages/ts/(lib|config)/(?!list-arrange/)", "^apps/", "node_modules/(react|react-dom|@xyflow|@tanstack)/"] },
    },
    {
      name: "ui-no-list-arrange",
      comment: "ui(그리기)는 list-arrange(계산)를 모른다. 묶음 데이터는 ListPane `groups` props로만 받는다(5.2R.61).",
      severity: "error",
      from: { path: "^packages/ts/lib/ui/src/" },
      to: { path: "^packages/ts/lib/list-arrange/" },
    },
    {
      name: "contracts-is-leaf",
      comment: "contracts는 다른 TS 패키지에 의존하지 않는다.",
      severity: "error",
      from: { path: "^packages/ts/lib/contracts/" },
      // config/ 아래(공용 tsconfig·ESLint 설정)는 빌드 도구라서 예외.
      to: { path: "^packages/ts/", pathNot: "^packages/ts/(lib/contracts|config)/" },
    },
    {
      name: "no-packages-to-apps",
      severity: "error",
      from: { path: "^packages/ts/" },
      to: { path: "^apps/" },
    },
    {
      name: "api-client-feature-independent",
      comment: "api-client의 기능 클라이언트(clients/*)끼리는 import 금지. 공유는 io.ts(전송 계약)로만(modularity-design §3.5·§3.7).",
      severity: "error",
      from: { path: "^packages/ts/lib/api-client/src/clients/([^/]+)\\.ts$" },
      to: { path: "^packages/ts/lib/api-client/src/clients/", pathNot: "^packages/ts/lib/api-client/src/clients/$1\\.ts$" },
    },
    {
      name: "web-feature-public-api-only",
      comment: "다른 기능 폴더는 그 폴더의 index.ts(공개 API)로만 import한다. features/ 밖의 앱 층(app·shell·links)은 대상이 아니다.",
      severity: "error",
      from: { path: "^apps/web/src/features/([^/]+)/" },
      to: {
        path: "^apps/web/src/features/([^/]+)/",
        pathNot: ["^apps/web/src/features/$1/", "^apps/web/src/features/[^/]+/index\\.tsx?$"],
      },
    },
    {
      name: "web-features-use-links-folder",
      comment: "두 기능을 함께 쓰는 컴포넌트는 apps/web/src/links/<a>-<b>/ 에 둔다. 기능 폴더는 links/를 import하지 않고, links/가 기능 폴더의 공개 API를 조립한다.",
      severity: "error",
      from: { path: "^apps/web/src/features/" },
      to: { path: "^apps/web/src/links/" },
    },
    {
      name: "not-to-unresolvable",
      comment: "해석할 수 없는 import(오타·누락된 의존)는 오류.",
      severity: "error",
      // vite-env.d.ts의 `/// <reference types>`는 tsPreCompilationDeps 때문에 보이는 타입 선언 참조다(번들러가 해석).
      from: { pathNot: "vite-env\\.d\\.ts$" },
      to: { couldNotResolve: true, pathNot: "^virtual:" },
    },
    { name: "no-circular", severity: "error", from: {}, to: { circular: true } },
  ],
  options: {
    // 타입 전용 import도 의존으로 잡는다(log-view-contracts-types-only가 type-only 여부를 구분하려면 필요).
    tsPreCompilationDeps: true,
    doNotFollow: { path: "node_modules" },
    exclude: { path: "node_modules" },
    enhancedResolveOptions: { exportsFields: ["exports"], conditionNames: ["development", "import", "require", "node", "default"] },
  },
};
