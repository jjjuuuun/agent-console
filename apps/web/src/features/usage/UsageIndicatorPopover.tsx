import { Gauge } from "@agent-console/ui";
import { itemValueText } from "./indicatorText";
import { usageIndicatorMessages as t, usageMessages as u } from "./messages";
import { formatResetClock } from "./resetDisplay";
import { indicatorFill, plainText, type IndicatorItem } from "./usageLib";

export interface UsageIndicatorPopoverProps {
  id: string;
  /** 보일 항목(값이 있는 사용률 창만, 호출자가 걸러 개수 제한) */
  items: readonly IndicatorItem[];
  valueMode: string;
  nowMs: number;
  emptyText?: string | undefined;
  /** 사이드바 배치면 오른쪽, 플로팅이면 위/아래 */
  side?: "right" | "up";
}

/**
 * 요약 팝오버(읽기 전용, 비대화형). 사이드바 항목과 같은 정보만 보인다: 제목·`N% 사용됨`, 막대, 초기화 시각
 * (출처·신뢰·관측 시각·상태·오류 수 등은 사용량 화면에서, 사용자 요청 10/28).
 */
export function UsageIndicatorPopover(p: UsageIndicatorPopoverProps) {
  const nowSec = p.nowMs / 1000;
  return (
    <div id={p.id} className="usage-ind-pop" role="group" aria-label={t.popoverTitle} data-side={p.side ?? "right"}>
      {p.items.length === 0 ? <p className="app-muted usage-ind-pop-line">{plainText(p.emptyText ?? t.noDataHint)}</p> : null}
      {p.items.map((i) => {
        const fill = indicatorFill(i, p.valueMode);
        const reset =
          i.reset === "passed" ? t.resetsPassed : i.reset === "future" && i.resetsAt != null ? formatResetClock(i.resetsAt, nowSec, { today: t.resetsClockToday, other: t.resetsClockOther }) : null;
        return (
          <div key={i.window} className="usage-ind-pop-item">
            <div className="usage-ind-pop-row">
              <span className="usage-ind-label ac-ellipsis">{i.name}</span>
              <span className="ac-num">{itemValueText(i, p.valueMode)}</span>
            </div>
            {fill !== undefined ? <Gauge value={fill} stale={i.stale || i.reset === "passed"} label={u.cards.gaugeLabel(i.name)} noValueLabel={u.cards.noRatio} valueText={itemValueText(i, p.valueMode)} /> : null}
            {reset === null ? null : <p className="usage-ind-pop-line app-muted">{reset}</p>}
          </div>
        );
      })}
    </div>
  );
}
