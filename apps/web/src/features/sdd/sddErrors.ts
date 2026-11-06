import { ApiError } from "@agent-console/api-client";
import { ERROR_CODES } from "@agent-console/contracts";
import { sddMessages as m } from "./messages";

/** 스펙 요청 실패를 화면이 다루는 종류로 나눈 것. 서버 코드는 화면에 노출하지 않는다. */
export type SddFailure =
  /** 프로젝트 연동이 꺼져 있다(409 `spaces_unavailable`): 본문 전체를 안내로 바꾼다 */
  | { kind: "unavailable" }
  /** 스펙을 찾을 수 없다(404) */
  | { kind: "notFound" }
  /** 프로젝트 폴더·설정 문제(폴더 없음·설정 파일 오류·쓰기 불가·모르는 프로젝트·허용되지 않는 경로) */
  | { kind: "problem"; message: string }
  | { kind: "generic"; message: string; code?: string };

/** 오류를 화면 종류로 분류한다. `fallback`은 서버 문장도 없을 때 쓴다. */
export function classifySddError(error: unknown, fallback: string): SddFailure {
  if (!(error instanceof ApiError)) return { kind: "generic", message: error instanceof Error && error.message !== "" ? error.message : fallback };
  switch (error.code) {
    case ERROR_CODES.SDD_SPACES_UNAVAILABLE:
      return { kind: "unavailable" };
    case ERROR_CODES.SDD_NOT_FOUND:
      return { kind: "notFound" };
    case ERROR_CODES.PROJECT_FOLDER_MISSING:
      return { kind: "problem", message: m.problem.folderMissing };
    case ERROR_CODES.PROJECT_MANIFEST_INVALID:
      return { kind: "problem", message: m.problem.manifestInvalid };
    case ERROR_CODES.PROJECT_CONFIG_READONLY:
    case ERROR_CODES.SDD_CONFIG_READONLY:
      return { kind: "problem", message: m.problem.configReadonly };
    case ERROR_CODES.PROJECT_NOT_FOUND:
      return { kind: "problem", message: m.problem.notFound };
    case ERROR_CODES.FOLDERS_INVALID_PATH:
      return { kind: "problem", message: m.problem.invalidPath(typeof error.details["reason"] === "string" ? error.details["reason"] : "") };
    default:
      return { kind: "generic", message: error.message !== "" ? error.message : fallback, code: error.code };
  }
}

/** 오류가 서버 코드 `code`인가. */
export function hasCode(error: unknown, code: string): error is ApiError {
  return error instanceof ApiError && error.code === code;
}
