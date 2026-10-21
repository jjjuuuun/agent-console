import { useState } from "react";
import type { EdgeSpec } from "@agent-console/contracts";
import { EdgeLayoutPanel, IssueSuggestionButtons, candidateEdgeKinds, edgeKindBadge, defaultMessages, type EdgeLayoutPanelProps } from "@agent-console/graph-editor";
import { Banner, Button, ConfirmDialog } from "@agent-console/ui";
import { configRelativePath, resolveCycleLimit, type ConfigIssue } from "../delegation";
import { issueMessage } from "../../lib/issues";
import { EdgeConfigForm } from "./forms";
import { teamMessages as t } from "./messages";
import type { TeamPanelContext } from "./panelContext";
import { edgeKindOf, edgesOf, issuesOfEdge, latestById, nodeLabel, nodesOf, withEdge } from "./teamsLogic";

/** 연결 패널: 출발→도착, 연결 종류 바꾸기, 종류의 `config_schema` 폼, "모양·경로"(편집기가 알려 준 값), 이 연결의 문제. 종류별 전용 화면은 없다. */
export function EdgePanel({ ctx, edge, layout }: { ctx: TeamPanelContext; edge: EdgeSpec; layout?: EdgeLayoutPanelProps | undefined }) {
  const [pending, setPending] = useState<string | null>(null);
  const kind = edgeKindOf(edge, ctx.edgeTypes);
  const byId = new Map(nodesOf(ctx.graph).map((n) => [n.id, n]));
  const src = byId.get(edge.source.node);
  const tgt = byId.get(edge.target.node);
  const kinds = src === undefined || tgt === undefined ? [] : candidateEdgeKinds(src.type, tgt.type, latestById(ctx.edgeTypes), ctx.nodeTypes);
  // 현재 종류가 후보에 없어도(자유도 우선: 서버 검증이 알린다) 선택지에는 남긴다
  const options = kind !== undefined && !kinds.some((k) => k.id === kind.id) ? [kind, ...kinds] : kinds;
  const configCount = Object.keys(edge.config ?? {}).length;
  const mine = issuesOfEdge(ctx.issues, edge.id);
  const badge = kind === undefined ? undefined : edgeKindBadge(kind);
  // 서버 이슈 중 연결 설정 안을 가리키는 것(조건 행·한도 필드)은 폼의 해당 위치에 매단다
  const configIssues: ConfigIssue[] = mine.flatMap((issue) => {
    const path = configRelativePath(issue.path);
    return path === undefined || path === "" ? [] : [{ path, message: issue.message, severity: issue.severity === "error" ? ("error" as const) : ("warning" as const) }];
  });
  const cycleLimit = kind?.cycle == null ? undefined : resolveCycleLimit({ edgeConfig: edge.config, teamSettings: ctx.graph.settings, commonSettings: ctx.workspace, kindDefault: kind.cycle.max_iterations });
  const sourceLabels = { edge: t.nested.sourceEdge, teamSettings: t.nested.sourceTeam, commonSettings: t.nested.sourceCommon, kindDefault: t.nested.sourceKind } as const;

  const change = (id: string) => {
    if (id === edge.kind) return;
    if (configCount > 0) setPending(id);
    else ctx.onGraphChange(withEdge(ctx.graph, edge.id, { kind: id }));
  };
  const confirm = () => {
    if (pending === null) return;
    const next = { ...edge, kind: pending } as EdgeSpec;
    delete (next as { config?: unknown }).config;
    ctx.onGraphChange({ ...ctx.graph, edges: edgesOf(ctx.graph).map((e) => (e.id === edge.id ? next : e)) });
    setPending(null);
  };

  return (
    <div className="team-panel-body">
      <header className="team-panel-head">
        <strong className="ac-ellipsis" title={`${src ? nodeLabel(src) : edge.source.node} → ${tgt ? nodeLabel(tgt) : edge.target.node}`}>
          {t.edge.header(src ? nodeLabel(src) : edge.source.node, tgt ? nodeLabel(tgt) : edge.target.node)}
        </strong>
        <span className="app-spacer" />
        <Button size="sm" variant="danger" disabled={ctx.disabled} onClick={() => ctx.onGraphChange({ ...ctx.graph, edges: edgesOf(ctx.graph).filter((e) => e.id !== edge.id) })}>
          {t.edge.delete}
        </Button>
      </header>
      <p className="lib-mono app-muted">{edge.source.port} → {edge.target.port}</p>
      {kind === undefined ? (
        <>
          <Banner tone="warning">{t.edge.kindUnknown(edge.kind)}</Banner>
          <p className="app-muted lib-field-note">{t.edge.readOnlyJson}</p>
          <pre className="ac-pre app-json">{JSON.stringify(edge, null, 2)}</pre>
        </>
      ) : (
        <div className="lib-form" data-edge-config="">
          <label className="lib-field">
            <span>{t.edge.kind}</span>
            <select value={edge.kind} disabled={ctx.disabled} onChange={(e) => change(e.target.value)}>
              {options.map((k) => (
                <option key={k.id} value={k.id}>{k.title}</option>
              ))}
            </select>
            {options.length <= 1 ? <span className="app-muted lib-field-note">{t.edge.noKinds}</span> : null}
          </label>
          {kind.description ? <p className="app-muted lib-field-note">{kind.description}</p> : null}
          {badge !== undefined && defaultMessages.kindBadgeLabels[badge] ? <span className="ac-tag">{defaultMessages.kindBadgeLabels[badge]}</span> : null}
          {kind.cycle != null ? <span className="ac-tag">{t.edge.cycleBadge}</span> : null}
          {kind.handles_failure === true ? <span className="ac-tag">{t.edge.failureBadge}</span> : null}
          <span className="lib-field-label">{t.edge.settings}</span>
          <EdgeConfigForm
            key={edge.id + edge.kind}
            kind={kind}
            config={(edge.config ?? {}) as Record<string, unknown>}
            onChange={(config) => {
              const next = { ...edge, config } as EdgeSpec;
              if (Object.keys(config).length === 0) delete (next as { config?: unknown }).config;
              ctx.onGraphChange({ ...ctx.graph, edges: edgesOf(ctx.graph).map((e) => (e.id === edge.id ? next : e)) });
            }}
            interactionKinds={ctx.interactionKinds}
            strategies={ctx.strategies}
            issues={configIssues}
            disabled={ctx.disabled}
          />
          {cycleLimit === undefined ? null : (
            <p className="app-muted lib-field-note" role="status">
              {cycleLimit.value === undefined || cycleLimit.source === undefined ? t.nested.cycleLimitNone : t.nested.cycleLimitLine(cycleLimit.value, sourceLabels[cycleLimit.source])}
            </p>
          )}
        </div>
      )}
      {layout !== undefined ? <EdgeLayoutPanel {...layout} readOnly={ctx.disabled || layout.readOnly === true} /> : null}
      <section aria-label={t.edge.problems}>
        <span className="lib-field-label">{t.edge.problems}</span>
        {mine.length === 0 ? <p className="app-muted lib-field-note">{t.node.noProblems}</p> : null}
        <ul className="team-problem-list">
          {mine.map((issue, i) => (
            <li key={`${i}:${issue.code}`}>
              <span className="app-sev" data-severity={issue.severity}>{issue.severity === "error" ? "✕" : "▲"}</span> {issueMessage(issue)}
              <div><IssueSuggestionButtons issue={issue} onApply={ctx.onApplySuggestion} /></div>
            </li>
          ))}
        </ul>
      </section>
      <ConfirmDialog
        open={pending !== null}
        title={t.edge.kindChangeTitle}
        confirmLabel={t.edge.kindChange}
        cancelLabel="취소"
        danger
        onConfirm={confirm}
        onCancel={() => setPending(null)}
      >
        <p className="ac-text">{t.edge.kindChangeBody(configCount)}</p>
      </ConfirmDialog>
    </div>
  );
}
