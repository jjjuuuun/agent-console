import { useMemo, useState, type ReactNode } from "react";
import type { Trace, TraceLink, TraceSpan } from "@agent-console/contracts";
import { TraceTimeline, defaultTraceMessages, type GroupBadge, type LinkBadge, type MethodBadge, type SpanLabel, type TraceGroupInfo } from "@agent-console/trace-view";
import { Button, Icon } from "@agent-console/ui";
import { useStorage } from "../../app/StorageContext";
import { ErrorBlock } from "../../app/ErrorBlock";
import { messages as appMessages } from "../../app/messages";
import { formatCount, formatDateTime, formatDuration } from "../../lib/format";
import { runsMessages as t } from "./messages";
import { FAILED_STATUS } from "./runsConfig";
import { filterFailedSpans } from "./runsLib";

/** 방식 글자 표시 토글의 로컬 저장 키(화면 선택이라 localStorage) */
export const TRACE_METHOD_TEXT_KEY = "ac.trace.methodText";

/** 위임 흐름 아이콘: 앱 아이콘 레지스트리(연결 종류 `ui_hints.icon`)로 그린다. 모르는 이름은 `↪`. */
export const renderTraceIcon = (name: string, size: number): ReactNode => <Icon name={name} size={size} fallbackText="↪" />;

export interface TraceTabProps {
  trace: Trace | undefined;
  status: "loading" | "ready" | "error";
  onRetry(): void;
  running: boolean;
  /** epoch 초 */
  nowSec: number;
  labelFor(span: TraceSpan): SpanLabel;
  methodBadgeFor(span: TraceSpan): MethodBadge | undefined;
  /** 자식 실행 묶음 행의 제목·배지(팀 구성 이름 등). 없으면 `자식 실행 {짧은 id}` */
  groupBadgeFor?(group: TraceGroupInfo): GroupBadge | undefined;
  /** span 사이 화살표 칩(반복 연결 `↻`·순번). 없으면 칩 없음 */
  linkBadgeFor?(link: TraceLink): LinkBadge | undefined;
  /** 묶음 행 [열기 ↗]·`Ctrl+Enter` */
  onOpenChildRun?(runId: string): void;
  selectedSpanId: string | null;
  onSelect(id: string | null): void;
  highlightNodeId: string | null;
  onSeeLog(actor: string): void;
  /** [노드 보기]. 자식 실행 안 span이면 `runId`가 그 자식 Run id다(자식 실행 화면으로 간다) */
  onSeeNode(nodeId: string, runId?: string): void;
  onSeeInteraction(interactionId: string): void;
  /** 상태 문자열(서버 값) → 한글 */
  statusLabel(status: string): string;
}

