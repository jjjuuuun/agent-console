import { Gauge, TrustBadge } from "@agent-console/ui";
import { formatDateTime, formatRelative } from "../../lib/format";
import { InfoHint, describeValue } from "./cardParts";
import { formatShortClock } from "./resetDisplay";
import { usageMessages as t } from "./messages";
import { Badge } from "@agent-console/ui";
import { formatRatio, isStaleObservation, resetState, type WindowGroup } from "./usageLib";

export interface TrustGroupCardProps {
  /** 묶음의 신뢰 등급 값(출처 디스크립터 원문) */
  trust: string;
  /** 이 등급의 창들(입력 순서대로 행이 된다) */
  rows: readonly WindowGroup[];
  /** 창 id·대표 출처 → 표시 이름 */
  nameOf(group: WindowGroup): string;
  sourceInfo(id: string): { title: string; trust: string };
  /** 격자에 공식 창 카드가 하나라도 있는가(기준 부제를 정한다) */
  hasOfficialCard: boolean;
  nowMs: number;
  /** 설정 `usage.stale_after_seconds`. null이면 오래된 관측을 판정하지 않는다 */
  staleAfterSeconds?: number | null | undefined;
}

/** 공식이 아닌 한 등급의 창들을 행으로 모은 카드. 행 값: `N% 사용` → 상태 라벨 → `토큰 n` → `–`. */
export function TrustGroupCard({ trust, rows, nameOf, sourceInfo, hasOfficialCard, nowMs, staleAfterSeconds }: TrustGroupCardProps) {
  const nowSec = nowMs / 1000;
  const title = t.group.title[trust] ?? t.group.titleFallback(t.trust[trust] ?? (trust === "" ? t.common.unknown : trust));
  const basis = hasOfficialCard ? t.group.basisReference : t.group.basisPrimary;
  const first = rows[0]?.primary;
  const sameFooter = first !== undefined && rows.every((r) => r.primary.source === first.source && formatRelative(r.primary.observed_at, nowMs) === formatRelative(first.observed_at, nowMs));
  return (
    <section className="usage-card usage-group" role="group" aria-label={`${title}, ${basis}`}>
      <header className="usage-card-head">
        <h3 className="usage-card-title ac-ellipsis" title={title}>{title}</h3>
        <TrustBadge trust={trust} label={t.trust[trust] ?? trust} />
      </header>
      <p className="usage-group-basis app-muted">{basis}</p>
      <ul className="usage-group-rows">
        {rows.map((g) => {
          const s = g.primary;
          const name = nameOf(g);
          const v = describeValue(s, name, g.fellBack);
          const src = sourceInfo(s.source);
          const reset = resetState(s.resets_at, nowSec);
          const rowTip = sameFooter ? undefined : `${src.title} · ${t.cards.observedAt(formatRelative(s.observed_at, nowMs))}`;
          const valueText = v.kind === "tokens" ? v.tokensLine ?? v.headline : v.kind === "none" ? t.group.noValueRow : v.headline;
          return (
            <li key={g.window} className="usage-group-row" aria-label={`${name}, ${v.aria}`} title={rowTip}>
              <span className="usage-group-name app-muted ac-ellipsis" title={name}>{name}</span>
              <span className="usage-group-value">
                <span className={v.kind === "ratio" || v.kind === "status" ? "usage-row-val ac-num" : "usage-none ac-num"}>{valueText}</span>
                {s.used_ratio != null ? <span className="usage-group-gauge"><Gauge value={s.used_ratio} stale={reset === "passed"} label={t.cards.gaugeLabel(name)} noValueLabel={t.cards.noRatio} valueText={formatRatio(s.used_ratio)} /></span> : null}
                {isStaleObservation(s.observed_at, nowSec, staleAfterSeconds) ? <Badge tone="warning">▲ {t.cards.staleChip}</Badge> : null}
                {v.kind === "ratio" && v.tokensLine ? <span className="app-muted ac-num usage-row-tokens">{v.tokensLine}</span> : null}
              </span>
              <span className="usage-group-reset app-muted ac-num" title={reset === "unknown" ? undefined : formatDateTime(s.resets_at as number)}>
                {reset === "future" ? formatShortClock(s.resets_at as number, nowSec) : reset === "passed" ? <span className="usage-warn">▲ {t.cards.resetsPassedShort}</span> : null}
              </span>
              <InfoHint lines={v.hidden} />
            </li>
          );
        })}
      </ul>
      {sameFooter && first !== undefined ? (
        <p className="usage-source app-muted usage-oneline" title={formatDateTime(first.observed_at)}>
          {t.cards.sourceLine(sourceInfo(first.source).title)} · {t.cards.observedAt(formatRelative(first.observed_at, nowMs))}
        </p>
      ) : null}
    </section>
  );
}
