import { ERROR_CODES, HTTP_STATUS_BY_ERROR_CODE } from "@agent-console/contracts";
import type { ErrorInfo, Fix, VersionConflictDetails } from "@agent-console/contracts";

/** 네트워크 자체가 실패했을 때(서버 응답 없음) 쓰는 클라이언트 전용 code. */
export const NETWORK_ERROR_CODE = "network_error" as const;

/** HTTP 상태 → 알려진 오류 code. 서버 오류 본문이 없을 때 추정에 쓴다(없으면 `http_<status>`). */
const STATUS_TO_CODE = new Map<number, string>();
// 같은 상태에 code가 여럿이면(409) 먼저 나온 것이 일반형이다(`already_exists`). 구체 code는 본문에서 온다.
for (const [code, status] of Object.entries(HTTP_STATUS_BY_ERROR_CODE)) {
  if (!STATUS_TO_CODE.has(status)) STATUS_TO_CODE.set(status, code);
}

/**
 * REST 호출이 실패했을 때 던지는 타입드 오류.
 * 서버가 준 `ErrorResponse{error:{code,message,details}}`를 그대로 담는다.
 * 모르는 `code`(플러그인 등)도 그대로 노출하며, 본문이 없으면 HTTP 상태에서 code를 추정한다.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;
  /** 서버가 준 해결 버튼(없으면 undefined). 역할 -> 화면 경로 해석은 웹 앱이 한다. */
  readonly fix: Fix | undefined;

  constructor(status: number, info: ErrorInfo, options?: { cause?: unknown }) {
    super(info.message, options);
    this.name = "ApiError";
    this.status = status;
    this.code = info.code;
    this.details = info.details ?? {};
    this.fix = info.fix ?? undefined;
  }

  /** 409 `interaction_closed`: 이미 답했거나 닫힌 상호작용(다른 탭이 먼저 답한 경우 등). */
  get isInteractionClosed(): boolean {
    return this.code === ERROR_CODES.INTERACTION_CLOSED;
  }

  /** 409 `conversation_busy`: `chat.busy_policy = reject`인데 대화가 실행 중. */
  get isConversationBusy(): boolean {
    return this.code === ERROR_CODES.CONVERSATION_BUSY;
  }

  /** 412 `version_conflict`이면 서버가 알려준 현재 버전 정보, 아니면 undefined. */
  get versionConflict(): VersionConflictDetails | undefined {
    if (this.code !== ERROR_CODES.VERSION_CONFLICT) return undefined;
    const current = this.details["current_version_hash"];
    if (typeof current !== "string") return undefined;
    return this.details as unknown as VersionConflictDetails;
  }
}

/** `error` 필드가 ErrorInfo 모양이면 돌려준다. */
export function parseErrorInfo(body: unknown): ErrorInfo | undefined {
  if (typeof body !== "object" || body === null) return undefined;
  const err = (body as { error?: unknown }).error;
  if (typeof err !== "object" || err === null) return undefined;
  const { code, message, details, fix } = err as Record<string, unknown>;
  if (typeof code !== "string" || typeof message !== "string") return undefined;
  const info: ErrorInfo = { code, message };
  if (typeof details === "object" && details !== null && !Array.isArray(details)) {
    info.details = details as Record<string, unknown>;
  }
  if (typeof fix === "object" && fix !== null && Array.isArray((fix as { actions?: unknown }).actions)) info.fix = fix as Fix;
  return info;
}

/** 응답 상태와 (파싱된) 본문에서 ApiError를 만든다. */
export function toApiError(status: number, body: unknown, fallbackText = ""): ApiError {
  const info = parseErrorInfo(body);
  if (info !== undefined) return new ApiError(status, info);
  return new ApiError(status, {
    code: STATUS_TO_CODE.get(status) ?? `http_${status}`,
    message: fallbackText !== "" ? fallbackText : `HTTP ${status}`,
  });
}
