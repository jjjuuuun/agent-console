import { Banner, Button } from "@agent-console/ui";
import { CONTRACTS_VERSION } from "@agent-console/contracts";
import { useApi } from "../app/ApiContext";
import { useAppStatus } from "../app/AppStatus";
import { messages as m } from "../app/messages";

/** 화면 영역 맨 위에 쌓는 전역 배너: 인증 만료, 서버·웹 계약 버전 불일치. */
export function GlobalBanners() {
  const { authRejected, reload } = useAppStatus();
  const { meta } = useApi();
  const mismatch = meta.contractsVersion !== "" && meta.contractsVersion !== CONTRACTS_VERSION;
  if (!authRejected && !mismatch) return null;
  const action = (
    <Button size="sm" onClick={reload}>
      {m.boot.reload}
    </Button>
  );
  return (
    <div className="app-banners">
      {authRejected ? (
        <Banner tone="danger" aria-label={m.boot.authRegion} actions={action}>
          {m.boot.authExpired}
        </Banner>
      ) : null}
      {mismatch ? (
        <Banner tone="warning" aria-label={m.boot.versionRegion} actions={action}>
          {m.boot.versionMismatch}
        </Banner>
      ) : null}
    </div>
  );
}
