import { KNOWN_ISSUE_CODES } from "@agent-console/contracts";

/**
 * 위키 이슈 코드 → 화면 문구 표. 키는 계약 `KNOWN_ISSUE_CODES` 값이다. 표에 없는 코드는 서버가 준 문구를 그대로 쓴다
 * (새 코드가 생겨도 화면은 깨지지 않는다).
 */
export const wikiIssueTexts: Readonly<Record<string, string>> = {
  [KNOWN_ISSUE_CODES.WIKI_UNKNOWN_TITLE_SOURCE]: "제목 출처에 알 수 없는 값이 있어 그 항목은 건너뜁니다. 문법 규칙의 제목 출처 값을 확인하세요.",
  [KNOWN_ISSUE_CODES.WIKI_REDACTED_CONTENT]: "가린 비밀 표시가 본문에 들어 있어 그대로 저장할 수 없습니다. 가린 줄을 직접 고치세요.",
};

/** 코드의 화면 문구. 표에 없으면 `fallback`(서버가 준 문구). */
export function wikiIssueText(code: string | null | undefined, fallback: string): string {
  return (code != null ? wikiIssueTexts[code] : undefined) ?? fallback;
}

/** 이슈의 문구를 표 문구로 바꾼 사본(모르는 코드는 같은 값). 나머지 필드는 그대로다. */
export function localizeIssue<T extends { code: string; message: string }>(issue: T): T {
  const text = wikiIssueTexts[issue.code];
  return text === undefined || text === issue.message ? issue : { ...issue, message: text };
}

/** 위키 접근 이벤트(payload `code`)의 한 줄 요약. 표에 있는 사유 코드가 아니면 undefined(기본 요약을 쓴다). */
export function wikiEventSummary(payload: Readonly<Record<string, unknown>> | null | undefined): string | undefined {
  const code = payload?.["code"];
  if (typeof code !== "string") return undefined;
  const text = wikiIssueTexts[code];
  if (text === undefined) return undefined;
  const op = typeof payload?.["op"] === "string" ? `${payload["op"]} · ` : "";
  const path = typeof payload?.["path"] === "string" && payload["path"] !== "" ? ` (${payload["path"]})` : "";
  return `${op}${text}${path}`;
}
