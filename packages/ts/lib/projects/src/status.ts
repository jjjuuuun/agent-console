/**
 * 프로젝트 상태 → 문구 키·색조·할 수 있는 일(screen-projects §1.4·§6.0).
 * 상태 값은 열린 문자열이다: 아는 값(`KNOWN_PROJECT_STATUSES`)은 문구 키로, 모르는 값은 원문과 일반 경고로 보인다.
 * "어떤 상태에서 무엇이 막히나"는 코드가 아니라 아래 표(데이터)이고, 버튼들이 `projectAbilities`로 읽는다.
 */
import { KNOWN_PROJECT_STATUSES } from "@agent-console/contracts/constants";
import type { ProjectView } from "@agent-console/contracts/projects";

import type { MessageRef } from "./messages";

/** 상태를 보여 주는 색조(색만으로 구분하지 않도록 아이콘·글자와 함께 쓴다). */
export type StatusTone = "ok" | "neutral" | "warning" | "danger";

/** 프로젝트에서 막힐 수 있는 동작. 값은 능력 표의 열 이름이다. */
export const PROJECT_ACTIONS = [
  "start_chat",
  "start_run",
  "copy_in",
  "edit",
  "save_settings",
  "memory_write",
  "save_to_library",
  "view_records",
  "collect_logs",
  "repath",
  "unregister",
] as const;
export type ProjectAction = (typeof PROJECT_ACTIONS)[number];

/** 능력 표의 행 이름(상태를 묶은 것). */
export type AbilityProfile = "ready" | "ready_readonly" | "unreadable" | "unset" | "manifest_invalid" | "archived" | "unknown";

const ALL: readonly ProjectAction[] = PROJECT_ACTIONS;
const only = (...allowed: ProjectAction[]): ReadonlySet<ProjectAction> => new Set(allowed);

/** 프로필 → 허용되는 동작(§6.0 표). 바꾸려면 이 표만 고친다. */
export const ABILITY_TABLE: Readonly<Record<AbilityProfile, ReadonlySet<ProjectAction>>> = {
  ready: new Set(ALL),
  ready_readonly: only("save_to_library", "view_records", "collect_logs", "repath", "unregister"),
  unreadable: only("view_records", "repath", "unregister"),
  unset: only("view_records", "repath", "unregister"),
  manifest_invalid: only("save_to_library", "view_records", "collect_logs", "repath", "unregister"),
  archived: only("view_records"),
  // 모르는 상태는 보수적으로: 읽기와 경로 정리만.
  unknown: only("view_records", "repath", "unregister"),
};

/** 상태 값 → 프로필. 표에 없는 상태는 `unknown`. */
export const STATUS_PROFILES: Readonly<Record<string, AbilityProfile>> = {
  [KNOWN_PROJECT_STATUSES.READY]: "ready",
  [KNOWN_PROJECT_STATUSES.FOLDER_MISSING]: "unreadable",
  [KNOWN_PROJECT_STATUSES.NOT_A_DIRECTORY]: "unreadable",
  [KNOWN_PROJECT_STATUSES.NO_ACCESS]: "unreadable",
  [KNOWN_PROJECT_STATUSES.FOLDER_UNSET]: "unset",
  [KNOWN_PROJECT_STATUSES.FOLDER_CONFLICT]: "unset",
  [KNOWN_PROJECT_STATUSES.MANIFEST_INVALID]: "manifest_invalid",
};

/** 동작 → 막혔을 때의 이유 문구 키(기본). 프로필별 덮어쓰기는 `reasonFor`. */
export const BLOCKED_KEYS: Readonly<Record<ProjectAction, string>> = {
  start_chat: "projects.blocked.new_chat",
  start_run: "projects.blocked.run",
  copy_in: "projects.blocked.copy_in",
  edit: "projects.blocked.edit",
  save_settings: "projects.blocked.edit",
  memory_write: "projects.blocked.edit",
  save_to_library: "projects.blocked.edit",
  view_records: "projects.blocked.archived",
  collect_logs: "projects.blocked.edit",
  repath: "projects.blocked.edit",
  unregister: "projects.blocked.edit",
};

const TONES: Readonly<Record<string, StatusTone>> = {
  [KNOWN_PROJECT_STATUSES.READY]: "ok",
  [KNOWN_PROJECT_STATUSES.FOLDER_MISSING]: "danger",
  [KNOWN_PROJECT_STATUSES.NOT_A_DIRECTORY]: "danger",
  [KNOWN_PROJECT_STATUSES.NO_ACCESS]: "danger",
  [KNOWN_PROJECT_STATUSES.FOLDER_UNSET]: "warning",
  [KNOWN_PROJECT_STATUSES.FOLDER_CONFLICT]: "warning",
  [KNOWN_PROJECT_STATUSES.MANIFEST_INVALID]: "danger",
};

