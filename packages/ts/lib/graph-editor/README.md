# @agent-console/graph-editor

디스크립터 기반 그래프 편집기(React 컴포넌트). 노드 타입·엣지 종류·포트를 서버가 준 데이터(디스크립터)로만 그리므로,
새 노드 타입이 생겨도 이 패키지를 고치지 않는다. 실행 보기용 읽기 전용 모드와 노드 상태 오버레이를 포함한다.

- 노드 추가(팔레트 항목 더블클릭·포커스 후 Enter·드래그) · 삭제(5초 되돌리기 토스트) · 연결 · 이동 · 복제
- 그룹, undo/redo(100단계)는 이번 범위가 아니다(그래프의 `groups` 등 모르는 필드는 그대로 보존).
- 팀 구성 모드(아래 "팀 구성 모드")를 포함한다: 정의 팔레트, 입구/답변/묻기 단축 조작, 연결 종류 고르기, 리소스 보기, 이슈 제안 적용.
- 공개 API에 React Flow 타입이 나오지 않는다. 다른 TS 패키지에 의존하지 않고 `@agent-console/contracts`의 타입만 쓴다.

## 최소 사용
이 블록은 `test/readme.test.ts`와 같고, 테스트가 실제로 실행한다(`pnpm pkg-lint`가 일치를 검사).

```ts readme
import { categoryColorSlot, categoryColorVar } from "@agent-console/graph-editor";

// 노드 분류(category) 문자열 -> 분류색 슬롯. 같은 문자열은 언제나 같은 색이다.
const slot = categoryColorSlot("review");
const cssVar = categoryColorVar("review");
```

## 설치
저장소 안에서는 `pnpm install`이 연결한다. 저장소 밖에서는 tarball(`pnpm pack:all` → `dist/npm`)을 설치한다: `npm install ./agent-console-<이름>-<버전>.tgz`
`react`/`react-dom`(^19)은 peer 의존이다. 앱은 `@agent-console/ui`의 `tokens.css`(색·글꼴·`[data-status]` 규칙·`.ac-ellipsis` 등)와 이 패키지의 `styles.css`를 각각 한 번 로드한다.

```ts
import "@agent-console/ui/tokens.css";
import "@agent-console/graph-editor/styles.css";
```

## 최소 사용 예
```tsx
import { GraphEditor } from "@agent-console/graph-editor";
import type { Graph, NodeTypeDescriptor, EdgeTypeDescriptor } from "@agent-console/contracts";

function Editor({ graph, nodeTypes, edgeTypes, setGraph }: {
  graph: Graph; nodeTypes: NodeTypeDescriptor[]; edgeTypes: EdgeTypeDescriptor[]; setGraph(g: Graph): void;
}) {
  return (
    <div style={{ height: 600 }}>
      <GraphEditor
        graph={graph}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onChange={(next, meta) => setGraph(next)}           // meta.reason: add-node | remove | connect | move | ...
        resolvePorts={(typeId, config) => api.resolvePorts(typeId, config)} // 동적 포트 타입만 호출됨
        renderConfigPanel={(ctx) => <MyForm node={ctx.node} onChange={ctx.onChangeNode} />}
      />
    </div>
  );
}
```
실행 보기: `<GraphEditor readOnly graph=… nodeTypes=… edgeTypes=… nodeStates={{ n1: { status: "running", summary: "00:03" } }} />`.

