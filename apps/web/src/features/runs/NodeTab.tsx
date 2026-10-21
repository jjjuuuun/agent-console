import { useMemo, useState, type ReactNode } from "react";
import type { NodeRun, Run, RunEvent } from "@agent-console/contracts";
import { Button, StatusChip, Tabs } from "@agent-console/ui";
import { messages as appMessages } from "../../app/messages";
import { formatCount, formatDuration, stringifyValue } from "../../lib/format";
import { runsMessages as t } from "./messages";
import { summarizeEvent } from "./runsLib";

export interface NodeTabProps {
  run: Run;
  /** 선택한 노드 id. null이면 실행 전체 요약 */
  nodeId: string | null;
  nodeLabel(id: string): string;
  /** 선택한 노드의 가장 최근 NodeRun(서브에이전트면 undefined) */
  nodeRun: NodeRun | undefined;
  /** 선택한 노드가 서브에이전트(NodeRun 없이 이벤트로만 상태를 아는 노드)인가 */
  isSubagentNode: boolean;
  /** 선택한 노드가 응답을 기다리는 중인가 */
  waiting: boolean;
  /** 이 노드(또는 서브에이전트)의 이벤트 */
  events: readonly RunEvent[];
  onSeeInteractions(): void;
  replies?: readonly string[];
  /** 선택한 노드의 실행 목록(2개 이상일 때만 앱이 채운다, 처음 선택은 최신 실행) */
  runList?: ReactNode;
  /** 선택한 실행의 회차·호출 문구(`3회차 · 호출 2`). 없으면 시도 번호만 */
  ordinalText?: string | undefined;
  /** 독립 위임으로 불린 노드의 안내("{위임자}가 위임해 실행된 별도 세션입니다.") */
  invokedNote?: string | undefined;
  /** 연결을 골랐으면 노드 대신 연결 상세를 보인다 */
  edgeView?: ReactNode;
}

function Json({ value }: { value: unknown }) {
  return <pre className="ac-pre app-wrap runs-json">{stringifyValue(value)}</pre>;
}

/** 탭 ⑤ 노드: 선택한 노드의 출력/입력/사용량/이벤트. 선택이 없으면 실행 전체 요약. */
export function NodeTab(p: NodeTabProps) {
  const [sub, setSub] = useState("out");
  const nr = p.nodeRun;
  const eventsView = useMemo(
    () => (
      <ul className="runs-node-events">
        {p.events.length === 0 ? <li className="app-muted">{t.node.noEvents}</li> : null}
        {p.events.slice(-200).map((e) => (
          <li key={e.seq}>
            <code className="app-mono">{e.type}</code> <span>{summarizeEvent(e, 120)}</span>
          </li>
        ))}
      </ul>
    ),
    [p.events],
  );

  if (p.edgeView !== undefined) return <div className="runs-node">{p.edgeView}</div>;

  if (p.nodeId === null) {
    const run = p.run;
    return (
      <div className="runs-node-overview">
        <h3 className="app-block-subtitle">{t.node.overview}</h3>
        <dl className="app-meta">
          <dt>{t.node.runInput}</dt>
          <dd><Json value={run.input} /></dd>
          {run.error ? (
            <>
              <dt>{t.node.runError}</dt>
              <dd className="runs-result-error">{run.error.message}</dd>
            </>
          ) : null}
          <dt>{t.node.totals}</dt>
          <dd>
            {run.totals ? `${formatCount(run.totals.input_tokens)} / ${formatCount(run.totals.output_tokens)}` : "–"} · {formatDuration(run.started_at != null && run.ended_at != null ? (run.ended_at - run.started_at) * 1000 : undefined)}
          </dd>
        </dl>
        {p.replies && p.replies.length > 0 ? (
          <ul>
            {p.replies.map((r, i) => (
              <li key={i} className="app-wrap">{r}</li>
            ))}
          </ul>
        ) : null}
        <p className="app-muted">{t.node.selectHint}</p>
      </div>
    );
  }

  const header = (
    <div className="runs-node-head">
      <h3 className="app-block-subtitle">{p.nodeLabel(p.nodeId)}</h3>
      {nr ? <StatusChip status={nr.status} label={appMessages.nodeStatus[nr.status] ?? nr.status} /> : null}
      {nr ? <span className="app-muted">{p.ordinalText ?? t.node.attemptOnly(nr.attempt ?? 1)}</span> : null}
    </div>
  );

  if (p.isSubagentNode && nr === undefined) {
    return (
      <div className="runs-node">
        {header}
        <p className="app-muted">{t.node.subagentNote}</p>
        {eventsView}
      </div>
    );
  }

  const outputs = nr?.outputs ?? {};
  const inputs = nr?.inputs ?? {};
  return (
    <div className="runs-node">
      {header}
      {p.runList}
      {p.invokedNote ? <p className="app-muted runs-note">{p.invokedNote}</p> : null}
      {nr?.error ? <p className="runs-result-error" role="alert">{t.node.error}: {nr.error.message}</p> : null}
      <Tabs
        ariaLabel={t.node.subTabs}
        activeId={sub}
        onChange={setSub}
        tabs={[
          {
            id: "out",
            label: t.node.output,
            content: p.waiting ? (
              <p>
                {t.node.waitingOutput} — <Button size="sm" onClick={p.onSeeInteractions}>{t.node.waitingAction}</Button>
              </p>
            ) : Object.keys(outputs).length === 0 ? (
              <p className="app-muted">{t.node.noOutput}</p>
            ) : (
              <Json value={outputs} />
            ),
          },
          { id: "in", label: t.node.input, content: Object.keys(inputs).length === 0 ? <p className="app-muted">{t.node.noInput}</p> : <Json value={inputs} /> },
          {
            id: "usage",
            label: t.node.usage,
            content: nr?.usage ? (
              <dl className="app-meta">
                <dt>{t.trace.usageInput}</dt><dd>{formatCount(nr.usage.input_tokens)}</dd>
                <dt>{t.trace.usageOutput}</dt><dd>{formatCount(nr.usage.output_tokens)}</dd>
                <dt>{t.trace.usageCache}</dt><dd>{formatCount(nr.usage.cache_read_tokens)}</dd>
                <dt>{t.trace.usageCost}</dt><dd>{nr.usage.cost_usd == null ? "–" : `$${nr.usage.cost_usd}`}</dd>
                <dt>{t.node.duration}</dt><dd>{formatDuration(nr.duration_ms)}</dd>
              </dl>
            ) : (
              <p className="app-muted">–</p>
            ),
          },
          { id: "events", label: t.node.events, content: eventsView },
        ]}
      />
    </div>
  );
}
