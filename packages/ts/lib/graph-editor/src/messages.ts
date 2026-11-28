import ko from "./locales/ko.json";

/** 모든 문구의 기본 한국어 값. `messages` prop으로 부분 덮어쓰기한다. `{name}` 자리표시자는 format()으로 채운다. */
export interface GraphEditorMessages {
  /** 상태 문자열 → 라벨. 없는 상태는 원문을 그대로 쓴다 */
  statusLabels: Record<string, string>;
  /** 노드 박스처럼 좁은 칸에 쓰는 짧은 상태 라벨. 없는 상태는 `statusLabels`를 쓴다(전체 단어는 title·aria-label에 남는다) */
  statusShortLabels?: Record<string, string>;
  unknownType: string; // {type}
  nodeAria: string; // {label} {typeTitle} {status}
  statusUnknown: string;
  errorCount: string; // {count}
  /** `errorCount`의 단수형(개수 1일 때) */
  errorCountOne: string;
  issueAria: string; // {error} {warning}
  issueAriaErrorOnly: string; // {error}
  /** `issueAriaErrorOnly`의 단수형(개수 1일 때) */
  issueAriaErrorOnlyOne: string;
  issueAriaWarningOnly: string; // {warning}
  /** `issueAriaWarningOnly`의 단수형(개수 1일 때) */
  issueAriaWarningOnlyOne: string;
  issueAriaInfo: string; // {info}
  /** `issueAriaInfo`의 단수형(개수 1일 때) */
  issueAriaInfoOne: string;
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
  /** 도구줄이 좁을 때 넘친 항목을 모아 둔 [⋯] 단추의 이름 */
  moreActions: string;
  duplicate: string;
  removed: string; // {count}
  /** `removed`의 단수형(개수 1일 때) */
  removedOne: string;
  undo: string;
  added: string; // {label}
  duplicated: string; // {count}
  /** `duplicated`의 단수형(개수 1일 때) */
  duplicatedOne: string;
  connected: string;
  selectedCount: string; // {count}
  cycleRejected: string;
  /** 연결 종류 선택: 순환을 닫는데 반복 종류가 아닌 후보 행의 사유(비활성) */
  connectCycleNeeded: string;
  /** 반복 영역 안내(라이브). {count} 노드 수, {names} 이름 목록(최대 5개 + 외 N개) */
  loopRegionAnnounce: string;
  /** `loopRegionAnnounce`의 단수형(개수 1일 때) */
  loopRegionAnnounceOne: string;
  /** 이름이 5개를 넘을 때 뒤에 붙는 말. {n} */
  loopRegionMore: string;
  /** 반복 영역 노드의 접근성 이름 덧붙임 */
  loopRegionNodeAria: string;
  /** 노드 접근성 이름에 붙는 상태 덧붙임. {status} */
  nodeAriaStatus: string;
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
  /** 사용 횟수가 1일 때(영어 단수형) */
  paletteUsageOne: string; // {n}
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
  offscreenNodes: string; // {count}
  /** `offscreenNodes`의 단수형(개수 1일 때) */
  offscreenNodesOne: string;
  offscreenHint: string;
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
  /** `routeResetConfirm`의 단수형(개수 1일 때) */
  routeResetConfirmOne: string;
  routeResetConfirmYes: string;
  routeResetDone: string;
  routeResetNothing: string;
  troubleHint: string;
  /** `troubleHint`의 단수형(개수 1일 때) */
  troubleHintOne: string;
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

/** 기본 문구 = 한국어 묶음(`locales/ko.json`의 `messages`). 다른 언어는 `locales/en` 등을 `messages` prop에 넘긴다. */
export const defaultMessages: GraphEditorMessages = ko.messages;

/** 부분 덮어쓰기(statusLabels는 키 단위로 병합). */
export function mergeMessages(partial?: Partial<GraphEditorMessages>): GraphEditorMessages {
  if (partial === undefined) return defaultMessages;
  return {
    ...defaultMessages,
    ...partial,
    statusLabels: { ...defaultMessages.statusLabels, ...(partial.statusLabels ?? {}) },
    statusShortLabels: { ...defaultMessages.statusShortLabels, ...(partial.statusShortLabels ?? {}) },
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
/** 개수에 맞는 문구를 고른다: 개수가 1이면 단수형(`xxxOne`), 아니면 `xxx`. 채우는 값은 `format`과 같다. */
export function formatCount(m: GraphEditorMessages, key: PluralKey, count: number, vars: Record<string, string | number>): string {
  return format(count === 1 ? m[`${key}One`] : m[key], vars);
}

/** 단수형 짝(`xxxOne`)을 가진 문구 이름 */
export type PluralKey = "errorCount" | "removed" | "duplicated" | "offscreenNodes" | "troubleHint" | "loopRegionAnnounce" | "routeResetConfirm" | "issueAriaInfo" | "issueAriaErrorOnly" | "issueAriaWarningOnly";

export function format(template: string, vars: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m));
}
