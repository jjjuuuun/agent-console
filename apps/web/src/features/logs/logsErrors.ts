import { ApiError } from "@agent-console/api-client";
import { describeError } from "../../app/errors";
import { logsMessages as t } from "./messages";

/**
 * 서버 422(`validation_failed`, `details.path`)를 필터 이름별 메시지로 바꾼다. `path`의 마지막 조각(`filter.model` → `model`)이 필터 이름이다.
 * 메시지는 서버 문장 그대로. 경로가 없으면 빈 객체(영역 오류 블록이 대신 보인다).
 */
export function fieldErrorsOf(error: unknown): Readonly<Record<string, string>> {
  if (!(error instanceof ApiError) || error.status !== 422) return {};
  const path = error.details["path"];
  if (typeof path !== "string" || path === "") return {};
  const name = path.split(".").pop() ?? path;
  return { [name]: error.message !== "" ? error.message : t.filters.unknownError };
}

/** 영역 오류 블록용 문장 + 접힌 상세(코드·경로). */
export function errorBlockOf(error: unknown, fallback: string): { message: string; detail?: string } {
  const v = describeError(error, fallback);
  const path = error instanceof ApiError && typeof error.details["path"] === "string" ? `path: ${error.details["path"] as string}` : undefined;
  const detail = [v.code === undefined ? undefined : `code: ${v.code}`, v.status ? `status: ${v.status}` : undefined, path].filter((x): x is string => x !== undefined).join("\n");
  return detail === "" ? { message: v.message } : { message: v.message, detail };
}
