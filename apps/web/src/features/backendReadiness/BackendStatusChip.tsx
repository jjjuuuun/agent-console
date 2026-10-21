import type { BackendReadiness } from "@agent-console/contracts";
import { StatusIcon } from "@agent-console/ui";
import { messages as m } from "../../app/messages";
import { READINESS_TONES, resolveTone } from "./tones";

export interface BackendStatusChipProps {
  readiness: BackendReadiness;
  /** 접근성 이름에 쓸 백엔드 이름 */
  title: string;
}

/** 선택 카드 항목의 짧은 상태 칩: 톤 아이콘 + `short_summary`(없으면 `summary`). 툴팁은 `summary` 전문. */
export function BackendStatusChip({ readiness, title }: BackendStatusChipProps) {
  const tone = resolveTone(readiness.tone);
  const full = readiness.summary || m.backendReadiness.unknownSummary;
  const text = readiness.short_summary || full;
  return (
    <span className="app-readiness-chip" data-tone={tone} title={full} data-testid="backend-status-chip">
      <StatusIcon status={READINESS_TONES[tone].icon} size={14} />
      <span className="ac-ellipsis">{text}</span>
      <span className="ac-sr-only">{m.backendReadiness.chipLabel(title, full)}</span>
    </span>
  );
}
