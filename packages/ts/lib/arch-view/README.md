# @agent-console/arch-view

관측 구조도 표현 컴포넌트. 서버가 좌표·라벨·지표까지 채워 준 `ArchitectureView`를 **영역·칸·연결(꺾은선)·라벨 칩**으로 그린다.
API·저장소·`ui`·`log-view`·`api-client`를 모른다. 데이터와 콜백은 전부 props다. 화면 명세: `docs/design/screen-architecture.md`.

- 칸 종류·연결 종류·색은 코드에 없다. 모든 이름은 데이터이고, 모르는 `tone`·`style`은 중립 모양으로 그린다.
- `value: null`은 어디서나 "–"/"수집 안 됨"이다. 합계·정렬·접근 이름에서도 0이 되지 않는다.
- 배율 0.45 미만이면 요약 표시(칸마다 숫자만)로 바뀐다. [그림|목록] 전환, 범례, 선택 정보 줄, 키보드 이동을 포함한다.

## 설치
저장소 안에서는 `pnpm install`이 로컬 패키지를 연결한다. 저장소 밖에서는 tarball(`pnpm pack:all` → `dist/npm`)을 설치한다.

```sh
npm install ./agent-console-arch-view-0.1.0.tgz
```

사용하는 앱은 토큰 CSS(`--ac-*` 변수, `@agent-console/ui/tokens.css`)와 이 패키지의 `@agent-console/arch-view/styles.css`를 한 번씩 불러온다.
이 패키지가 쓰는 토큰은 `styles.css`의 `var(--ac-…)` 참조뿐이다.

| 의존 | 왜 | 대안 |
| --- | --- | --- |
| `@xyflow/react` | 확대·이동·사용자 노드(칸·영역). 연결선은 `points`가 정한 꺾은선이라 `ViewportPortal` 위에 직접 그린다 | 손 SVG(§5.5R.4 대체안) |
| `@agent-console/contracts` | `ArchitectureView` 등 타입만 (`import type`) | — |

## 최소 사용
```ts readme
import { checkLayout, edgePath, formatMetric, gridLayout } from "@agent-console/arch-view";
import { defaultProfileView } from "@agent-console/arch-view/testing";

const view = defaultProfileView();
const problems = checkLayout(view);
const rects = gridLayout(view);
const llm = formatMetric({ status: "not_collected", value: null });
const line = edgePath(null, rects["input"], rects["sdk"]);
```

`problems`는 `[]`(기본 프로필 좌표에 겹침·교차 없음), `llm.text`는 `"–"`(수집 안 됨은 0이 아니다), `line`은 두 칸 경계에서 6px 바깥을 잇는 두 점이다.
이 블록은 `test/readme.test.ts`와 같아야 한다.

그림 컴포넌트:

```tsx
import "@agent-console/arch-view/styles.css";
import { ArchitectureDiagram } from "@agent-console/arch-view";

<ArchitectureDiagram
  view={view}                       // ArchitectureView (undefined면 불러오는 중)
  selection={selection}             // 지금 걸러 둔 대상 {kind, id, group?} | null
  highlight={membership}            // 선택한 이벤트가 맞은 칸·연결·묶음
  onSelect={setSelection}           // 같은 대상을 다시 누르면 null
  onBlocked={(target, reason) => toast(reason)}  // 수집 안 됨 칸·구조 연결: 걸러낼 이벤트 없음
  onDrill={(cellId, group) => drillInto(cellId, group)}
  messages={{ /* 문구 덮어쓰기 */ }}
/>;
```

