import type { CSSProperties, ReactNode, Ref } from "react";
import type { DelegationStrategyDescriptor, EdgeSpec, Issue, IssueSuggestion, EdgeTypeDescriptor, Graph, NodeSpec, NodeTypeDescriptor, PortSpec } from "@agent-console/contracts";
import type { GraphEditorMessages } from "./messages";
import type { PortView } from "./logic/ports";
import type { DirectionSides } from "./logic/layout";
import type { EdgeShapeDescriptor } from "./shapes/types";
import type { LayoutEngineDescriptor } from "./layout/types";
import type { EdgeRouter } from "./logic/route";
import type { KeyValueStorage } from "./logic/storage";
import type { RoleToggle, ToggleInfo, ToggleOptions } from "./logic/team";
import type { EdgeLayoutPanelProps } from "./components/EdgeLayoutPanel";
import type { NodeLayoutPanelProps } from "./components/NodeLayoutPanel";
import type { MultiLayoutPanelProps } from "./components/MultiLayoutPanel";

export type { PortView } from "./logic/ports";

/** 노드 상태 오버레이. `status`는 서버 상태 문자열 그대로(모르는 값도 허용). */
export interface NodeStateView {
  status: string;
  attempt?: number;
  iteration?: number;
  /** 한 줄 요약 예: "1.2초 · 340 토큰" */
  summary?: string;
  errorSummary?: string;
}

export type ChangeReason =
  | "add-node"
  /** 첫 실행 노드를 놓으면서 입구·답변 연결을 함께 만들었다(`autoConnectIo`) */
  | "auto-connect"
  | "remove"
  | "connect"
  | "move"
  | "duplicate"
  | "edit-label"
  | "edit-config"
  | "edit-edge"
  | "role-toggle"
  | "apply-suggestion"
  | "layout"
  | "auto-layout"
  | "undo";

export interface ChangeMeta {
  reason: ChangeReason;
  /** 변경 직전 그래프(삭제 되돌리기 등에 사용) */
  previous: Graph;
}

export interface Selection {
  nodeIds: string[];
  edgeIds: string[];
}

export interface ConfigPanelContext {
  node?: NodeSpec;
  edge?: EdgeSpec;
  descriptor?: NodeTypeDescriptor;
  ports?: PortSpec;
  /** 선택된 항목 수(2 이상이면 다중 선택) */
  multi: number;
  onChangeNode: (patch: Partial<NodeSpec>) => void;
  onChangeEdge: (patch: Partial<EdgeSpec>) => void;
  close: () => void;
  /** 선택 노드의 입구/답변/묻기 토글 상태(노드 1개 선택일 때). 키 = 스케줄링·interaction 어휘 */
  roleToggles?: Record<RoleToggle, ToggleInfo>;
  /** 입구/답변/묻기 켜기·끄기. 엣지를 만들거나 지우고 `onChange`(reason `role-toggle`)로 내보낸다 */
  onToggleRole?: (toggle: RoleToggle, on: boolean, options?: ToggleOptions) => void;
  /** 선택 노드가 리소스를 받을 수 있는가(리소스 탭 표시 여부) */
  canHaveResources?: boolean;
  /** 선택 엣지 1개일 때: "모양·경로" 섹션. `<EdgeLayoutPanel {...ctx.edgeLayout} />`로 그대로 그린다(변경은 reason `layout`으로 나간다) */
  edgeLayout?: EdgeLayoutPanelProps;
  /** 선택 노드 1개일 때: [배치] 탭. `<NodeLayoutPanel {...ctx.nodeLayout} />`로 그대로 그린다(변경은 reason `layout`으로 나간다) */
  nodeLayout?: NodeLayoutPanelProps;
  /** 연결선만 또는 노드만 둘 이상 선택했을 때: 일괄 [모양 ▾]·[경로 초기화] / [방향]. `<MultiLayoutPanel {...ctx.multiLayout} />`로 그대로 그린다 */
  multiLayout?: MultiLayoutPanelProps;
}

