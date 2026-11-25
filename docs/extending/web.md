# 웹

웹 화면을 바꾸는 길은 세 단계다. 위에서부터 묻고, 앞 단계로 되면 뒤로 가지 않는다.

1. **웹 코드 없이 된다**: 서버 쪽 데이터(설정 스키마, `x-ui`, 모듈 `web_roles`)만 바꾸면 화면이 따라온다.
2. **웹 앱에 한 줄 등록하고 다시 빌드한다**: 새 위젯·칸 그리기·폼 위젯처럼 화면 조각이 새로 필요할 때.
3. **표현 라이브러리를 다른 React 앱에서 쓴다**: `@agent-console/*` 표현 패키지를 가져다 자기 화면에 넣는다.

단계 2와 3의 예제는 [@agent-console/example-web](../../examples/web/agent-console-example-web/README.md)이다.
위젯 하나, 구조도 칸 그리기 하나, 설정 폼 위젯 하나를 만들어 실제 컴포넌트에 등록해 그린다.

## 웹에는 런타임 플러그인이 없다

서버 플러그인은 설치하고 서버를 다시 시작하면 켜진다. 웹은 그렇지 않다. 웹 앱은 빌드 때 조립되고, 서버가 준 JavaScript를
받아 실행하는 장치가 없다. 이유는 셋이다.

- 서버가 준 코드를 브라우저에서 실행하면 로컬 서버라도 공급망·권한 문제가 생긴다.
- 화면 조각이 React와 계약 타입을 앱과 같은 것으로 써야 하는데, 이를 런타임에 맞추려면 모듈 공유와 버전 협상 장치가 따로 필요하다.
- 단계 1 덕분에 서버 플러그인 작성자는 대부분 웹을 고치지 않아도 된다.

그래서 화면 조각이 꼭 필요하면 웹 앱을 고쳐 다시 빌드한다. 서버가 모르는 이름을 보내도 화면이 깨지지 않게 하는 것은
아래 "단계 1" 표가 보인다.

## 단계 1: 웹 코드 없이 되는 것

- 서버 플러그인의 설정 스키마(JSON Schema와 `x-ui`)는 스키마 폼이 그린다. 설명·예시·기본값·필수 칩·고급 접힘이 모두 스키마 데이터에서 나온다.
- 화면 진입은 서버 모듈의 `web_roles`(데이터)가 정한다. 켜진 모듈의 역할만 사이드바에 나온다.
- 웹이 모르는 이름이 오면 아래처럼 낮춰 그린다. 값은 지우지 않는다.

| 서버가 보내는 것 | 웹이 모를 때 | 근거 테스트 |
| --- | --- | --- |
| 설정 스키마의 `ui:widget` 이름 | 구조화 값(객체·배열)이면 JSON 편집으로 바꾸고 안내를 붙인다. 단순 값이면 이름을 그대로 둔다 | [위젯 이름 이어 주기](../../apps/web/src/features/delegation/delegationLib.test.ts) |
| `x-ui`가 없거나 일부만 있는 스키마 | 스키마만으로 폼을 그린다(필수 여부 등은 폴백 규칙) | [x-ui 폴백](../../packages/ts/lib/schema-form/src/xui.test.tsx) |
| 상호작용 renderer 이름 | 응답 스키마 폼으로 그린다. 내장 폴백은 요청 내용만 보인다 | [상호작용 카드](../../packages/ts/lib/chat/src/interaction/InteractionCard.test.tsx) |
| 대시보드 위젯 종류 | "알 수 없는 위젯" 자리 표시를 그리고 설정(JSON)을 보존한다 | [대시보드 격자](../../packages/ts/lib/log-view/test/dashboard.test.tsx) |
| 로그 이벤트 범주 | id 원문을 중립 톤으로 보인다 | [로그 구성요소](../../packages/ts/lib/log-view/test/components.test.tsx) |
| 구조도 칸의 `tone`·`style`·`view` | 중립 색·기본 선·기본 칸 본문 | [구조도](../../packages/ts/lib/arch-view/src/ArchitectureDiagram.test.tsx) |
| 그래프 노드 상태 | 상태 원문을 보인다 | [그래프 편집기](../../packages/ts/lib/graph-editor/src/GraphEditor.test.tsx) |
| 모듈 `web_roles` | 켜진 모듈의 역할 화면만 사이드바에 나온다 | [앱 셸](../../apps/web/src/app/App.test.tsx) |