/** 탭 ① 위임 흐름. `TraceTimeline`에 이름·방식 해석과 상세 드로어를 더한다. */
export function TraceTab(p: TraceTabProps) {
  const [showUserWait, setShowUserWait] = useState(true);
  const [scale, setScale] = useState(1);
  const [follow, setFollow] = useState(false);
  const [failedOnly, setFailedOnly] = useState(false);
  const storage = useStorage();
  const [methodText, setMethodText] = useState(() => storage.get(TRACE_METHOD_TEXT_KEY) === "1");
  const changeMethodText = (v: boolean) => {
    setMethodText(v);
    if (v) storage.set(TRACE_METHOD_TEXT_KEY, "1");
    else storage.remove(TRACE_METHOD_TEXT_KEY);
  };

  const shown = useMemo(() => (p.trace === undefined ? undefined : failedOnly ? filterFailedSpans(p.trace, FAILED_STATUS) : p.trace), [p.trace, failedOnly]);

  if (p.status === "loading" && p.trace === undefined) return <div className="app-loading" role="status">{t.trace.loading}</div>;
  if (p.status === "error" && p.trace === undefined) return <ErrorBlock title={t.trace.loadFailed} retryLabel={appMessages.common.retry} onRetry={p.onRetry} />;
  if (shown === undefined) return null;

  const renderDetail = (span: TraceSpan): ReactNode => {
    const usage = span.usage;
    const isChild = span.parent_id != null;
    const duration = span.started_at != null && span.ended_at != null ? (span.ended_at - span.started_at) * 1000 : undefined;
    return (
      <div className="runs-span-detail">
        <h3 className="app-block-subtitle">{p.labelFor(span).title}</h3>
        <dl className="app-meta">
          <dt>{t.trace.status}</dt>
          <dd>{span.status ? p.statusLabel(span.status) : "–"}</dd>
          <dt>{t.trace.started}</dt>
          <dd>{formatDateTime(span.started_at)}</dd>
          <dt>{t.trace.ended}</dt>
          <dd>{formatDateTime(span.ended_at)}</dd>
          <dt>{t.trace.duration}</dt>
          <dd>{formatDuration(duration)}</dd>
          <dt>{t.trace.usage}</dt>
          <dd>
            {usage == null ? (
              "–"
            ) : isChild ? (
              t.trace.usageTotalOnly(formatCount(usage.total_tokens))
            ) : (
              <span>
                {t.trace.usageInput} {formatCount(usage.input_tokens)} · {t.trace.usageOutput} {formatCount(usage.output_tokens)} · {t.trace.usageCache} {formatCount(usage.cache_read_tokens)} · {t.trace.usageCost} {usage.cost_usd == null ? "–" : `$${usage.cost_usd}`}
              </span>
            )}
          </dd>
        </dl>
        {span.task_preview ? (
          <details>
            <summary>{t.trace.task}</summary>
            <pre className="ac-pre app-wrap">{span.task_preview}</pre>
          </details>
        ) : null}
        {span.result_preview ? (
          <details>
            <summary>{t.trace.result}</summary>
            <pre className="ac-pre app-wrap">{span.result_preview}</pre>
          </details>
        ) : null}
        <div className="runs-span-links">
          {span.actor ? <Button size="sm" onClick={() => p.onSeeLog(span.actor as string)}>{t.trace.seeLog}</Button> : null}
          {span.node_id ? <Button size="sm" onClick={() => p.onSeeNode(span.node_id as string, span.run_id != null && span.run_id !== "" && span.run_id !== p.trace?.run_id ? span.run_id : undefined)}>{t.trace.seeNode}</Button> : null}
          {span.interaction_id ? <Button size="sm" onClick={() => p.onSeeInteraction(span.interaction_id as string)}>{t.trace.seeInteraction}</Button> : null}
          <Button size="sm" variant="ghost" onClick={() => p.onSelect(null)}>{t.trace.close}</Button>
        </div>
      </div>
    );
  };

  return (
    <div className="runs-trace">
      <div className="runs-trace-tools">
        <label className="app-check">
          <input type="checkbox" checked={failedOnly} onChange={(e) => setFailedOnly(e.target.checked)} />
          {t.trace.failedOnly}
        </label>
      </div>
      <TraceTimeline
        trace={shown}
        now={p.nowSec}
        running={p.running}
        selectedSpanId={p.selectedSpanId}
        onSelect={p.onSelect}
        highlightNodeId={p.highlightNodeId}
        labelFor={p.labelFor}
        methodBadgeFor={p.methodBadgeFor}
        {...(p.groupBadgeFor ? { groupBadgeFor: p.groupBadgeFor } : {})}
        {...(p.linkBadgeFor ? { linkBadgeFor: p.linkBadgeFor } : {})}
        {...(p.onOpenChildRun ? { onOpenChildRun: p.onOpenChildRun } : {})}
        showUserWait={showUserWait}
        onShowUserWaitChange={setShowUserWait}
        timeScale={scale}
        onTimeScaleChange={setScale}
        follow={follow}
        onFollowChange={p.running ? setFollow : undefined}
        showMethodText={methodText}
        onShowMethodTextChange={changeMethodText}
        renderIcon={renderTraceIcon}
        renderDetail={renderDetail}
        messages={{ empty: t.trace.empty, sameSession: t.trace.sessionSame, separateSession: t.trace.sessionSeparate, statusText: { ...appMessages.runStatus, ...appMessages.nodeStatus, ...defaultTraceMessages.statusText } }}
      />
    </div>
  );
}
