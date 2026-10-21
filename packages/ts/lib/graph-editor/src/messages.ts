/** 모든 문구의 기본 한국어 값. `messages` prop으로 부분 덮어쓰기한다. `{name}` 자리표시자는 format()으로 채운다. */
export interface GraphEditorMessages {
  /** 상태 문자열 → 라벨. 없는 상태는 원문을 그대로 쓴다 */
  statusLabels: Record<string, string>;
  unknownType: string; // {type}
  nodeAria: string; // {label} {typeTitle} {status}
  statusUnknown: string;
  errorCount: string; // {count}
  issueAria: string; // {error} {warning}
  issueAriaErrorOnly: string; // {error}
  issueAriaWarningOnly: string; // {warning}
  attemptBadge: string; // {n}
  portMissing: string;
  portsLoading: string;
  portsFailed: string;
  edgeInvalid: string;
  edgeAria: string; // {source} {sourcePort} {target} {targetPort}
  paletteTitle: string;
  paletteSearch: string;
  paletteSearchLabel: string;
  paletteEmpty: string;
  paletteNoMatch: string;
  paletteLoading: string;
  paletteError: string;
  paletteRetry: string;
  paletteUncategorized: string;
  paletteAddHint: string;
  canvasLabel: string;
  remove: string;
  duplicate: string;
  removed: string; // {count}
  undo: string;
  added: string; // {label}
  duplicated: string; // {count}
  connected: string;
  selectedCount: string; // {count}
  cycleRejected: string;
  /** 연결 종류 선택: 순환을 닫는데 반복 종류가 아닌 후보 행의 사유(비활성) */
  connectCycleNeeded: string;
  /** 반복 영역 안내(라이브). {count} 노드 수, {names} 이름 목록(최대 5개 + 외 N개) */
  loopRegionAnnounce: string;
  /** 이름이 5개를 넘을 때 뒤에 붙는 말. {n} */
  loopRegionMore: string;
  /** 반복 영역 노드의 접근성 이름 덧붙임 */
  loopRegionNodeAria: string;
  /** 칩 줄에서 보이지 않는 칩 수. {n} */
  edgeChipsMore: string;
  /** 연결 접근성 이름에 칩을 이을 때 구분자 앞 말. 종류 이름 앞에 붙는다. {title} */
  edgeAriaKind: string;
  /** 정의 바인딩 노드 카드의 [열기] 단추 문구 */
  bindOpen: string;
  /** 정의를 찾을 수 없는 노드 카드의 접근성 문구 */
  bindMissing: string;
  /** 정의 바인딩 노드 접근성 이름 덧붙임. {subtitle} {title} */
  bindAria: string;
  /** 팔레트 안내: [열기]를 Alt+Enter로 연다는 상태 문구. {label} */
  bindOpenAnnounce: string;
  /** 팔레트 항목 비활성 사유가 있는 항목을 누를 때 안내. {reason} */
  paletteItemDisabled: string;
  /** 팔레트로 추가한 노드가 화면 밖이어서 이동했다는 안내. {label} */
  addedRevealed: string;
  /** `T` 키: 바꿀 수 있는 다른 종류가 없을 때 */
  kindChangeNone: string;
  /** 종류를 바꾼 뒤 안내. {title} */
  kindChanged: string;
  selfRejected: string;
  portRejected: string;
  duplicateEdge: string;
  noEdgeType: string;
  edgeKindTitle: string;
  /** 입구·답변 자동 연결 알림 */
  autoConnected: string;
  edgeKindConfirm: string;
  edgeKindCancel: string;
  noTitle: string;
  // ---- 팀 구성 모드 ----
  /** 상황 배지 문구(키 = 스케줄링·interaction 어휘) */
  badgeLabels: Record<string, string>;
  /** 연결 종류 선택의 보조 배지(키 = 디스크립터 속성에서 계산한 어휘) */
  kindBadgeLabels: Record<string, string>;
  unknownEdgeKind: string; // {kind}
  edgeKindHint: string;
  /** 선택 UI 행의 포트 열. {source} {target} */
  edgeKindPorts: string;
  /** 노드 몸체에 놓아 연결한 뒤 안내. {source} {target} (포트는 자동으로 정했다) */
  connectedInferred: string;
  /** 연결을 끌고 있을 때 노드 위에 보이는 라벨 */
  dropHere: string;
  noKindRejected: string;
  noKindRejectedRoles: string; // {source} {target}
  paletteDefinitionsSection: string;
  paletteBaseSection: string;
  paletteNoDefinitions: string; // {kind}
  /** 구역의 항목이 모두 비활성(자기 자신뿐 등)일 때의 안내 */
  paletteOnlyDisabled: string; // {kind}
  paletteCreateDefinition: string; // {kind}
  paletteUsage: string; // {n}
  /** 선언형 배지·칩(`ui_hints.badges/chips`)의 `label_key` → 문구. 기본은 비어 있고 앱/디스크립터 `label`이 채운다 */
  hintLabels: Record<string, string>;
  toggleLabels: Record<string, string>;
  toggleUnavailable: Record<string, string>;
  toggleKind: string;
  toggleUserNode: string;
  toggleChoose: string;
  toolbarLabel: string; // {label}
  roleToggleAdded: string;
  roleToggleRemoved: string;
  showResources: string;
  minimapShow: string;
  minimapHide: string;
  resourceChipsLabel: string;
  resourceChipTitle: string; // {title} {count} {names}
  moreResourceChips: string; // {n}
  teamSharedTitle: string;
  teamSharedEmpty: string;
  teamSharedAdd: string;
  teamSharedRemove: string; // {title}
  teamSharedInherited: string; // {n}
  suggestionMore: string;
  suggestionApplied: string;
  waitingFor: string; // {elapsed}
  elapsedSeconds: string; // {s}
  elapsedMinutes: string; // {m} {s}
  elapsedHours: string; // {h} {m}
  edgeOrderBadge: string; // {n}
  edgeCountBadge: string; // {n}
  // ---- 연결선 모양·경로(graph-edges §2, §6) ----
  /** 모양 이름은 레지스트리 title이 우선. 이 문구는 title이 없는 모양의 대체 */
  shapeInherited: string; // {title}
  unknownShape: string; // {id}
  waypointRoleDescription: string;
  waypointAria: string; // {i} {n} {x} {y}
  waypointAddAria: string; // {i}
  waypointAdded: string; // {i} {x} {y}
  waypointMoved: string; // {i} {x} {y}
  waypointRemoved: string; // {i} {n}
  waypointLimit: string; // {max}
  waypointCoord: string; // {x} {y}
  waypointZoomHint: string;
  labelHandleAria: string; // {pct}
  labelMoved: string; // {pct}
  labelReset: string;
  pathEditStarted: string;
  pathEditEnded: string;
  pathReset: string;
  shapeChanged: string; // {title}
  edgeAriaShape: string; // {title}
  edgeAriaWaypoints: string; // {n}
  edgeLayoutTitle: string;
  edgeLayoutShape: string;
  edgeLayoutRadius: string;
  edgeLayoutBend: string;
  edgeLayoutLabelPos: string;
  edgeLayoutWaypoints: string; // {n} {max}
  edgeLayoutAddWaypoint: string;
  edgeLayoutWaypointRow: string; // {i}
  edgeLayoutMoveUp: string; // {i}
  edgeLayoutMoveDown: string; // {i}
  edgeLayoutRemove: string; // {i}
  edgeLayoutMoveUpText: string;
  edgeLayoutMoveDownText: string;
  edgeLayoutRemoveText: string;
  edgeLayoutResetLabel: string;
  edgeLayoutResetPath: string;
  edgeLayoutResetAll: string;
  edgeLayoutInheritedBadge: string;
  edgeLayoutWaypointsIgnored: string; // {n}
  edgeLayoutChanged: string; // {items}
  /** 바뀐 항목 이름(키 = layout 키). {n}은 경유점 개수 */
  edgeLayoutChangedLabels: Record<string, string>;
  /** 노드 [배치] 탭(graph-edges §3.4) */
  layoutTabTitle: string;
  nodeLayoutDirection: string;
  nodeLayoutInherit: string;
  nodeLayoutInheritAria: string; // {title}
  /** {source} {direction} */
  nodeLayoutInheritedNow: string;
  /** 방향 id -> 표시 이름. 모르는 id는 id 그대로 */
  directionLabels: Record<string, string>;
  /** 방향 값이 어느 층에서 왔는가(키 = 층 이름) */
  directionSourceLabels: Record<string, string>;
  /** 면 이름(키 = 면 id) */
  sideLabels: Record<string, string>;
  nodeLayoutPorts: string;
  nodeLayoutIn: string;
  nodeLayoutOut: string;
  /** {io} {label} */
  nodeLayoutPortSide: string;
  /** {side} */
  nodeLayoutInheritOption: string;
  nodeLayoutChangedMark: string;
  /** {value} */
  nodeLayoutUnknown: string;
  /** 포트 면 드롭다운의 `자동` 선택지 */
  nodeLayoutAutoSide: string;
  /** 노드 방향 "자동" 버튼 설명 */
  nodeLayoutAutoDirectionHint: string;
  /** 다중 선택에서 항목마다 값이 다를 때 */
  multiLayoutMixed: string;
  /** 연결선 우클릭 메뉴 */
  edgeMenuLabel: string;
  edgeMenuEditPath: string;
  edgeMenuDelete: string;
  edgeMenuShapeHeading: string;
  /** 정리: 엔진이 `edgeShapeOption`을 선언했을 때의 체크 문구(선언에 `title`이 없으면 이것) */
  tidyAutoRoutes: string;
  /** {id} */
  nodeLayoutOrphan: string;
  nodeLayoutRemoveOrphan: string;
  nodeLayoutMakeDefault: string;
  nodeLayoutReset: string;
  /** {title} */
  directionChanged: string;
  /** {label} {side} */
  portMoved: string;
  /** 핸들 title(포인터 대안 안내) */
  portMoveHint: string;
  portMoveCancelled: string;
  tidyTitle: string;
  tidyOpen: string;
  tidyDirection: string;
  tidyScope: string;
  tidyScopeAll: string;
  tidyScopeSelected: string;
  tidyEngine: string;
  tidyEngineOptions: string;
  tidyEdges: string;
  tidyDefaultShape: string;
  tidyShapeByKind: string;
  tidyShapeInherit: string;
  tidyResetRoutes: string;
  tidyAlignNodes: string;
  tidyKinds: string;
  tidyPreview: string;
  tidyPreviewOff: string;
  tidyCancel: string;
  tidyApply: string;
  tidyClose: string;
  tidyRunning: string;
  tidyFailed: string;
  tidyRetry: string;
  tidyTimeout: string;
  tidyDone: string;
  tidyCancelled: string;
  tidyNeedTwoNodes: string;
  tidyPreviewShown: string;
  tidyResetAllRoutes: string;
  routeResetConfirm: string;
  routeResetConfirmYes: string;
  routeResetDone: string;
  routeResetNothing: string;
  troubleHint: string;
  troubleAutoRoute: string;
  troubleDismiss: string;
  /** 실행 상세 [연결선 ▾] 보기 전용 덮어쓰기 */
  viewEdges: string;
  viewStored: string;
  /** {title} */
  viewTemp: string;
  viewTempClear: string;
  viewAuto: string;
  viewAutoShort: string;
  viewCurve: string;
  viewCurveShort: string;
  layoutUndone: string;
  layoutRedone: string;
  /** 방향 순환 버튼 */
  rotateDirection: string;
  /** 캔버스 라이브러리가 쓰는 보조기술 문구(키는 내부 규약, 모르는 키는 무시) */
  flowLabels: Record<string, string>;
}

