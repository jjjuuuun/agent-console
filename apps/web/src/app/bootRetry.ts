import { ApiError, NETWORK_ERROR_CODE } from "@agent-console/api-client";
import { BootError } from "./boot";

/**
 * 부팅 자동 재시도 정책(데이터). 서버가 아직 켜지는 중이면 사용자가 새로고침하지 않아도 저절로 붙는다.
 * 앱 호출자가 `AppRoot`의 `bootRetry`로 바꿀 수 있다.
 */
export interface BootRetryPolicy {
  /** 첫 재시도까지 기다림 */
  initialMs: number;
  /** 재시도 간격 상한 */
  maxMs: number;
  /** 간격 배수 */
  factor: number;
  /** 이 시간 동안 계속 실패하면 자동 재시도를 멈추고 오류 화면([다시 시도]·[새로고침])을 보인다. 0이면 바로 오류 */
  giveUpMs: number;
}

export const BOOT_RETRY: BootRetryPolicy = { initialMs: 500, maxMs: 5000, factor: 2, giveUpMs: 60_000 };

/**
 * 부팅 실패 분류.
 * - `not-ready`: 서버가 응답했지만 준비 전(503 `not_ready`) — "서버 준비 중"
 * - `unreachable`: 아직 연결이 안 됨(연결 거부·프록시 5xx 등) — "서버 연결 대기"
 * - `fatal`: 기다려도 소용없는 오류(4xx, 계약 위반 등) — 바로 오류 화면
 */
export type BootFailureKind = "not-ready" | "unreachable" | "fatal";

export function classifyBootFailure(error: unknown): BootFailureKind {
  const cause = error instanceof BootError ? error.cause : error;
  if (!(cause instanceof ApiError)) return "fatal";
  if (cause.status === 503 && cause.code === "not_ready") return "not-ready";
  if (cause.code === NETWORK_ERROR_CODE || cause.status >= 500) return "unreachable";
  return "fatal";
}

/** `attempt`(0부터)번째 재시도 전 대기(ms). */
export function bootRetryDelay(policy: BootRetryPolicy, attempt: number): number {
  return Math.min(policy.maxMs, policy.initialMs * policy.factor ** attempt);
}
