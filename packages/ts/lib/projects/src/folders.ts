/**
 * 폴더 선택 어댑터: 계약(`FolderCheck`·`FolderPickResult`·`FolderCapabilities`)을 `@agent-console/folder-picker`가
 * 받는 모양으로 바꾸는 순수 함수. 이 패키지는 folder-picker를 import하지 않는다 — 아래 `Picker*` 타입은 picker의
 * `FolderCheckData`·`FolderCheckOutcome`·`FolderPickOutcome`·`FolderCapabilitiesData`와 구조가 같다(앱의 호환 검사가 지킨다).
 *
 * 규칙: `conflict`(`taken`·`overlap_*`)는 `outcome`의 `taken`·`overlap`으로 바꾼다. 프로젝트 이름은 계약이 주지 않으므로
 * 이름 표(`projectName`)로 찾고 없으면 id를 쓴다. 모르는 선택 상태는 `failed`처럼 다룬다.
 */
import { KNOWN_ISSUE_CODES } from "@agent-console/contracts/constants";
import type {
  FolderCapabilities,
  FolderCheck,
  FolderConflict,
  FolderPickResult,
  ProjectFolderConflictDetails,
} from "@agent-console/contracts/projects";

/** picker `FolderCheckData`와 같은 모양. */
export interface PickerFolderCheck {
  input: string;
  path: string | null;
  exists: boolean;
  is_dir: boolean;
  readable: boolean;
  writable: boolean;
  can_create: boolean;
  hidden?: boolean;
  link?: boolean;
  nearest_existing?: string | null;
  problem?: string | null;
}

/** picker `FolderCheckOutcome`과 같은 모양. */
export type PickerCheckOutcome =
  | { kind: "checked"; check: PickerFolderCheck }
  | { kind: "taken"; projectId: string; name: string; archived?: boolean; check?: PickerFolderCheck }
  | { kind: "overlap"; relation: "parent" | "child"; projectId: string; name: string; path: string; check?: PickerFolderCheck }
  | { kind: "remote_disabled" };

/** picker `FolderPickOutcome`과 같은 모양. */
export interface PickerPickOutcome {
  status: string;
  path?: string | null;
  check?: PickerFolderCheck | null;
  outcome?: PickerCheckOutcome | null;
  reason?: string | null;
}

/** picker `FolderCapabilitiesData`와 같은 모양. */
export interface PickerCapabilities {
  browse?: boolean;
  native_dialog?: boolean;
  reason?: string | null;
}

/** 프로젝트 id → 표시 이름. 없으면 id를 이름으로 쓴다. */
export interface FolderAdapterOptions {
  projectName?: (projectId: string) => string | undefined;
}

/** `FolderCheck` → picker 확인 데이터(`status`·`conflict`는 필드로 다시 계산하므로 빼고, 필드 기본값을 채운다). */
export function folderCheckData(check: FolderCheck): PickerFolderCheck {
  return {
    input: check.input,
    path: check.path ?? null,
    exists: check.exists ?? false,
    is_dir: check.is_dir ?? false,
    readable: check.readable ?? false,
    writable: check.writable ?? false,
    can_create: check.can_create ?? false,
    ...(check.hidden === undefined ? {} : { hidden: check.hidden }),
    ...(check.link === undefined ? {} : { link: check.link }),
    ...(check.nearest_existing === undefined ? {} : { nearest_existing: check.nearest_existing }),
    ...(check.problem === undefined ? {} : { problem: check.problem }),
  };
}

type ConflictLike = Pick<FolderConflict, "project_id"> & { relation?: string | null | undefined; archived?: boolean | undefined; folder?: string | null | undefined };

function nameOf(id: string, options: FolderAdapterOptions): string {
  const n = options.projectName?.(id);
  return n !== undefined && n !== "" ? n : id;
}

