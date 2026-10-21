import type { BackendDescriptor } from "@agent-console/contracts";
import { Banner, Button } from "@agent-console/ui";
import { messages as m } from "../../app/messages";
import { describeError } from "../../app/errors";
import { useNow } from "../../app/useNow";
import { BackendReadinessCard } from "./BackendReadinessCard";
import { useBackendProbe, useBackendReadiness } from "./hooks";

function ConnectedCard({ descriptor, ...rest }: { descriptor: BackendDescriptor } & Omit<React.ComponentProps<typeof BackendReadinessCard>, "descriptor" | "probe">) {
  const probe = useBackendProbe(descriptor);
  return <BackendReadinessCard descriptor={descriptor} probe={probe} {...rest} />;
}

export interface BackendReadinessSectionProps {
  backends: readonly BackendDescriptor[];
}

/**
 * 설정 › 실행 백엔드: 백엔드마다 인증·준비 상태 카드. 상태 점검 능력이 있는 백엔드만 그린다.
 * 상태 API가 없으면(모듈 꺼짐) 아무것도 그리지 않는다.
 */
export function BackendReadinessSection({ backends }: BackendReadinessSectionProps) {
  const t = m.backendReadiness;
  const { readiness, error, refetch, recheck, rechecking, isPending } = useBackendReadiness();
  const nowMs = useNow(true, 30_000);
  const shown = backends.filter((b) => b.capabilities?.status === true || b.capabilities?.probe === true || readiness[b.id] !== undefined);
  if (shown.length === 0 && error === null) return null;
  if (error !== null) {
    return (
      <Banner tone="warning" actions={<Button size="sm" onClick={() => void refetch()}>{m.common.retry}</Button>}>
        {t.loadFailed} <span className="app-muted">{describeError(error, "").message}</span>
      </Banner>
    );
  }
  if (isPending) return null;
  return (
    <section className="app-readiness-section" aria-label={t.sectionTitle} data-testid="backend-readiness-section">
      <h3 className="app-block-title">{t.sectionTitle}</h3>
      <p className="app-muted">{t.sectionLead}</p>
      {shown.map((b) => (
        <ConnectedCard key={b.id} descriptor={b} readiness={readiness[b.id]} nowMs={nowMs} rechecking={rechecking === b.id} onRecheck={() => void recheck(b.id)} />
      ))}
    </section>
  );
}
