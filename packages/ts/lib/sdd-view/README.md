# @agent-console/sdd-view

스펙(SDD) 표현 컴포넌트 모음: 스펙 목록, 문서 목록, 문서 편집기(편집 + 마크다운 미리보기), 작업 표(가상 목록·단계 묶음·상태 메뉴),
계획 그래프(읽기 전용)·묶음 글, 요구-작업 추적 표, 관문 안내와 순수 함수.
데이터와 콜백은 전부 props이고 API·저장소·`api-client`를 모른다. 상태·문서 종류·단계·톤 이름은 코드에 없고 서버가 준 데이터(`label`·`tone`)다.
사내 의존은 `@agent-console/contracts`(타입만)와 `@agent-console/markdown-doc`뿐이다(문서 편집기·칩·출처 배지는 거기로 옮겼고 이 패키지가 같은 이름으로 다시 내보낸다, 7R.6). react 19는 peer다.

## 최소 사용
이 블록은 `test/readme.test.ts`와 같고, 테스트가 실제로 실행한다(`pnpm pkg-lint`가 일치를 검사).

```ts readme
import { groupByStage, planToFlow, statusTone } from "@agent-console/sdd-view";
import { samplePlan, sampleStatuses, sampleTasks } from "@agent-console/sdd-view/testing";

const statuses = sampleStatuses();
const tasks = sampleTasks();
const groups = groupByStage(tasks, (s) => statuses.some((x) => x.id === s && x.done === true));
const chip = statusTone("s-done", statuses);
const flow = planToFlow(samplePlan(), tasks);
```

## 설치 / 사용
저장소 안에서는 `pnpm install`이 연결한다. 저장소 밖에서는 tarball(`pnpm pack:all` → `dist/npm`)을 설치한다(react 19 필요).
`@agent-console/ui/tokens.css`(디자인 토큰)와 이 패키지의 `styles.css`를 앱이 한 번씩 로드한다(`styles.css`가 markdown-doc의 `styles.css`를 `@import`한다).

```tsx
import "@agent-console/sdd-view/styles.css";
import { TaskTable, DocumentEditor, PlanGraph, TraceMatrix } from "@agent-console/sdd-view";

<TaskTable tasks={view.index.tasks} statuses={view.task_statuses} onStatusChange={(task, status) => patch(task.key, status, task.line_hash)} />
<DocumentEditor document={doc} value={draft} onChange={setDraft} onSave={save} readOnly={!writable} conflict={changedOutside} />
```

## 컴포넌트
| 컴포넌트 | 용도 |
| --- | --- |
| `SpecList` | 스펙 목록(가상). 진행·지금 단계·문서 상태 칩. 열 머리 정렬(`sortColumns`·`sort`·`onSortChange`, `aria-sort`)과 행 메뉴 slot(`renderRowMenu`)은 props로 받는다 |
| `DocumentNav` / `DocumentStateChip` / `ToneChip` | 문서 목록, 상태 칩(톤 5종 공통 규칙) |
| `DocumentEditor` (markdown-doc에서 다시 내보냄) | text-editor + react-markdown 미리보기. 읽기 전용·파일 없음·충돌·IME 조합. 비교 기준 `compare`(→ [변경 비교], TextDiff)·`externalChange` 띠·`onCopyMine`([내 변경 복사]), 제어형 `mode`/`onModeChange`, `initialLine`·`handleRef`(`openGoToLine`·`goToLine`) — 데이터와 콜백만 받고 클립보드·확인 대화상자·단축키 등록은 호출자가 한다 |
| `TaskTable` (`TaskStatusMenu`·`TaskFieldChips`·`TaskRunChips`) | 작업 표(가상, 단계 묶음, 인라인 펼침). 문법 없음·빈 상태·줄 충돌. 행 체크박스 선택(`selectable`·`selectedKeys`), 단계 접힘 덮어쓰기(`collapsedOverrides`), 행 아래 인라인 안내(`renderRowNotice`), 행 컨텍스트 메뉴(`rowMenuItems`), 단축키 처리기용 손잡이(`ref`: `TaskTableHandle`) |
| `PlanGraph` / `PlanBundles` | @xyflow/react + elkjs 읽기 전용 그래프 / 병렬 묶음 글 |
| `TraceMatrix` | 요구-작업-실행-검증 표(가상), 빈 곳 거르기 |
| `GateNotice` / `RulesSourceBadge` (markdown-doc에서 다시 내보냄) | 관문 막힘 안내 / 규칙 값 출처 배지 |

순수 함수: `groupByStage`, `flattenTaskRows`, `statusTone`, `codeDisplay`, `toneAttr`, `planToFlow`, `planBundles`, `applyPositions`, `createElkPlanLayout`, `filterTraceRows`, `gapLabelKey`.
문구는 `messages` prop(부분 덮어쓰기)과 `defaultMessages`다. 하위 경로 `./testing`은 표본 데이터(앱 번들에 넣지 않음).

## 의존성(무엇을 / 왜 / 대안)
- `@xyflow/react` — 계획 그래프 렌더. 대안: 직접 SVG(팬·줌·접근성 직접 구현).
- `elkjs` — 층 배치. 처음 필요할 때만 동적 import, 엔진은 `engine` prop으로 바꿀 수 있다. 대안: 층별 열 배치(실패 시 폴백으로 이미 있음).
- `@tanstack/react-virtual` — 큰 표 가상 스크롤. 대안: 쪽 나누기.
- `react-markdown` + `remark-gfm` — 문서 미리보기. 이제 `@agent-console/markdown-doc`가 가진다.
