import type { BackendLoginPhase } from "@agent-console/contracts";

/** 더 이상 바뀌지 않는 단계(폴링을 멈춘다). 단계 이름은 계약의 열거형이다. */
const TERMINAL: ReadonlySet<BackendLoginPhase> = new Set<BackendLoginPhase>(["succeeded", "failed", "cancelled", "expired"]);

export function isTerminalPhase(phase: BackendLoginPhase): boolean {
  return TERMINAL.has(phase);
}

/** 웹이 그릴 줄 아는 동작 종류(`ReadinessAction.kind`). 모르는 값은 그리지 않는다. */
export const KNOWN_ACTION_KINDS: readonly string[] = ["login", "logout"];

/** 남은 시간 `m:ss`. */
export function formatRemaining(expiresAtSec: number, nowMs: number): string {
  const left = Math.max(0, Math.ceil(expiresAtSec - nowMs / 1000));
  return `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
}

/** 로그인 링크를 새 탭으로 열어도 되는가(https만). 허용 호스트는 서버가 이미 걸렀다. */
export function isOpenableUrl(url: string | null | undefined): url is string {
  return typeof url === "string" && url.startsWith("https://");
}
