/**
 * 메모리 화면의 데이터 표(`docs/design/screen-memory.md`). 수치·저장소 키·주소 인자 이름이 전부 여기 있고 화면 코드는 이 표만 읽는다.
 * 범위 종류·범위 이름·도구 이름은 이 파일에도 없다(서버 데이터). 계약 어휘(쓴 주체 종류·가져오기 정책)는 `memoryData.json`.
 */
import { MEMORY_ENTRY_SORTS } from "@agent-console/contracts/constants";
import data from "./memoryData.json";

/** 이 화면이 맡는 역할(라우트 `serves`·`requires`와 같은 값). 모듈 id가 아니다. */
export const MEMORY_ROLE = "memory";

/** 모듈 옵션에서 설치자 한도를 읽을 때의 키(서버 모듈이 정한 옵션 이름). */
export const LIMIT_OPTION_KEYS = { maxEntryBytes: "max_entry_bytes" } as const;
/** 사용자 설정 섹션 이름(공통 설정 문서의 키)과 그 안의 버전 보관 수 키 */
export const SETTINGS_SECTION = "memory";

export const MEMORY_LIMITS = {
  pageSize: 50,
  searchDebounceMs: 300,
  /** 실시간 알림에서 표 질의를 다시 하는 간격(최대 1회) */
  liveDebounceMs: 500,
  /** 나무 수 갱신 디바운스 */
  treeDebounceMs: 1000,
  undoMs: 8000,
  /** 본문 폭이 이 값 이상이면 3칸, 미만이면 2칸 */
  threeColumnMinWidth: 1180,
  tree: { def: 240, min: 200, max: 320 },
  detail: { def: 420, min: 320, max: 640 },
  /** 뷰포트 높이가 이 값 이상이면 정보 영역이 기본 펼침 */
  metaOpenMinHeight: 800,
  /** 정리·내보내기 같은 표 한 번 질의의 항목 상한 */
  retentionPlanLimit: 200,
  /** 범위 비우기가 항목을 가져오는 쪽 크기 */
  clearPageSize: 200,
  /** "새 변경" 안내를 읽어 주는 최소 간격 */
  announceMs: 10_000,
  /** 최근 쓴 항목 강조 시간(CSS 애니메이션과 같은 값) */
  highlightMs: 1500,
} as const;

/** 화면 상태를 저장하는 localStorage 키(서버 설정이 아니다). */
export const MEMORY_STORAGE = {
  treeWidth: "ac.memory.tree.w",
  detailWidth: "ac.memory.detail.w",
  treeOpen: "ac.memory.tree.open",
  metaOpen: "ac.memory.meta.open",
  diffLayout: "ac.memory.diff.layout",
} as const;

/** 주소 인자 이름(`memoryData.json`). 선택은 URL이 진실이다. */
export const MEMORY_PARAMS: Readonly<Record<keyof typeof data.params, string>> = data.params;

/** 서버가 받는 정렬 값(계약). 열 머리는 이 중 열이 있는 것만 누를 수 있다. */
export const ENTRY_SORTS: readonly string[] = MEMORY_ENTRY_SORTS;
/** 표 열 → 서버 정렬 값. 쓴 주체·고정·태그 열은 정렬 대상이 아니다. */
export const SORT_KEYS_BY_COLUMN = { key: "key", updated: "updated_at", size: "bytes", version: "version" } as const;
/** 서버 기본 정렬(사용자가 고르지 않았을 때 주소에 쓰지 않는 값). */
export const DEFAULT_SORT = "updated_at";

export const AUTHOR_KIND_FILTERS: readonly string[] = data.authorKindFilters;
export const IMPORT_POLICIES: readonly { id: string; warns: boolean }[] = data.importPolicies;
export const DEFAULT_IMPORT_POLICY: string = data.defaultImportPolicy;
/** 가져오기·정리가 남기는 항목의 쓴 주체 종류(결과 화면의 [메모리에서 보기] 필터) */
export const IMPORTED_AUTHOR_KIND: string = data.importedAuthorKind;

/** 서버 경고(`/server-info`의 warnings) 중 이 접두 코드만 이 화면이 쓴다. */
export const WARNING_PREFIX = "memory.";

/** 서버 경고 코드(화면이 따로 다루는 것). 그 밖의 `memory.` 경고는 서버 원문을 그대로 보인다. */
export const WARNING_CODES: { readonly storageMemory: string; readonly searchFallback: string } = data.warningCodes;

/**
 * 실행 상세 요약 줄의 메모리 칩 데이터(`memoryData.json`): 이 실행의 `typePrefix` 이벤트를 세어 type 뒤쪽 이름이 `write.types`면 쓰기, `read.types`면 읽기로 센다.
 * `cap`을 넘으면 "{cap}+"로 보이고 `okStatus`가 아닌 payload `status`는 실패로 센다. 읽기 칩은 이벤트 목록을 `read.openPrefix`로 연다.
 */
export const RUN_CHIPS: {
  readonly typePrefix: string;
  readonly write: { readonly types: readonly string[] };
  readonly read: { readonly types: readonly string[]; readonly openPrefix: string };
  readonly cap: number;
  readonly debounceMs: number;
  readonly okStatus: string;
} = data.runChips;
