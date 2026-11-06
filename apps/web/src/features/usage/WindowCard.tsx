import { useId, useState } from "react";
import { Badge, Gauge, TrustBadge } from "@agent-console/ui";
import { formatDateTime, formatRelative } from "../../lib/format";
import { InfoHint, describeValue } from "./cardParts";
import { formatResetLine } from "./resetDisplay";
import { usageMessages as t } from "./messages";
import { formatRatio, isStaleObservation, resetState, type WindowGroup } from "./usageLib";
import type { UsageWindowSnapshot } from "@agent-console/contracts";

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

/** 다른 출처 목록 한 줄의 값 글자. */
function otherValueText(o: UsageWindowSnapshot, name: string): string {
  const v = describeValue(o, name);
  return v.tokensLine && v.kind !== "tokens" ? `${v.headline} · ${v.tokensLine}` : v.kind === "tokens" ? v.tokensLine ?? v.headline : v.headline;
}

/** 공식 값을 가진 창 하나의 카드. 헤드라인은 `N% 사용` 하나이고, 값이 없는 쪽은 그리지 않는다(지어내지 않음). */
export function WindowCard({ name, group, sourceInfo, nowMs, staleAfterSeconds }: WindowCardProps) {
  const s = group.primary;
  const nowSec = nowMs / 1000;
  const src = sourceInfo(s.source);
  const [open, setOpen] = useState(false);
  const othersId = useId();
  const reset = resetState(s.resets_at, nowSec);
  const stale = isStaleObservation(s.observed_at, nowSec, staleAfterSeconds);
  const oldValue = reset === "passed";
  const v = describeValue(s, name, group.fellBack);
  const resetLine = reset === "future" ? formatResetLine(s.resets_at as number, nowSec, { line: t.cards.resetsLine }) : undefined;
  const label = t.cards.ariaLabel(name, v.aria, reset === "passed" ? t.cards.resetsPassed : (resetLine?.text ?? ""));

  return (
    <section className="usage-card" role="group" aria-label={label} data-old={oldValue ? "true" : undefined} data-stale={stale ? "true" : undefined}>
      <header className="usage-card-head">
        <h3 className="usage-card-title ac-ellipsis" title={name}>{name}</h3>
        {stale ? <Badge tone="warning">▲ {t.cards.staleChip}</Badge> : null}
        <TrustBadge trust={src.trust} label={t.trust[src.trust] ?? src.trust} />
      </header>
      <div className="usage-value">
        <div className="usage-headline">
          <span className={v.kind === "ratio" || v.kind === "status" ? "usage-big ac-num" : v.kind === "tokens" ? "usage-big-muted" : "usage-none"}>{v.headline}</span>
          {v.chip ? <Badge tone={v.chip.tone}>{v.chip.label}</Badge> : null}
        </div>
        {s.used_ratio != null ? <Gauge value={s.used_ratio} stale={stale || oldValue} label={t.cards.gaugeLabel(name)} noValueLabel={t.cards.noRatio} valueText={formatRatio(s.used_ratio)} /> : null}
        {v.tokensLine ? <span className="usage-tokens app-muted ac-num" title={s.used_tokens != null ? s.used_tokens.toLocaleString("ko-KR") : undefined}>{v.tokensLine}</span> : null}
      </div>
      {reset === "passed" ? (
        <p className="usage-reset usage-warn">▲ {t.cards.resetsPassed}</p>
      ) : resetLine ? (
        <p className="usage-reset usage-oneline" title={resetLine.full}>{resetLine.text}</p>
      ) : null}
      <p className="usage-source app-muted">
        <span className="usage-oneline">
          {t.cards.sourceLine(src.title)} · <span title={formatDateTime(s.observed_at)}>{t.cards.observedAt(formatRelative(s.observed_at, nowMs))}</span>
        </span>
        <InfoHint lines={v.hidden} />
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
                    <TrustBadge trust={info.trust} label={t.trust[info.trust] ?? info.trust} /> <span>{info.title}</span> · <span className="ac-num">{otherValueText(o, name)}</span> ·{" "}
                    <span className="app-muted" title={formatDateTime(o.observed_at)}>{t.cards.observedAt(formatRelative(o.observed_at, nowMs))}</span>
                  </li>
                );
              })}
            </ul>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