## 공개 API
| 이름 | 역할 |
| --- | --- |
| `ArchitectureDiagram` | 도구줄(확대·맞춤·그림/목록·범례) + 캔버스 + 선택 정보 줄. `scale`·`fitMode`·`viewMode`는 제어/비제어 겸용 |
| `ArchitectureCellList` | 칸·연결 목록(그림과 같은 선택 상태·같은 콜백) |
| `ArchitectureInfoBar` | 선택·포커스 대상을 풀어 쓴 줄(지표 전체 값, 묶음 칩, 하위 구조도 단추) |
| `ArchitectureLegend` | 범례 견본(실제 칸·연결과 같은 클래스). 영역 견본은 prop `zoneLegend`(기본 `defaultZoneLegend`, `[]`면 없음) |
| `hasBatchim`·`josa`·`withJosa` | 한국어 조사 받침 맞춤 순수 함수. 문구 틀에서는 `{to\|으로/로}`(받침 있을 때/없을 때)로 쓴다. 연결 접근 이름 기본 틀이 이를 쓰고, `messages.ariaEdgeFlow`로 덮어쓴다 |
| `gridLayout(view)` | 좌표 없는 칸을 선언 순서대로 격자에 배치한 칸 사각형 표 |
| `edgePath(points, from, to)` | `points`가 있으면 그대로, 없으면 두 칸 경계 사이 직선(6px 바깥) |
| `formatMetric(metric, messages, opts)` | 지표 → 칸 글자·접근 이름·풀어 쓴 글자. 수집 안 됨은 "–" |
| `checkLayout(view)` | 칸–칸, 연결–칸, 연결–연결, 칩–칩 겹침·교차 목록(순수 함수, 설정 미리보기에도 쓸 수 있음) |
| 맞춤 `auto`(5.5R.20, 기본) | `autoFit`·`AUTO_CONTAIN_MIN`·prop `autoContainMin`: 폭 맞춤이 들어가면 폭, 아니면 전체 맞춤 배율이 기준(0.55) 이상일 때 전체, 미만이면 폭 맞춤 + 잘림 표시(하단 그라데이션·"아래 칸 n개 ↓" 칩·스크롤 표시). 캔버스 크기가 바뀔 때마다 다시 계산한다 |
| `fitViewport`·`zoomAround`·`ensureVisible`·`nearestInDirection` | 맞춤·확대·최소 스크롤·방향키 이동 순수 함수 |
| `@agent-console/arch-view/testing` | 예제 `ArchitectureView`(기본 프로필 좌표, 지표는 임시 값) |

## 확장 지점 (X24)
데이터에 쓰인 `tone`·`style`·`view`·지표 이름은 열린 문자열이다. 코드는 이름을 모르고 아래 대응표로만 바꾼다.
값은 **CSS 색이 아니라 토큰 변수 이름**(`--ac-…`)만 받으며, 그 밖의 값(`#ff0000` 등)은 중립 모양으로 그린다.

```tsx
<ArchitectureDiagram
  view={view}
  tones={{ ...defaultTones, mint: "--ac-cat-2" }}                       // tone → 칸 띠·테두리 색
  edgeStyles={{ ...defaultEdgeStyles, slow: { stroke: "--ac-cat-3", dash: "--ac-edge-pattern-3" } }}  // style → 선 모양
  edgeLegend={{ slow: "느린 호출" }}                                     // 새 style의 범례 글자
  metricKinds={{ ...defaultMetricKinds, bytes: { kind: "number" } }}    // 지표 이름 → 표기 종류
  cellRenderers={{ gauge: ({ cell, defaultBody }) => <>{defaultBody}<Gauge cell={cell} /></> }}  // 칸의 view 키 → 안쪽 그리기
/>
```

## 접근성
칸·연결 칩은 `button`(`aria-pressed`), 접근 이름은 "이름, 지표 조각, 상태 조각"이다. `Tab`은 칸(선언 순서) → 연결, 방향키는 가까운 칸, `Home`/`End`, `Shift+Enter` 하위 구조도, `Esc` 선택 해제, `+`/`-`/`0` 확대·축소·맞춤, `Backspace` 한 단계 위로(`onBack`).
상태는 색만으로 전달하지 않는다(빗금·점선·글자·아이콘).

## 개발·재사용
- `pnpm build` · `pnpm typecheck` · `pnpm lint` · `pnpm test`는 이 폴더 안에서 단독으로 돈다.
- 공개 API는 `exports`에 적힌 경로뿐이다. 다른 패키지는 `src/`·`dist/`를 직접 import하지 않는다.
- 저장소 밖으로 복사해도 되는지는 `pnpm portability --package @agent-console/arch-view`로 확인한다.
