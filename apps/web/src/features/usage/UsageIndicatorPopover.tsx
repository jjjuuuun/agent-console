import { Gauge } from "@agent-console/ui";
import { formatDateTime, formatRelative } from "../../lib/format";
import { itemFlags, itemValueText } from "./indicatorText";
import { usageIndicatorMessages as t, usageMessages as u } from "./messages";
import { SourceLine } from "./UsageIndicatorView";
import { futureResetsText } from "./resetDisplay";
import { indicatorFill, plainText, type IndicatorItem } from "./usageLib";

export interface UsageIndicatorPopoverProps {
  id: string;
  /** 보일 항목(관측된 모든 창, 호출자가 개수 제한) */
  items: readonly IndicatorItem[];
  /** 개수 제한으로 못 보인 창 수 */
  hiddenCount: number;
  valueMode: string;
  nowMs: number;
  /** 데이터를 마지막으로 받은 시각(ms). 없으면 생략 */
  updatedAtMs?: number | undefined;
  sourceInfo: (id: string) => { title: string; trust: string };
  /** 오류 난 출처 수 / 대표값에서 접힌 다른 출처 스냅샷 수 */
  sourceErrors: number;
  otherCount: number;
  emptyText?: string | undefined;
  /** 사이드바 배치면 오른쪽, 플로팅이면 위/아래 */
  side?: "right" | "up";
  /** 남은 양을 사용 옆에 함께 보일지(기본 꺼짐: 사용 기준 하나만) */
  showRemaining?: boolean | undefined;
}

/** 요약 팝오버(읽기 전용, 비대화형). 표시 대상 창이 아니라 관측된 모든 창을 보여 준다. */
export function UsageIndicatorPopover(p: UsageIndicatorPopoverProps) {
  const nowSec = p.nowMs / 1000;
  return (
    <div id={p.id} className="usage-ind-pop" role="group" aria-label={t.popoverTitle} data-side={p.side ?? "right"}>
      <div className="usage-ind-pop-head">
        <strong>{t.popoverTitle}</strong>
        {p.updatedAtMs === undefined ? null : <span className="app-muted">{t.updated(formatRelative(Math.floor(p.updatedAtMs / 1000), p.nowMs))}</span>}
      </div>
      {p.items.length === 0 ? <p className="app-muted usage-ind-pop-line">{plainText(p.emptyText ?? t.noDataHint)}</p> : null}
      {p.items.map((i) => {
        const src = i.source === undefined ? undefined : p.sourceInfo(i.source);
        const fill = indicatorFill(i, p.valueMode);
        return (
          <div key={i.window} className="usage-ind-pop-item">
            <div className="usage-ind-pop-row">
              <span className="usage-ind-label ac-ellipsis">{i.name}</span>
              {src ? <SourceLine trust={src.trust} title={src.title} /> : null}
            </div>
            <div className="usage-ind-pop-row">
              <span className="ac-num">
                {i.kind === "ratio" ? p.showRemaining ? t.both(i.used ?? 0, i.remaining ?? 0) : t.spokenUsed(i.used ?? 0) : i.kind === "status" ? `${itemValueText(i, p.valueMode)} · ${t.statusOnlyDetail}` : i.kind === "tokens" ? `${itemValueText(i, p.valueMode)} · ${t.tokensDetail}` : i.observed ? u.cards.noValue : t.notObserved}
              </span>
            </div>
            {i.kind === "ratio" && fill !== undefined ? (
              <Gauge value={fill} stale={i.stale || i.reset === "passed"} label={u.cards.gaugeLabel(i.name)} noValueLabel={u.cards.noRatio} valueText={itemValueText(i, p.valueMode)} />
            ) : null}
            {i.observed ? (
              <p className="usage-ind-pop-line app-muted">
                {i.reset === "future" && i.resetsAt != null
                  ? futureResetsText(i.resetsAt, nowSec)
                  : i.reset === "passed"
                    ? t.oldValue
                    : u.cards.resetsUnknown}
              </p>
            ) : null}
            {i.observedAt !== undefined ? <p className="usage-ind-pop-line app-muted" title={formatDateTime(i.observedAt)}>{u.cards.observedAt(formatRelative(i.observedAt, p.nowMs))}</p> : null}
            {itemFlags(i).map((f) => <p key={f} className="usage-ind-pop-line usage-ind-pop-flag">{f}</p>)}
          </div>
        );
      })}
      {p.hiddenCount > 0 ? <p className="usage-ind-pop-line app-muted">{t.moreWindows(p.hiddenCount)}</p> : null}
      {p.sourceErrors > 0 || p.otherCount > 0 ? (
        <p className="usage-ind-pop-line app-muted usage-ind-pop-foot">
          {[p.sourceErrors > 0 ? t.sourceErrors(p.sourceErrors) : "", p.otherCount > 0 ? t.otherSources(p.otherCount) : ""].filter(Boolean).join(" · ")}
        </p>
      ) : null}
      <p className="usage-ind-pop-line app-muted">{t.clickToOpen}</p>
    </div>
  );
}