## props 요약
| prop | 설명 |
| --- | --- |
| `graph` | 제어형 그래프. 편집기가 모르는 필드는 `onChange`에서 그대로 통과 |
| `nodeTypes`, `edgeTypes` | 디스크립터 배열(팔레트·모양·포트·엣지 종류의 유일한 출처) |
| `nodeStates`, `edgeStates` | 상태 오버레이. 상태는 `data-status` 속성만 단다(스타일은 tokens.css). 라벨은 `messages.statusLabels` |
| `resolvePorts(typeId, config)` | `dynamic_ports` 타입의 포트 계산. 300ms 디바운스·(타입+config) 캐시·마지막 요청 응답만 채택(`PortResolver`) |
| `onChange(next, {reason, previous})` | 모든 편집의 단일 출구. 드래그는 드롭 시 한 번 |
| `renderConfigPanel(ctx)` | 우측 패널 슬롯(선택이 있을 때). 설정 폼은 앱이 채움 |
| `readOnly` | 팔레트·삭제·연결·이동 없음. 선택·패닝·줌·패널 슬롯은 동작 |
| `issues` | 계약 `Issue[]` 그대로. 노드 배지(오류 ✕, 경고 ▲ + 개수, 접근성 이름 '검증 오류 N건, 경고 M건')와 엣지 무효 스타일만 담당 |
| `focusRequest` | `{ nodeId, token }`. token이 바뀔 때마다 그 노드를 선택하고 화면에 맞춤(이슈 행 클릭 이동용). 같은 노드를 다시 눌러도 token(카운터 등)만 바꾸면 다시 동작, token이 같으면 무시 |
| `defaultEdgeKind` | 새 연결의 엣지 종류. 없으면 `edgeTypes[0]`(둘 이상이면 첫 항목이 미리 선택된 선택 UI) |
| `canvasActions` | 캔버스 좌상단 도구줄 슬롯(앱의 [+ 추가 ▾] 같은 단추, 5.2R.20). 읽기 전용이면 그리지 않음 |
| `showMinimap`, `onShowMinimapChange` | 미니맵(140x96, 우하단). `onShowMinimapChange`를 주면 우하단 토글 아이콘이 생긴다(제어형, 기본 켬/끔은 앱이 정함) |
| `paletteOverlay`, `paletteOpen`, `onPaletteClose` | 좁은 화면용 오버레이 팔레트: 캔버스 폭을 차지하지 않고 `paletteOpen`일 때만 위에 뜬다. Esc는 `onPaletteClose` |
| `idFactory`, `snapToGrid`, `showPalette`, `palette`, `undoWindowMs`, `messages` | 기타 설정·문구 |

노드 어디서나 연결(5.2R.24): 노드를 선택하면 가장자리 띠가 생기고, 띠(또는 포트 핸들)에서 끌어 상대 노드 몸체에 놓으면 연결된다. 포트는 `inferKindPorts`(순수 함수)가 `default_ports` -> 첫 호환 포트 순으로 정하고, 후보 종류가 여럿이면 선택 UI의 포트 열(`EdgeKindCandidateInfo.portsText`)에서 고른다.

`GraphEditorHandle.addNodeAtCenter(typeId, definition?)`(5.2R.20): 팔레트 [추가]와 같은 선택·자동 연결·`onChange`로 노드를 **보이는 영역 중앙**에 놓고(겹치면 격자 단위로 대각선 이동, `centerFreePosition`) 새 노드 id를 돌려준다.

하위 공개 컴포넌트/순수 함수: `NodeCard`, `NodePalette`, `EdgeKindDialog`, `categoryColorSlot`, `measureNodeSize`, `addNode/removeSelection/duplicateNodes/moveNodes/checkConnection/decideEdgeKind`, `PortResolver`.

**역할 분리:** 이슈 패널(목록, 행 클릭 이동)은 앱 책임이고, 노드, 엣지 표시는 `issues` prop이 담당한다. 행 클릭 시 앱은 `focusRequest={{ nodeId, token: ++n }}`로 선택과 이동을 요청한다.
캔버스에는 오류(✕)와 경고(▲)만 표시한다. info 등 그 밖의 심각도는 캔버스에 표시하지 않으며, 목록과 패널에서 보여 주는 것은 앱 책임이다.

## 팀 구성 모드 (1R.21)
편집기는 **노드 타입 id·연결 종류 id를 모른다.** 아래는 모두 디스크립터 속성으로만 판단한다(테스트는 `src/testing.ts`의 임의 이름 디스크립터).

| 기능 | 근거 속성 |
| --- | --- |
| 팔레트 "정의에서 만드는 노드" | 노드 타입 `binds{kind,field}` × `definitionLists[binds.kind]`. 추가하면 `config[binds.field] = 정의 id`, label = 정의 이름 |
| 팔레트 "기본 노드" | `binds` 없는 타입. `ui_hints.hidden`인 타입은 어디에도 안 나옴(이미 그래프에 있으면 그려짐) |
| 칩 카드 | `ui_hints.shape`(`chip`/`card`) 우선, 없으면 `executable === false` |
| 연결 시 종류 후보 | `connects.source/target` × 노드 타입 `role` (`candidateEdgeKinds`). 후보 0개 = 거부, 1개 = 바로 연결, 2개 이상 = 선택 UI(미리 선택 = 마지막으로 고른 종류 → `defaultEdgeKind` → 첫 후보) |
| 사이클 거부 | 새 종류의 `scheduling`이 `flow`(기본)일 때만, 기존 `flow` 엣지만 따라 검사. `none/entry/exit`는 제외 |
| 입구 / 답변 / 묻기 토글 | 종류는 `scheduling = entry` / `exit` / `interaction`이 있는 것. 사용자 노드는 그 종류 `connects`의 상대 역할로 찾음. 포트는 `default_ports`, 없으면 노드 타입 포트 순서의 첫 포트 |
| 상황 배지 | 같은 속성(입구 = entry 도착, 답변 = exit 출발, 묻기 = interaction 출발) |
| 연결 종류 보조 배지 | `scheduling`/`invocation`/`interaction` 에서 계산(`edgeKindBadge`) |
| 이슈 제안 | `Issue.suggestions[].patch`를 그대로 적용(`applyGraphPatch`). 이슈 코드를 해석하지 않음 |
| 동적 포트(사용자 노드 결정 포트) | `dynamic_ports` + `resolvePorts`(Phase 1과 동일) |

