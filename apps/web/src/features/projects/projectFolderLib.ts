import type { FolderCheck } from "@agent-console/contracts/projects";
import type { FolderCheckState } from "@agent-console/folder-picker";

/** 경로의 마지막 폴더 이름(구분자 `/`·`\` 모두). 루트거나 비면 빈 문자열. 이름 칸의 첫 제안값에만 쓴다(slug 계산 아님). */
export function folderBaseName(path: string): string {
  const parts = path.split(/[\\/]+/).filter((p) => p !== "");
  const last = parts[parts.length - 1] ?? "";
  return /^[A-Za-z]:$/.test(last) ? "" : last;
}

/** 확인이 끝나 제출할 수 있는 상태에서만 부가 정보(이름·id 제안)를 쓴다. */
export interface FolderSuggestion {
  name: string;
  id: string;
  description: string;
  /** 폴더 안 설정이 읽히는 기존 프로젝트: 구성 개수(없으면 null) */
  adopted: { name: string; definitions: number } | null;
  /** 폴더 안 설정 파일이 깨졌는가 */
  manifestInvalid: boolean;
}

/**
 * 확인 응답에서 이름·id·설명 제안을 만든다(screen-projects §3.1).
 * - 기존 구성이 읽히면 그 이름·설명, 깨졌으면 폴더 이름(깨진 파일의 이름은 신뢰하지 않는다).
 * - id는 서버가 계산한 `suggested_id` 그대로(웹이 slug를 만들지 않는다).
 */
export function suggestionFor(state: FolderCheckState, info: FolderCheck | undefined): FolderSuggestion {
  const path = state.check?.path ?? state.forInput ?? "";
  const existing = info?.existing ?? null;
  const found = existing?.state === "found";
  const invalid = existing?.state === "invalid";
  const foundName = found && existing?.name ? existing.name : "";
  return {
    name: foundName !== "" ? foundName : folderBaseName(path),
    id: info?.suggested_id ?? "",
    description: found ? (existing?.description ?? "") : "",
    adopted: found ? { name: foundName, definitions: existing?.definitions ?? 0 } : null,
    manifestInvalid: invalid,
  };
}

/** 제출 버튼을 켤 수 있는가: 폴더 확인이 통과했고(`submittable`) 이름이 있고 선택 대기·제출 중이 아니다. */
export function canSubmitAdd(state: FolderCheckState, name: string, busy: boolean, waiting: boolean): boolean {
  return state.submittable && !busy && !waiting && (state.reregister || name.trim() !== "");
}

/** 경로 다시 지정 제출 가능: 확인 통과 + 같은 경로가 아님(`same_path`는 `submittable`이 아니다). */
export function canSubmitRepath(state: FolderCheckState, busy: boolean, waiting: boolean): boolean {
  return state.submittable && !state.reregister && !busy && !waiting;
}
