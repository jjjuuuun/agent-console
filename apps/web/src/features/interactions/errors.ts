import { ApiError } from "@agent-console/api-client";
import type { Interaction } from "@agent-console/contracts";

export interface FieldProblem {
  path: string;
  message: string;
}

/** 422 `validation_failed`의 `details`에서 필드 오류를 읽는다(`errors`·`issues` 배열의 `{path|loc, message|msg}`). */
export function fieldProblems(error: ApiError): FieldProblem[] {
  const list = error.details["errors"] ?? error.details["issues"];
  if (!Array.isArray(list)) return [];
  const out: FieldProblem[] = [];
  for (const raw of list) {
    if (typeof raw !== "object" || raw === null) continue;
    const r = raw as Record<string, unknown>;
    const message = typeof r.message === "string" ? r.message : typeof r.msg === "string" ? r.msg : undefined;
    if (message === undefined) continue;
    const loc = r.path ?? r.loc;
    const path = typeof loc === "string" ? loc : Array.isArray(loc) ? "/" + loc.filter((p) => p !== "response" && p !== "body").join("/") : "";
    out.push({ path: path === "/" ? "" : path, message });
  }
  return out;
}

/** 409 `interaction_closed`의 `details.interaction`(서버가 알려 주는 현재 상태). */
export function closedInteraction(error: ApiError): Interaction | undefined {
  const i = error.details["interaction"];
  return typeof i === "object" && i !== null && typeof (i as Interaction).id === "string" ? (i as Interaction) : undefined;
}

/** 네트워크 오류(서버 응답 없음)인가. */
export function isNetworkError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 0;
}