export const defaultMessages: GraphEditorMessages = {
  statusLabels: {
    pending: "대기",
    queued: "대기열",
    running: "실행 중",
    succeeded: "성공",
    failed: "실패",
    skipped: "건너뜀",
    waiting: "대기 중(입력·승인)",
    cancelled: "취소됨",
  },
  unknownType: "알 수 없는 타입: {type}",
  nodeAria: "노드 {label}, 타입 {typeTitle}{status}",
  statusUnknown: "",
  errorCount: ", 검증 오류 {count}건",
  issueAria: "검증 오류 {error}건, 경고 {warning}건",
  issueAriaErrorOnly: "검증 오류 {error}건",
  issueAriaWarningOnly: "경고 {warning}건",
  attemptBadge: "×{n}",
  portMissing: "이 포트는 더 이상 없습니다",
  portsLoading: "포트를 계산하는 중",
  portsFailed: "포트를 계산하지 못했습니다",
  edgeInvalid: "!",
  edgeAria: "{source}의 {sourcePort}에서 {target}의 {targetPort}로 연결",
  paletteTitle: "노드 팔레트",
  paletteSearch: "검색",
  paletteSearchLabel: "노드 타입 검색",
  paletteEmpty: "등록된 노드 타입이 없습니다. 서버에 노드 타입 플러그인이 로드되었는지 확인하세요.",
  paletteNoMatch: "일치하는 노드 타입이 없습니다",
  paletteLoading: "노드 타입을 불러오는 중",
  paletteError: "노드 타입을 불러오지 못했습니다",
  paletteRetry: "다시 시도",
  paletteUncategorized: "기타",
  paletteAddHint: "더블클릭하거나 Enter로 추가, 캔버스로 끌어다 놓기",
  canvasLabel: "그래프 캔버스",
  remove: "삭제",
  duplicate: "복제",
  removed: "{count}개를 삭제했습니다.",
  undo: "되돌리기",
  added: "{label} 노드를 추가했습니다.",
  duplicated: "{count}개 노드를 복제했습니다.",
  connected: "연결했습니다.",
  selectedCount: "{count}개 선택됨",
  cycleRejected: "순환 연결은 지원하지 않습니다 — 반복 연결 종류가 없습니다.",
  connectCycleNeeded: "순환이 됩니다 — 반복 연결이 필요합니다",
  loopRegionAnnounce: "반복 영역: 노드 {count}개 — {names}",
  loopRegionMore: "외 {n}개",
  loopRegionNodeAria: "반복 영역",
  edgeChipsMore: "+{n}",
  edgeAriaKind: "종류 {title}",
  bindOpen: "열기",
  bindMissing: "찾을 수 없음",
  bindAria: "{subtitle} {title}",
  bindOpenAnnounce: "{label}을(를) 엽니다.",
  paletteItemDisabled: "추가할 수 없습니다: {reason}",
  addedRevealed: "{label}을(를) 추가하고 화면을 옮겼습니다.",
  kindChangeNone: "바꿀 수 있는 다른 연결 종류가 없습니다.",
  kindChanged: "연결 종류를 ‘{title}’(으)로 바꿨습니다.",
  selfRejected: "같은 노드끼리는 연결할 수 없습니다.",
  portRejected: "출력 포트에서 입력 포트로만 연결할 수 있습니다.",
  duplicateEdge: "이미 같은 연결이 있습니다.",
  noEdgeType: "사용할 수 있는 엣지 종류가 없습니다.",
  edgeKindTitle: "연결 종류 선택",
  autoConnected: "입구·답변 연결을 만들었습니다",
  edgeKindConfirm: "연결",
  edgeKindCancel: "취소",
  noTitle: "(이름 없음)",
  badgeLabels: { entry: "입구", exit: "답변", interaction: "묻기" },
  kindBadgeLabels: { entry: "입구", exit: "답변", delegate: "위임", ask: "묻기", flow: "순서", none: "" },
  unknownEdgeKind: "알 수 없는 연결 종류: {kind}",
  edgeKindHint: "숫자키 또는 방향키로 고르고 Enter로 연결합니다.",
  edgeKindPorts: "{source} → {target}",
  connectedInferred: "연결했습니다: {source} → {target}",
  dropHere: "여기에 연결",
  noKindRejected: "이 두 노드를 이을 수 있는 연결 종류가 없습니다.",
  noKindRejectedRoles: "이 두 노드를 이을 수 있는 연결 종류가 없습니다. (출발 {source} → 도착 {target})",
  paletteDefinitionsSection: "정의에서 만드는 노드",
  paletteBaseSection: "기본 노드",
  paletteNoDefinitions: "{kind} 정의가 없습니다",
  paletteOnlyDisabled: "넣을 다른 {kind}이(가) 없습니다",
  paletteCreateDefinition: "{kind} 만들기",
  paletteUsage: "{n}회 사용",
  hintLabels: {},
  toggleLabels: { entry: "입구", exit: "답변", interaction: "되묻기·승인 허용" },
  toggleUnavailable: { "no-kind": "이 노드에 쓸 수 있는 연결 종류가 없습니다", "no-counterpart": "연결할 사용자 노드가 없습니다" },
  toggleKind: "연결 종류",
  toggleUserNode: "연결할 노드",
  toggleChoose: "연결할 대상을 고르세요",
  toolbarLabel: "{label} 노드 빠른 조작",
  roleToggleAdded: "연결을 추가했습니다.",
  roleToggleRemoved: "연결을 지웠습니다.",
  showResources: "리소스 보기",
  minimapShow: "미니맵 보기",
  minimapHide: "미니맵 숨기기",
  resourceChipsLabel: "리소스",
  resourceChipTitle: "{title} {count}개: {names}",
  moreResourceChips: "+{n}",
  teamSharedTitle: "팀 공용:",
  teamSharedEmpty: "(없음)",
  teamSharedAdd: "+ 붙이기",
  teamSharedRemove: "{title} 제거",
  teamSharedInherited: "공통 {n}개 상속",
  suggestionMore: "더 보기",
  suggestionApplied: "제안을 적용했습니다.",
  waitingFor: "응답 대기 {elapsed}",
  elapsedSeconds: "{s}초",
  elapsedMinutes: "{m}분 {s}초",
  elapsedHours: "{h}시간 {m}분",
  edgeOrderBadge: "{n}번째로 지나감",
  edgeCountBadge: "{n}회",
  shapeInherited: "상속 (현재: {title})",
  unknownShape: "알 수 없음: {id}",
  waypointRoleDescription: "경유점",
  waypointAria: "경유점 {i}/{n}, 위치 x {x} y {y}. 화살표 키로 이동, Delete로 삭제",
  waypointAddAria: "경유점 추가 위치 {i}",
  waypointAdded: "경유점 {i} 추가, x {x} y {y}",
  waypointMoved: "경유점 {i} 이동, x {x} y {y}",
  waypointRemoved: "경유점 {i} 삭제, 남은 경유점 {n}개",
  waypointLimit: "경유점은 연결 하나에 {max}개까지",
  waypointCoord: "x {x} · y {y}",
  waypointZoomHint: "경유점 편집은 화면을 확대한 뒤 할 수 있습니다.",
  labelHandleAria: "라벨 위치 {pct}%. 좌우 화살표 키로 이동",
  labelMoved: "라벨 위치 {pct}%",
  labelReset: "라벨 위치를 초기화했습니다.",
  pathEditStarted: "경로 편집 모드. Tab으로 경유점·추가 위치·라벨을 옮겨 다니고 Esc로 끝냅니다.",
  pathEditEnded: "경로 편집 모드를 끝냈습니다.",
  pathReset: "경로를 초기화했습니다.",
  shapeChanged: "모양: {title}",
  edgeAriaShape: "; 모양 {title}",
  edgeAriaWaypoints: "; 경유점 {n}개",
  edgeLayoutTitle: "모양·경로",
  edgeLayoutShape: "모양",
  edgeLayoutRadius: "모서리 둥글기(px)",
  edgeLayoutBend: "꺾임 위치(%)",
  edgeLayoutLabelPos: "라벨 위치(%)",
  edgeLayoutWaypoints: "경유점 {n}/{max}",
  edgeLayoutAddWaypoint: "+ 추가",
  edgeLayoutWaypointRow: "경유점 {i}",
  edgeLayoutMoveUp: "경유점 {i} 위로",
  edgeLayoutMoveDown: "경유점 {i} 아래로",
  edgeLayoutRemove: "경유점 {i} 삭제",
  edgeLayoutMoveUpText: "위",
  edgeLayoutMoveDownText: "아래",
  edgeLayoutRemoveText: "삭제",
  edgeLayoutResetLabel: "라벨 초기화",
  edgeLayoutResetPath: "경로 초기화",
  edgeLayoutResetAll: "전부 기본으로",
  edgeLayoutInheritedBadge: "상속",
  edgeLayoutWaypointsIgnored: "이 모양은 경유점을 쓰지 않습니다(저장된 {n}개 보존)",
  edgeLayoutChanged: "기본값에서 바뀐 항목: {items}",
  edgeLayoutChangedLabels: { shape: "모양", radius: "모서리 둥글기", bend: "꺾임 위치", waypoints: "경유점 {n}", label_t: "라벨 위치", label_offset: "라벨 위치" },
  layoutTabTitle: "배치",
  nodeLayoutDirection: "방향",
  nodeLayoutInherit: "상속",
  nodeLayoutInheritAria: "상속 (현재: {title})",
  nodeLayoutInheritedNow: "상속 중: {source} → {direction}",
  directionLabels: { lr: "오른쪽", tb: "아래", rl: "왼쪽", bt: "위", auto: "자동" },
  directionSourceLabels: { node: "이 노드", graph: "그래프 방향", settings: "설정의 기본 방향", hint: "노드 타입 기본", builtin: "기본" },
  sideLabels: { left: "왼쪽", right: "오른쪽", top: "위", bottom: "아래" },
  nodeLayoutPorts: "포트",
  nodeLayoutIn: "입력",
  nodeLayoutOut: "출력",
  nodeLayoutPortSide: "{io} {label}의 면",
  nodeLayoutInheritOption: "상속 ({side})",
  nodeLayoutChangedMark: "이 노드에서 바꾼 값",
  nodeLayoutUnknown: "알 수 없음: {value}",
  nodeLayoutAutoSide: "자동",
  multiLayoutMixed: "여러 값",
  edgeMenuLabel: "연결선 메뉴",
  edgeMenuEditPath: "경로 편집",
  edgeMenuDelete: "삭제",
  edgeMenuShapeHeading: "모양",
  tidyAutoRoutes: "연결선도 자동 경로로",
  nodeLayoutAutoDirectionHint: "연결된 노드가 있는 쪽으로 면을 고릅니다",
  nodeLayoutOrphan: "사라진 포트 {id}",
  nodeLayoutRemoveOrphan: "삭제",
  nodeLayoutMakeDefault: "이 방향을 그래프 기본으로",
  nodeLayoutReset: "배치 초기화",
  directionChanged: "방향: {title}",
  portMoved: "포트 {label}을 {side}으로 이동",
  portMoveHint: "길게 누르거나 Alt를 누른 채 끌어 면을 옮깁니다",
  portMoveCancelled: "포트 이동을 취소했습니다.",
  tidyTitle: "정리",
  tidyOpen: "정리",
  tidyDirection: "배치 방향",
  tidyScope: "범위",
  tidyScopeAll: "전체",
  tidyScopeSelected: "선택한 노드({n})",
  tidyEngine: "엔진",
  tidyEngineOptions: "배치 옵션",
  tidyEdges: "연결선",
  tidyDefaultShape: "기본 모양",
  tidyShapeByKind: "종류별 모양",
  tidyShapeInherit: "상속",
  tidyResetRoutes: "연결선 경로 다시 만들기(경유점 지움)",
  tidyAlignNodes: "노드 방향을 위 방향에 맞추기",
  tidyKinds: "배치에 쓸 연결",
  tidyPreview: "미리보기",
  tidyPreviewOff: "미리보기 해제",
  tidyCancel: "취소",
  tidyApply: "적용",
  tidyClose: "닫기",
  tidyRunning: "정리 계산 중…",
  tidyFailed: "정리하지 못했습니다: {reason}",
  tidyRetry: "다시 시도",
  tidyTimeout: "시간이 초과되었습니다({sec}초)",
  tidyDone: "정리했습니다",
  tidyCancelled: "정리를 취소했습니다.",
  tidyNeedTwoNodes: "정리할 노드가 둘 이상 필요합니다",
  tidyPreviewShown: "미리보기를 표시했습니다.",
  tidyResetAllRoutes: "모든 연결선 경로 초기화",
  routeResetConfirm: "연결선 {n}개의 경유점·꺾임·라벨 위치를 지웁니다. 계속할까요?",
  routeResetConfirmYes: "초기화",
  routeResetDone: "연결선 경로를 모두 초기화했습니다.",
  routeResetNothing: "초기화할 연결선 경로가 없습니다.",
  troubleHint: "연결선 {count}개가 노드를 지납니다",
  troubleAutoRoute: "자동 경로로",
  troubleDismiss: "닫기",
  viewEdges: "연결선",
  viewStored: "저장된 대로",
  viewTemp: "임시 보기: {title}",
  viewTempClear: "임시 보기 해제",
  viewAuto: "자동 경로로 보기",
  viewAutoShort: "자동 경로",
  viewCurve: "곡선으로 보기",
  viewCurveShort: "곡선",
  layoutUndone: "레이아웃 변경을 되돌렸습니다.",
  layoutRedone: "레이아웃 변경을 다시 적용했습니다.",
  rotateDirection: "방향 바꾸기",
  flowLabels: {
    "node.a11yDescription.default": "Enter 또는 Space로 선택하고, 선택한 뒤 방향키로 이동합니다.",
    "node.a11yDescription.keyboardDisabled": "이 캔버스에서는 키보드로 노드를 이동할 수 없습니다.",
    "edge.a11yDescription.default": "Enter 또는 Space로 연결을 선택합니다.",
    "controls.ariaLabel": "캔버스 조작",
    "controls.zoomIn.ariaLabel": "확대",
    "controls.zoomOut.ariaLabel": "축소",
    "controls.fitView.ariaLabel": "화면에 맞춤",
    "controls.interactive.ariaLabel": "상호작용 잠금 전환",
    "minimap.ariaLabel": "미니맵",
    "handle.ariaLabel": "포트 핸들",
  },
};

