import { Button } from "@agent-console/ui";
import type { BackendConnectSummary } from "./context";
import { BackendConnectIcon } from "./BackendConnectBadge";
import "./backendConnect.css";

export interface BackendConnectChipProps {
  tone: BackendConnectSummary["tone"];
  /** 짧은 상태(말줄임 대상) */
  summary: string;
  /** 앞글자("백엔드") */
  label: string;
  /** 툴팁. `aria-label`은 보이는 글자(`label · summary`)로 시작하고 뒤에 이 문구를 덧붙인다(WCAG 2.5.3) */
  tip?: string;
  /** true면 글자 없이 아이콘만(좁은 머리). 머리 폭에 따른 줄이기는 CSS 컨테이너 쿼리가 따로 한다 */
  compact?: boolean;
  onClick: () => void;
}

/** 페이지 머리용 칩 단추: [상태 모양 · 백엔드 · 짧은 상태]. 표현 컴포넌트이며 데이터는 props로만 받는다. */
export function BackendConnectChip({ tone, summary, label, tip, compact = false, onClick }: BackendConnectChipProps) {
  const visible = `${label} · ${summary}`;
  const name = tip === undefined || tip === visible ? visible : `${visible}. ${tip}`;
  const title = tip ?? visible;
  return (
    <Button size="sm" variant="ghost" className="app-bc-chip" data-tone={tone} data-compact={compact ? "true" : undefined} aria-label={name} title={title} onClick={onClick} data-testid="backend-connect-chip">
      <span className="app-bc-chip-body">
        <BackendConnectIcon tone={tone} />
        <span className="app-bc-chip-label">{label}</span>
        <span className="app-bc-chip-status ac-ellipsis" aria-hidden="true">
          <span aria-hidden="true">· </span>
          {summary}
        </span>
      </span>
    </Button>
  );
}
