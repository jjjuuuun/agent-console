import type { BackendDescriptor } from "@agent-console/contracts";
import { messages as m } from "../../app/messages";
import { useNow } from "../../app/useNow";
import { BackendProbeButton } from "./BackendProbeButton";
import { useBackendProbe } from "./hooks";
import { ProbeResultBlock } from "./ProbeResultBlock";

/**
 * 로그인 성공 화면의 보조 [연결 테스트]. 카드와 같은 probe 호출(`useBackendProbe`)을 쓰고, 자동 호출은 없다.
 * 비용 안내는 백엔드가 준 문구(`probe_cost_note` → `cost_note`)가 있으면 그것을, 없으면 일반 문장을 보인다.
 */
export function LoginSuccessProbe({ backend }: { backend: BackendDescriptor }) {
  const t = m.backendReadiness;
  const probe = useBackendProbe(backend);
  const nowMs = useNow(true, 30_000);
  if (backend.capabilities?.probe !== true) return null;
  const note = backend.probe_cost_note || backend.cost_note || t.probeDialogBody;
  return (
    <>
      <div className="app-login-probe-row">
        <BackendProbeButton descriptor={backend} probe={probe} />
        <span className="app-muted" data-testid="login-probe-note">{note}</span>
      </div>
      <div aria-live="polite" className="app-login-probe-result">
        <ProbeResultBlock probe={probe} nowMs={nowMs} />
      </div>
    </>
  );
}