추가 props: `definitionLists`, `definitionKindTitles`, `mode`(`edit`|`readonly-run`), `showResources`/`onShowResourcesChange`, `onOpenResources`, `teamShared`, `onRoleToggle`, `onApplySuggestion`, `onConnectRejected`, `waitingNodes`, `edgeOrder`, `edgeCounts`, `nodeBadgesOverride`, `portLabels`(`auto`|`always`), `nowMs`, `ref`, `palette.onCreateDefinition`.

```tsx
const ref = useRef<GraphEditorHandle>(null);
<GraphEditor ref={ref} graph={g} nodeTypes={nt} edgeTypes={et}
  definitionLists={{ [binds_kind]: [{ id: "a1", name: "PL", usageCount: 2 }] }}
  defaultEdgeKind={settings.editor.default_edge_kind}
  onChange={(next, meta) => setDraft(next)}        // meta.reason: ... | 'role-toggle' | 'apply-suggestion'
  onConnectRejected={(info) => toast(info.reason)}   // 지정하면 내부 토스트 대신 앱이 문구를 만든다
  renderConfigPanel={(ctx) => (
    <RoleToggleRow info={ctx.roleToggles!.entry} label="입구" onToggle={(on, opt) => ctx.onToggleRole?.("entry", on, opt)} />
  )} />;
// 이슈 목록: <IssueSuggestionButtons issue={issue} onApply={(i, s) => ref.current?.applySuggestion(i, s)} />
```
- `GraphEditorHandle`(ref): `getRoleToggleInfo(nodeId)`, `toggleRole(nodeId, toggle, on, options?)`, `applySuggestion(issue, suggestion)`, `canHaveResources(nodeId)`. 읽기 전용이면 아무것도 바꾸지 않고 `false`.
- 순수 함수(UI 없이 사용): `candidateEdgeKinds`, `deriveNodeBadges`, `getRoleToggleInfo`, `applyRoleToggle`, `applyGraphPatch`, `canHaveResources`, `deriveResourceChips`, `buildTeamPalette`, `checkConnection(g, c, portsOf?, {edgeTypes, kind}?)`, `decideEdgeKind(후보 id[], 기본값?)`.
- 하위 컴포넌트: `TeamPalette`, `PaletteItem`, `RoleToggleRow`, `ResourceChips`, `IssueSuggestionButtons`, `TeamSharedBar`, `EdgeKindDialog`(후보 + 선 미리보기 + 숫자키).
- 리소스 보기: 끄면 `executable=false` 노드와 그 노드가 끝점인 연결을 숨기고 도착 카드에 리소스 칩 줄(타입별 아이콘 + 개수). 단축키 `V`. 캔버스 하단 중앙 체크박스(리소스 타입이 있을 때만).
- 알려진 한계: 엣지 라벨 칩은 Phase 1 규칙(선택/무효/배지·칩이 있을 때만 보임)을 유지한다. 줌 LOD, 연결 종류 팝오버의 드롭 지점 배치는 아직 없다(모달 다이얼로그).

### 선언형 배지·칩 (1R.34)
노드/엣지 타입 디스크립터의 `ui_hints.badges` / `ui_hints.chips` = `[{label_key?, label?, when?}]`를 해석한다(형식과 조건 어휘: design.md "선언형 배지·칩").
조건: `config_path`(존재) + `equals`/`not_equals`/`in`/`exists`, 노드 전용 `incoming_scheduling`/`outgoing_scheduling`. 객체 = AND, 배열 = OR. 문구는 `messages.hintLabels[label_key]` → `label` → 키 순. 순수 함수: `declaredLabels`, `evaluateWhen`, `evaluateCondition`.
- 토글 후보(연결 종류 × 상대 사용자 노드)가 여럿이면 편집기가 첫 후보를 고르지 않는다: 툴바는 선택 메뉴를 열고, `applyRoleToggle`은 옵션이 없으면 `reason: "ambiguous"`로 변경 없이 돌려준다(`toggleChoices(info)`로 조합 목록).
  - 후보 메뉴 키보드: 열리면 첫 항목에 포커스, ↑↓·Home/End 이동, Enter/Space 선택(항목은 button), Escape는 닫고 토글 버튼으로 포커스 복귀. 선택 노드가 바뀌면 자동으로 닫힌다.
