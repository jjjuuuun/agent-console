import { Icon, IconButton, Tooltip } from "@agent-console/ui";
import { BackendConnectIcon } from "./BackendConnectBadge";
import { useBackendConnectPhase, useBackendConnectSummary, useOpenBackendConnect } from "./context";
import "./backendConnect.css";

/** 단추가 사라졌을 때 초점을 돌려줄 대상 표식(모달을 닫은 뒤 폴백). */
export const BACKEND_CONNECT_TRIGGER_ATTR = "data-backend-connect-trigger";

/**
 * 사이드바 도구줄의 "백엔드 연결" 아이콘 단추(플러그 + 오른쪽 아래 상태 배지). 글자는 없고 툴팁 = `aria-label`.
 * 판정 전에는 같은 크기의 빈자리만 잡고, 숨김이면 아무것도 그리지 않는다(도구줄이 원래 모양으로 돌아간다).
 */
export function BackendConnectButton() {
  const phase = useBackendConnectPhase();
  const summary = useBackendConnectSummary();
  const open = useOpenBackendConnect();
  if (phase === "loading") return <span className="app-bc-slot" aria-hidden="true" data-testid="backend-connect-slot" />;
  if (summary === undefined || open === undefined) return null;
  return (
    <Tooltip placement="top" align="start" className="app-bc-tip" content={summary.tip}>
      <IconButton
        label={summary.tip}
        title=""
        size="md"
        className="app-bc-btn"
        {...{ [BACKEND_CONNECT_TRIGGER_ATTR]: "" }}
        data-testid="backend-connect-button"
        data-tone={summary.tone}
        icon={
          <>
            <Icon name="plug" />
            <span className="app-bc-badge" data-tone={summary.tone === "unavailable" ? "unknown" : summary.tone}>
              <BackendConnectIcon tone={summary.tone} />
            </span>
          </>
        }
        onClick={() => open()}
      />
    </Tooltip>
  );
}
