import type { Issue } from "@agent-console/contracts";
import type { FormError } from "@agent-console/schema-form";
import { messages } from "../app/messages";

/** 서버 검증기(JSON Schema 키워드) 이슈의 영어 메시지를 한국어로. 모르면 서버 메시지 그대로. */
export function issueMessage(issue: Issue): string {
  const validator = issue.details?.["validator"];
  const ko = typeof validator === "string" ? messages.issues.validators[validator] : undefined;
  return ko !== undefined && !/[가-힣]/.test(issue.message) ? ko : issue.message;
}

export interface IssueCounts {
  error: number;
  warning: number;
  info: number;
}

export function countIssues(issues: readonly Issue[]): IssueCounts {
  const counts: IssueCounts = { error: 0, warning: 0, info: 0 };
  for (const issue of issues) counts[issue.severity] += 1;
  return counts;
}

export interface NodeIssueSplit {
  /** config 안의 경로(JSON Pointer)가 있어 폼 필드에 붙는 오류 */
  fieldErrors: FormError[];
  /** 경로가 없거나 정보 수준이라 "이 노드의 문제" 목록으로 보여 줄 이슈 */
  unmapped: Issue[];
}

/**
 * 한 노드의 이슈를 폼 필드 오류와 나머지로 나눈다.
 * 서버 `Issue.path`는 노드 `config` 기준 JSON Pointer다.
 */
export function splitNodeIssues(issues: readonly Issue[], nodeId: string): NodeIssueSplit {
  const fieldErrors: FormError[] = [];
  const unmapped: Issue[] = [];
  for (const issue of issues) {
    if (issue.node_id !== nodeId) continue;
    const path = issue.path;
    if (typeof path === "string" && (path === "" || path.startsWith("/")) && issue.severity !== "info") {
      fieldErrors.push({ path, message: issueMessage(issue), severity: issue.severity === "warning" ? "warning" : "error" });
    } else {
      unmapped.push(issue);
    }
  }
  return { fieldErrors, unmapped };
}

/** 이슈 행 정렬: 오류 -> 경고 -> 정보. 같은 심각도는 원래 순서 유지. */
export function sortIssues(issues: readonly Issue[]): Issue[] {
  const rank = { error: 0, warning: 1, info: 2 } as const;
  return issues
    .map((issue, index) => ({ issue, index }))
    .sort((a, b) => rank[a.issue.severity] - rank[b.issue.severity] || a.index - b.index)
    .map((x) => x.issue);
}