- `applySuggestion`은 실제 적용(그래프가 바뀐 경우) 뒤에만 `onApplySuggestion`을 부른다.
- 포트 라벨 `auto`: 연결 드래그 중에는 모든 포트 라벨을 보인다.

## 표시 규칙
- 아이콘/색: 디스크립터 `ui_hints.icon`(1~2자)·`color`(안전한 CSS 색)가 있으면 사용, 없거나 해석 불가하면 카테고리 문자열 해시(`--ac-cat-1..8`) + 제목 첫 글자.
- 모르는 노드 타입도 그린다(중립색, 점선 위험 테두리, 포트는 엣지에서 복원). 포트가 사라진 엣지는 지우지 않고 무효(점선 + "!") 표시.
- 연결: 자기 연결·흐름 순환(`scheduling = flow`)은 거부하고 안내 토스트, 같은 (포트, 종류) 연결이 이미 있으면 기존 엣지 선택.
- 화살촉은 대상 노드 경계에서 6px 바깥에서 끝난다. 긴 텍스트는 `.ac-clamp-2`/`.ac-ellipsis`(tokens.css) + `title` 전체 값.
- 단축키: `Delete`/`Backspace` 삭제, `Ctrl/⌘+D` 복제, Shift/Ctrl+클릭 다중 선택, 방향키 이동(캔버스 라이브러리 기본).

## 의존성 (무엇을 / 왜 / 대안)
| 의존 | 왜 | 대안 |
| --- | --- | --- |
| `@xyflow/react` ^12.12 (MIT) | 노드/엣지 캔버스, 패닝·줌·핸들 연결·미니맵·접근성 기본 제공. 이 패키지 안에만 둠(`components/flow.tsx`, `GraphEditor.tsx`) | 직접 SVG 캔버스 구현(비용 큼), Rete.js, Cytoscape.js(노드 UI에 부적합) |
| `elkjs` ~0.12.0 (`EPL-2.0 OR GPL-3.0-or-later` 중 **EPL-2.0 선택**, 결정 E-5) | 자동 배치 [정리 ▾]: 계층형 배치에서 포트 면 제약·방향 4종·교차 최소화·순환 처리. 동적 import + Web Worker로만 쓰고 `layout/elkEngine.ts` 밖으로 타입이 나오지 않는다. 수정 없이 번들로 쓰며 소스를 고쳐 배포하게 되면 라이선스를 다시 본다 | `dagre`(포트 면 미지원), 자체 구현(품질·유지 비용), `libavoid-js`(배치 불가·LGPL·WASM) |
| `react`, `react-dom` ^19 (peer + dev) | 컴포넌트 | — |
| `@testing-library/react` (dev) | 컴포넌트 테스트 | — |

## 테스트
`pnpm test` (패키지 폴더 또는 루트, Vitest, happy-dom). `src/logic/*`는 UI 없이 도는 순수 로직 단위 테스트, `GraphEditor.test.tsx`는 임의 이름의 디스크립터 3종 + 모르는 타입으로 렌더·편집 테스트.
happy-dom에는 레이아웃이 없어 노드 크기가 0으로 측정되므로, 드래그 이동·핸들 연결 제스처는 단위 테스트(순수 함수)로 검증하고 브라우저 E2E(Playwright)에서 확인한다.

## 배치·표시 메모
- 위치 없이 추가한 노드는 선택된 노드(없으면 가장 오른쪽 노드)의 오른쪽, 겹치면 아래로 배치된다(`nextFreePosition(g, grid, anchorId)`).
- 엣지 라벨 칩은 선택됐거나 무효인 엣지에서만 보인다(좁은 간격에서 겹침 방지). 미니맵은 `--ac-*` 토큰을 쓴다.

## 연결선 모양·경로 편집 (3R.22)

엣지를 선택하면 캔버스에 조작 점이 나타난다(읽기 전용·줌 0.5 미만에서는 숨김). 한 번의 조작 = `onChange` 1회, `meta.reason === "layout"`.
`layout`은 실행·버전 해시와 무관한 화면 데이터라서 저장해도 새 버전이 생기지 않는다.

