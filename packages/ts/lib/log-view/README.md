# @agent-console/log-view

로그 분석 **표현** 패키지: 이벤트 표(가상 스크롤), 필터 막대, 범주 칩, 이벤트 상세, 세션 목록, 재생 막대, 레인 띠,
handoff 행렬, 대시보드 격자(위젯 레지스트리 + 차트 어댑터), 위젯 편집기, 템플릿 선택. 데이터·콜백은 모두 props다.
서버 호출·라우팅·저장은 앱이 한다. 출처·범주·위젯·차원·지표 이름은 코드에 없고 전부 받은 데이터에서 그린다.

사내 의존은 `@agent-console/contracts`(타입만)뿐이다. 공용 UI(`ui`), 위임 흐름 그림(`trace-view`), 스키마 폼(`schema-form`),
JSON 보기(`text-editor`)는 import하지 않고 슬롯 props(`renderCodeBlock`, `renderLinks`, `renderOptionsForm`, `filterBar`, `preview`)로 받는다.
슬롯이 없으면 기본 HTML로 그리거나 그 영역을 숨긴다. 색 슬롯 해시는 앱이 `slotFor(key) => 0..7`로 주입한다(해시를 복사하지 않는다).

## 설치
저장소 안에서는 `pnpm install`이 로컬 패키지를 연결한다. 저장소 밖에서는 tarball(`pnpm pack:all` → `dist/npm`)을 설치한다.

```sh
npm install ./agent-console-log-view-0.1.0.tgz
```

## 최소 사용
이 블록은 `test/readme.test.ts`와 같고, 테스트가 실제로 실행한다(`pnpm pkg-lint`가 일치를 검사).

```ts readme
import { isErrorEvent, sortEvents, splitSearchParams, toTaxonomyView } from "@agent-console/log-view";

// 오류 표시는 분류 체계의 tone="danger" 항목만 근거다(이름 비교 없음).
const taxonomy = toTaxonomyView({ categories: { "x-fail": { tone: "danger" } } });
const failing = isErrorEvent({ category: "x-fail" }, taxonomy);
// 재생 순서는 (time, seq) 오름차순.
const order = sortEvents([{ seq: 2, time: 5 }, { seq: 1, time: 9 }]).map((e) => e.seq);
// 화면 전용 URL 파라미터(through·lane·view·range·tab)는 서버 필터에서 빠진다.
const { filter, screen } = splitSearchParams("q=abc&through=7");
```

`failing`은 `true`, `order`는 `[2, 1]`, `filter`는 `{ q: "abc" }`, `screen`은 `{ through: ["7"] }`이다.

## 스타일
```ts
import "@agent-console/ui/tokens.css";
import "@agent-console/log-view/styles.css";
```
`--ac-log-*`·`--ac-dash-*` 토큰(tokens.md 5.9)이 정의돼 있으면 쓰고, 없으면 `styles.css`의 기본값을 쓴다.

## 공개 API 요약
| 영역 | 이름 |
| --- | --- |
| 컴포넌트 | `LogEventTable` `LogFilterBar` `CategoryChips` `LogEventDetail` `SessionList` `PlaybackBar` `LaneRibbon` `HandoffMatrixView` `DashboardGrid` `WidgetEditor` `TemplatePicker` `ColorSlotPicker` `UnknownWidget` `AggregateTable` |
| 명령형 API(5R.21) | `LogEventTable`·`LogEventDetail`는 `ref`로 `LogEventTableHandle`(`scrollToUid`·`focus`)·`LogEventDetailHandle`(`selectTabAt`·`focusTab`·`visibleTabs`)를 낸다. `onActivate`(표 Enter)·`activeTab`/`onActiveTabChange`(상세)·`onActiveChange`(`SessionList`)로 앱이 DOM을 읽거나 클릭하지 않는다 |
| 위젯 레지스트리(X21) | `WidgetDescriptor` `createWidgetRegistry` `builtinWidgets`(metric·bar·line·table) `validateQuery` |
| 재생 | `sortEvents` `visibleThrough` `indexOfSeq` `seqAtIndex` `usePlayback`(가짜 `clock` 주입) `playbackDelay` `nextSpeed` `clipTraceAt` |
| 필터·URL | `reservedParams` `splitSearchParams` `buildFilterQuery` `buildScreenSearch` `findReservedConflicts` `createLocalStorageSavedFilters` |
| 분류 체계 | `toTaxonomyView` `isErrorEvent`(판정은 한 곳) `isHiddenEvent` `colorFor` `orderCategories` `groupByMessage` |
| 대시보드 배치 | `layoutFlow` `moveWidget` `resizeWidget` `updateWidget` `removeWidget` `duplicateWidget` `preserveUnknown` `preserveUnknownDashboards` |
| 서식 | `defaultFormatters` `formatRelativeTime` `formatDurationMs` `formatTokensShort` (앱이 `formatters` prop으로 덮어쓸 수 있다) |

- 위젯 종류를 더하려면 `WidgetDescriptor`를 만들어 `createWidgetRegistry(builtinWidgets, mine)`에 넘긴다. 목록에 `switch`가 없고, 레지스트리에 없는 `kind`는 `UnknownWidget`(설정 보존)으로 그린다.
- 차트는 `charts/` 어댑터 안에서만 recharts를 쓰고 지연 로드한다. 로드 실패 시 위젯은 표로 대체된다. recharts 타입은 공개 API에 나오지 않는다.
- 서식 함수: 이 저장소의 기존 포맷터(`apps/web/src/lib/format.ts`, `features/runs/runsLib.ts`)는 앱 안에 있어 패키지가 가져다 쓸 수 없으므로 같은 규칙(`screen-logs.md` §1.7)의 내장 구현을 둔다. 앱이 이미 가진 포맷터가 있으면 `formatters` prop으로 주입한다.

## 새 의존
| 무엇을 | 버전·라이선스 | 왜 | 대안 |
| --- | --- | --- | --- |
| `@tanstack/react-virtual` | 3.14.x, MIT, peer `react ^16.8 \|\| ... \|\| ^19` | 이벤트 표·세션 표·관련 목록 가상 스크롤(헤드리스) | react-window(MIT) |
| `recharts` | 3.10.x, MIT, peer `react`·`react-dom`·`react-is` `^16.8 \|\| ... \|\| ^19` | 꺾은선 차트(선언형 React). `charts/` 어댑터 안에서만 쓰고 지연 로드 | ECharts(Apache-2.0, 무거움), uPlot(MIT, 명령형) |
| `react-is` | 19.x, MIT | recharts의 peer 의존 | — |

## 테스트
`pnpm test` — 임의 분류 체계(0개·100자 이름·모르는 색)·임의 위젯 디스크립터·임의 필터 필드로 렌더하고, 재생은 가짜 시계로 돌린다.
