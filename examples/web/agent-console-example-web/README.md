# @agent-console/example-web

웹 화면에 **대시보드 위젯 하나, 구조도 칸 그리기 하나, 설정 폼 위젯 하나**를 더하는 예제.
웹에는 런타임 플러그인이 없다. 이 예제는 라이브러리로 만든 표현 코드이고, 웹 앱에 한 줄씩 등록한 뒤 앱을 다시 빌드해야 보인다.
서버·계약 코드는 고치지 않는다. 앱에 등록하지 않으면 아무것도 바뀌지 않는다.

| 지점 | 이 예제의 것 | 키(데이터) |
| --- | --- | --- |
| 대시보드 위젯 | `gaugeWidget` (지표 하나를 최대값 대비 막대로) | 위젯 종류 `example.gauge` |
| 구조도 칸 그리기 | `cellRenderers` (칸에 `count` 배지를 덧붙임) | 칸의 `view` 값 `example-badge` |
| 설정 폼 위젯 | `configWidgets` (쉼표로 나눈 태그 목록 입력) | 설정 스키마 `ui:widget` 이름 `example.tags` |

세 가지 모두 모르는 값에 무해하다. 위젯 종류가 등록되지 않았으면 격자가 "알 수 없는 위젯" 자리 표시를 그리고 설정은 보존된다.
`view` 키가 맞지 않는 칸은 기본 모양이다. 값이 `null`(수집 안 됨)이면 0이 아니라 "–"이거나 배지를 달지 않는다.

## 최소 코드

세 조각 모두 표현 컴포넌트와 등록 객체로 나뉘어 있고 서버 호출이 없다. 데이터와 콜백은 props로 받는다.

```ts readme
import { builtinWidgets, createWidgetRegistry } from "@agent-console/log-view";
import { cellRenderers, configWidgets, gaugeWidget } from "@agent-console/example-web";

const registry = createWidgetRegistry(builtinWidgets, [gaugeWidget]);
const gaugeRegistered = registry.has("example.gauge");
const cellViews = Object.keys(cellRenderers);
const widgetNames = Object.keys(configWidgets);
```

`gaugeRegistered`는 `true`, `cellViews`는 `["example-badge"]`, `widgetNames`는 `["example.tags"]`다. 이 블록은 `test/readme.test.ts`와 같아야 한다.

실제 구현은 `src/GaugeWidget.tsx`·`src/BadgeCell.tsx`·`src/TagsField.tsx`.

## 등록

웹 앱(`apps/web`)에서 지점마다 한 줄이다. 라이브러리가 받는 props 이름은 지점 선언의 `interface`와 같다.

```tsx
// 1) 대시보드 위젯: DashboardGrid·WidgetEditor가 쓰는 레지스트리에 목록을 더한다
const registry = createWidgetRegistry(builtinWidgets, [gaugeWidget]);
<DashboardGrid registry={registry} /* … */ />;

// 2) 구조도 칸: cellRenderers prop에 표를 넘긴다. 칸의 view 값은 서버 구조도 프로필 데이터가 정한다
<ArchitectureDiagram cellRenderers={cellRenderers} /* … */ />;

// 3) 설정 폼 위젯: 앱의 위젯 레지스트리에 펼쳐 넣는다. 이름은 서버 설정 스키마의 ui:widget이다
export const CONFIG_WIDGETS = { /* 기존 위젯 */ ...configWidgets };
```

앱은 이 예제를 `package.json` 의존으로 가져온 뒤 **웹 앱을 다시 빌드**한다(`pnpm --filter @agent-console/web build`).
이 예제의 폴더는 앱이 import하지 않도록 두었다(저장소는 의존 검사로 막는다). 가져다 쓰려면 폴더를 복사해 이름을 바꾸거나 자기 패키지로 옮긴다.

## 설치·제거

- 설치: 이 폴더를 pnpm 워크스페이스 멤버로 둔다(`pnpm-workspace.yaml`에 `examples/web/*`). 앱에 쓰려면 위 등록 코드를 앱에 더하고 의존에 넣는다.
- 제거: 앱의 등록 한 줄과 의존을 지우고 다시 빌드한다. 저장된 대시보드 위젯은 지워지지 않고 "알 수 없는 위젯"으로 남아 설정이 보존된다.
- 저장소 밖에서는 tarball(`pnpm pack:all` → `dist/npm`)을 설치한다.

## 테스트

```sh
pnpm --filter @agent-console/example-web test
pnpm --filter @agent-console/example-web typecheck
```

위젯은 `DashboardGrid`, 칸 그리기는 `ArchitectureDiagram`, 설정 폼 위젯은 `SchemaForm`에 실제로 등록해 그린다.
모르는 값(null, 맞지 않는 옵션·`view` 키·배열이 아닌 값)과 접근성(axe 0건)을 함께 확인한다.
저장소 밖 복사 검사: `pnpm portability --package @agent-console/example-web`.
