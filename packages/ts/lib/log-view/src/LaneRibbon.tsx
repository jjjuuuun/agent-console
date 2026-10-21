import { useMemo, useRef, useState, type KeyboardEvent, type WheelEvent } from "react";
import type { LogLane } from "@agent-console/contracts/logs";
import { mergeFormatters } from "./format";
import { fmt, mergeMessages, type DeepPartial, type LogViewMessages } from "./messages";
import { colorFor, slotColor } from "./taxonomy";
import type { Formatters, LogTaxonomyView, SlotFor } from "./types";

export interface LaneEvent {
  uid: string;
  lane: string;
  /** epoch 초. */
  time: number;
  /** 짝 이벤트의 끝(있으면 시작~끝 막대). */
  endTime?: number | null;
  category: string;
  error: boolean;
}

export interface LaneRibbonProps {
  lanes: readonly LogLane[];
  events: readonly LaneEvent[];
  /** 재생 위치 시각(epoch 초). 있으면 세로 커서선을 그리고 이후 이벤트는 그리지 않는다. */
  cursorTime?: number | null;
  taxonomy: LogTaxonomyView;
  slotFor: SlotFor;
  selectedUid?: string | null | undefined;
  onSelectEvent?: (uid: string, opts: { additive: boolean }) => void;
  onSelectLane?: (laneId: string) => void;
  /** 가로 줌 배율(1~16). */
  timeScale?: number;
  onTimeScaleChange?: (scale: number) => void;
  laneLabelWidth?: number;
  formatters?: Partial<Formatters>;
  messages?: DeepPartial<LogViewMessages>;
  ariaLabel?: string;
}

const MIN_ZOOM = 1;
const MAX_ZOOM = 16;

/** 레인을 부모-자식 순서의 평면 목록으로(부모가 없거나 모르면 최상위). 순환이 있어도 한 번씩만. */
export function flattenLanes(lanes: readonly LogLane[]): { lane: LogLane; depth: number }[] {
  const ids = new Set(lanes.map((l) => l.id));
  const children = new Map<string, LogLane[]>();
  const roots: LogLane[] = [];
  for (const l of lanes) {
    if (l.parent_id && ids.has(l.parent_id) && l.parent_id !== l.id) children.set(l.parent_id, [...(children.get(l.parent_id) ?? []), l]);
    else roots.push(l);
  }
  const out: { lane: LogLane; depth: number }[] = [];
  const seen = new Set<string>();
  const walk = (l: LogLane, depth: number) => {
    if (seen.has(l.id)) return;
    seen.add(l.id);
    out.push({ lane: l, depth });
    for (const c of children.get(l.id) ?? []) walk(c, depth + 1);
  };
  for (const r of roots) walk(r, 0);
  for (const l of lanes) walk(l, 0); // 순환에 갇힌 레인도 보이게
  return out;
}

/**
 * 레인 띠: 레인(thread)마다 한 줄, 이벤트는 범주 색 틱(짝 이벤트는 막대, 오류는 높은 틱 + 다이아몬드).
 * `role="grid"`(행 = 레인), 레인 행에서 `←→`로 이벤트 단위 이동(Tab 정지점은 레인 행 하나), `Enter` 선택.
 */
