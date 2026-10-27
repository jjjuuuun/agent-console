# @agent-console/ui

디자인 토큰(`tokens.css`)과 도메인을 모르는 기본 컴포넌트. 노드 타입·그래프·API를 모른다.
다른 TS 패키지를 import하지 않는다(react는 peer). graph-editor·schema-form은 이 패키지에 의존하지 않고
**`--ac-*` CSS 변수, 유틸 클래스 이름, `data-status` 규칙**만 약속으로 쓴다.

## 최소 사용
이 블록은 `test/readme.test.ts`와 같고, 테스트가 실제로 실행한다(`pnpm pkg-lint`가 일치를 검사).

```ts readme
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Button, formatBadgeCount } from "@agent-console/ui";

const html = renderToStaticMarkup(createElement(Button, null, "저장"));
const badge = formatBadgeCount(120);
```

## 설치 / import
저장소 안에서는 `pnpm install`이 연결한다. 저장소 밖에서는 tarball(`pnpm pack:all` → `dist/npm`)을 설치한다: `npm install ./agent-console-<이름>-<버전>.tgz` (react 19 필요)

앱이 진입점에서 **한 번만**, 다른 패키지 `styles.css`보다 **먼저** 불러온다.
```ts
import "@agent-console/ui/tokens.css";
import "@agent-console/graph-editor/styles.css";
```

## tokens.css 구성
- 색: 기본은 시스템(`data-theme` 속성이 없으면 `prefers-color-scheme`; 라이트 선호가 아니면 다크 값 `:root`), `[data-theme="dark|light"]`로 고정. `--ac-bg`, `--ac-surface-1..3`, `--ac-text*`, `--ac-accent*`, 의미색(`--ac-danger/warning/success/info` + `-bg`), 분류색 `--ac-cat-1..8`·`--ac-cat-neutral`, 엣지·캔버스, 상태색 `--ac-status-<state>`(+`-bg`).
- 타입: `--ac-font-sans`(Pretendard → Noto Sans KR → Malgun Gothic → Apple SD Gothic Neo → system-ui), `--ac-font-mono`, `--ac-text-xs..xl/code`(12px 이상), `--ac-lh-*`.
- 간격 `--ac-space-0..7`, 반경 `--ac-radius-*`, 컨트롤 높이, 레이아웃 상수, z-index, 모션, 그림자.
- 유틸: `.ac-text`, `.ac-ellipsis`, `.ac-clamp-2/3`, `.ac-mono-wrap`, `.ac-pre`, `.ac-num`, `.ac-sr-only`.
- 상태: `[data-status="pending|queued|running|succeeded|failed|skipped|waiting|cancelled"]`가 색·테두리 패턴·아이콘 마스크를 CSS 변수로 준다. Run 상태는 `data-status-kind="run"`에서 `completed|paused|interrupted`가 추가된다. 그 외 값은 점선 + 물음표 폴백. 아이콘은 인라인 SVG data URI(외부 파일 없음). reduced-motion이면 정지.

## 상태 표시 규칙
요소에 `data-status="<서버 상태 문자열>"`만 달고, 그 안에 빈 `<span class="ac-status-icon">`을 두면 아이콘이 나온다. 박스(노드 카드 등)에 테두리 패턴·헤더 tint까지 주려면 아래 범용 훅 클래스를 단다. 한글 라벨은 JS 표 없이 호출자가 `messages`로 넘긴다.

### 범용 훅 클래스
| 클래스 | 붙이는 곳 | 효과 |
| --- | --- | --- |
| `ac-status-box` | `data-status`를 가진 박스 | 상태별 테두리 색·패턴·두께, skipped 빗금·흐림, waiting 바깥 링 |
| `ac-status-header` | 박스의 직계 헤더 | 상태 tint, running 진행 막대 |
| `ac-status-keep` | skipped 박스의 직계 자식 중 흐리게 하지 않을 것(분류색 막대 등) | 불투명도 .7 제외 |
| `ac-status-icon` | 빈 `<span>` (가장 가까운 `data-status` 조상 것을 사용) | 상태 아이콘(마스크), running 회전, waiting 깜박임 |

