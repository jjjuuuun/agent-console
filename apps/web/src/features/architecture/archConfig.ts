/**
 * 구조도 화면의 데이터 표(`docs/design/screen-architecture.md`). 저장소 키·시간·크기 상수가 전부 여기 있다.
 * 칸·연결·프로필 이름은 없다(서버가 주는 `ArchitectureView`). 지표 이름은 서버 계약(`count`·`errors`·`tokens`·`duration`)이다.
 */

/** 화면 상태를 저장하는 localStorage 키(서버 설정이 아니다). */
export const ARCH_STORAGE = {
  profile: "ac.arch.profile",
  fit: "ac.arch.fit",
  view: "ac.arch.view",
  /** 실행 상세 탭의 그림 높이 */
  runHeight: "ac.arch.run.height",
  runProfile: "ac.arch.run.profile",
  runFit: "ac.arch.run.fit",
  runView: "ac.arch.run.view",
  runDialogFit: "ac.arch.run.dialog.fit",
  runDialogView: "ac.arch.run.dialog.view",
} as const;

/** 서버 쿼리 이름(로그 필터 확장 X28과 구조도 요청). 값은 `ArchitectureSelector`가 준다. */
export const ARCH_QUERY = {
  profile: "profile",
  arch: "arch",
  group: "arch_group",
  sources: "arch_sources",
  maxSeq: "max_seq",
} as const;

/** 표 질의에서 횟수를 읽는 지표 이름(계약). */
export const ARCH_COUNT_METRIC = "count";

export const ARCH_LIMITS = {
  /** `logs.ingested` 뒤 다시 질의하기까지(ms) */
  liveDebounceMs: 1000,
  /** 이 폭 미만이면 기본 보기가 [목록] */
  listBelowWidth: 1280,
  /** 선택한 대상의 이벤트 한 쪽 크기(서버 `limit` 상한과 같다) */
  rowsPage: 200,
  /** 한 번에 자동으로 읽는 최대 쪽 수 */
  rowsMaxPages: 200,
  /** "새 이벤트 n건 반영"을 알리는 최소 간격(ms) */
  announceMs: 10_000,
  /** 4단계 이상이면 가운데를 접는다 */
  crumbFoldFrom: 4,
} as const;

/** 실행 상세 탭의 범위 질의(로그 필터 `scope`, 범위 종류 id는 서버 `link-logs-runs`가 정한 X27). */
export const ARCH_RUN_SCOPE = { param: "scope", run: "run", tree: "run-tree" } as const;

/** 실행 상세 탭 그림 높이(px, 화면 명세 §6.2: 기본 240, 조절 160~480). `chrome`은 캔버스 위 도구줄과 아래 선택 정보 줄의 높이 합. */
export const ARCH_RUN_HEIGHT = { default: 240, min: 160, max: 480, chrome: 104 } as const;