/** 선택 항목 1개의 배치 패널 값. 앱이 자기 패널 안에 `NodeLayoutPanel`·`EdgeLayoutPanel`을 그릴 때 쓴다. */
export interface LayoutPanels {
  node?: { nodeId: string; props: NodeLayoutPanelProps };
  edge?: { edgeId: string; props: EdgeLayoutPanelProps };
  /** 연결선만 또는 노드만 둘 이상 선택(`edgeIds`·`nodeIds` 중 한쪽만 채워진다) */
  multi?: { edgeIds: string[]; nodeIds: string[]; props: MultiLayoutPanelProps };
}

/** 팔레트 "정의에서 만드는 노드" 구역의 항목 하나(정의 하나). 키는 노드 타입 `binds.kind`. */
export interface DefinitionItem {
  id: string;
  name: string;
  description?: string;
  /** 1~2자 아바타 텍스트(없으면 이름 첫 글자) */
  iconName?: string;
  /** 구역/소그룹 제목에 쓸 표시 이름(같은 kind의 첫 항목 값을 씀) */
  groupLabel?: string;
  usageCount?: number;
  /** 부제 한 줄(예: "노드 5개 · 입구 있음"). 없으면 설명 */
  meta?: string;
  /** 있으면 항목을 비활성(`aria-disabled`)으로 두고 추가 동작을 무시한다. 툴팁·안내에 이 문구를 쓴다 */
  disabledReason?: string;
}

/** 팔레트·`onAdd`가 돌려주는 추가 요청. */
export interface PaletteAddSpec {
  typeId: string;
  definition?: { id: string; name: string };
}

/**
 * 칩 하나(팀 공용 칸, 연결 라벨 옆 추가 칩, 정의 카드 배지가 함께 쓴다).
 * 색만으로 의미를 전달하지 않는다: `tone`은 보조이고 의미는 글자·아이콘이 가진다.
 */
export interface ChipView {
  key: string;
  title: string;
  iconText?: string;
  /** 예: "대체", "제외" */
  modeText?: string;
  /** 칩 전문(접근성 이름·툴팁). `title`이 줄여 쓴 문구일 때 전체를 담는다 */
  fullTitle?: string;
  /** 아이콘 이름. `renderIcon`이 그리고, 못 그리면 `iconText`나 제목 첫 글자 */
  iconName?: string;
  tone?: "neutral" | "info" | "warning" | "danger";
  /** 점선 테두리(상속된 값 등) */
  dashed?: boolean;
  /** 있으면 칩이 단추가 된다(클릭·Enter·Space). 연결 위 칩이면 누르는 쪽이 연결을 고르고 해당 필드로 포커스를 옮기는 일을 앱이 한다 */
  onActivate?: () => void;
}

/** 노드 카드 아바타 지정(앱이 에이전트 정의에서 해석해 넘긴다). 둘 다 선택이며 없으면 노드 타입 힌트로 돌아간다. */
export interface NodeAvatar {
  /** 1~2자(또는 이모지) */
  text?: string;
  /** CSS 색 값(분류색 변수 참조 포함) */
  color?: string;
}

/** 정의를 바인딩한 노드 카드의 요약(앱이 정의 목록·메타에서 만든다). 에디터는 config 키를 읽지 않는다. */
export interface BindSummary {
  /** 바인딩한 정의의 이름(접근성 이름용) */
  title: string;
  /** 노드 타입 제목 줄을 대신하는 부제(예: 정의 종류 표시 이름) */
  subtitle?: string;
  /** 본문 한 줄(예: "노드 5개") */
  meta?: string;
  badges?: readonly ChipView[];
  /** 정의를 찾을 수 없음: 카드 테두리를 위험 점선으로 */
  missing?: boolean;
  /** 있으면 카드 하단 [열기 ↗] 단추와 노드 `Alt+Enter`가 이 동작을 부른다 */
  open?: { label: string; onOpen(): void; disabledReason?: string };
}

