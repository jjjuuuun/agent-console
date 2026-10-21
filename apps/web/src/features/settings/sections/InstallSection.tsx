import { Button } from "@agent-console/ui";
import { messages as m } from "../../../app/messages";
import { usePwaInstall, usePwaUpdate } from "../../../pwa/PwaContext";

/** 빌드 버전(Vite 정의 변수). 정의되지 않은 환경(테스트)에서는 `dev`. */
export const APP_VERSION: string = (import.meta.env["VITE_APP_VERSION"] as string | undefined) ?? "dev";

/** ⑤ 앱 설치(PWA): 실행 상태, 설치 버튼(또는 수동 안내), 업데이트, 알림 안내. */
export function InstallSection({ onApplyUpdate }: { onApplyUpdate: () => void }) {
  const install = usePwaInstall();
  const update = usePwaUpdate();
  const t = m.settings.install;
  return (
    <div className="app-install-section">
      <p role="status">{install.standalone ? t.runningStandalone : t.runningBrowser}</p>
      {install.standalone ? null : install.canPrompt ? (
        <Button variant="primary" onClick={() => void install.install()}>{t.button}</Button>
      ) : (
        <p className="app-muted">{t.manual}</p>
      )}
      <p className="app-muted">{t.version(APP_VERSION)}</p>
      {update.available ? (
        <p>
          {t.updateWaiting} <Button size="sm" onClick={onApplyUpdate}>{t.updateNow}</Button>
        </p>
      ) : null}
    </div>
  );
}
