import type { BackendDescriptor, BackendReadiness } from "@agent-console/contracts";
import { visibleBackends } from "../../app/backendVisibility";

/**
 * 준비 상태 카드를 그릴 백엔드: 보이는 백엔드 중 상태 점검·연결 테스트 능력이 있거나 이미 상태 응답이 있는 것.
 * 설정의 준비 상태 섹션과 "백엔드 연결" 바로가기(도구줄·사용량·명령)가 같은 판정을 쓴다. 백엔드 id는 보지 않는다.
 */
export function readinessShownBackends<T extends Pick<BackendDescriptor, "id" | "ui_hints" | "capabilities">>(
  backends: readonly T[],
  readiness: Readonly<Record<string, BackendReadiness | undefined>>,
): T[] {
  return visibleBackends(backends).filter((b) => b.capabilities?.status === true || b.capabilities?.probe === true || readiness[b.id] !== undefined);
}