/** 상태를 판단할 때 필요한 `ProjectView`의 부분(모든 새 필드는 선택, 없으면 정상으로 본다). */
export type ProjectStateInput = Pick<ProjectView, "status"> & {
  config_writable?: boolean | undefined;
  project?: { archived?: boolean | undefined } | undefined;
};

/** `config_writable`이 없으면 true(옛 서버 응답). */
export function isConfigWritable(view: ProjectStateInput): boolean {
  return view.config_writable !== false;
}

/** 등록 해제(보관)된 프로젝트인가. */
export function isArchived(view: ProjectStateInput): boolean {
  return view.project?.archived === true;
}

/** 능력 표에서 쓸 프로필. 보관 > 상태 > 읽기 전용 순으로 정해진다. */
export function abilityProfile(view: ProjectStateInput): AbilityProfile {
  if (isArchived(view)) return "archived";
  const base = STATUS_PROFILES[view.status] ?? "unknown";
  return base === "ready" && !isConfigWritable(view) ? "ready_readonly" : base;
}

export interface StatusInfo {
  /** 상태 문구(`projects.status.…`). 모르는 값은 `unknown` + `params.status`. */
  label: MessageRef;
  tone: StatusTone;
  /** 정상(`ready`이고 쓸 수 있고 보관 아님)이면 true — 칩을 그리지 않아도 된다. */
  plain: boolean;
  profile: AbilityProfile;
}

/** 칩·배너에 쓸 상태 표현. 보관 > 읽기 전용 > 서버 상태 순. */
export function statusInfo(view: ProjectStateInput): StatusInfo {
  const profile = abilityProfile(view);
  if (profile === "archived") return { label: { key: "projects.status.archived" }, tone: "neutral", plain: false, profile };
  if (profile === "ready_readonly") return { label: { key: "projects.status.readonly" }, tone: "warning", plain: false, profile };
  const known = view.status in TONES;
  return {
    label: known ? { key: `projects.status.${view.status}` } : { key: "projects.status.unknown", params: { status: view.status } },
    tone: known ? (TONES[view.status] ?? "warning") : "warning",
    plain: profile === "ready",
    profile,
  };
}

export interface ProjectAbility {
  allowed: boolean;
  /** 막혔을 때만. `aria-disabled` 버튼의 이유로 보인다. */
  reason: MessageRef | null;
}

export interface AbilityOptions {
  /** 프로젝트 기록 DB를 쓸 수 있는가(33c3 이후 `records_writable`). false면 시작·편집·옮기기 같은 쓰기가 막힌다. 생략 = true. */
  recordsWritable?: boolean | undefined;
  /** 표를 바꾸고 싶을 때(테스트·확장). */
  table?: Readonly<Record<AbilityProfile, ReadonlySet<ProjectAction>>> | undefined;
}

const RECORD_WRITES: ReadonlySet<ProjectAction> = new Set(["start_chat", "start_run", "edit", "copy_in", "memory_write"]);

/** 막힌 동작의 이유. 프로필이 이유를 덮어쓰는 경우(설정 파일 오류·보관·읽기 전용 시작)를 처리한다. */
function reasonFor(action: ProjectAction, profile: AbilityProfile, status: string): MessageRef {
  if (profile === "archived") return { key: "projects.blocked.archived" };
  if (profile === "manifest_invalid") return { key: "projects.blocked.manifest" };
  if (profile === "ready_readonly" && (action === "start_chat" || action === "start_run")) return { key: "projects.blocked.records_readonly" };
  if (profile === "unknown") return { key: "projects.status.blocked_reason", params: { status } };
  return { key: BLOCKED_KEYS[action] };
}

/**
 * 프로젝트 상태에서 각 동작이 되는지와 안 될 때의 이유. 버튼은 이 값으로 `aria-disabled`와 이유를 정한다.
 * @param view `ProjectView`(또는 같은 모양의 부분)
 */
export function projectAbilities(view: ProjectStateInput, options: AbilityOptions = {}): Record<ProjectAction, ProjectAbility> {
  const profile = abilityProfile(view);
  const allowedSet = (options.table ?? ABILITY_TABLE)[profile];
  const out = {} as Record<ProjectAction, ProjectAbility>;
  for (const action of PROJECT_ACTIONS) {
    let allowed = allowedSet.has(action);
    let reason: MessageRef | null = null;
    if (allowed && options.recordsWritable === false && RECORD_WRITES.has(action)) {
      allowed = false;
      reason = { key: "projects.blocked.records_readonly" };
    }
    if (!allowed && reason === null) reason = reasonFor(action, profile, view.status);
    out[action] = { allowed, reason: allowed ? null : reason };
  }
  return out;
}

/** 구성 폴더 이름 문구(`{dir}`)에 넣을 값. 서버가 준 값이 없으면 `fallback`(메시지 `projects.dir_fallback`의 글자). */
export function configDirLabel(dir: string | null | undefined, fallback: string): string {
  return dir === undefined || dir === null || dir.trim() === "" ? fallback : dir;
}