## dashboard-widget

<!-- extdocs:facts dashboard-widget -->
- 등록: 컴포넌트 `@agent-console/log-view#DashboardGridProps`의 props로 넘긴다(빌드 시 등록).
- 인터페이스:
  - `@agent-console/log-view#WidgetDescriptor`
  - `@agent-console/log-view#WidgetRenderProps`
  - `@agent-console/log-view#WidgetRegistry`
  - `@agent-console/log-view#createWidgetRegistry`
- 기본 구현: —
- 예제:
  - package: [examples/web/agent-console-example-web](../../examples/web/agent-console-example-web/README.md)
- 끄기·제거: props에서 빼고 다시 빌드한다.
<!-- /extdocs:facts -->

로그 대시보드에 새 위젯 종류를 더할 때 쓴다. 위젯 종류는 `WidgetDescriptor` 객체 하나다.
`kind`(종류 이름), `title`, 질의 모양(`queryShape`), 옵션 스키마(`optionsSchema`), 기본 크기, `render(props)`를 가진다.
대시보드에 저장된 위젯은 `kind` 이름만 가지므로, 이름이 같은 종류가 등록되어 있으면 그려진다.

```tsx
import { builtinWidgets, createWidgetRegistry, DashboardGrid } from "@agent-console/log-view";

const registry = createWidgetRegistry(builtinWidgets, [myWidget]);   // 뒤 목록이 같은 kind를 덮어쓴다
<DashboardGrid registry={registry} widgets={widgets} results={results} slotFor={slotFor} />
```

- `render`는 서버를 부르지 않는다. 집계 결과(`rows`)·로딩·오류는 props로 온다. 값이 `null`이면 0으로 바꾸지 말고 "–"를 보인다.
- 옵션은 `optionsSchema`(JSON Schema)로 편집기 폼이 그려진다. 모르는 옵션 값에는 기본값으로 돌아가야 한다.
- 종류가 등록되지 않으면 자리 표시가 나오고 설정은 보존된다. 등록을 빼도 저장된 위젯은 지워지지 않는다.

흔한 실수: 종류 이름을 내장과 같게 쓰면 내장을 덮어쓴다. 게이지 본문에 접근 가능한 이름(`aria-label`)을 붙이지 않는 것.
전체 코드: [예제의 게이지 위젯](../../examples/web/agent-console-example-web/README.md).

## architecture-cell-renderer

<!-- extdocs:facts architecture-cell-renderer -->
- 등록: 컴포넌트 `@agent-console/arch-view#ArchitectureDiagramProps`의 props로 넘긴다(빌드 시 등록).
- 인터페이스:
  - `@agent-console/arch-view#CellRenderer`
  - `@agent-console/arch-view#CellRenderProps`
  - `@agent-console/arch-view#EdgeStyleSpec`
- 기본 구현: —
- 예제:
  - package: [examples/web/agent-console-example-web](../../examples/web/agent-console-example-web/README.md)
- 끄기·제거: props에서 빼고 다시 빌드한다.
<!-- /extdocs:facts -->

구조도 칸 안쪽이나 연결선 모양을 바꿀 때 쓴다. 구조도 데이터(서버가 만든 프로필)의 칸은 `view` 문자열을 가질 수 있고,
`ArchitectureDiagram`의 `cellRenderers` 표(`view` 값 → 그리기 함수)에서 맞는 함수를 찾아 칸 안쪽을 맡긴다.
칸 껍데기(버튼·상태 표기·키보드 이동)는 라이브러리가 그리므로 그리기 함수는 안쪽만 책임진다.