## 사용 예
```tsx
import { Button, IconButton, StatusChip, StatusIcon, Banner, ThemeProvider } from "@agent-console/ui";

<ThemeProvider theme={theme} onThemeChange={setTheme /* 저장은 앱 */}>
  <StatusChip status="running" label="실행 중" />
  <StatusChip status="interrupted" kind="run" label="중단됨" />
  <StatusChip status="나중에-생긴-상태" />{/* 라벨 생략 시 원문, 스타일은 폴백 */}
  <Button variant="primary" loading={saving} onClick={save}>저장</Button>
  <IconButton label="삭제" icon={<TrashSvg />} />
  <Banner tone="danger" title="저장 실패">버전이 충돌했습니다.</Banner>
</ThemeProvider>
```

## 공개 API
- 기본: `Button`, `IconButton`, `Spinner`, `StatusIcon`, `StatusChip`, `Badge`, `Tag`, `Banner`, `ThemeProvider`/`useTheme`.
- v2(1R.18, 모두 제어형·문구는 props): `Sidebar`(`items`·`activeId`·`onNavigate`·`collapsed`·`messages`, 방향키 roving, 배지 `99+`; `groups` + 항목 `group`으로 묶음 제목·접힘 구분선, 항목이 없는 묶음은 안 그림(`groupSidebarItems`); `position:'bottom'` 항목과 `tools` 슬롯은 하단 도구줄에 아이콘으로, 접기 버튼은 도구줄 오른쪽 끝(`messages.toggle` = 고정 이름 + `aria-expanded`)), `Dialog`/`ConfirmDialog`(포커스 가둠·Esc·배경 inert·포커스 복귀, `danger`는 취소 기본 포커스), `ToastProvider`/`useToast`(오류 assertive, 액션 버튼 1개, `regionLabel`), `Tabs`(`←→ Home End`, `lazy`, 제어/비제어), `ProvenanceBadge`(색 슬롯 = `layer.index mod 6`, 텍스트 라벨 필수), `Gauge`(값 없음 상태, `role=meter`는 값이 있을 때만), `EmptyState`(`steps`, `secondaryAction`).
- `Drawer({open,title,onClose,closeLabel,description?,actions?,width?=560,initialFocus?,testId?})`(5.2R.20): 오른쪽 모달 서랍. 머리(제목·닫기) / 스크롤 본문 / 하단 고정 `actions` 3행, Esc·Tab 순환·배경 inert·포커스 복귀(`Dialog`와 같은 모달 훅). 제어형이라 닫아도 호출자의 편집 상태는 그대로다. 문구는 모두 props.
- 모달 훅(5R.21): `useModalBackdrop(open, backdropRef, { inert? })`(배경 inert + 포커스 복귀, `inert:false`는 비모달 패널), `trapTabKey(event, root)`(`Tab` 순환), `FOCUSABLE_SELECTOR`. `Dialog`와 앱의 드로어가 같이 쓴다.
- 1R.32(제어형·문구는 props, 종류 이름 없음):
  - `PageHeader`(`title`, `breadcrumb`, `status`, `actions`; 제목 h1, 마지막 breadcrumb = `aria-current`).
  - `CommandPalette`(`open`, `onClose`, `groups: {id,title,items:{id,label,hint?,icon?,badge?,shortcut?,disabled?,run}[]}[]`, `query`, `onQueryChange`, `loading`, `messages`). `role=combobox`+`listbox`, `↑↓` 순환(비활성 건너뜀), `Enter` 실행, `Esc` 닫기, **한글 IME 조합 중 Enter·방향키 무시**, 열면 배경 inert·닫으면 포커스 복귀. 필터는 호출자 몫이며 `filterCommandGroups(groups, query, maxPerGroup?)` 헬퍼 제공. 항목 `run`은 팔레트가 닫은 뒤 호출한다.
  - 단축키: `useKeyCombo(combo, handler, {platform})`, `matchKeyCombo`, `parseKeyCombo`, `formatKeyCombo`. 조합 문자열(`"Mod+K"`, `"Alt+J"`)은 **데이터**(웹 기본 표 + 사용자 설정 `ui.keybindings` 덮어쓰기)로 받는다. 수식키 일치는 정확 일치, IME 조합 중 무시. 전역 단축키 처리기는 아래 1R.33.
  - `ListPane<T>`(`items`, `getItemId?`, `selectedId`, `onSelect`, `renderItem`, `rowHeight?`, `loading/error/empty` 슬롯(오류 > 로딩 > 빈), `searchValue/onSearchChange`, `toolbar`, `messages`). `role=listbox`, `↑↓ Home End` 포커스 이동, `Enter/Space`/클릭 선택, 검색창 `↓`로 목록 진입.
  - `ListPane`의 `groups`(`ListPaneGroup[]`: key·label·title·count·depth·collapsed·items)와 `onToggleGroup(key, collapsed)`: 묶음 머리(`GroupHeader`, sticky·`aria-expanded`)와 `role=group` 항목. 머리도 `↑↓` 이동 대상, 머리에서 `←` 접기 `→` 펴기 `Enter/Space` 토글. 하위 묶음 숨김·계산은 호출자(예: `@agent-console/list-arrange`)가 한다. `ListViewMenu`: 묶는 기준·정렬 선택지를 `ListViewOption[]`로 받는 "보기" 메뉴(`menuitemradio`, 선택해도 열린 채, `open/onOpenChange`로 `G` 단축키 연결, 모두 접기/펼치기).
  - `AttachmentList`(`groups: {layer,items:Attachment[],editable}[]`, `modeOptions`(데이터), `renderRow`, `onReorder(layerId, orderedKeys)`, `onRemove`, `onModeChange`, `onAdd`, `messages`). 순서 변경은 위/아래 버튼(키보드 가능), 편집 불가 층은 읽기 전용.
  - `Disclosure`(`<details>` 기반, 제어/비제어, 요약 Enter/Space).
  - `FileTree`(2R.15; `items: {path, trailing?, leading?}[]`, `view` tree/flat, `selected`, `onSelect`). `role=tree`, `↑↓ ←→ Home End Enter`, 폴더는 경로에서 만든다(도메인 무관).
  - `TrustBadge`(`trust: string` 열린 값, `label`). 스타일이 아는 등급은 색·아이콘·테두리 모양이 달라지고, 모르는 값은 중립 배지 + 원문(코드에 등급 목록 없음, CSS `[data-trust]`만).
  - 아이콘: `iconRegistry`(앱 고정 이름 `defaultIcons`: entry/exit/ask/override/inherit/lock/external-link/copy/eye/eye-off), `createIconRegistry`, `registerIcons(icons, base?)`(불변, 새 레지스트리 반환), `IconRegistryProvider`(`registry`/`icons`, 중첩 시 상위에 더함), `Icon({name,size,label,fallbackText})`. 모르는 이름은 `fallbackText` 첫 글자 아바타.

