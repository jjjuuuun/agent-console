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

/** 맞춤(화면 명세 §4.2, 5.5R.20). 값은 전부 여기서만 바꾼다. */
export const ARCH_FIT = {
  /** 저장된 선택이 없을 때의 맞춤 */
  default: "auto",
  /** 자동 맞춤이 높이가 모자랄 때 전체 맞춤으로 바꾸는 최소 배율(미만이면 폭 맞춤 + 잘림 표시) */
  autoContainMin: 0.55,
  /** 이 배율 미만이면 요약 표시(명세 §4.2 `auto` 규칙의 0.45) */
  fullScaleMin: 0.45,
  /**
   * [크게 보기] 대화상자에서 그림과 이벤트 표의 높이 비(약 78% : 22%). 명세는 75 : 25이지만 1440×900에서 75%면 캔버스가 466(전체 맞춤 배율 0.53 < 0.55)이라
   * 칸이 잘려서, 전체 맞춤 기준(0.55)을 넘는 최소 비율로 잡았다(캔버스 약 489, 배율 0.56).
   */
  dialogSplit: { diagram: 7, table: 2 },
  /** 1280px 미만 폭에서의 비(55% : 45%, 명세 §6.4) */
  dialogSplitNarrow: { diagram: 11, table: 9 },
  /** 대화상자 이벤트 표 최소 높이(px) */
  dialogTableMin: 120,
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