/** 충돌 하나 → `taken`(같은 폴더) 또는 `overlap`(상위·하위). 관계를 모르면 null. */
function conflictOutcome(c: ConflictLike, check: PickerFolderCheck | undefined, options: FolderAdapterOptions): PickerCheckOutcome | null {
  const withCheck = check === undefined ? {} : { check };
  const name = nameOf(c.project_id, options);
  if (c.relation === "parent" || c.relation === "child") {
    return { kind: "overlap", relation: c.relation, projectId: c.project_id, name, path: c.folder ?? "", ...withCheck };
  }
  if (c.relation === "same" || c.relation === undefined || c.relation === null) {
    return { kind: "taken", projectId: c.project_id, name, ...(c.archived === true ? { archived: true } : {}), ...withCheck };
  }
  return null;
}

/**
 * 폴더 확인 응답 → picker 결과. `conflict`가 있으면 `taken`·`overlap`, 없으면 `checked`.
 * `taken_archived` 상태는 `archived`로 표시한다(해제된 프로젝트의 폴더).
 */
export function folderCheckOutcome(check: FolderCheck, options: FolderAdapterOptions = {}): PickerCheckOutcome {
  const data = folderCheckData(check);
  if (check.conflict !== undefined && check.conflict !== null) {
    const found = conflictOutcome({ ...check.conflict, archived: check.conflict.archived === true || check.status === "taken_archived" }, data, options);
    if (found !== null) return found;
  }
  return { kind: "checked", check: data };
}

/** 오류에서 읽을 최소 모양(`ApiError`가 그대로 맞는다). */
export interface ErrorLike {
  code: string;
  details?: Record<string, unknown> | undefined;
}

/**
 * 거절 오류 → picker 결과. 예상한 거절만 바꾼다: 원격 접속 차단(`folders.remote_disabled`),
 * 폴더 등록 충돌(`project.folder_taken`·`project.folder_overlaps`, 등록 요청의 409).
 * 그 밖의 오류는 null(호출자가 다시 던진다).
 */
export function folderErrorOutcome(error: ErrorLike, options: FolderAdapterOptions = {}): PickerCheckOutcome | null {
  if (error.code === KNOWN_ISSUE_CODES.FOLDERS_REMOTE_DISABLED) return { kind: "remote_disabled" };
  if (error.code !== KNOWN_ISSUE_CODES.PROJECT_FOLDER_TAKEN && error.code !== KNOWN_ISSUE_CODES.PROJECT_FOLDER_OVERLAPS) return null;
  const d = error.details as Partial<ProjectFolderConflictDetails> | undefined;
  if (d === undefined || typeof d.project_id !== "string") return null;
  return conflictOutcome(
    { project_id: d.project_id, relation: error.code === KNOWN_ISSUE_CODES.PROJECT_FOLDER_TAKEN ? "same" : d.relation, archived: d.archived, folder: d.folder },
    undefined,
    options,
  );
}

/** 선택 창이 돌려줄 수 있는 상태(문서 상수). 이 밖의 값은 `failed`. */
const PICK_STATUSES: ReadonlySet<string> = new Set(["picked", "cancelled", "unavailable", "busy", "timeout", "failed"]);

/**
 * OS 선택 창 응답 → picker 결과. `picked`면 `check`·`outcome`(충돌 포함)을 채워 picker가 다시 확인 요청을 보내지 않게 한다.
 * 모르는 상태는 `failed`.
 */
export function folderPickOutcome(result: FolderPickResult, options: FolderAdapterOptions = {}): PickerPickOutcome {
  const status = PICK_STATUSES.has(result.status) ? result.status : "failed";
  const out: PickerPickOutcome = { status };
  if (result.path !== undefined) out.path = result.path;
  if (status === "picked" && result.check !== undefined && result.check !== null) {
    const outcome = folderCheckOutcome(result.check, options);
    out.check = folderCheckData(result.check);
    out.outcome = outcome;
    out.path ??= out.check.path;
  }
  return out;
}

/** 폴더 고르기 방법 → picker 데이터. 필드가 없으면 `browse`는 켜짐으로 본다(찾아보기는 늘 마지막 수단). */
export function folderCapabilities(c: FolderCapabilities): PickerCapabilities {
  return {
    browse: c.browse !== false,
    native_dialog: c.native_dialog === true,
    ...(c.reason === undefined ? {} : { reason: c.reason }),
  };
}
