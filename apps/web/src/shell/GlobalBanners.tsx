import { Banner, Button } from "@agent-console/ui";
import { CONTRACTS_VERSION } from "@agent-console/contracts";
import { useApi } from "../app/ApiContext";
import { useAppStatus } from "../app/AppStatus";
import { messages as m } from "../app/messages";
import { contractsCompat } from "./contractsCompat";

/**
 * 화면 영역 맨 위에 쌓는 전역 배너: 인증 만료, 서버·웹 계약 버전 불일치.
 * 버전 배너는 호환되지 않을 때만(`contractsCompat`, 패치 차이는 호환) 두 값과 조치를 보인다.
 * 새로고침 버튼은 서버가 낡았다고 판정되면 효과가 없으므로 그때는 두지 않는다.
 */
export function GlobalBanners() {
  const { authRejected, reload } = useAppStatus();
  const { meta } = useApi();
  const compat = contractsCompat(meta.contractsVersion, CONTRACTS_VERSION);
  const mismatch = !compat.compatible;
  if (!authRejected && !mismatch) return null;
  const action = (
    <Button size="sm" onClick={reload}>
      {m.boot.reload}
    </Button>
  );
  const older = compat.compatible ? null : compat.older;
  const fix = older === "server" ? m.boot.versionFixServer : older === "web" ? m.boot.versionFixWeb : m.boot.versionFixUnknown;
  return (
    <div className="app-banners">
      {authRejected ? (
        <Banner tone="danger" aria-label={m.boot.authRegion} actions={action}>
          {m.boot.authExpired}
        </Banner>
      ) : null}
      {mismatch ? (
        <Banner tone="warning" aria-label={m.boot.versionRegion} actions={older === "server" ? undefined : action}>
          {m.boot.versionMismatch(meta.contractsVersion, CONTRACTS_VERSION)} {fix}
        </Banner>
      ) : null}
    </div>
  );
}
