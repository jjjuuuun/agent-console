import "./teams.css";
import type { GraphValidationSummary, Issue } from "@agent-console/contracts";
import { Button } from "@agent-console/ui";
import { sortIssues } from "../../lib/issues";
import { teamMessages as t } from "./messages";

export type ValidationChipKind = "blocked" | "errors" | "warnings";

export interface ValidationChipInfo {
  kind: ValidationChipKind;
  count: number;
}

/**
 * 검증 요약 -> 칩 정보. `null`/`undefined`는 "계산 안 함"이라 칩이 없다(차단 아님).
 * 차단 여부는 `blocks_run`만 본다. 이슈 코드는 해석하지 않는다.
 */
export function validationChipOf(summary: GraphValidationSummary | null | undefined): ValidationChipInfo | undefined {
  if (summary == null) return undefined;
  const errors = summary.error_count ?? 0;
  const warnings = summary.warning_count ?? 0;
  if (summary.blocks_run) return { kind: "blocked", count: errors };
  if (errors > 0) return { kind: "errors", count: errors };
  if (warnings > 0) return { kind: "warnings", count: warnings };
  return undefined;
}

/** 행 선택·실행이 막혀 있는가(서버 `blocks_run`). 요약이 없으면 막지 않는다. */
export function blocksRun(summary: GraphValidationSummary | null | undefined): boolean {
  return summary?.blocks_run === true;
}

const MARK: Record<ValidationChipKind, string> = { blocked: "✕", errors: "✕", warnings: "▲" };

export interface ValidationChipProps {
  summary: GraphValidationSummary | null | undefined;
}

/** 검증 요약 칩: 아이콘 + 텍스트(색 단독 금지). 표시할 것이 없으면 아무것도 그리지 않는다. */
export function ValidationChip({ summary }: ValidationChipProps) {
  const info = validationChipOf(summary);
  if (info === undefined) return null;
  const text = info.kind === "blocked" ? t.validation.blocked(info.count) : info.kind === "errors" ? t.validation.errors(info.count) : t.validation.warnings(info.count);
  return (
    <span className="app-sev team-vchip" data-severity={info.kind === "warnings" ? "warning" : "error"} data-kind={info.kind} title={info.kind === "errors" ? t.validation.errorsRunnable : undefined}>
      <span aria-hidden="true">{MARK[info.kind]}</span> {text}
    </span>
  );
}

export const ISSUE_PREVIEW_LIMIT = 5;

/** 펼침에 보일 이슈: 막는 팀 구성이면 `blocks_run` 이슈 우선(없으면 전부), 오류 -> 경고 순서, 최대 5개. */
export function previewIssues(issues: readonly Issue[], blocked: boolean, limit = ISSUE_PREVIEW_LIMIT): { shown: Issue[]; rest: number } {
  const blocking = issues.filter((i) => i.blocks_run === true);
  const pool = sortIssues(blocked && blocking.length > 0 ? blocking : issues);
  return { shown: pool.slice(0, limit), rest: Math.max(0, pool.length - limit) };
}

export interface IssuePreviewProps {
  issues: readonly Issue[] | undefined;
  loading: boolean;
  failed: boolean;
  blocked: boolean;
  codes?: readonly string[] | undefined;
  onRetry: () => void;
}

/** 팀 구성 행 아래 펼침: 서버 메시지 그대로 최대 5개 + "외 N건" + 코드(mono muted). */
export function IssuePreview({ issues, loading, failed, blocked, onRetry }: IssuePreviewProps) {
  if (loading) return <p className="app-muted" role="status">{t.validation.loadingIssues}</p>;
  if (failed) {
    return (
      <p role="alert" className="app-sev" data-severity="error">
        {t.validation.loadIssuesFailed} <Button size="sm" onClick={onRetry}>{t.validation.retry}</Button>
      </p>
    );
  }
  const { shown, rest } = previewIssues(issues ?? [], blocked);
  return (
    <div className="team-vpreview">
      <ul className="team-vpreview-list">
        {shown.map((issue, i) => (
          <li key={`${i}:${issue.code}`}>
            <span className="app-sev" data-severity={issue.severity}>{issue.severity === "error" ? "✕" : issue.severity === "warning" ? "▲" : "ℹ"}</span> {issue.message}{" "}
            <span className="app-muted lib-mono">{issue.code}</span>
          </li>
        ))}
      </ul>
      {rest > 0 ? <p className="app-muted">{t.validation.more(rest)}</p> : null}
    </div>
  );
}