| 조작 | 방법 |
| --- | --- |
| 경유점 만들기 | 중점 `◇`을 끌기(임계 3px) / 선 더블클릭 / 경로 편집 모드에서 중점 Enter·Space·W |
| 경유점 이동 | `■` 끌기(격자 스냅, Alt 해제, Shift 축 고정) / ←↑↓→ 8px(Shift 32, Alt 1) / 연결 패널 x·y 입력 |
| 경유점 삭제 | 더블클릭 / Delete·Backspace / 앞뒤 점과 일직선(화면 6px)에 놓으면 자동 삭제 |
| 라벨 이동 | 칩을 끌면 경로를 따라(`label_t`, 0.05 단위), Shift면 자유 위치(`label_offset`), 더블클릭은 초기화 |
| 모양 / 경로 초기화 | `S`·`Shift+S`(레지스트리 순서, 마지막 다음은 상속) / `X` |
| 경로 편집 모드 | 엣지에서 `Enter` -> Tab 순서 경유점, 중점, 라벨 칩 -> `Esc` 종료. 결과는 `aria-live`로 알림 |

연결 패널의 "모양·경로" 섹션은 `renderConfigPanel`이 받는 `ctx.edgeLayout`을 그대로 넘겨 그린다. 모양 목록은 `edgeShapes` 레지스트리에서 나오고,
`supportsRadius`·`supportsBend`·`supportsWaypoints`가 false인 입력은 숨긴다.

```tsx
<GraphEditor
  graph={graph}
  nodeTypes={nodeTypes}
  edgeTypes={edgeTypes}
  onChange={(next, meta) => save(next, meta.reason)}
  renderConfigPanel={(ctx) => (ctx.edgeLayout ? <EdgeLayoutPanel {...ctx.edgeLayout} /> : null)}
/>
```

`EdgeLayoutPanel`·`EdgeWaypointLayer`는 React Flow에 의존하지 않는 표현 컴포넌트이고, `layout`을 고치는 순수 함수(`patchEdgeLayout`, `normalizeEdgeLayout`,
`cycleShape`, `insertWaypoint`, `isRedundantWaypoint` 등)는 `logic/edgeLayoutOps.ts`에 있다. 저장 정규화: 키 순서 `shape, radius, bend, waypoints, label_t, label_offset`,
빈 값은 키째 삭제, 좌표·반경 소수 1자리(라벨 위치는 0.05 단위라 2자리), 모르는 키는 통과. 문구는 `messages`(`waypoint*`, `edgeLayout*`)로 바꾼다.

## 노드 배치 (3R.23)

노드를 선택하면 방향과 포트 면을 바꿀 수 있다. 한 번의 조작 = `onChange` 1회(`reason === "layout"`).

- `R` / `Shift+R`: 방향 순환(어휘는 `directions` props 표, 기본 lr → tb → rl → bt → 상속). 툴바에도 같은 버튼이 있다.
- 핸들을 400ms 누르고 있거나 `Alt`를 누른 채 끌면 이동 모드가 되고, 가장 가까운 면에 놓으면 그 포트의 면이 저장된다(`Esc` 취소). 읽기 전용에서는 꺼진다.
- `Ctrl+Z` / `Ctrl+Shift+Z`(`Ctrl+Y`): 레이아웃 변경(`layout`·`move`·`auto-layout`)만 30단계 되돌린다. 다른 편집이 끼어 그래프가 달라지면 스택이 비워진다.
- 두 노드를 함께 옮기면 그 사이 엣지의 경유점도 같은 변위만큼 옮겨진다(한쪽만 옮기면 제자리).
- 노드 방향 `auto`(4R.20): 방향 값으로 `auto`를 쓰면(노드·그래프·설정·힌트 중 처음 유효한 층) 포트별 지정이 없는 모든 포트의 면을 연결된 상대 노드 방향으로 정한다. 파생 값이라 저장하지 않고(저장되는 것은 `"auto"` 문자열뿐), 드롭·연결 변경 때만 갱신한다. `R` 순환은 방향 표 → 자동 → 상속.
- 같은 면 핸들 순서(4R.20): 위·아래 면(과 입출력이 섞인 좌·우 면)의 핸들은 연결 상대 노드의 가로(세로) 위치 순으로 늘어서 입출력 선이 서로 교차하지 않는다. 상대가 없는 포트는 제자리. layout이 없는 기본 구성은 그대로다.
- 다중 선택(4R.20): 연결선만 둘 이상 선택하면 `ctx.multiLayout`(= `<MultiLayoutPanel>` props)으로 일괄 [모양 ▾]·[경로 초기화](확인 단계), 노드만 둘 이상이면 [방향]을 준다. `onLayoutPanelsChange`에는 `panels.multi`로 온다. 한 번의 조작 = `onChange` 1회(reason `layout`).
- 연결선 우클릭 메뉴(4R.20): 우클릭 또는 선택 후 `Shift+F10`/ContextMenu 키. 모양(레지스트리 목록)·경로 편집·경로 초기화·삭제. 여러 연결선을 선택한 채 그중 하나를 열면 선택 전체에 적용하고 [경로 초기화]는 확인 단계를 거친다. 방향키·`Home`/`End`·`Esc`(닫으면 연결선으로 포커스 복귀).
- 패널: `renderConfigPanel`의 `ctx.nodeLayout` / `ctx.edgeLayout`을 `<NodeLayoutPanel>` / `<EdgeLayoutPanel>`로 그리거나, 앱이 자기 패널을 쓰면 `onLayoutPanelsChange(panels)`로 선택 항목의 값을 받아 그린다(값이 바뀔 때만 호출).
- `Graph.ui`는 `patchGraphUiLayout`이 `ui.layout`만 병합한다(viewport 등 다른 키 보존).

