/**
 * 구조도 화면의 한글 문구(앱 층, `screen-architecture.md` §12 `arch.*`). 칸 이름·연결 라벨·설명·프로필 제목은 서버 데이터라 여기 없다.
 * 그림 안쪽 문구(지표·상태·도구줄)는 `@agent-console/arch-view`의 기본 문구를 쓴다.
 */
export const archMessages = {
  segment: "구조도",
  region: "구조도",
  profile: "프로필",
  breadcrumb: { label: "구조도 위치", root: "세션", up: "상위 구조도로", folded: "중간 단계 보기" },
  status: {
    events: (n: number) => `이벤트 ${n.toLocaleString("ko-KR")}`,
    wholeRange: "전체 기준",
    unassigned: (n: number) => `분류 안 됨 ${n.toLocaleString("ko-KR")}`,
    unassignedView: "보기",
    unavailable: (n: number) => `수집 안 됨 항목 ${n}`,
    live: "실행 중",
    liveUpdated: (time: string) => `실행 중 · 갱신 ${time}`,
    reflected: (n: number) => `새 이벤트 ${n.toLocaleString("ko-KR")}건 반영`,
    laneBasis: (name: string) => `레인 ${name} 기준`,
    loading: "구조도를 그리는 중…",
    refreshing: "다시 그리는 중…",
    unavailableOpen: "펼치기",
    unavailableClose: "접기",
    unavailableItem: (item: string, reason: string) => (reason === "" ? item : `${item} — ${reason}`),
  },
  chip: {
    cell: (name: string) => `구조도: ${name}`,
    edge: (label: string) => `구조도: ${label}`,
    group: (cell: string, group: string) => `구조도: ${cell} › ${group}`,
    unassigned: "구조도: 분류 안 됨",
    clear: "구조도 필터 지우기",
    drillClear: (label: string) => `${label} 필터 지우기`,
  },
  noName: "(이름 없음)",
  unassigned: "분류 안 됨",
  toast: {
    notCollected: "수집 안 됨 칸은 걸러낼 이벤트가 없습니다.",
    structural: "구조 연결은 이벤트가 없습니다.",
    pickGroup: "하위 구조도는 묶음 칩을 눌러 들어갑니다.",
    rejected: (message: string) => message,
  },
  table: {
    only: (name: string, n: number) => `구조도 ${name} ${n.toLocaleString("ko-KR")}건`,
    partial: (name: string, n: number, k: number) => `구조도 ${name} ${n.toLocaleString("ko-KR")}건 중 ${k.toLocaleString("ko-KR")}건 (다른 필터 적용)`,
    loading: (name: string) => `구조도 ${name} 이벤트를 불러오는 중…`,
    zero: (name: string) => `구조도 ${name} 0건이라 걸러낼 이벤트가 없습니다`,
  },
  /** 서버 안내(`view.notes`)는 서버가 만든 문구를 그대로 쓰고, 설정으로 가는 단추만 앱이 단다. */
  banner: {
    openSettings: "설정에서 보기",
  },
  empty: {
    rules: { title: "구조도 규칙이 없습니다", body: "구조도를 그리는 규칙(프로필)이 없어서 그림을 만들 수 없습니다. 로그와 실행 기록은 그대로 쓸 수 있습니다.", action: "설정 열기" },
    noEvents: { title: "이 범위에 이벤트가 없습니다", body: "그림은 규칙대로 그려 두었습니다. 이벤트가 들어오면 숫자가 채워집니다.", action: "필터 지우기" },
    noSource: {
      title: "어떤 칸도 채울 수 없습니다",
      body: (kinds: string) => `이 범위의 로그 출처${kinds === "" ? "" : `(${kinds})`}는 이 프로필의 어떤 칸도 기록하지 않습니다.`,
      action: "로그 출처 설정 열기",
    },
    tooBig: {
      title: "범위가 너무 큽니다",
      body: (n: number | undefined, max: number | undefined) =>
        n !== undefined && max !== undefined
          ? `이벤트가 ${n.toLocaleString("ko-KR")}건으로 구조도 상한(${max.toLocaleString("ko-KR")})을 넘었습니다. 필터를 좁혀 주세요.`
          : "이 범위의 이벤트가 구조도 상한을 넘었습니다. 필터를 좁혀 주세요.",
      action: "필터 열기",
    },
    error: { title: "구조도를 불러오지 못했습니다", action: "다시 시도" },
    profileError: { title: "이 프로필을 그릴 수 없습니다", action: "설정에서 고치기" },
  },
  runTab: {
    explain: "이 실행의 플랫폼 기록과 에이전트 세션 로그를 합쳐 그린 구조도입니다. 같은 호출은 한 번만 셉니다.",
    includeChildren: "자식 실행 포함",
    on: "포함",
    off: "제외",
    rootLabel: "실행",
    scopeRun: "이 실행",
    scopeTree: "자식 실행 포함",
    splitLabel: "구조도 높이 조절",
  },
  dialog: {
    title: (profile: string, scope: string) => `구조도 · ${profile} · ${scope}`,
    close: "닫기",
    expand: "크게 보기",
  },
  /** 구조도 분리 창(새 창으로 분리, 다시 합치기) */
  popout: {
    open: "새 창으로 분리",
    openHelp: "구조도를 새 창으로 분리합니다. 이 창의 로그와 선택·강조를 주고받습니다.",
    focus: "분리 창 열기",
    redock: "다시 합치기",
    detachedTitle: "구조도가 다른 창에 열려 있음",
    detachedBody: "그 창에서 칸을 누르면 이 창의 이벤트 표가 걸러지고, 이 창에서 고른 이벤트는 그 창에서 강조됩니다.",
    pendingTitle: "구조도를 새 창으로 분리해서 보도록 설정되어 있음",
    pendingBody: "브라우저가 허락해야 새 창을 열 수 있어 자동으로 열지 않습니다.",
    dock: "이 화면에 보기",
    blocked: "브라우저가 새 창을 막았습니다. 주소 표시줄의 팝업 차단을 허용한 뒤 [새 창으로 분리]를 다시 눌러 주세요.",
    unsupported: "이 브라우저는 창 사이 연동을 지원하지 않아 구조도를 분리할 수 없습니다.",
    windowTitle: (label: string) => `구조도 · ${label}`,
    standalone: "원래 창과 연결되지 않았습니다. 칸을 눌러도 로그 표는 걸러지지 않습니다.",
    needArch: "이 서버에는 구조도 연동이 없어 그릴 수 없습니다.",
    needKey: "범위 정보가 없는 주소입니다. 로그 세션이나 실행 상세에서 [새 창으로 분리]를 눌러 여세요.",
    closeWindow: "분리 창 닫기",
  },
  aria: { live: "구조도 갱신 알림" },
} as const;
