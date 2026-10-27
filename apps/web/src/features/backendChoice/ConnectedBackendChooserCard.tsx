import { useNow } from "../../app/useNow";
import { ReadinessActionButtons, useBackendLogin } from "../backendLogin";
import { BackendProbeButton, LoginSuccessProbe, ProbeResultBlock, useBackendProbe, useBackendReadiness } from "../backendReadiness";
import { BackendChooserCard, type BackendChooserCardProps } from "./BackendChooserCard";
import type { BackendDescriptor } from "@agent-console/contracts";

function SelectedProbe({ backend }: { backend: BackendDescriptor }) {
  const probe = useBackendProbe(backend);
  const nowMs = useNow(true, 30_000);
  if (backend.capabilities?.probe !== true) return null;
  return (
    <div className="app-backend-probe">
      <BackendProbeButton descriptor={backend} probe={probe} />
      <div aria-live="polite">
        <ProbeResultBlock probe={probe} nowMs={nowMs} />
      </div>
    </div>
  );
}

/**
 * `BackendChooserCard`에 서버의 정적 점검 상태(칩·경고·해결 버튼)와 [연결 테스트]를 연결한다.
 * 상태를 읽지 못하면(모듈 꺼짐·오류) 칩 없이 기본 카드로 동작한다.
 */
export function ConnectedBackendChooserCard(props: Omit<BackendChooserCardProps, "readiness" | "renderSelectedExtra">) {
  const { readiness, recheck } = useBackendReadiness();
  const login = useBackendLogin({ backends: props.options, onSettled: (id) => void recheck(id), renderSuccessExtra: (b) => <LoginSuccessProbe backend={b} /> });
  return (
    <>
      <BackendChooserCard
        {...props}
        readiness={readiness}
        renderSelectedExtra={(b) => (
          <>
            <ReadinessActionButtons actions={readiness[b.id]?.actions?.filter((a) => a.kind === "login")} onAction={(a) => login.run(b.id, a)} />
            <SelectedProbe backend={b} />
          </>
        )}
      />
      {login.dialogs}
    </>
  );
}