## 정리·자동 배치 (3R.26)

`layoutEngines`에 `LayoutEngineDescriptor`를 하나 이상 주면 캔버스 아래 툴바에 [정리 ▾](`L` 키)가 생기고 "엉킨 연결" 힌트 칩이 켜진다. 없으면 이 기능만 꺼진다.
엔진 목록·옵션(`OptionDecl`: enum/number/boolean)은 선언에서 그려지므로 새 엔진은 디스크립터 하나면 된다. 내장 어댑터 `createElkEngine()`은 elkjs를 처음 계산할 때만 동적으로 불러 Web Worker에서 돌린다.

- 팝오버: 배치 방향·범위(전체/선택한 노드)·엔진 옵션·연결선 모양(기본/종류별)·경로 다시 만들기·노드 방향 맞추기·배치에 쓸 연결 종류. [미리보기]는 반투명 윤곽만 그리고 `onChange`를 내지 않는다. [적용]은 노드 좌표(8px 격자) + 선택한 정리 + `Graph.ui.layout`(방향·모양) 기록을 **`onChange` 1회(reason `auto-layout`)** 로 낸다. 토스트 [되돌리기]와 `Ctrl+Z` 모두 한 번에 되돌린다(`ui.layout`도 함께 복원, `ui`의 다른 키는 현재 값 유지).
- 취소(`Esc`·[취소])는 워커를 종료하고 아무것도 바꾸지 않는다. 실패(엔진 로드·계산 오류·10초 초과)는 팝오버 안 오류 줄 + [다시 시도]. 마지막 사용 옵션은 `storage`(기본 `localStorage`)에만 기억하고 그래프 데이터는 건드리지 않는다.
- "연결선도 자동 경로로"(4R.20): 엔진 디스크립터가 `edgeShapeOption: { shapeId, default, title? }`를 선언하면 팝오버에 체크가 생긴다. 켜면 "기본 모양"이 그 모양이 되어 적용 때 `ui.layout.edge_shape`에 기록된다(방향만 바꿔 곡선이 노드를 가로지르는 일을 막는다). 처음 값은 선언의 `default`, 이후는 마지막 선택을 `storage`에 기억한다. `createElkEngine()`은 `auto`를 처음부터 권하며 `edgeShapeOption`으로 바꾸거나 `null`로 끈다. 엣지 자신의 `layout.shape`는 그대로 우선한다.
- [모든 연결선 경로 초기화]: 확인 뒤 경유점·꺾임·라벨 위치를 모두 지운다(모양은 유지, reason `layout`).
- 엉킨 연결: `detectEdgeTrouble`(순수)이 노드를 가로지르거나 핸들이 반대로 향한 엣지를 찾는다. 그래프를 연 뒤 800ms 안정되면 칩을 한 번 띄우고, 닫으면 그래프 id별로 기억한다. 데이터는 바꾸지 않는다.

```tsx
import { GraphEditor, createElkEngine } from "@agent-console/graph-editor";

const engines = [createElkEngine()]; // 컴포넌트 밖(또는 useMemo)에서 한 번만 만든다
<GraphEditor graph={graph} nodeTypes={nodeTypes} edgeTypes={edgeTypes} onChange={setGraph} layoutEngines={engines} />;
```

번들러 주의: 기본 워커는 `new Worker(new URL("elkjs/lib/elk-worker.min.js", import.meta.url))`이다(Vite가 `assets/elk-worker.min-<해시>.js`로 낸다). 다른 번들러면 `createElkEngine({ workerFactory })` 또는 `{ load }`로 ELK 인스턴스를 직접 준다.
PWA를 쓰는 앱은 elk 자산(약 1.4MB)을 사전 캐시에서 빼고 런타임 CacheFirst로 두는 것을 권한다(예: `apps/web/pwa-workbox.ts`).

