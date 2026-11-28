import type { Issue } from "@agent-console/contracts";
import { useServerText, useT } from "@agent-console/i18n";

/** 검사 문제 목록(심각도는 글자와 기호로도 구분한다). */
export function IssueList({ issues, label }: { issues: readonly Issue[]; label: string }) {
  const t = useT("memorySettings");
  const serverText = useServerText();
  if (issues.length === 0) return null;
  return (
    <ul className="memset-issues" aria-label={label}>
      {issues.map((i, n) => (
        <li key={`${i.code}:${i.path ?? ""}:${n}`} className="memset-issue" data-severity={i.severity}>
          <span className="app-sev" data-severity={i.severity} aria-hidden="true">{i.severity === "error" ? "●" : "▲"}</span>
          <span className="memset-issue-text">
            <span className="ac-sr-only">{`${i.severity === "error" ? t("issues.error") : t("issues.warning")} `}</span>
            {serverText.issue(i.code, i.details, serverText.text(i.message))}
            {i.path ? <span className="memset-issue-path"> {i.path}</span> : null}
          </span>
        </li>
      ))}
    </ul>
  );
}
