import { useId, useState, type ReactNode } from "react";
import type { BackendDescriptor, BackendReadiness } from "@agent-console/contracts";
import { Badge, Banner, Button } from "@agent-console/ui";
import { messages as m } from "../../app/messages";
import { FixButtons } from "../../app/fix";
import { BackendStatusChip, resolveTone } from "../backendReadiness";

export interface BackendChooserCardProps {
  /** 고를 수 있는 백엔드(서버 디스크립터). 항목·설명·비용 문구·배지는 전부 이 데이터다 */
  options: readonly BackendDescriptor[];
  /** 백엔드가 비어 있는 노드의 화면 이름(문구에만 쓴다) */
  nodeLabels?: readonly string[];
  /** `resolve`(기본): 값이 없어 고르는 카드. `change`: 이미 값이 있는 상태에서 바꾸는 카드(문구만 다르다) */
  mode?: "resolve" | "change";
  /** 고르고 [선택하고 계속]을 눌렀을 때. 저장·재전송은 호출자가 한다 */
  onConfirm: (backendId: string) => void;
  /** 미리 고를 백엔드 id(현재 값). 목록에 있을 때만 쓴다 */
  initialId?: string | null | undefined;
  /** 저장·재전송 중 */
  busy?: boolean;
  /** 직전 시도 실패 문구 */
  error?: string | undefined;
  className?: string;
  /** 설명 문장 덮어쓰기(기본은 "같은 메시지를 다시 보냅니다"). 채팅이 아닌 곳(팀 편집기)에서 쓴다 */
  explain?: string | undefined;
  /** 저장 중 버튼 문구 덮어쓰기 */
  busyLabel?: string | undefined;
  /** 백엔드 id별 정적 점검 상태. 있으면 항목마다 상태 칩을 붙이고, 선택한 항목이 error 톤이면 경고와 해결 버튼을 보인다(선택은 막지 않는다) */
  readiness?: Readonly<Record<string, BackendReadiness>> | undefined;
  /** 선택된 항목 아래에 그릴 보조 영역(예: [연결 테스트]) */
  renderSelectedExtra?: ((backend: BackendDescriptor) => ReactNode) | undefined;
}

/**
 * 실행 백엔드 해결 카드. 처음 선택은 없다(비용이 걸린 선택을 실수로 하지 않게). 디스크립터가 하나뿐이면 그것을 미리 고른다.
 * 서버·화면을 모르는 표현 컴포넌트다(데이터와 콜백만 받는다).
 */
export function BackendChooserCard({ options, nodeLabels = [], mode = "resolve", initialId, onConfirm, busy = false, error, className, explain, busyLabel, readiness, renderSelectedExtra }: BackendChooserCardProps) {
  const t = m.backendChooser;
  const name = useId();
  const [picked, setPicked] = useState<string | null>(options.some((o) => o.id === initialId) ? (initialId ?? null) : options.length === 1 ? (options[0]?.id ?? null) : null);
  return (
    <section className={["app-backend-card", className].filter(Boolean).join(" ")} aria-labelledby={`${name}-title`} data-testid="backend-chooser">
      <h3 id={`${name}-title`} className="app-block-title">{t.title}</h3>
      <p className="ac-text">{mode === "change" ? t.leadChange : t.lead(nodeLabels)}</p>
      {options.length === 0 ? (
        <Banner tone="warning">{m.settings.backendNone}</Banner>
      ) : (
        <>
          <p className="app-muted">{explain ?? (mode === "change" ? t.explainChange : t.explain)}</p>
          <fieldset className="app-backend-options" disabled={busy}>
            <legend className="ac-sr-only">{t.group}</legend>
            {options.map((b) => {
              const badge = b.ui_hints?.badge;
              const ready = readiness?.[b.id];
              const selected = picked === b.id;
              return (
                <div key={b.id} className="app-backend-entry">
                <label className="app-backend-option" data-checked={picked === b.id ? "true" : undefined}>
                  <input type="radio" name={name} value={b.id} checked={picked === b.id} onChange={() => setPicked(b.id)} />
                  <span className="app-backend-option-body">
                    <strong>{b.title}</strong>
                    {badge ? <Badge>{badge}</Badge> : null}
                    {ready ? <BackendStatusChip readiness={ready} title={b.title} /> : null}
                    {b.cost_note ? <span className="app-muted app-backend-cost">{b.cost_note}</span> : null}
                    {b.description ? <span className="app-muted">{b.description}</span> : null}
                  </span>
                </label>
                {selected && ready && resolveTone(ready.tone) === "error" ? (
                  <div className="app-backend-warn" data-testid="backend-chooser-warn">
                    <Banner tone="warning">{m.backendReadiness.chooserWarn} {ready.summary}</Banner>
                    <FixButtons fix={{ actions: ready.fixes ?? [] }} />
                  </div>
                ) : null}
                {selected && renderSelectedExtra ? <div className="app-backend-extra">{renderSelectedExtra(b)}</div> : null}
                </div>
              );
            })}
          </fieldset>
          <p className="app-muted">{t.saveNote}</p>
          <p className="app-muted">{t.perNode}</p>
          {error ? <Banner tone="danger">{error}</Banner> : null}
          <div className="app-backend-actions">
            <Button variant="primary" disabled={picked === null || busy} onClick={() => picked !== null && onConfirm(picked)}>
              {busy ? (busyLabel ?? t.submitting) : t.submit}
            </Button>
          </div>
        </>
      )}
    </section>
  );
}