- 5.2R.13 넘침 방지·아이콘 버튼 기반(ux-overhaul §3·§4, 모두 제어형·문구는 props·`min-width:0`+말줄임+툴팁):
  - `Dialog({open,title,onClose,children,actions?,size?: "sm"|"md"|"lg"|"xl",initialFocus?})`: 제목 / **스크롤 본문** / **하단 고정 `actions`** 3행 그리드(최대 높이 `--ac-dialog-max-h`, 폭 `--ac-dialog-w-*` 이하 94vw, 폭 < 480이면 버튼이 전체 폭 세로 쌓기). 버튼은 반드시 `actions`에 둔다(본문 안 버튼 줄 금지: 대시보드 템플릿 다이얼로그가 깨진 원인은 `actions` 없이 본문 안에 버튼 줄을 그려 `overflow:auto` 안에 잘렸기 때문). 본문의 `fieldset`은 테두리 없음, 라디오·체크 한 줄은 `<label class="ac-choice"><input/><span>라벨</span></label>`. `wide`는 `size="lg"` 별칭(사용 중단).
  - `Tabs`(+`moreLabel?`, `TabItem.title?`): 한 줄, 폭 `[--ac-tab-min-w, --ac-tab-max-w]`, 넘치면 오른쪽 "더 보기 ▾" 메뉴. **활성 탭은 항상 보임**, 키보드 ←→는 숨은 탭까지 이동하고 승격.
  - `ChipRow({chips: {id,label,title?,icon?,tone?,active?,onSelect?}[], ariaLabel, moreLabel?(n)})`: 한 줄, 칩 최대 `--ac-chip-max-w`, 넘치면 `+N` 버튼과 팝오버. `active` 칩은 항상 보임.
  - `MiddleEllipsis({value, head?, tail?, copyLabel?})` / `middleEllipsis(value, head=8, tail=4)`: 긴 id·해시를 `abcdefgh…wxyz`로 줄이고 전체 값은 툴팁. `copyLabel`을 주면 복사 버튼.
  - `ActionButton({icon?: 레지스트리 이름, label, shortcut?, display?: "icon"|"icon-label"|"label", variant?, size?, loading?, pressed?, platform?, ...button})`: `label` = `aria-label` = 툴팁(+`Ctrl+…`), 로딩이면 스피너·`aria-busy`. `ActionDef = {id, icon?, label, shortcut?}`가 화면 설정 표의 한 줄 모양이다.
  - `Tooltip({content, placement?, align?})`(CSS 전용, 호버 400ms/포커스 즉시, 장식이라 `aria-hidden`), `Popover({open,onOpenChange,renderTrigger,panelRole,panelLabel,align})`(비모달, Esc·바깥 클릭, 포털 없음), `Menu({items: MenuItemDef[], onClose})`(`role=menu`, `↑↓ Home End`).
  - `PageHeader`(+`secondaryActions: MenuItemDef[]`, `moreLabel?`): 제목 최대 `--ac-header-title-max` + 말줄임 + 툴팁. 헤더(컨테이너) 폭 < 640이면 보조 액션이 `more` 메뉴로 접힌다(컨테이너 쿼리, 뷰포트 아님).
  - 훅·순수 함수: `useOverflowFit`, `computeVisible(widths,gap,available,moreWidth,priority)`.
  - 아이콘 추가: `refresh close more plus undo check trash send stop panel-left-close panel-left-open filter columns table chevron-left/right/down expand play pencil pin`. 앱이 같은 이름을 등록하면 앱 것이 이긴다.
  - 기본 라벨(`moreLabel` "더 보기" 등)은 한국어 기본값이다. 다른 언어는 props로 넘긴다.
  - ESLint: `@agent-console/eslint-config/react`의 `agent-console/button-name`이 아이콘만 있는 `<button>`을 막는다.

