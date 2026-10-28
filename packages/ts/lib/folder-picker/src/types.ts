/**
 * folder-picker가 받는 데이터 모양. 서버 쪽 `ac-local-folders`의 `FolderCheck`·`FolderListing`·`FolderRoot`
 * (`to_dict()` 결과)와 같은 필드 이름이다. 계약 타입(`@agent-console/contracts`)이 나오면 앱이 이 모양에 맞춰 변환하거나
 * 구조가 같은 계약 타입을 그대로 넘긴다(구조적 타입이라 import 없이 호환된다).
 */

/** 폴더 확인 결과(`FolderCheck`). `status`는 쓰지 않는다(여기서 필드로 다시 계산). */
export interface FolderCheckData {
  input: string;
  /** 저장될 경로(정규화 + 링크를 푼 실제 경로). 입력이 경로가 아니면 null. */
  path: string | null;
  exists: boolean;
  is_dir: boolean;
  readable: boolean;
  writable: boolean;
  can_create: boolean;
  hidden?: boolean;
  link?: boolean;
  /** path가 폴더면 그 자신, 아니면 가장 가까운 존재하는 상위 폴더. null 가능. */
  nearest_existing?: string | null;
  /** 입력이 쓸 수 없는 이유(열린 문자열: empty·invalid_path·relative·foreign_path·no_home·outside_roots …). */
  problem?: string | null;
  /**
   * 폴더에 프로젝트 구성이 이미 있을 때(선택 필드, 없으면 안내를 숨긴다). 계약 필드가 확정되면 앱이 이 모양으로 옮겨 준다.
   * `valid: false`면 설정 파일이 있으나 읽을 수 없다.
   */
  manifest?: FolderManifestInfo | null;
}

/** 폴더 안 기존 프로젝트 구성 요약(선택 필드). */
export interface FolderManifestInfo {
  /** 구성에 저장된 이름. */
  name?: string | null;
  /** 구성 항목 수. */
  count?: number | null;
  /** 읽을 수 있는가(기본 true). */
  valid?: boolean;
}

/** 폴더 확인 요청. `create`는 사용자가 [폴더 만들기]를 눌렀을 때만 true. */
export interface FolderCheckRequest {
  path: string;
  create?: boolean;
  /** 경로 다시 지정 모드에서 자기 자신을 겹침 검사에서 빼기 위한 프로젝트 id(K33-13). */
  excludeProjectId?: string;
}

/** `check` 콜백이 돌려주는 값. 409·403 같은 "예상한 거절"은 던지지 말고 아래 종류로 돌려준다. 그 밖의 실패는 reject한다. */
export type FolderCheckOutcome =
  | { kind: "checked"; check: FolderCheckData }
  /** 같은 폴더가 이미 등록됨(409 `…folder_taken`). `archived`면 해제된 프로젝트의 폴더. */
  | { kind: "taken"; projectId: string; name: string; archived?: boolean; check?: FolderCheckData }
  /** 상위·하위 폴더가 이미 등록됨(409 `…folder_overlaps`). `path`는 겹치는 프로젝트의 폴더. */
  | { kind: "overlap"; relation: "parent" | "child"; projectId: string; name: string; path: string; check?: FolderCheckData }
  /** 서버가 원격 접속을 허용해 폴더 확인·탐색이 꺼져 있다(403). */
  | { kind: "remote_disabled" };

export type FolderCheckFn = (request: FolderCheckRequest, signal: AbortSignal) => Promise<FolderCheckOutcome>;

/** 탐색 시작 위치 하나(`FolderRoot`). */
export interface FolderRootData {
  kind?: string;
  path: string;
  label: string;
}

/** 하위 폴더 하나(`FolderEntry`) + 등록된 프로젝트 표시. */
export interface FolderEntryData {
  name: string;
  path: string;
  hidden?: boolean;
  link?: boolean;
  locked?: boolean;
  /** 이 폴더가 이미 프로젝트로 등록돼 있으면 그 id·이름(칩 "등록됨: …"). */
  project_id?: string | null;
  project_name?: string | null;
}

/** 하위 폴더 목록(`FolderListing`). */
export interface FolderListingData {
  path: string;
  parent: string | null;
  entries: readonly FolderEntryData[];
  truncated?: boolean;
  timed_out?: boolean;
  hidden_count?: number;
}

export interface FolderListRequest {
  path: string;
  /** 숨김 폴더도 받는가. */
  hidden: boolean;
}
export type FolderListFn = (request: FolderListRequest, signal: AbortSignal) => Promise<FolderListingData>;

export interface FolderCreateRequest {
  /** 만들 위치(현재 목록 경로). */
  parent: string;
  name: string;
}
/** 새 폴더 결과. 서버가 거절하면 `ok: false` + `code`(`exists`·`invalid_name` …)와 서버 문구를 돌려준다. */
export type FolderCreateResult = { ok: true; path: string } | { ok: false; code: string; message?: string };
export type FolderCreateFn = (request: FolderCreateRequest, signal: AbortSignal) => Promise<FolderCreateResult>;

/** 서버가 제공하는 폴더 고르기 방법(`FolderCapabilities`와 같은 필드). */
export interface FolderCapabilitiesData {
  /** 앱 안 찾아보기를 쓸 수 있는가. */
  browse?: boolean;
  /** OS 폴더 선택 창을 띄울 수 있는가. */
  native_dialog?: boolean;
  /** 쓸 수 없는 이유(열린 문자열, 그대로 보여 주지 않는다). */
  reason?: string | null;
}

/** 선택 결과 상태. 모르는 값은 `failed`로 다룬다. */
export type FolderPickStatus = "picked" | "cancelled" | "unavailable" | "busy" | "timeout" | "failed";

/** `onPickNative`가 돌려주는 값(`FolderPickResult`와 같은 필드 + 이미 변환한 확인 결과). */
export interface FolderPickOutcome {
  status: FolderPickStatus | (string & {});
  /** `picked`일 때 고른 경로. */
  path?: string | null;
  /** 고른 경로의 폴더 확인 결과. 있으면 다시 요청하지 않고 그대로 쓴다. */
  check?: FolderCheckData | null;
  /** 충돌(등록됨·겹침)까지 담은 확인 결과. `check`보다 우선한다. */
  outcome?: FolderCheckOutcome | null;
  /** 쓸 수 없는 이유(`unavailable`·`failed`일 때 "자세히"로 보인다). */
  reason?: string | null;
}

/**
 * OS 선택 창 콜백. 사용자가 고를 때까지 열려 있다. `initial`은 처음 열 폴더(없으면 서버 기본).
 * `signal`이 abort되면 요청을 끊어야 한다(서버가 창을 닫는다). 네트워크 오류는 reject한다(→ `failed`).
 */
export type FolderPickFn = (initial: string | undefined, signal: AbortSignal) => Promise<FolderPickOutcome>;