/** 실행 상세용 노드 회차·호출 배지(`#3`, `×4`). 1개뿐인 노드에는 앱이 넘기지 않는다. */
export interface NodeRunBadge {
  text: string;
  ariaLabel: string;
  /** 사용자가 고른 실행을 가리킴(테두리) */
  picked?: boolean;
  onClick?(): void;
}

/** 실행 상세용 연결 배지(`↻×2`, 한도 도달). */
export interface EdgeBadge {
  text: string;
  ariaLabel: string;
  tone?: "neutral" | "info" | "warning" | "danger";
}

export interface TeamSharedProps {
  items: readonly ChipView[];
  onAdd?: () => void;
  onRemove?: (key: string) => void;
  onSelect?: (key: string) => void;
  inheritedCount?: number;
  onOpenInherited?: () => void;
}

export interface ConnectRejection {
  reason: "no-kind" | "cycle" | "self" | "duplicate" | "port";
  sourceRole?: string;
  targetRole?: string;
}

/** `ref`로 얻는 명령형 API(앱의 노드 패널·이슈 패널이 사용). */
export interface GraphEditorHandle {
  getRoleToggleInfo(nodeId: string): Record<RoleToggle, ToggleInfo>;
  toggleRole(nodeId: string, toggle: RoleToggle, on: boolean, options?: ToggleOptions): boolean;
  applySuggestion(issue: Issue, suggestion: IssueSuggestion): boolean;
  canHaveResources(nodeId: string): boolean;
  /**
   * 노드 타입 하나를 추가한다(정의에 묶는 타입이면 `definition`). 팔레트 [추가]와 달리 위치는 **캔버스 보이는 영역 중앙**이고
   * 겹치면 격자 단위로 밀린다. 선택·입구/답변 자동 연결·`onChange`(reason `add-node` 또는 `auto-connect`)는 팔레트 추가와 같다.
   * @returns 새 노드 id(타입을 못 찾거나 읽기 전용이면 undefined)
   */
  addNodeAtCenter(typeId: string, definition?: { id: string; name: string }): string | undefined;
}

export interface PaletteStatus {
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
  /** 정의가 하나도 없는 구역의 [만들기] 버튼 콜백(인자 = `binds.kind`). 없으면 버튼 없음 */
  onCreateDefinition?: (kind: string) => void;
}

/** 보기 전용 덮어쓰기 선택지: 연결선 모양 id와 표시 문구 */
export interface ViewOverride {
  shapeId: string;
  /** 목록 항목 문구. 예 "자동 경로로 보기" */
  label: string;
  /** "임시 보기: {short}" 칩에 쓰는 짧은 이름 */
  short: string;
}

