import type { FolderCheckData, FolderCheckOutcome } from "./types";

export type CheckTone = "info" | "success" | "warning" | "danger";
/** 화면이 구분하는 대표 6종. */
export type CheckGroup = "idle" | "checking" | "ok" | "missing" | "conflict" | "blocked";

/** 세부 상태 id(명세 §3.3 표). */
export type CheckStateId =
  | "idle" | "checking" | "ok" | "ok_readonly" | "manifest_found" | "manifest_invalid" | "missing" | "missing_parent" | "not_directory" | "no_access"
  | "invalid" | "taken" | "taken_archived" | "overlap_parent" | "overlap_child" | "remote_disabled" | "same_path" | "error";

export interface FolderCheckState {
  id: CheckStateId;
  group: CheckGroup;
  /** idle이면 null. */
  tone: CheckTone | null;
  /** 이 상태에서 제출 버튼을 켤 수 있는가(이름 등 다른 조건은 앱 몫). */
  submittable: boolean;
  /** 제출 버튼 라벨을 "다시 등록"류로 바꿔야 하는가. */
  reregister: boolean;
  /** 찾아보기 패널을 막는가. */
  browseDisabled: boolean;
  /** 확인이 끝난 입력 경로(결과가 어느 입력의 것인지). */
  forInput: string | null;
  check: FolderCheckData | null;
  outcome: FolderCheckOutcome | null;
}

const base: FolderCheckState = {
  id: "idle", group: "idle", tone: null, submittable: false, reregister: false, browseDisabled: false, forInput: null, check: null, outcome: null,
};

export const IDLE_STATE: FolderCheckState = base;
export const checkingState = (forInput: string): FolderCheckState => ({ ...base, id: "checking", group: "checking", tone: "info", forInput });
export const errorState = (forInput: string): FolderCheckState => ({ ...base, id: "error", group: "blocked", tone: "danger", forInput });

export interface DeriveOptions {
  /** 경로 다시 지정 모드의 이전 경로. 확인된 경로와 문자열이 같으면 `same_path`. */
  currentFolder?: string | null;
}

/** 서버 확인 결과를 화면 상태로 바꾸는 순수 함수(명세 §3.3 표). */
export function deriveCheckState(forInput: string, outcome: FolderCheckOutcome, opts: DeriveOptions = {}): FolderCheckState {
  const mk = (id: CheckStateId, group: CheckGroup, tone: CheckTone, extra: Partial<FolderCheckState> = {}): FolderCheckState => ({
    ...base, id, group, tone, forInput, outcome, check: "check" in outcome ? (outcome.check ?? null) : null, ...extra,
  });
  switch (outcome.kind) {
    case "remote_disabled":
      return mk("remote_disabled", "blocked", "warning", { submittable: true, browseDisabled: true });
    case "taken":
      return outcome.archived
        ? mk("taken_archived", "conflict", "info", { submittable: true, reregister: true })
        : mk("taken", "conflict", "danger");
    case "overlap":
      return mk(outcome.relation === "parent" ? "overlap_parent" : "overlap_child", "conflict", "danger");
    case "checked":
      break;
  }
  const c = outcome.check;
  if (c.problem != null || c.path == null) return mk("invalid", "blocked", "danger");
  if (!c.exists) return c.can_create ? mk("missing", "missing", "warning") : mk("missing_parent", "blocked", "danger");
  if (!c.readable) return mk("no_access", "blocked", "danger");
  if (!c.is_dir) return mk("not_directory", "blocked", "danger");
  if (opts.currentFolder != null && c.path === opts.currentFolder) return mk("same_path", "blocked", "info");
  if (!c.writable) return mk("ok_readonly", "ok", "warning", { submittable: true });
  const m = c.manifest ?? null;
  if (m) return m.valid === false ? mk("manifest_invalid", "ok", "warning", { submittable: true }) : mk("manifest_found", "ok", "info", { submittable: true });
  return mk("ok", "ok", "success", { submittable: true });
}

/**
 * 찾아보기 시작 위치(K33-13). 확인 결과만 쓴다: 존재하는 폴더면 그 경로, 아니면 `nearest_existing`, 없으면 null(= 시작 위치 목록).
 */
export function browseStartPath(state: FolderCheckState): string | null {
  const c = state.check;
  if (!c) return null;
  if (c.path != null && c.exists && c.is_dir && c.readable) return c.path;
  return c.nearest_existing ?? null;
}