/** 부분 덮어쓰기(statusLabels는 키 단위로 병합). */
export function mergeMessages(partial?: Partial<GraphEditorMessages>): GraphEditorMessages {
  if (partial === undefined) return defaultMessages;
  return {
    ...defaultMessages,
    ...partial,
    statusLabels: { ...defaultMessages.statusLabels, ...(partial.statusLabels ?? {}) },
    flowLabels: { ...defaultMessages.flowLabels, ...(partial.flowLabels ?? {}) },
    badgeLabels: { ...defaultMessages.badgeLabels, ...(partial.badgeLabels ?? {}) },
    kindBadgeLabels: { ...defaultMessages.kindBadgeLabels, ...(partial.kindBadgeLabels ?? {}) },
    hintLabels: { ...defaultMessages.hintLabels, ...(partial.hintLabels ?? {}) },
    toggleLabels: { ...defaultMessages.toggleLabels, ...(partial.toggleLabels ?? {}) },
    toggleUnavailable: { ...defaultMessages.toggleUnavailable, ...(partial.toggleUnavailable ?? {}) },
    edgeLayoutChangedLabels: { ...defaultMessages.edgeLayoutChangedLabels, ...(partial.edgeLayoutChangedLabels ?? {}) },
    directionLabels: { ...defaultMessages.directionLabels, ...(partial.directionLabels ?? {}) },
    directionSourceLabels: { ...defaultMessages.directionSourceLabels, ...(partial.directionSourceLabels ?? {}) },
    sideLabels: { ...defaultMessages.sideLabels, ...(partial.sideLabels ?? {}) },
  };
}

/** `{name}` 자리표시자 치환. */
export function format(template: string, vars: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m));
}
