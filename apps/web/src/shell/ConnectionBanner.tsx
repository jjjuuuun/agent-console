import { Button, Icon } from "@agent-console/ui";
import { messages as m } from "../app/messages";
import type { ConnectionBannerView } from "../app/connectionBanner";

export interface ConnectionBannerProps {
  /** null이면 아무것도 그리지 않는다 */
  view: ConnectionBannerView | null;
  onRetry: () => void;
  onReload: () => void;
}

/**
 * 앱 서버(브라우저 ↔ 로컬 서버 WebSocket) 연결 문제 띠. 정상일 때는 없다.
 * 문구 표는 `messages.connection.banner`, 표시 여부·타이밍은 `useConnectionBanner`가 정한다.
 */
export function ConnectionBanner({ view, onRetry, onReload }: ConnectionBannerProps) {
  const t = m.connection.banner;
  // live region은 항상 있어야 상태 변화가 낭독된다
  return (
    <div className="app-conn-slot" role={view?.tone === "danger" ? "alert" : "status"} aria-live="polite" aria-label={t.region}>
      {view === null ? null : (
        <div className="app-conn-banner" data-tone={view.tone} data-kind={view.kind}>
          <Icon name={view.tone === "success" ? "check" : "triangle-alert"} />
          <span className="app-conn-banner-text">{t[view.kind]}</span>
          {view.canRetry ? (
            <Button size="sm" disabled={view.retryBusy} onClick={onRetry}>
              {view.retryBusy ? t.retryBusy : t.retry}
            </Button>
          ) : null}
          {view.canReload ? (
            <Button size="sm" onClick={onReload}>
              {t.reload}
            </Button>
          ) : null}
        </div>
      )}
    </div>
  );
}