export interface GraphEditorProps {
  /** 제어형 그래프. 모르는 필드는 onChange에서 그대로 통과한다 */
  graph: Graph;
  nodeTypes: readonly NodeTypeDescriptor[];
  edgeTypes: readonly EdgeTypeDescriptor[];
  /** 키 = 노드 id */
  nodeStates?: Readonly<Record<string, NodeStateView>>;
  /** 키 = 엣지 id. 값: 'traversed' | 'dead' | 그 외 문자열 */
  edgeStates?: Readonly<Record<string, string>>;
  /** 동적 포트 계산(앱이 서버 API로 연결). 300ms 디바운스·캐시·마지막 응답 채택은 패키지가 책임 */
  resolvePorts?: (typeId: string, config: unknown) => Promise<PortSpec>;
  /** 모든 편집의 단일 출구. 드래그 이동은 드롭 시점에 한 번 */
  onChange?: (next: Graph, meta: ChangeMeta) => void;
  /**
   * 선택 항목 하나의 배치 패널 값을 알린다(선택이 없거나 둘 이상이면 `null`). 앱이 `renderConfigPanel` 대신
   * 자기 패널 안에 `NodeLayoutPanel`·`EdgeLayoutPanel`을 그릴 때 쓴다. 값의 변경은 편집기를 거쳐 `onChange`(reason `layout`)로 나가고
   * 레이아웃 되돌리기 스택(`Ctrl+Z`)에 쌓인다. 값이 바뀔 때만 호출한다.
   */
  onLayoutPanelsChange?: (panels: LayoutPanels | null) => void;
  /** 우측 설정 패널 슬롯(선택이 있을 때만 표시) */
  renderConfigPanel?: (ctx: ConfigPanelContext) => ReactNode;
  /** 검증 이슈(계약 Issue 그대로). 노드 배지(✕/▲+개수)와 엣지 무효 스타일만 담당. 이슈 패널(목록·행 클릭)은 앱 책임 */
  issues?: readonly Issue[];
  /** token이 바뀔 때마다 nodeId 노드를 선택하고 화면에 맞춘다(이슈 행 클릭 이동 등). 같은 노드를 다시 눌러도 token만 바꾸면 다시 동작 */
  focusRequest?: { nodeId: string; token: number | string; /** 있으면 노드 대신 이 연결을 선택하고 양 끝 노드를 화면에 맞춘다(없는 연결이면 `nodeId` 노드) */ edgeId?: string };
  readOnly?: boolean;
  showPalette?: boolean;
  /**
   * 팔레트를 캔버스 위 오버레이로 그린다(폭이 좁을 때). true면 `paletteOpen`일 때만 보이고, 캔버스 폭을 차지하지 않는다.
   */
  paletteOverlay?: boolean;
  /** `paletteOverlay`일 때 열림 여부(제어형) */
  paletteOpen?: boolean;
  /** 오버레이 팔레트에서 Esc를 눌렀을 때 */
  onPaletteClose?: () => void;
  showMinimap?: boolean;
  /** 주면 우하단에 미니맵 켜기/끄기 아이콘 버튼을 그린다(제어형: 값은 `showMinimap`). 기본 미니맵은 작게(140x96) 그린다 */
  onShowMinimapChange?: (show: boolean) => void;
  /** 캔버스 좌상단 도구줄 슬롯(앱의 [+ 추가] 같은 단추). 선택 도구줄(역할 토글·삭제)보다 앞에 놓인다 */
  canvasActions?: ReactNode;
  /** 격자 스냅(px). false면 끔. 기본 8 */
  snapToGrid?: number | false;
  idFactory?: (prefix: string, existingIds: Set<string>) => string;
  /** 새 연결의 기본 엣지 종류. 연결 가능한 후보 중 이 종류가 미리 선택된다(없으면 첫 후보). 후보가 하나면 선택 UI 없이 바로 연결 */
  defaultEdgeKind?: string;
  /**
   * 첫 실행 노드를 놓을 때 입구·답변 연결을 자동으로 만든다(`planAutoConnect` 조건을 만족할 때만). 기본 꺼짐: 앱이 설정
   * (`editor.auto_connect_io !== false`)을 읽어 넘긴다. 추가와 연결은 한 번의 `onChange`(reason `auto-connect`)로 나간다
   */
  autoConnectIo?: boolean;
  /**
   * 자동 연결이 일어난 뒤 알림. 지정하면 내부 토스트를 띄우지 않으니 앱이 자기 알림과 되돌리기(`withoutEdges(graph, addedEdgeIds)`)를 만든다.
   * 지정하지 않으면 내부 토스트 + [되돌리기](두 연결만 제거)
   */
  onAutoConnect?: (info: { addedEdgeIds: string[]; graph: Graph; previous: Graph }) => void;
  /** 팔레트 "정의에서 만드는 노드" 데이터. 키 = 노드 타입 디스크립터의 `binds.kind` */
  definitionLists?: Readonly<Record<string, readonly DefinitionItem[]>>;
  /** 정의 종류(`binds.kind`) → 구역 표시 이름. 없으면 항목의 `groupLabel`, 그것도 없으면 kind 문자열 */
  definitionKindTitles?: Readonly<Record<string, string>>;
  /** `edit`(기본) | `readonly-run`(실행 상세용: 읽기 전용, 팔레트 없음, 리소스 보기 기본 끔) */
  mode?: "edit" | "readonly-run";
  /** 리소스 보기(제어형). 끄면 `executable=false` 노드와 그 연결을 숨기고 도착 카드에 리소스 칩 줄을 보인다. 생략하면 내부 상태(기본 mode별) */
  showResources?: boolean;
  onShowResourcesChange?: (show: boolean) => void;
  /** 리소스 칩 클릭(앱이 패널의 리소스 탭을 연다) */
  onOpenResources?: (nodeId: string) => void;
  /** 연결선 모양 목록(생략 = 내장 5종). 모양 선택·경로 계산은 이 목록만 본다(graph-edges §1.1) */
  edgeShapes?: readonly EdgeShapeDescriptor[];
  /** 사용자 설정 층의 기본값(`settings.editor.default_direction`·`default_edge_shape`). 앱이 설정에서 읽어 넘긴다 */
  layoutDefaults?: { direction?: string | null; edgeShape?: string | null };
  /** 방향 어휘 표(생략 = 내장 lr·tb·rl·bt) */
  directions?: DirectionSides;
  /**
   * 자동 배치 엔진 목록. 하나 이상 주면 캔버스 좌하단에 [정리 ▾]가 생기고(`L` 키), "엉킨 연결" 힌트 칩이 켜진다.
   * 생략하거나 비우면 정리 기능이 꺼진다(나머지 편집은 그대로). 앱이 `createElkEngine()` 등으로 만들어 넘긴다
   */
  layoutEngines?: readonly LayoutEngineDescriptor[];
  /**
   * 자동 경로(`route`를 가진 모양)를 계산할 라우터. 생략하면 편집기 인스턴스마다 `createAStarRouter()`를 하나 만들어 재사용한다
   * (작업 메모리가 크므로 여러 캔버스를 동시에 띄우면 이 prop으로 하나를 나눠 쓸 수 있다)
   */
  edgeRouter?: EdgeRouter;
  /**
   * `readonly-run`의 [연결선 ▾] 보기 전용 덮어쓰기 목록(데이터를 쓰지 않는다). 기본: 자동 경로·곡선.
   * 레지스트리에 없는 `shapeId`는 목록에서 빠지고, 비우면 [연결선 ▾]이 없다.
   */
  viewOverrides?: readonly ViewOverride[];
  /** 정리 팝오버의 마지막 사용값·힌트 닫기 기억 저장소. 기본 `window.localStorage`, `null`이면 기억하지 않음 */
  storage?: KeyValueStorage | null;
  /** 저장소 키 앞에 붙이는 이름(기본 `agent-console.graph-editor.`) */
  storageKeyPrefix?: string;
  /** "엉킨 연결" 힌트 칩 사용(기본 true. `layoutEngines`가 있을 때만 의미가 있다) */
  troubleHint?: boolean;
  /** 캔버스 상단 "팀 공용" 칸(없으면 칸 없음) */
  teamShared?: TeamSharedProps;
  /** 입구/답변/묻기 토글이 적용된 뒤 알림(그래프 변경은 이미 `onChange`로 나갔다) */
  onRoleToggle?: (nodeId: string, toggle: RoleToggle, on: boolean, options?: ToggleOptions) => void;
  /** 이슈 제안 버튼을 눌렀을 때. 없어도 `applySuggestion`(ref)은 패치를 적용해 `onChange`로 낸다 */
  onApplySuggestion?: (issue: Issue, suggestion: IssueSuggestion) => void;
  /** 연결이 거부됐을 때(앱이 토스트 문구를 만들고 싶으면 지정. 지정하면 내부 토스트는 띄우지 않는다) */
  onConnectRejected?: (info: ConnectRejection) => void;
  /** 실행 상세용: 응답 대기 중인 노드(`since` = ISO 시각). 노드에 "응답 대기 {경과}" 줄을 보인다 */
  waitingNodes?: Readonly<Record<string, { since: string }>>;
  /** 지나간 엣지 순번 배지(1부터) */
  edgeOrder?: Readonly<Record<string, number>>;
  /** 엣지 호출 횟수 배지 */
  edgeCounts?: Readonly<Record<string, number>>;
  /** 앱이 노드 헤더에 더하는 텍스트 배지(예: `×3`) */
  nodeBadgesOverride?: Readonly<Record<string, readonly string[]>>;
  /** 실행 상세용 노드 회차·호출 배지. 키 = 노드 id. `nodeBadgesOverride`(문자열)와 따로 헤더 오른쪽에 그린다 */
  nodeRunBadges?: Readonly<Record<string, NodeRunBadge>>;
  /** 실행 상세용 연결 배지. 키 = 엣지 id */
  edgeBadges?: Readonly<Record<string, readonly EdgeBadge[]>>;
  /** 앱이 계산한 연결 추가 칩(조건 요약·회차 한도·위임 방식). 키 = 엣지 id. 선언형 칩 뒤에 같은 덩어리로 붙고 접근성 이름에도 들어간다. 편집기는 연결 config 키를 읽지 않는다 */
  edgeExtraChips?: Readonly<Record<string, readonly ChipView[]>>;
  /** 정의를 바인딩한 노드의 카드 요약. 키 = 노드 id */
  bindSummaries?: Readonly<Record<string, BindSummary>>;
  /** 노드별 아바타(글자·색). 키 = 노드 id. 채팅 답변 머리와 같은 해석 결과를 앱이 넘긴다 */
  nodeAvatars?: Readonly<Record<string, NodeAvatar>>;
  /** 위임 방식 목록. 위임 연결의 선 패턴을 방식 id 정렬 순서로 정한다(`resolveEdgeStyle`) */
  delegationStrategies?: readonly Pick<DelegationStrategyDescriptor, "id">[];
  /** 연결마다 유효한 위임 방식 id(연결 설정의 덮어쓰기 → 종류 기본을 앱이 계산). 키 = 엣지 id. 없으면 종류 기본 */
  edgeStrategyIds?: Readonly<Record<string, string>>;
  /** 아이콘 이름(`ChipView.iconName`·연결 스타일 아이콘)을 그리는 함수. 없거나 null을 돌려주면 짧은 아바타 문자·제목 첫 글자로 그린다 */
  renderIcon?: (name: string) => ReactNode;
  /** 포트 라벨 표시: `auto`(기본) = 연결됨·호버·선택·포커스 때만 보임(접근성 이름은 항상 유지), `always` */
  portLabels?: "auto" | "always";
  /** 경과 시간 계산용 현재 시각(ms). 테스트·고정 화면용. 생략하면 실제 시계 */
  nowMs?: number;
  /** 명령형 API 핸들(React 19: ref를 prop으로 받는다) */
  ref?: Ref<GraphEditorHandle>;
  /** 팔레트 로딩/오류 상태 */
  palette?: PaletteStatus;
  onSelectionChange?: (selection: Selection) => void;
  /** 삭제 후 되돌리기 제한 시간(ms). 기본 5000 */
  undoWindowMs?: number;
  messages?: Partial<GraphEditorMessages>;
  className?: string;
  style?: CSSProperties;
}

/** NodeCard가 받는 항목별 포트 핸들 슬롯. React Flow 비의존. */
export type PortHandleRenderer = (port: PortView, side: "in" | "out") => ReactNode;
