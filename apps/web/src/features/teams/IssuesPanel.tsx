import { Fragment, useState } from "react";
import type { Graph, Issue, IssueSuggestion } from "@agent-console/contracts";
import { IssueSuggestionButtons } from "@agent-console/graph-editor";
import { Button } from "@agent-console/ui";
import { messages as m } from "../../app/messages";
import { issueMessage, sortIssues } from "../../lib/issues";
import { IssueActions } from "./IssueActions";
import { buildIssueRows, rowSuggestions, severityCounts, type IssueRow } from "./issueRows";
import type { ValidationState } from "./useValidation";
import { teamMessages as t } from "./messages";
import { issueTarget, type IssueTarget } from "./teamsLogic";

type Filter = "all" | "error" | "warning" | "info";

const SEV_MARK = { error: "✕", warning: "▲", info: "ⓘ" } as const;

export interface IssuesPanelProps {
  graph: Graph;
  validation: ValidationState;
  open: boolean;
  onToggle: () => void;
  onValidate: () => void;
  /** 이슈 행 클릭: 해당 노드·연결로 이동 */
  onFocus: (target: IssueTarget, issue: Issue) => void;
  onApplySuggestion: (issue: Issue, suggestion: IssueSuggestion) => void;
  /** [노드 설정 열기]: 노드 선택 + 설정 탭 + `path`(없으면 `details.field`) 필드 포커스 */
  onOpenNode?: (nodeId: string, path: string | undefined) => void;
}

/** 이슈의 필드 위치: 서버 `path`, 없으면 `details.field`(JSON Pointer로 보정) */
export function issueFieldPath(issue: Issue): string | undefined {
  if (typeof issue.path === "string" && issue.path !== "") return issue.path;
  const f = issue.details?.["field"];
  return typeof f === "string" && f !== "" ? (f.startsWith("/") ? f : `/${f}`) : undefined;
}

/**
 * 검증 이슈 패널(캔버스 아래). 서버가 준 이슈를 그대로 보여 주고(코드는 해석하지 않는다) 제안 버튼을 붙인다.
 * 검증 실패 시 기존 이슈를 흐리게 유지하고 [다시 시도]를 준다.
 */