export function LaneRibbon(props: LaneRibbonProps) {
  const { lanes, events, cursorTime, taxonomy, slotFor, selectedUid, onSelectEvent, onSelectLane, timeScale = 1, onTimeScaleChange, laneLabelWidth = 160, ariaLabel } = props;
  const m = useMemo(() => mergeMessages(props.messages), [props.messages]);
  const formatters = useMemo(() => mergeFormatters(props.formatters), [props.formatters]);
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());
  const [focusLane, setFocusLane] = useState(0);
  const rowRefs = useRef<(HTMLDivElement | null)[]>([]);
  const [evIdx, setEvIdx] = useState<Record<string, number>>({});
  const zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, timeScale));

  const flat = useMemo(() => flattenLanes(lanes), [lanes]);
  const rows = useMemo(() => {
    const hidden = new Set<string>();
    const out: { lane: LogLane; depth: number; hasChildren: boolean }[] = [];
    const parentOf = new Map(lanes.map((l) => [l.id, l.parent_id] as const));
    const childCount = new Map<string, number>();
    for (const l of lanes) if (l.parent_id) childCount.set(l.parent_id, (childCount.get(l.parent_id) ?? 0) + 1);
    for (const f of flat) {
      let p = parentOf.get(f.lane.id);
      let skip = false;
      const guard = new Set<string>();
      while (p && !guard.has(p)) {
        guard.add(p);
        if (collapsed.has(p)) skip = true;
        p = parentOf.get(p);
      }
      if (skip) hidden.add(f.lane.id);
      else out.push({ ...f, hasChildren: (childCount.get(f.lane.id) ?? 0) > 0 });
    }
    return out;
  }, [flat, lanes, collapsed]);

  const visibleEvents = useMemo(() => (cursorTime == null ? events : events.filter((e) => e.time <= cursorTime)), [events, cursorTime]);
  const byLane = useMemo(() => {
    const map = new Map<string, LaneEvent[]>();
    for (const e of visibleEvents) map.set(e.lane, [...(map.get(e.lane) ?? []), e]);
    for (const list of map.values()) list.sort((a, b) => a.time - b.time);
    return map;
  }, [visibleEvents]);

  const times = events.flatMap((e) => (e.endTime != null ? [e.time, e.endTime] : [e.time]));
  const min = times.length ? Math.min(...times) : 0;
  const max = times.length ? Math.max(...times) : 1;
  const span = Math.max(max - min, 1e-6);
  const pos = (t: number) => `${((t - min) / span) * 100}%`;

  if (lanes.length === 0) return <p className="ac-lv-empty" role="status">{m.noLanes}</p>;

  const onWheel = (e: WheelEvent) => {
    if (!e.ctrlKey || !onTimeScaleChange) return;
    e.preventDefault();
    onTimeScaleChange(Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom * (e.deltaY < 0 ? 1.25 : 0.8))));
  };

  const onRowKey = (e: KeyboardEvent<HTMLDivElement>, ri: number, laneId: string) => {
    const list = byLane.get(laneId) ?? [];
    const cur = evIdx[laneId] ?? 0;
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      if (list.length === 0) return;
      e.preventDefault();
      const next = Math.min(list.length - 1, Math.max(0, cur + (e.key === "ArrowRight" ? 1 : -1)));
      setEvIdx({ ...evIdx, [laneId]: next });
      const ev = list[next];
      if (ev) onSelectEvent?.(ev.uid, { additive: false });
    } else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const to = Math.min(rows.length - 1, Math.max(0, ri + (e.key === "ArrowDown" ? 1 : -1)));
      setFocusLane(to);
      rowRefs.current[to]?.focus();
    } else if (e.key === "Enter") {
      e.preventDefault();
      const ev = list[cur];
      if (e.shiftKey || !ev) onSelectLane?.(laneId);
      else onSelectEvent?.(ev.uid, { additive: e.ctrlKey });
    } else if ((e.key === "+" || e.key === "=") && onTimeScaleChange) onTimeScaleChange(Math.min(MAX_ZOOM, zoom * 1.5));
    else if (e.key === "-" && onTimeScaleChange) onTimeScaleChange(Math.max(MIN_ZOOM, zoom / 1.5));
  };

  const tickCount = 6;
  return (
    <div className="ac-lv-lanes" onWheel={onWheel}>
      <div role="grid" aria-label={ariaLabel ?? m.laneRibbon} aria-rowcount={rows.length}>
        <div className="ac-lv-lanes-scroll">
          <div className="ac-lv-lane-axis" style={{ marginLeft: laneLabelWidth, width: `calc((100% - ${laneLabelWidth}px) * ${zoom})` }} aria-hidden="true">
            {Array.from({ length: tickCount }, (_, i) => {
              const t = min + (span * i) / (tickCount - 1);
              return (
                <span key={i} className="ac-lv-num ac-lv-muted" style={{ left: `${(i / (tickCount - 1)) * 100}%` }}>
                  {formatters.relativeTime((t - min) * 1000)}
                </span>
              );
            })}
          </div>
          {rows.map(({ lane, depth, hasChildren }, ri) => {
            const list = byLane.get(lane.id) ?? [];
            const name = lane.label?.trim() ? lane.label : lane.id;
            return (
              <div
                key={lane.id}
                ref={(el) => {
                  rowRefs.current[ri] = el;
                }}
                role="row"
                aria-rowindex={ri + 1}
                aria-label={fmt(m.laneLabel, { name, n: list.length })}
                tabIndex={ri === Math.min(focusLane, rows.length - 1) ? 0 : -1}
                className="ac-lv-lane"
                onFocus={() => setFocusLane(ri)}
                onKeyDown={(e) => onRowKey(e, ri, lane.id)}
              >
                <div role="rowheader" className="ac-lv-lane-label" style={{ width: laneLabelWidth, paddingLeft: depth * 12 }}>
                  {hasChildren ? (
                    <button
                      type="button"
                      tabIndex={-1}
                      className="ac-lv-linkbtn"
                      aria-expanded={!collapsed.has(lane.id)}
                      aria-label={collapsed.has(lane.id) ? m.expandGroup : m.collapseGroup}
                      onClick={() => setCollapsed((prev) => { const next = new Set(prev); if (next.has(lane.id)) next.delete(lane.id); else next.add(lane.id); return next; })}
                    >
                      {collapsed.has(lane.id) ? "▸" : "▾"}
                    </button>
                  ) : null}
                  <span className="ac-lv-avatar" style={{ background: slotColor(slotFor(lane.id)) }} aria-hidden="true" />
                  <button type="button" tabIndex={-1} className="ac-lv-linkbtn ac-lv-ellipsis" title={name} onClick={() => onSelectLane?.(lane.id)}>
                    {name}
                  </button>
                </div>
                <div role="gridcell" className="ac-lv-lane-track" style={{ width: `calc((100% - ${laneLabelWidth}px) * ${zoom})` }}>
                  {list.map((e, ei) => {
                    const color = colorFor(e.category, taxonomy, slotFor);
                    const paired = e.endTime != null && e.endTime > e.time;
                    return paired ? (
                      <span
                        key={e.uid}
                        className="ac-lv-lane-bar"
                        data-selected={e.uid === selectedUid || undefined}
                        data-error={e.error || undefined}
                        data-focus={evIdx[lane.id] === ei || undefined}
                        style={{ left: pos(e.time), width: `calc(${pos(e.endTime as number)} - ${pos(e.time)})`, ["--lv-cat" as string]: color }}
                        onClick={(ev) => onSelectEvent?.(e.uid, { additive: ev.ctrlKey })}
                      />
                    ) : (
                      <span
                        key={e.uid}
                        className="ac-lv-lane-tick"
                        data-selected={e.uid === selectedUid || undefined}
                        data-error={e.error || undefined}
                        data-focus={evIdx[lane.id] === ei || undefined}
                        style={{ left: pos(e.time), ["--lv-cat" as string]: color }}
                        onClick={(ev) => onSelectEvent?.(e.uid, { additive: ev.ctrlKey })}
                      />
                    );
                  })}
                  {cursorTime != null ? <span className="ac-lv-lane-cursor" style={{ left: pos(Math.min(max, Math.max(min, cursorTime))) }} aria-hidden="true" /> : null}
                </div>
              </div>
            );
          })}
        </div>
      </div>
      {onTimeScaleChange ? (
        <div className="ac-lv-row-actions">
          <button type="button" className="ac-lv-iconbtn" aria-label="+" onClick={() => onTimeScaleChange(Math.min(MAX_ZOOM, zoom * 1.5))}>
            +
          </button>
          <button type="button" className="ac-lv-iconbtn" aria-label="-" onClick={() => onTimeScaleChange(Math.max(MIN_ZOOM, zoom / 1.5))}>
            −
          </button>
        </div>
      ) : null}
    </div>
  );
}
