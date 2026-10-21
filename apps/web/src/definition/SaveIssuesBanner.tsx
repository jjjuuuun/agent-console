import type { Issue } from "@agent-console/contracts";
import { Banner } from "@agent-console/ui";
import { messages as m } from "../app/messages";

export interface SaveIssuesBannerProps {
  /** 저장 응답의 경고(`X-Console-Issues`). 비면 아무것도 그리지 않는다 */
  issues: readonly Issue[];
}

/** 저장은 성공했지만 서버가 경고한 이슈 목록(정의 편집 화면 공용, 표현 전용). */
export function SaveIssuesBanner({ issues }: SaveIssuesBannerProps) {
  if (issues.length === 0) return null;
  const t = m.definition.issues;
  return (
    <Banner tone="warning" title={t.title} aria-label={t.region}>
      <ul className="lib-issue-list">
        {issues.map((i, n) => (
          <li key={`${i.code}-${n}`}>
            {i.message}
            {i.path != null && i.path !== "" ? <> <code>{t.at(i.path)}</code></> : null}
          </li>
        ))}
      </ul>
    </Banner>
  );
}