- 1R.33 단축키 관리(components.md 9.5, 도메인 무관 — 동작 id·핸들러·제목 키는 데이터):
  - `ShortcutProvider({defaults: ShortcutDef[], overrides?: Record<id, keys>, platform?, enabled?, onWarn?, target?})`, `ShortcutDef = {id, scope, keys, titleKey, modifierRequired?, run}`.
  - `useShortcuts(defs)`(화면이 등록/해제, 같은 id면 화면 정의가 이김, 최신 핸들러 호출), `useEffectiveShortcuts()`(도움말·설정 표, 변경 시 갱신), `useShortcutRegistry().getEffectiveKeys()` → `{id, scope, titleKey, keys, isDefault, conflict?}[]`, 순수 함수 `computeEffectiveKeys`.
  - 키 표기: `"Mod+K"`, `"?"`, 시퀀스는 공백(`"g c"`). `overrides`의 빈 문자열 = 비활성.
  - 규칙: 수식키(Ctrl/Meta/Alt) 없는 한 글자 키는 input·textarea·select·contenteditable·`[data-ac-editable]` 안에서 동작 안 함(수식키 조합은 동작). 시퀀스는 두 번째 키 1초 안(아니면, 또는 다른 키면 취소). IME 조합 중 무시. 같은 범위(global은 모든 범위와 겹침)의 중복 키는 `conflict`로 표시하고 `onWarn`(기본 console.warn, `null`이면 끔)으로 경고.
  - Esc 레이어 스택은 이 패키지가 아니라 앱(1R.22) 몫이다.

```tsx
<Sidebar items={routes} activeId={active} onNavigate={go} collapsed={c} onCollapsedChange={setC}
  messages={{ navLabel: "주 메뉴", collapse: "접기", expand: "펼치기" }} />
<Gauge value={usage /* 없으면 undefined */} label="5시간 창" noValueLabel="사용률 정보 없음" />
<ProvenanceBadge layer={{ id, label, index }} variant="set" />
```

## 의존성 (무엇을 / 왜 / 대안)
추가된 런타임 의존성 없음(react peer만). 아이콘은 호출자가 ReactNode로 넘기고, 다이얼로그/토스트도 자체 구현(작고 도메인 무관). 대안: Radix UI/React Aria(포커스·접근성 보장이 필요해지면 어댑터 뒤에서 교체).

## 테스트
`pnpm test` (패키지 폴더 또는 루트, Vitest). `tokens.test.ts`는 tokens.css를 텍스트로 파싱해 다른 패키지가 읽는 모든 `--ac-*` 변수·유틸 클래스·상태 8종 규칙이 정의돼 있는지 검사한다. 다른 패키지를 단독 테스트할 때는 테스트 설정에서 `tokens.css`를 함께 로드한다.
