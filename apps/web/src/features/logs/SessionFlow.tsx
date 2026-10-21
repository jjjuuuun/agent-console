import { useMemo, useState } from "react";
import { TraceTimeline, defaultTraceMessages, type MethodBadge, type SpanLabel } from "@agent-console/trace-view";
import { Button } from "@agent-console/ui";
import { LaneRibbon, clipTraceAt, type LaneEvent, type LogTaxonomyView } from "@agent-console/log-view";
import type { LogLane, Trace, TraceSpan } from "@agent-console/contracts";
import { ErrorBlock } from "../../app/ErrorBlock";
import { messages as appMessages } from "../../app/messages";
import { logsMessages as t } from "./messages";
import { slotFor } from "./slots";

/** 위임 흐름의 span이 가리키는 레인 id. span id가 레인 id와 같거나 `<접두>:<레인 id>` 꼴이면 그 레인이다(모르면 undefined). */
export function laneOfSpan(spanId: string, laneIds: readonly string[]): string | undefined {
  return laneIds.find((l) => spanId === l) ?? laneIds.find((l) => spanId.endsWith(`:${l}`));
}

export type FlowView = "lane" | "trace";

export interface SessionFlowProps {
  view: FlowView;
  lanes: readonly LogLane[];
  laneLabelFor(id: string): string;
  events: readonly LaneEvent[];
  /** 재생 위치 시각(epoch 초, 끝이면 null) */
  cursorTime: number | null;
  /** 위임 흐름 데이터(위임 흐름 연동이 있을 때) */
  trace: { data: Trace | undefined; loading: boolean; error: Error | null; refetch(): void };
  taxonomy: LogTaxonomyView;
  selectedUid: string | null;
  onSelectEvent(uid: string, additive: boolean): void;
  onSelectLane(id: string): void;
  /** 재생 중인지(끝이 아닌 동안 위임 흐름은 실행 중으로 그린다) */
  playing: boolean;
  atEnd: boolean;
  lastTime: number | null;
}

/** 흐름 패널 본문: [레인] 띠 또는 [위임 흐름](재생 위치까지 자른 `Trace`). */
export function SessionFlow(p: SessionFlowProps) {
  const [scale, setScale] = useState(1);
  const [spanId, setSpanId] = useState<string | null>(null);
  const [wait, setWait] = useState(true);
  const laneIds = useMemo(() => p.lanes.map((l) => l.id), [p.lanes]);
  const clipped = useMemo(() => (p.trace.data === undefined ? undefined : clipTraceAt(p.trace.data, p.cursorTime)), [p.trace.data, p.cursorTime]);

  if (p.view === "lane") {
    return (
      <LaneRibbon
        lanes={p.lanes}
        events={p.events}
        cursorTime={p.cursorTime}
        taxonomy={p.taxonomy}
        slotFor={slotFor}
        selectedUid={p.selectedUid}
        onSelectEvent={(uid, o) => p.onSelectEvent(uid, o.additive)}
        onSelectLane={p.onSelectLane}
        timeScale={scale}
        onTimeScaleChange={setScale}
      />
    );
  }
  if (p.trace.error !== null && p.trace.data === undefined) {
    return <ErrorBlock title={t.detail.traceFailed} message={p.trace.error.message} retryLabel={appMessages.common.retry} onRetry={p.trace.refetch} />;
  }
  if (clipped === undefined) return <div className="app-loading" role="status">{t.loading}</div>;
  const labelFor = (span: TraceSpan): SpanLabel => {
    const lane = laneOfSpan(span.id, laneIds);
    return { title: lane !== undefined ? p.laneLabelFor(lane) : span.actor || span.id };
  };
  const methodBadgeFor = (span: TraceSpan): MethodBadge | undefined => {
    const link = (clipped.links ?? []).find((l) => l.target === span.id);
    return link?.kind ? { text: link.kind } : undefined;
  };
  const running = !p.atEnd || p.playing;
  return (
    <TraceTimeline
      trace={clipped}
      now={p.cursorTime ?? p.lastTime ?? 0}
      running={running}
      selectedSpanId={spanId}
      onSelect={(id) => {
        setSpanId(id);
        const lane = id === null ? undefined : laneOfSpan(id, laneIds);
        if (lane !== undefined) p.onSelectLane(lane);
      }}
      labelFor={labelFor}
      methodBadgeFor={methodBadgeFor}
      showUserWait={wait}
      onShowUserWaitChange={setWait}
      timeScale={scale}
      onTimeScaleChange={setScale}
      messages={{ empty: t.detail.traceEmpty, statusText: { ...appMessages.runStatus, ...appMessages.nodeStatus, ...defaultTraceMessages.statusText } }}
    />
  );
}

/** 세그먼트 컨트롤([레인 | 위임 흐름]). 위임 흐름 연동이 없으면 호출하는 쪽이 그리지 않는다. */
export function FlowSegments({ view, onChange }: { view: FlowView; onChange(v: FlowView): void }) {
  return (
    <div role="group" aria-label={t.detail.flowView} className="logs-segments">
      <Button size="sm" aria-pressed={view === "lane"} onClick={() => onChange("lane")}>{t.detail.flowLanes}</Button>
      <Button size="sm" aria-pressed={view === "trace"} onClick={() => onChange("trace")}>{t.detail.flowTrace}</Button>
    </div>
  );
}
