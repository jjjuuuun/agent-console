import { useId, type ReactNode } from "react";
import type { BackendDescriptor, BackendReadiness, ReadinessAction } from "@agent-console/contracts";
import { IconButton, Spinner, StatusIcon } from "@agent-console/ui";
import { useAppMessages } from "../../app/appMessages";
import { FixButtons } from "../../app/fix";
import { ReadinessActionButtons } from "../backendLogin";
import { BackendProbeButton } from "./BackendProbeButton";
import type { ProbeView } from "./hooks";
import { ProbeResultBlock } from "./ProbeResultBlock";
import { PROBE_PASS_FRESH_MS, READINESS_TONES, resolveTone } from "./tones";
import { useFormat, useServerRender } from "../../i18n";

export interface BackendReadinessCardProps {
  descriptor: BackendDescriptor;
  /** 정적 점검 결과. 없으면(아직 못 읽음) 확인 불가로 그린다 */
  readiness: BackendReadiness | undefined;
  probe: ProbeView;
  onRecheck: () => void;
  rechecking?: boolean;
  nowMs: number;
  /** 서버가 준 동작(`readiness.actions`)을 눌렀을 때. 없으면 동작 버튼을 그리지 않는다 */
  onAction?: ((action: ReadinessAction) => void) | undefined;
  /** 카드 제목 바로 옆에 끼울 요소(예: [기본] 칩). 없으면 제목만 */
  titleExtra?: ReactNode;
  /** 카드 맨 아래에 끼울 요소(예: 모델 줄). 없으면 아무것도 그리지 않는다 */
  footer?: ReactNode;
}

/**
 * 실행 백엔드 한 줄 카드(설정). 상태 줄·해결 버튼·[연결 테스트]·결과 블록.
 * 표현 컴포넌트다: 상태 이름은 비교하지 않고 톤 표와 서버가 준 문구만 쓴다.
 */
export function BackendReadinessCard({ descriptor, readiness, probe, onRecheck, rechecking = false, nowMs, onAction, titleExtra, footer }: BackendReadinessCardProps) {
  const fmt = useFormat();
  const render = useServerRender();
  const m = useAppMessages();
  const t = m.backendReadiness;
  const titleId = useId();
  const tone = resolveTone(readiness?.tone);
  const view = READINESS_TONES[tone];
  const templates = readiness?.text_templates ?? {};
  const summary = readiness?.summary ? render(readiness.summary, templates["/summary"]) : t.unknownSummary;
  const canProbe = descriptor.capabilities?.probe === true;
  const passed = probe.result?.ok === true && probe.finishedAtMs !== null;
  const passedFresh = passed && probe.finishedAtMs !== null && nowMs - probe.finishedAtMs < PROBE_PASS_FRESH_MS;
  const fixes = tone === "error" || tone === "warn" ? (readiness?.fixes ?? []) : [];
  return (
    <section className="app-readiness" data-tone={tone} aria-labelledby={titleId} data-testid={`backend-readiness-${descriptor.id}`}>
      <header className="app-readiness-head">
        {titleExtra === undefined || titleExtra === null ? (
          <h3 id={titleId} className="app-block-title">{render(descriptor.title)}</h3>
        ) : (
          <span className="app-readiness-title">
            <h3 id={titleId} className="app-block-title">{render(descriptor.title)}</h3>
            {titleExtra}
          </span>
        )}
        <span className="app-readiness-actions">
          {onAction ? <ReadinessActionButtons actions={readiness?.actions} onAction={onAction} /> : null}
          {canProbe ? <BackendProbeButton descriptor={descriptor} probe={probe} /> : null}
        </span>
      </header>
      <p className="app-readiness-line" data-testid="readiness-line">
        {probe.running ? (
          <>
            <StatusIcon status="running" size={16} />
            <span role="status">{t.probeRunning}</span>
          </>
        ) : (
          <>
            <StatusIcon status={view.icon} size={16} />
            <span className="app-readiness-summary" data-tone={tone}>{summary}</span>
            {passed ? (
              <span className="app-readiness-pass">
                {passedFresh ? t.probePassed : t.probePassedAgo(fmt.relative(probe.finishedAtMs === null ? null : probe.finishedAtMs / 1000, nowMs))}
              </span>
            ) : null}
          </>
        )}
      </p>
      {readiness?.detail ? <p className="app-muted">{render(readiness.detail, templates["/detail"])}</p> : null}
      {descriptor.cost_note ? <p className="app-muted">{render(descriptor.cost_note)}</p> : null}
      {!canProbe ? <p className="app-muted">{t.probeUnsupported}</p> : null}
      <p className="app-muted app-readiness-checked">
        {t.checkedAt(fmt.relative(readiness?.checked_at ?? null, nowMs))}
        <IconButton
          size="sm"
          label={rechecking ? t.recheckBusy : t.recheck}
          disabled={rechecking || probe.running}
          icon={rechecking ? <Spinner /> : <span>↻</span>}
          onClick={onRecheck}
        />
      </p>
      {fixes.length > 0 ? <FixButtons fix={{ actions: fixes }} /> : null}
      {(readiness?.checks ?? []).length > 0 ? (
        <details className="app-details">
          <summary>{t.checks}</summary>
          <ul className="app-readiness-details">
            {(readiness?.checks ?? []).map((c, i) => (
              <li key={c.id}>
                {c.ok ? "✓" : "✗"} {render(c.title, templates[`/checks/${i}/title`])}
                {c.note ? <span className="app-muted"> — {render(c.note, templates[`/checks/${i}/note`])}</span> : null}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      <div aria-live="polite">
        <ProbeResultBlock probe={probe} nowMs={nowMs} />
      </div>
      {footer === undefined || footer === null ? null : footer}
    </section>
  );
}
