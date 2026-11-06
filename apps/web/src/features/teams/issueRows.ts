import type { Issue, IssueSuggestion } from "@agent-console/contracts";
import { mergeSuggestions } from "@agent-console/graph-editor";
import { sortIssues } from "../../lib/issues";

/** 이슈 행 하나: 묶음이 없으면 이슈 1개, 있으면 같은 `group.key` 이슈 전부. 이슈 코드는 해석하지 않는다. */
export interface IssueRow {
  /** 행 키(묶음이면 `group.key`) */
  key: string;
  severity: Issue["severity"];
  /** 묶음 문장(그룹의 message 필드). 묶음이 아니면 undefined */
  groupMessage?: string;
  issues: Issue[];
}

/** 행에 붙을 제안: 같은 `id`는 하나로 합친다(`count`개 이슈의 패치). */
export interface RowSuggestion {
  suggestion: IssueSuggestion;
  count: number;
}

/** 오류 -> 경고 -> 정보 순으로 정렬하고, 같은 `group.key`의 이슈는 첫 이슈 자리의 한 행으로 묶는다. */
export function buildIssueRows(issues: readonly Issue[]): IssueRow[] {
  const rows: IssueRow[] = [];
  const byKey = new Map<string, IssueRow>();
  sortIssues(issues).forEach((issue, i) => {
    const g = issue.group;
    if (g == null || g.key === "") {
      rows.push({ key: `#${i}`, severity: issue.severity, issues: [issue] });
      return;
    }
    const k = `${issue.severity}:${g.key}`;
    const found = byKey.get(k);
    if (found !== undefined) {
      found.issues.push(issue);
      return;
    }
    const row: IssueRow = { key: `g:${k}`, severity: issue.severity, groupMessage: g.message, issues: [issue] };
    byKey.set(k, row);
    rows.push(row);
  });
  return rows;
}

/** 행의 제안 버튼 목록: 첫 이슈의 제안 순서를 따르고, 같은 `id`의 다른 이슈 제안은 합친다. */
export function rowSuggestions(row: IssueRow): RowSuggestion[] {
  const out: RowSuggestion[] = [];
  const seen = new Set<string>();
  for (const s of row.issues.flatMap((i) => i.suggestions ?? [])) {
    if (seen.has(s.id)) continue;
    seen.add(s.id);
    const same = row.issues.flatMap((i) => (i.suggestions ?? []).filter((x) => x.id === s.id));
    const merged = mergeSuggestions(same);
    if (merged !== undefined) out.push({ suggestion: merged, count: same.length });
  }
  return out;
}

/** 심각도별 개수(정보 포함). 묶음이 아니라 이슈 단위. */
export function severityCounts(issues: readonly Issue[]): { error: number; warning: number; info: number } {
  const c = { error: 0, warning: 0, info: 0 };
  for (const i of issues) c[i.severity] += 1;
  return c;
}
