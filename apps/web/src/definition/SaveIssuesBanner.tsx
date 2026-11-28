import type { Issue } from "@agent-console/contracts";
import { useServerText } from "@agent-console/i18n";
import { Banner } from "@agent-console/ui";
import { useAppMessages, type AppMessages } from "../app/appMessages";

export interface SaveIssuesBannerProps {
  /** 저장 응답의 경고(`X-Console-Issues`). 비면 아무것도 그리지 않는다 */
  issues: readonly Issue[];
}

/** 이슈 경로(`/config/wikis/1/wiki`)를 사람이 읽는 위치로 바꾼다: 숫자 칸은 "n번째"(0부터 → 1부터), 나머지는 키 그대로, 구분은 메시지 표. */
export function readablePath(path: string, t: Pick<AppMessages["definition"]["issues"], "pathIndex" | "pathSeparator">): string {
  const parts = path.split("/").filter((p) => p !== "");
  if (parts.length === 0) return path;
  return parts.map((p) => (/^\d+$/.test(p) ? t.pathIndex(Number(p) + 1) : p)).join(t.pathSeparator);
}

/** 저장은 성공했지만 서버가 경고한 이슈 목록(정의 편집 화면 공용, 표현 전용). */
export function SaveIssuesBanner({ issues }: SaveIssuesBannerProps) {
  const m = useAppMessages();
  const serverText = useServerText();
  if (issues.length === 0) return null;
  const t = m.definition.issues;
  return (
    <Banner tone="warning" title={t.title} aria-label={t.region}>
      <ul className="lib-issue-list">
        {issues.map((i, n) => (
          <li key={`${i.code}-${n}`}>
            {serverText.issue(i.code, i.details, serverText.text(i.message))}
            {i.path != null && i.path !== "" ? <> <code>{t.at(readablePath(i.path, t))}</code></> : null}
          </li>
        ))}
      </ul>
    </Banner>
  );
}
