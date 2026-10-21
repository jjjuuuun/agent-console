# @agent-console/trace-view

위임 흐름(`Trace`) 타임라인 **표현** 패키지. 왼쪽 트리 + 오른쪽 시간 막대. 데이터·콜백은 props, 문구는 `messages`.
다른 TS 패키지는 import하지 않는다(`@agent-console/contracts` 타입만).

## 최소 사용
이 블록은 `test/readme.test.ts`와 같고, 테스트가 실제로 실행한다(`pnpm pkg-lint`가 일치를 검사).

```ts readme
import { formatDuration } from "@agent-console/trace-view";

const text = formatDuration(125, { s: "초", m: "분", h: "시간" });
```

## 스타일
```ts
import "@agent-console/ui/tokens.css";
import "@agent-console/trace-view/styles.css";
```

## 최소 사용 예
```tsx
<TraceTimeline trace={trace} now={nowSec} running labelFor={(s) => ({ title: nodeLabel(s.node_id) })}
  methodBadgeFor={(s) => ({ text: methodTitle(s) })} selectedSpanId={sel} onSelect={setSel} />
```

## 규칙
- 부모-자식은 `parent_id`가 가리키는 span이 있을 때만(시간상 추정 없음) → 들여 쓴 행 + "같은 세션". 최상위는 "별도 세션" + `trace.links`의 넘기기 화살표와 `order` 칩. 세션 판정은 `session_id` 비교, 없으면 부모 유무.
- 사용자 대기는 `interaction_id`가 있는 span(waiting 빗금 막대). 종류 문자열은 비교하지 않으므로 모르는 `kind`는 일반 행.
- 방식 배지 문구는 `methodBadgeFor`(앱이 연결 종류/위임 방식 `title` 전달). `now`는 epoch 초.
- 키보드: `↑↓←→ Enter Home End + -`, 접근성 이름 "{이름}, {방식}, {상태}, {소요}".

## 호출·회차·자식 실행 (5R.16)
종류 id는 비교하지 않고 span 필드로만 판정한다.
- 호출 span(`call` 또는 `invoked_by`가 있는 span): 위임자 span 아래 들여 쓴 행 + 항상 "별도 세션" 배지, 과제 미리보기(`task_preview`)가 막대 안 한 줄.
- 같은 노드에 회차(`iteration`)가 둘 이상(또는 1 이상)이면 이름 뒤 ` #n`, 호출이 둘 이상이면 ` · 호출 n`(번호는 값 + 1, 문구는 `messages.iterationSuffix`·`callSuffix`). `spanOrdinals`.
- 자식 Run(`span.run_id` ≠ `trace.run_id`)은 Run별 묶음 행 하나 아래로 모인다(`flattenRows`의 `runId`). 묶음은 그 Run의 맨 위 span이 가리키는 부모 span 아래에, 후손 Run은 부모 묶음 안에 중첩된다. 묶음 행: `Enter`/클릭 = 접기·펴기, `Ctrl+Enter`·[열기] = `onOpenChildRun(runId)`.
- 접힘은 제어형이 가능: `expandedGroupIds` + `onGroupToggle(runId, expanded)`. 생략하면 `defaultExpandedGroups`(끝나지 않은 span이 있으면 펼침, 끝났으면 접힘)로 시작하고 사용자의 선택을 화면이 유지한다.
- 앱 주입: `groupBadgeFor(group)`(묶음 제목·부제·배지), `linkBadgeFor(link)`(span 사이 화살표 칩, 예: 반복 연결 `↻`).

## 행 레이아웃 (5.2R.16, docs/design/ux-overhaul.md §4.4)
- 행은 CSS grid 한 벌(라벨 칸 / 막대 칸 / 수치 열). 요소는 자기 칸 밖으로 나가지 않고, 호버·선택은 배경색만 바꾼다. 컨테이너 쿼리로 좁은 패널(<560)·<640에서 부제·토큰·연결 칩을 숨긴다.
- 방식·세션은 글자 칩이 아니라 아이콘: 방식 = `MethodBadge.iconName`(연결 종류 `ui_hints.icon`), 세션 = 점선(같은)/실선(별도) 원. 문구는 `aria-label`·`title`. `showMethodText`(+`onShowMethodTextChange`)를 켜면 부제 자리에 문구를 글자로 보인다.
- 앱 주입(패키지는 `ui`를 import하지 않는다): `renderIcon(name, size)`, `renderTooltip(content, children)`(기본 = 글리프·`title`), `labelWidth`(px, 200~360으로 자름).
- 기계 검사용 속성: `data-trace-{toggle,order,label,icons,open,bar,link,tail}`.

## 테스트
`pnpm test`