```tsx
const cellRenderers = {
  "my-badge": ({ cell, defaultBody }) => <>{defaultBody}<Badge count={cell.metrics?.count?.value} /></>,
};
<ArchitectureDiagram view={view} cellRenderers={cellRenderers} />
```

- 그리기 함수는 `defaultBody`(기본 본문)를 받는다. 감싸거나 덧붙이면 기본 모양을 잃지 않는다.
- `view` 키가 표에 없으면 기본 칸이 그려진다. 지표 값이 `null`이면 배지를 달지 않는다(수집 안 됨을 0으로 보이지 않는다).
- 연결선 모양은 `edgeStyles` 표(스타일 이름 → 토큰 변수)로 바꾼다. 색은 토큰 변수 이름만 받고 임의 색은 중립으로 낮춰 그린다.

예제: [칸 배지 그리기](../../examples/web/agent-console-example-web/README.md).

## config-form-widget

<!-- extdocs:facts config-form-widget -->
- 등록: 웹 앱 레지스트리 `@agent-console/web/src/features/delegation/configWidgets.ts#CONFIG_WIDGETS`에 항목 하나를 더한다(빌드 시 등록).
- 인터페이스:
  - `@agent-console/web/src/features/delegation/widgetRegistry#WidgetRegistry`
  - `@agent-console/web/src/features/delegation/widgetRegistry#ConfigWidget`
- 기본 구현: —
- 예제:
  - package: [examples/web/agent-console-example-web](../../examples/web/agent-console-example-web/README.md)
- 끄기·제거: 항목을 빼고 다시 빌드한다.
<!-- /extdocs:facts -->

서버 설정 스키마의 `ui:widget` 이름에 화면 컴포넌트를 연결할 때 쓴다. 이름은 서버가 정하는 데이터이고, 앱의 위젯
레지스트리(`이름 → { Component, summary? }`)에 한 줄 등록하면 그 이름이 붙은 필드가 컴포넌트로 그려진다.
`Component`는 스키마 폼의 필드 props(`SchemaFormFieldProps`: 값·`onChange`·`label`·`errors` …)만 받는다.

```ts
export const CONFIG_WIDGETS: WidgetRegistry = {
  /* 기존 위젯 */
  "my.tags": { Component: TagsField },
};
```

- 레지스트리에 있는 이름은 `ui:field`로 이어져 한 컴포넌트가 필드 값 전체를 그린다. 없는 이름이 구조화 값에 붙으면 JSON 편집과 안내로 낮춘다.
- 알 수 없는 모양의 값(배열이 아닌데 태그 필드 등)은 빈 입력으로 보되 사용자가 고치기 전에는 값을 바꾸지 않는다.
- `summary`를 주면 연결선 위 칩으로 요약이 나온다. 필요 없으면 생략한다.
- 라벨(`label`)과 오류(`errors`)를 연결해 키보드·스크린리더로 쓸 수 있게 한다.

예제: [태그 입력 위젯](../../examples/web/agent-console-example-web/README.md).

## screen-entry

<!-- extdocs:facts screen-entry -->
- 등록: 웹 앱 레지스트리 `@agent-console/web/src/shell/routeConfig.ts#DEFAULT_ROUTES`에 항목 하나를 더한다(빌드 시 등록).
- 인터페이스:
  - `@agent-console/web/src/shell/routeConfig.ts#RouteDef`
  - `@agent-console/web/src/shell/routes.tsx#PageTable`
  - `@agent-console/web/src/shell/routes.tsx#DEFAULT_PAGES`
- 기본 구현: —
- 예제:
  - reference: [apps/web](../../apps/web/README.md)
