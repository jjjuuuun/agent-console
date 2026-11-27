import { KNOWN_ISSUE_CODES } from "@agent-console/contracts";
import type { ServerText } from "@agent-console/i18n";

/**
 * 위키 이슈 코드 중 화면이 서버 코드 묶음(`codes`)의 문구로 바꿔 보이는 것. 문구는 서버 묶음이 현재 언어로 준다(앱에 따로 두지 않는다).
 * 목록에 없는 코드와 묶음에 문구가 없는 코드는 서버가 준 원문을 그대로 쓴다(새 코드가 생겨도 화면은 깨지지 않는다).
 */
const LOCALIZED_CODES: ReadonlySet<string> = new Set([KNOWN_ISSUE_CODES.WIKI_UNKNOWN_TITLE_SOURCE, KNOWN_ISSUE_CODES.WIKI_REDACTED_CONTENT]);

/** 코드의 화면 문구. 묶음에 없으면 `fallback`(서버가 준 문구). */
export function wikiIssueText(code: string | null | undefined, fallback: string, server: ServerText): string {
  return code != null && LOCALIZED_CODES.has(code) ? server.issue(code, null, fallback) : fallback;
}

/** 이슈의 문구를 현재 언어 문구로 바꾼 사본(모르는 코드는 같은 값). 나머지 필드는 그대로다. */
export function localizeIssue<T extends { code: string; message: string }>(issue: T, server: ServerText): T {
  const text = wikiIssueText(issue.code, issue.message, server);
  return text === issue.message ? issue : { ...issue, message: text };
}

/** 위키 접근 이벤트(payload `code`)의 한 줄 요약. 문구가 있는 사유 코드가 아니면 undefined(기본 요약을 쓴다). */
export function wikiEventSummary(payload: Readonly<Record<string, unknown>> | null | undefined, server: ServerText): string | undefined {
  const code = payload?.["code"];
  if (typeof code !== "string" || !LOCALIZED_CODES.has(code)) return undefined;
  const text = server.issue(code, null, "");
  if (text === "") return undefined;
  const op = typeof payload?.["op"] === "string" ? `${payload["op"]} · ` : "";
  const path = typeof payload?.["path"] === "string" && payload["path"] !== "" ? ` (${payload["path"]})` : "";
  return `${op}${text}${path}`;
}
