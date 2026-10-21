import { useState } from "react";
import type { Graph, Issue, IssueSuggestion } from "@agent-console/contracts";
import { IssueSuggestionButtons } from "@agent-console/graph-editor";
import { Button } from "@agent-console/ui";
import { messages as m } from "../../app/messages";
import { issueMessage, sortIssues } from "../../lib/issues";
import type { ValidationState } from "./useValidation";
import { teamMessages as t } from "./messages";
import { issueTarget, type IssueTarget } from "./teamsLogic";

type Filter = "all" | "error" | "warning";

export interface IssuesPanelProps {
  graph: Graph;
  validation: ValidationState;
  open: boolean;
  onToggle: () => void;
  onValidate: () => void;
  /** 이슈 행 클릭: 해당 노드·연결로 이동 */
  onFocus: (target: IssueTarget, issue: Issue) => void;
  onApplySuggestion: (issue: Issue, suggestion: IssueSuggestion) => void;
}

/**
 * 검증 이슈 패널(캔버스 아래). 서버가 준 이슈를 그대로 보여 주고(코드는 해석하지 않는다) 제안 버튼을 붙인다.
 * 검증 실패 시 기존 이슈를 흐리게 유지하고 [다시 시도]를 준다.
 */
export function IssuesPanel({ graph, validation, open, onToggle, onValidate, onFocus, onApplySuggestion }: IssuesPanelProps) {
  const [filter, setFilter] = useState<Filter>("all");
  const { issues, phase } = validation;
  const errors = issues.filter((i) => i.severity === "error").length;
  const warnings = issues.filter((i) => i.severity === "warning").length;
  const firstError = sortIssues(issues).find((i) => i.severity === "error");
  const rows = sortIssues(issues).filter((i) => filter === "all" || i.severity === filter);
  return (
    <section className="team-issues" aria-label={t.issues.region} data-open={open ? "true" : "false"} data-stale={phase === "failed" ? "true" : undefined}>
      <header className="team-issues-head">
        <button type="button" className="app-link-btn team-issues-toggle" aria-expanded={open} aria-label={t.issues.toggle} onClick={onToggle}>
          {open ? "▾" : "▸"} {t.issues.title(errors, warnings)}
        </button>
        {!open && firstError !== undefined ? (
          <span className="team-issues-first" data-testid="issues-first-error">
            <span className="app-sev team-issues-first-msg" data-severity="error" title={issueMessage(firstError)}>✕ {issueMessage(firstError)}</span>
            <IssueSuggestionButtons issue={{ ...firstError, suggestions: (firstError.suggestions ?? []).slice(0, 1) }} primary onApply={onApplySuggestion} />
          </span>
        ) : null}
        {phase === "running" ? <span role="status" className="app-muted">{t.issues.running}</span> : null}
        {phase === "failed" ? (
          <span role="alert" className="app-sev" data-severity="error">
            {t.issues.failed} <Button size="sm" onClick={onValidate}>{t.issues.retry}</Button>
          </span>
        ) : null}
        {validation.validated && phase === "idle" && issues.length === 0 ? <span role="status" className="app-sev" data-severity="info">{t.issues.ok}</span> : null}
        <span className="app-spacer" />
        <div className="lib-chips" role="group" aria-label={t.issues.filterLabel}>
          {(["all", "error", "warning"] as const).map((f) => (
            <button key={f} type="button" className="lib-chip" aria-pressed={filter === f} onClick={() => setFilter(f)}>
              {{ all: t.issues.filterAll, error: t.issues.filterError, warning: t.issues.filterWarning }[f]}
            </button>
          ))}
        </div>
      </header>
      {open && rows.length > 0 ? (
        <div className="team-issues-body">
          <table className="lib-grid" aria-label={t.issues.region}>
            <thead>
              <tr>
                <th>{t.issues.colSeverity}</th>
                <th>{t.issues.colTarget}</th>
                <th>{t.issues.colMessage}</th>
                <th>{t.issues.colCode}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {rows.map((issue, i) => {
                const target = issueTarget(issue, graph);
                const clickable = target.kind !== "graph";
                return (
                  <tr key={`${i}:${issue.code}:${issue.node_id ?? issue.edge_id ?? ""}`} className="team-issue-row" data-severity={issue.severity} onClick={() => clickable && onFocus(target, issue)}>
                    <td>
                      <span className="app-sev" data-severity={issue.severity}>{issue.severity === "error" ? "✕" : issue.severity === "warning" ? "▲" : "ℹ"} {m.severity[issue.severity]}</span>
                      {issue.blocks_run ? <span className="ac-tag" title={t.issues.blocksRun}>{t.issues.blocksRun}</span> : null}
                    </td>
                    <td className="lib-cell-clip" title={target.label}>
                      {clickable ? (
                        <button type="button" className="app-link-btn" onClick={(e) => { e.stopPropagation(); onFocus(target, issue); }}>{target.label}</button>
                      ) : (
                        <span className="app-muted">{t.issues.targetGraph}</span>
                      )}
                    </td>
                    <td className="ac-clamp-2">{issueMessage(issue)}</td>
                    <td className="lib-mono app-muted">{issue.code}</td>
                    <td className="team-issue-fix" onClick={(e) => e.stopPropagation()}>
                      <IssueSuggestionButtons issue={issue} primary onApply={onApplySuggestion} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
