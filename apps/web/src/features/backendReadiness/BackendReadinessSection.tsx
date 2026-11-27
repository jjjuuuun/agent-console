import { useEffect, useRef, type ReactNode } from "react";
import { useLocation } from "react-router";
import type { BackendDescriptor } from "@agent-console/contracts";
import { Banner, Button } from "@agent-console/ui";
import { useAppMessages } from "../../app/appMessages";
import { useDescribeError } from "../../app/errors";
import { useNow } from "../../app/useNow";
import { useBackendLogin } from "../backendLogin";
import { BackendReadinessCard } from "./BackendReadinessCard";
import { useBackendProbe, useBackendReadiness } from "./hooks";
import { LoginSuccessProbe } from "./LoginSuccessProbe";
import { readinessShownBackends } from "./shown";

/** 준비 상태 섹션 제목의 앵커 id. 주소 해시 `#<섹션>/backend-readiness`로 오면 이 제목으로 스크롤하고 초점을 준다. */
export const BACKEND_READINESS_ANCHOR = "backend-readiness";

function ConnectedCard({ descriptor, ...rest }: { descriptor: BackendDescriptor } & Omit<React.ComponentProps<typeof BackendReadinessCard>, "descriptor" | "probe">) {
  const probe = useBackendProbe(descriptor);
  return <BackendReadinessCard descriptor={descriptor} probe={probe} {...rest} />;
}

export interface BackendReadinessSectionProps {
  backends: readonly BackendDescriptor[];
  /** 제목·안내 머리를 그릴지(기본 `shown`). 모달처럼 바깥에 이미 제목이 있으면 `hidden`(섹션의 접근성 이름은 유지) */
  heading?: "shown" | "hidden";
  /** 맨 위로 올릴 백엔드 id(보이는 목록에 있을 때만). 없으면 서버 순서 */
  defaultBackendId?: string | undefined;
  /** 카드 제목 옆에 끼울 요소 */
  titleExtra?: (backend: BackendDescriptor) => ReactNode;
  /** 카드 맨 아래에 끼울 요소. 아무것도 돌려주지 않으면 카드 높이는 그대로 */
  footer?: (backend: BackendDescriptor) => ReactNode;
}

/**
 * 설정 › 실행 백엔드: 백엔드마다 인증·준비 상태 카드. 상태 점검 능력이 있는 백엔드만 그린다.
 * 상태 API가 없으면(모듈 꺼짐) 아무것도 그리지 않는다.
 */
export function BackendReadinessSection({ backends, heading = "shown", defaultBackendId, titleExtra, footer }: BackendReadinessSectionProps) {
  const describeError = useDescribeError();
  const m = useAppMessages();
  const t = m.backendReadiness;
  const { readiness, error, refetch, recheck, rechecking, isPending, available } = useBackendReadiness();
  const nowMs = useNow(true, 30_000);
  const login = useBackendLogin({ backends, onSettled: (id) => void recheck(id), renderSuccessExtra: (b) => <LoginSuccessProbe backend={b} /> });
  const shownAll = readinessShownBackends(backends, readiness);
  const first = defaultBackendId === undefined ? undefined : shownAll.find((b) => b.id === defaultBackendId);
  const shown = first === undefined ? shownAll : [first, ...shownAll.filter((b) => b !== first)];
  const { hash } = useLocation();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const wantAnchor = heading === "shown" && hash.replace(/^#/, "").split("?")[0]?.split("/")[1] === BACKEND_READINESS_ANCHOR;
  const drawn = error === null && !isPending && available && shown.length > 0;
  useEffect(() => {
    if (!wantAnchor || !drawn) return;
    const el = headingRef.current;
    el?.scrollIntoView?.({ block: "start" });
    el?.focus({ preventScroll: true });
  }, [wantAnchor, drawn]);
  if (!available || (shown.length === 0 && error === null)) return null;
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
      {heading === "shown" ? (
        <>
          <h3 id={BACKEND_READINESS_ANCHOR} ref={headingRef} tabIndex={-1} className="app-block-title">{t.sectionTitle}</h3>
          <p className="app-muted">{t.sectionLead}</p>
        </>
      ) : null}
      {shown.map((b) => (
        <ConnectedCard
          key={b.id}
          descriptor={b}
          readiness={readiness[b.id]}
          nowMs={nowMs}
          rechecking={rechecking === b.id}
          onRecheck={() => void recheck(b.id)}
          onAction={(action) => login.run(b.id, action)}
          titleExtra={titleExtra?.(b)}
          footer={footer?.(b)}
        />
      ))}
      {login.dialogs}
    </section>
  );
}