## 연결선 모양·경로 (순수 로직)

`resolveEdgeShape`·`resolveDirection`·`resolvePortSide`가 화면 배치 값을 층 순서(엣지 > 그래프 > 사용자 설정 > 디스크립터 힌트 > 내장)로 정한다.
모르는 값은 건너뛰고 다음 층으로 간다. 모양은 `EdgeShapeDescriptor` 레지스트리(`createEdgeShapeRegistry`, 내장 5종 `BUILTIN_EDGE_SHAPES`)에 등록하며,
`buildEdgePath`가 면 바깥 법선 방향 간격(`ARROW_GAP`)을 적용해 모양의 `build`를 부른다. React Flow에 의존하지 않는다(명세: `docs/design/graph-edges.md`).

```ts
import { buildEdgePath, createEdgeShapeRegistry, resolveEdgeShape } from "@agent-console/graph-editor";

const shapes = createEdgeShapeRegistry();
const { value } = resolveEdgeShape({ edge: { shape: "step" }, isKnown: shapes.has });
const path = buildEdgePath({
  source: { x: 0, y: 0, side: "right" },
  target: { x: 200, y: 100, side: "left" },
  shape: shapes.get(value)!,
});
console.log(value, path.d.startsWith("M"));
```

### 자동 경로 라우터 (`shape: "auto"`, 3R.25)

`createAStarRouter(options?)`가 노드 사각형(패딩 16)을 피하는 직각 경로를 엣지 id 순으로 계산한다(`logic/route.ts`, 순수 함수, 의존 없음).
비용(직진 1·꺾임 +4·교차 +8)·패딩·격자·스텁·탐색 상한(확장 20,000회 / 엣지당 8ms)은 모두 `RouteOptions`로 주입한다.
상한을 넘기거나 경로가 없으면 경유점 없는 `smoothstep` 경로로 대체하고 `RoutedEdge.fallback`을 켠다(렌더 쪽은 `routeFallbackAttrs`로 `data-route-fallback="true"`를 붙인다).
엣지별 메모(장애물 + 엣지 입력 + 앞선 엣지 입력의 해시)가 있어 노드 하나를 옮길 때만 다시 계산한다. `EdgeRouter` 인터페이스로 다른 라우터로 교체할 수 있다.
탐색선은 부풀린 노드 경계와 끝점·경유점·중간선(격자 8px에 맞춤)이다. 8px 칸을 모두 확장하지 않아도 같은 최적 경로를 얻기 위한 선택이다.
라우터는 새 외부 의존이 없다(무엇을: 자체 A* / 왜: 면·스텁 규칙에 정확히 맞고 동기 순수 함수라 테스트가 쉬움 / 대안: `libavoid-js`(LGPL), ELK 엣지 라우팅 — `docs/design/graph-edges.md` §4.4).

```ts
import { createAStarRouter } from "@agent-console/graph-editor";

const a = { id: "a", x: 0, y: 0, width: 160, height: 64 };
const b = { id: "b", x: 400, y: 0, width: 160, height: 64 };
const router = createAStarRouter();
const routed = router.route(
  [{ id: "e1", source: { x: 160, y: 32, side: "right" }, target: { x: 400, y: 32, side: "left" }, sourceNodeId: "a", targetNodeId: "b" }],
  [a, b],
);
console.log(routed.get("e1")?.fallback, routed.get("e1")?.path.d.startsWith("M"));
```

#### 캔버스 연결 (3R.27)

모양에 `route`가 있는 엣지(내장 `auto`)는 `GraphEditor`가 라우터로 그린다. 라우터는 **편집기 인스턴스당 하나**(`edgeRouter` prop으로 직접 주거나, 처음 필요할 때 `createAStarRouter()`를 만든다. 작업 메모리가 크므로 한 화면에 캔버스를 여럿 띄우면 같은 라우터를 나눠 줄 수 있다).
보이는 자동 경로 엣지를 **한 번의 `route()`** 로 계산하고(교차 비용이 앞선 엣지에 의존), 끝점은 React Flow가 측정한 핸들 상자에서 읽는다. 노드를 끄는 동안은 50ms 스로틀, 폴백 엣지에는 `data-route-fallback="true"`.
`troubleOfModel`의 `selfAvoiding`은 라우터가 그리는(폴백이 아닌) 엣지이고, [정리] 미리보기 중심선도 같은 라우터 경로다. `layout`이 없는 엣지는 기본 곡선 그대로라 라우터를 만들지 않는다.
자동 경로의 장애물 크기(4R.20)는 실제로 그려진 카드(`offsetWidth/Height`) → React Flow 측정값 → 추정값 순으로 쓴다(`actualNodeSize`). 실행 상세의 카드는 상태·요약 줄 때문에 편집기의 추정보다 커서 추정값을 쓰면 경로가 카드 가장자리를 스쳤다.
`mode="readonly-run"`에는 [연결선 ▾](`viewOverrides`, 기본 자동 경로·곡선)가 있다. 브라우저 로컬 상태일 뿐 `onChange`를 내지 않고, 임시 보기에서는 저장된 경유점·꺾임·라벨 위치를 쓰지 않는다.

