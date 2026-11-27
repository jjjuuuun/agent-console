import { StatusIcon } from "@agent-console/ui";
import { READINESS_TONES } from "../backendReadiness";
import type { BackendConnectSummary } from "./context";
import "./backendConnect.css";

/**
 * 톤 → `StatusIcon`의 상태 이름. 네 톤은 준비 상태 카드가 쓰는 같은 표(`READINESS_TONES`)에서 오고,
 * 확인 중은 회전 호, 조회 실패는 물음표(알 수 없음)다. 색이 아니라 모양으로도 구별된다(warn = 정지, unknown = 물음표).
 */
export function badgeStatus(tone: BackendConnectSummary["tone"]): string {
  if (tone === "checking") return "running";
  if (tone === "unavailable") return READINESS_TONES.unknown.icon;
  return READINESS_TONES[tone].icon;
}

/** 톤이 `data-tone`인 상태 모양(12px). 장식이다: 읽는 이름은 바깥 단추가 가진다. */
export function BackendConnectIcon({ tone, className }: { tone: BackendConnectSummary["tone"]; className?: string }) {
  return <StatusIcon status={badgeStatus(tone)} size={14} className={className} data-tone={tone === "unavailable" ? "unknown" : tone} />;
}
