import { useId, useState } from "react";
import type { UsageWindowSnapshot } from "@agent-console/contracts";
import { Badge, Gauge, TrustBadge } from "@agent-console/ui";
import { formatDateTime, formatRelative } from "../../lib/format";
import { compactCount } from "./indicatorText";
import { futureResetsText } from "./resetDisplay";
import { usageMessages as t } from "./messages";
import { formatRatio, isStaleObservation, resetState, type PrimaryRule, type WindowGroup } from "./usageLib";

export interface WindowCardProps {
  /** 표시 이름(호출자가 `windowDisplayName`으로 해석: 사용자 → 출처 → 폴백) */
  name: string;
  group: WindowGroup;
  /** 출처 id → 표시 정보 */
  sourceInfo(id: string): { title: string; trust: string };
  /** 지금(ms, 주입) */
  nowMs: number;
  /** 설정 `usage.stale_after_seconds`. null이면 오래된 관측을 판정하지 않는다 */
  staleAfterSeconds: number | null | undefined;
}

const RULE_TEXT: Record<PrimaryRule, string> = {
  order: t.cards.ruleOrder,
  "recent-official": t.cards.ruleRecentOfficial,
  recent: t.cards.ruleRecent,
};

function statusView(status: string | null | undefined) {
  if (status == null || status === "") return undefined;
  const known = t.status[status];
  return { label: known?.label ?? status, tone: known?.tone };
}

function valueText(s: UsageWindowSnapshot): string {
  if (s.used_ratio != null) return t.cards.usedValue(formatRatio(s.used_ratio));
  const st = statusView(s.status);
  if (st) return st.label;
  if (s.used_tokens != null) return t.cards.tokensUsed(compactCount(s.used_tokens));
  return t.cards.noValue;
}

/** 창 하나의 카드. 값이 없는 쪽은 그리지 않고(지어내지 않음), 초기화·관측 시각·출처 신뢰 등급을 사실대로 보여 준다. */
export function WindowCard({ name, group, sourceInfo, nowMs, staleAfterSeconds }: WindowCardProps) {
  const s = group.primary;
  const nowSec = nowMs / 1000;
  const src = sourceInfo(s.source);
  const [open, setOpen] = useState(false);
  const othersId = useId();
  const reset = resetState(s.resets_at, nowSec);
  const stale = isStaleObservation(s.observed_at, nowSec, staleAfterSeconds);
  const oldValue = reset === "passed";
  const st = statusView(s.status);
  const resetsText =
    reset === "unknown" ? t.cards.resetsUnknown : reset === "passed" ? t.cards.resetsPassed : futureResetsText(s.resets_at as number, nowSec);
  const label = t.cards.ariaLabel(name, valueText(s), resetsText);

  const valueArea =
    s.used_ratio != null ? (
      <div className="usage-value">
        <span className="usage-big ac-num">{t.cards.usedValue(formatRatio(s.used_ratio))}</span>
        {st ? <Badge tone={st.tone}>{st.label}</Badge> : null}
        <Gauge value={s.used_ratio} stale={stale || oldValue} label={t.cards.gaugeLabel(name)} noValueLabel={t.cards.noRatio} valueText={formatRatio(s.used_ratio)} />
      </div>
    ) : st ? (
      <div className="usage-value">
        <span className="usage-big">{st.label}</span>
        <Gauge label={t.cards.gaugeLabel(name)} noValueLabel={t.cards.statusOnly} />
      </div>
    ) : (
      <div className="usage-value">
        {s.used_tokens != null ? (
          <>
            <span className="usage-big ac-num" title={s.used_tokens.toLocaleString("ko-KR")}>{t.cards.tokensUsed(compactCount(s.used_tokens))}</span>
            <span className="usage-none">{t.cards.noLimit}</span>
          </>
        ) : (
          <span className="usage-none">{t.cards.noValue}</span>
        )}
      </div>
    );

  return (
    <section className="usage-card" role="group" aria-label={label} data-old={oldValue ? "true" : undefined} data-stale={stale ? "true" : undefined}>
      <header className="usage-card-head">
        <h3 className="usage-card-title ac-ellipsis" title={name}>{name}</h3>
        {stale ? <Badge tone="warning">▲ {t.cards.staleChip}</Badge> : null}
        <TrustBadge trust={src.trust} label={t.trust[src.trust] ?? src.trust} />
      </header>
      {valueArea}
      <p className={reset === "passed" ? "usage-reset usage-warn" : "usage-reset"}>{reset === "passed" ? "▲ " : ""}{resetsText}</p>
      <p className="usage-source app-muted">
        <span className="ac-ellipsis">{t.cards.sourceLine(src.title)}</span> · <span title={formatDateTime(s.observed_at)}>{t.cards.observedAt(formatRelative(s.observed_at, nowMs))}</span>
      </p>
      {group.others.length > 0 ? (
        <div className="usage-others">
          <button type="button" className="app-link-btn" aria-expanded={open} aria-controls={othersId} onClick={() => setOpen(!open)}>
            {open ? "▾" : "▸"} {t.cards.otherSources(group.others.length)}
          </button>
          {open ? (
            <ul id={othersId} className="usage-others-list">
              {group.others.map((o) => {
                const info = sourceInfo(o.source);
                return (
                  <li key={o.source}>
                    <TrustBadge trust={info.trust} label={t.trust[info.trust] ?? info.trust} /> <span>{info.title}</span> · <span className="ac-num">{valueText(o)}</span> ·{" "}
                    <span className="app-muted" title={formatDateTime(o.observed_at)}>{t.cards.observedAt(formatRelative(o.observed_at, nowMs))}</span>
                  </li>
                );
              })}
            </ul>
          ) : null}
        </div>
      ) : null}
      <p className="app-muted usage-rule">{RULE_TEXT[group.rule]}{group.fellBack ? ` — ${t.cards.ruleFallback}` : ""}</p>
    </section>
  );
}