- 끄기·제거: 항목을 빼고 다시 빌드한다.
<!-- /extdocs:facts -->

새 화면을 사이드바에 넣을 때 쓴다. 두 가지가 필요하다: 라우트 데이터 한 줄(`RouteDef`: 경로·제목 메시지 키·아이콘·묶음·역할)과
`routeId → 화면 컴포넌트` 표의 한 줄이다. 사이드바·빠른 이동·도움말 단축키 표가 모두 이 데이터에서 만들어진다.
서버 모듈이 `web_roles`에 같은 역할을 선언하면 그 모듈이 꺼졌을 때 항목도 사라진다.

- 화면 코드는 라우트 id가 아니라 `serves`(역할)로 다른 화면을 찾는다. id를 바꿔도 링크가 깨지지 않는다.
- 화면이 쓰는 API 호출은 컨테이너에서 하고, 화면 컴포넌트는 데이터와 콜백을 props로 받게 나눈다.
- 참조: [웹 앱](../../apps/web/README.md)의 셸과 라우트.

## interaction-renderer

<!-- extdocs:facts interaction-renderer -->
- 등록: 컴포넌트 `@agent-console/chat#defaultRenderers`의 props로 넘긴다(빌드 시 등록).
- 인터페이스:
  - `@agent-console/chat#RendererComponent`
  - `@agent-console/chat#RendererProps`
- 기본 구현: —
- 예제:
  - reference: [packages/ts/lib/chat](../../packages/ts/lib/chat/README.md)
- 끄기·제거: props에서 빼고 다시 빌드한다.
<!-- /extdocs:facts -->

에이전트가 사용자에게 되묻는 요청(상호작용)의 응답 화면을 바꿀 때 쓴다. 서버의 요청 설명에 renderer 이름이 있으면
`InteractionCard`의 `renderers` 표(이름 → 컴포넌트)에서 찾는다. 내장은 선택지·권한·검토 세 가지(`defaultRenderers`)이고
`renderers` prop으로 더하거나 바꾼다.

- 모르는 renderer 이름이면 응답 스키마 폼(또는 내장 폴백)으로 낮춘다. 사용자가 답할 수 없는 상태가 되지 않는다.
- 응답 값은 요청의 응답 스키마를 따른다. renderer는 보이는 모양만 바꾼다.
- 참조: [채팅 패키지](../../packages/ts/lib/chat/README.md)의 상호작용 구성요소.

## 라이브러리 재사용

`@agent-console/*` 표현 패키지(`log-view`·`arch-view`·`schema-form`·`chat` …)는 데이터와 콜백을 props로 받고 서버 API
클라이언트를 모른다. 다른 React 앱에서 쓸 수 있다.

- 번들러가 `development` 조건을 지원하면 소스를, 아니면 `dist`를 읽는다. 앱 번들러 설정의 `resolve.conditions`에 `development`를 넣으면 소스를 읽는다.
- 사내 패키지 의존은 `^x.y.z` 범위로 적는다. 저장소 밖에서는 tarball(`pnpm pack:all` → `dist/npm`)을 설치한다.
- 스타일은 각 패키지의 `styles.css`와 공용 토큰 CSS를 한 번씩 불러온다.
- 계약 타입(`@agent-console/contracts`)은 타입만 가져온다(`import type`).
- 저장소 밖에서 동작하는지는 `pnpm portability --package <이름>`으로 확인한다(`examples/web/` 예제도 같다). 필요한 tarball이 없으면
  도구가 `pnpm pack:all`을 먼저 돌리고, 소스를 고친 뒤에는 `--pack`으로 다시 만든다. 자세한 내용은 [패키지 만들기](packages.md).

## 앱에 쓰지 않는 예제

예제 패키지는 가져다 쓰는 견본이다. 저장소의 앱과 패키지는 예제를 import하지 않는다(의존 검사로 막는다). 앱 번들에는 예제가 들어가지 않는다.