export function IssuesPanel({ graph, validation, open, onToggle, onValidate, onFocus, onApplySuggestion, onOpenNode }: IssuesPanelProps) {
  const [filter, setFilter] = useState<Filter>("all");
  const { issues, phase } = validation;
  const [infoOpen, setInfoOpen] = useState(false);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const { error: errors, warning: warnings, info: infos } = severityCounts(issues);
  const firstError = sortIssues(issues).find((i) => i.severity === "error");
  const rows = buildIssueRows(issues.filter((i) => filter === "all" || i.severity === filter));
  const showInfoRows = filter === "info" || infoOpen;
  const infoRows = filter === "all" ? rows.filter((r) => r.severity === "info") : [];
  const mainRows = filter === "all" ? rows.filter((r) => r.severity !== "info") : rows;
  const toggleRow = (key: string) =>
    setExpanded((cur) => {
      const next = new Set(cur);
      if (!next.delete(key)) next.add(key);
      return next;
    });
  const renderRow = (row: IssueRow) => {
    const first = row.issues[0]!;
    const grouped = row.groupMessage !== undefined;
    const firstTarget = issueTarget(first, graph);
    const nodeTargets = row.issues.map((i) => issueTarget(i, graph));
    const targetText = grouped && row.issues.length > 1 ? t.issues.groupTargets(firstTarget.label, row.issues.length - 1) : firstTarget.label;
    const allLabels = nodeTargets.map((x) => x.label).join(", ");
    const clickable = firstTarget.kind !== "graph";
    const hint = first.hint;
    const open_ = expanded.has(row.key);
    const openNode = (issue: Issue) => {
      if (issue.node_id != null) onOpenNode?.(issue.node_id, issueFieldPath(issue));
      else onFocus(issueTarget(issue, graph), issue);
    };
    return (
      <>
        <tr key={row.key} className="team-issue-row" data-severity={row.severity} data-grouped={grouped ? "true" : undefined} onClick={() => clickable && onFocus(firstTarget, first)}>
          <td>
            {grouped ? (
              <button type="button" className="app-link-btn team-issue-expand" aria-expanded={open_} aria-label={open_ ? t.issues.groupCollapse : t.issues.groupExpand} onClick={(e) => { e.stopPropagation(); toggleRow(row.key); }}>
                {open_ ? "▾" : "▸"}
              </button>
            ) : null}
            <span className="app-sev" data-severity={row.severity}>{SEV_MARK[row.severity]} {m.severity[row.severity]}</span>
            {first.blocks_run ? <span className="ac-tag" title={t.issues.blocksRun}>{t.issues.blocksRun}</span> : null}
          </td>
          <td className="lib-cell-clip" title={allLabels}>
            {clickable ? (
              <button type="button" className="app-link-btn" onClick={(e) => { e.stopPropagation(); onFocus(firstTarget, first); }}>{targetText}</button>
            ) : (
              <span className="app-muted">{t.issues.targetGraph}</span>
            )}
          </td>
          <td>
            <div className="ac-clamp-2">{grouped ? row.groupMessage : issueMessage(first)}</div>
            {hint ? <div className="team-issue-hint app-muted">{hint}</div> : null}
          </td>
          <td className="lib-mono app-muted">{grouped ? "" : first.code}</td>
          <td className="team-issue-fix" onClick={(e) => e.stopPropagation()}>
            <IssueActions
              issue={first}
              suggestions={rowSuggestions(row)}
              canOpenNode={first.node_id != null && onOpenNode !== undefined}
              onApply={onApplySuggestion}
              onOpenNode={() => openNode(first)}
            />
          </td>
        </tr>
        {grouped && open_
          ? row.issues.map((issue, j) => (
              <tr key={`${row.key}:${j}`} className="team-issue-sub" data-severity={row.severity} aria-label={t.issues.groupSub}>
                <td />
                <td className="lib-cell-clip" title={nodeTargets[j]!.label}>
                  <span className="team-issue-sub-label">{nodeTargets[j]!.label}</span>
                </td>
                <td className="ac-clamp-2">{issueMessage(issue)}</td>
                <td />
                <td className="team-issue-fix">
                  <button type="button" className="ac-ge-btn" onClick={() => openNode(issue)}>{t.issues.actionOpenNode}</button>
                </td>
              </tr>
            ))
          : null}
      </>
    );
  };
  return (
    <section className="team-issues" aria-label={t.issues.region} data-open={open ? "true" : "false"} data-stale={phase === "failed" ? "true" : undefined}>
      <header className="team-issues-head">
        <button type="button" className="app-link-btn team-issues-toggle" aria-expanded={open} onClick={onToggle}>
          {open ? "▾" : "▸"} {t.issues.title(errors, warnings, infos)}
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
        {validation.validated && phase === "idle" && errors + warnings === 0 ? <span role="status" className="app-sev" data-severity="info">{infos > 0 ? t.issues.okInfoOnly(infos) : t.issues.ok}</span> : null}
        <span className="app-spacer" />
        <div className="lib-chips" role="group" aria-label={t.issues.filterLabel}>
          {(["all", "error", "warning", "info"] as const).map((f) => (
            <button key={f} type="button" className="lib-chip" aria-pressed={filter === f} onClick={() => setFilter(f)}>
              {{ all: t.issues.filterAll, error: t.issues.filterError, warning: t.issues.filterWarning, info: t.issues.filterInfo }[f]}
              {f === "all" ? ` ${issues.length}` : ` ${{ error: errors, warning: warnings, info: infos }[f]}`}
            </button>
          ))}
        </div>
      </header>
      {open && (mainRows.length > 0 || infoRows.length > 0) ? (
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
              {mainRows.map((row) => <Fragment key={row.key}>{renderRow(row)}</Fragment>)}
              {infoRows.length > 0 ? (
                <>
                  <tr className="team-issue-bucket" data-severity="info">
                    <td colSpan={5}>
                      <button type="button" className="app-link-btn" aria-expanded={infoOpen} onClick={() => setInfoOpen((v) => !v)}>
                        {infoOpen ? "▾" : "▸"} {t.issues.infoBucket(infos)}
                      </button>
                    </td>
                  </tr>
                  {showInfoRows ? infoRows.map((row) => <Fragment key={row.key}>{renderRow(row)}</Fragment>) : null}
                </>
              ) : null}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