## 독립 위임·반복·조건·중첩 팀 (5R.16)
연결 종류·노드 종류의 **이름은 코드에 없다**. 아래는 모두 디스크립터 속성(`cycle`·`handles_failure`·`invocation`·`scheduling`·`binds`·`ui_hints`)과 앱이 넘기는 데이터로만 동작한다(`test/noHardcoding.test.ts`).

| 기능 | 어떻게 |
| --- | --- |
| `resolveEdgeStyle(edgeType, strategies, hints?)` | 순수. 색·`stroke-dasharray`(토큰 `--ac-edge-pattern-N` 참조)·아이콘·기본 모양을 정한다. 순위: `ui_hints` → 속성 기본값(실패 처리 > 반복 > 위임, 처음 맞는 하나) → 내장. 위임 패턴은 방식 id 정렬 순서 % 4 |
| `loopRegion(graph, edgeTypes, edgeId)` | 순수. 사이클 연결의 반복 영역 노드 id. 서버 `loop_regions`와 같은 정의(흐름 연결만, **모든** 사이클 연결을 경로에서 뺌, 자기 반복은 그 노드 하나) |
| `closesFlowLoop(graph, newEdge, edgeTypes)` | 순수. 새 연결이 흐름 순환을 닫는가(`scheduling = flow`만 검사) |
| 연결 만들기 | 순환을 닫으면 `cycle`이 있는 종류가 기본 선택이고 나머지 흐름 종류는 비활성 행(사유 포함). 반복 후보가 없으면 `onConnectRejected` reason `cycle`. `EdgeKindDialog`의 `info` prop(`disabledReason`·`preferred`·`iconName`)과 순수 `planConnection` |
| 연결 칩 | `edgeExtraChips`(앱이 계산한 조건 요약·회차 한도·방식 칩), 선언형 칩과 합쳐 4개까지 + `+N`, 접근성 이름 포함. `edgeBadges`는 실행 상세 배지. 줌 < 0.6이면 아이콘만. 아이콘 이름은 `renderIcon`이 그리고, 못 그리면 짧은 문자·제목 첫 글자 |
| 반복 영역 강조 | 사이클 연결 하나를 선택하면 영역 노드에 윤곽(`--ac-loop-region`)과 aria-live 안내(읽기 전용에서도) |
| 정의 바인딩 카드 | `bindSummaries`(부제·본문 한 줄·배지·`missing`·`open`). 노드 `Alt+Enter`와 [열기 ↗]. 편집기는 config 키를 읽지 않는다 |
| `ui_hints.shape: "stacked"` | 겹친 카드(뒤 두 장). 모르는 값은 일반 카드. 자동 경로 장애물 +8px |
| `nodeRunBadges` | 실행 상세 회차·호출 배지(`#3`, `×4`). `picked`·`onClick` |
| 팔레트 | `DefinitionItem.meta`(부제)·`disabledReason`(비활성: 추가·끌기 무시). 항목 순서는 앱이 준 그대로(이름순 정렬은 앱 몫) |
| 자동 정리(ELK) | 디스크립터 `cycle` 연결은 되돌아가는 연결(`LayoutEdgeInput.back`)로 다룬다. 노드를 되돌림 제외 위상 순서로 주고 `cycleBreaking`(엔진 옵션, 기본 `MODEL_ORDER`)을 쓴다. 도착 노드가 출발 노드보다 앞 층이 아니면 그 연결을 빼고 다시 계산 |
| 연결 종류 바꾸기 | 연결 하나를 선택하고 `T` → 새 연결 만들기와 같은 `EdgeKindDialog`(현재 종류 미리 선택, 순환을 닫는 흐름 종류는 비활성). 확정하면 `onChange` reason `edit-edge`로 종류만 바뀌고 이전 종류의 `config`는 비워진다 |
| 새 노드 화면 이동 | 위치를 정하지 않은 추가(팔레트)는 새 노드가 뷰포트 밖이면 그 노드로 화면을 옮긴다(움직임 줄이기면 즉시) |

layout 값이 없는 그래프의 렌더·`onChange` 결과는 이전과 같다(새 props를 안 주면 DOM도 같다).

