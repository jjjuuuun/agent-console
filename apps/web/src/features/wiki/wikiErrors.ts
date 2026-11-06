import { ApiError } from "@agent-console/api-client";
import { ERROR_CODES } from "@agent-console/contracts";
import type { WikiPageNotFoundDetails, WikiRuleRejectedDetails } from "@agent-console/contracts/wiki";
import { wikiMessages as m } from "./messages";

/** 위키 요청 실패를 화면이 다루는 종류로 나눈 것. 서버 코드는 화면에 노출하지 않는다. */
export type WikiFailure =
  /** 프로젝트 연동이 꺼져 있다(409 `wiki.spaces_unavailable`): 본문 전체를 안내로 바꾼다 */
  | { kind: "unavailable" }
  /** 위키를 찾을 수 없다(404 `wiki.not_found`) */
  | { kind: "notFound" }
  /** 페이지를 찾을 수 없다(404 `wiki.page_not_found`). `hasHistory`면 지운 페이지의 기록이 남아 있다 */
  | { kind: "pageNotFound"; hasHistory: boolean }
  /** 기록 저장소가 없다(409 `wiki.history_unavailable`) */
  | { kind: "historyUnavailable" }
  /** 해시가 달라 저장이 거부됐다(412) */
  | { kind: "conflict" }
  /** 쓰기 규칙이 막았다(422 `wiki.rule_rejected`). 규칙 id와 메시지는 서버 값 그대로 */
  | { kind: "ruleRejected"; ruleId: string; message: string; lines: number[] }
  /** 비밀로 보이는 값이 있어 막혔다(422 `wiki.secret_rejected`). 줄 번호만 있고 값은 없다 */
  | { kind: "secretRejected"; lines: number[]; message: string }
  /** 페이지가 한도를 넘는다(422 `wiki.too_large`) */
  | { kind: "tooLarge"; limit: number | null; message: string }
  /** 같은 경로의 페이지가 이미 있다(409 `wiki.page_exists`) */
  | { kind: "pageExists"; message: string }
  /** 없는 기록 버전(404 `wiki.version_not_found`) */
  | { kind: "versionNotFound"; message: string }
  /** 링크 삽입 틀이 없다(422 `wiki.link_insert_unavailable`) */
  | { kind: "linkInsertUnavailable" }
  /** 경로가 허용되지 않는다(422 `wiki.invalid_path`·`folders.invalid_path`). 사유는 서버 문장 */
  | { kind: "invalidPath"; message: string }
  /** 프로젝트 폴더·설정 문제(폴더 없음·설정 파일 오류·쓰기 불가·모르는 프로젝트) */
  | { kind: "problem"; message: string }
  | { kind: "generic"; message: string; code?: string };

function numbers(raw: unknown): number[] {
  return Array.isArray(raw) ? raw.filter((x): x is number => typeof x === "number") : [];
}

/** 비밀 거부 이슈들(`details.issues`)의 줄 번호를 모은다(값은 없다). */
function issueLines(details: Readonly<Record<string, unknown>>): number[] {
  const direct = numbers(details["lines"]);
  if (direct.length > 0) return direct;
  const issues = details["issues"];
  if (!Array.isArray(issues)) return [];
  return issues.flatMap((i) => (typeof i === "object" && i !== null ? numbers((i as { details?: { lines?: unknown } }).details?.lines) : []));
}

/** 오류를 화면 종류로 분류한다. `fallback`은 서버 문장도 없을 때 쓴다. */
export function classifyWikiError(error: unknown, fallback: string): WikiFailure {
  if (!(error instanceof ApiError)) return { kind: "generic", message: error instanceof Error && error.message !== "" ? error.message : fallback };
  const message = error.message !== "" ? error.message : fallback;
  const d = error.details;
  const rule = d as unknown as Partial<WikiRuleRejectedDetails>;
  const notFound = d as unknown as Partial<WikiPageNotFoundDetails>;
  switch (error.code) {
    case ERROR_CODES.WIKI_SPACES_UNAVAILABLE:
      return { kind: "unavailable" };
    case ERROR_CODES.WIKI_NOT_FOUND:
      return { kind: "notFound" };
    case ERROR_CODES.WIKI_PAGE_NOT_FOUND:
      return { kind: "pageNotFound", hasHistory: notFound.has_history === true };
    case ERROR_CODES.WIKI_HISTORY_UNAVAILABLE:
      return { kind: "historyUnavailable" };
    case ERROR_CODES.VERSION_CONFLICT:
      return { kind: "conflict" };
    case ERROR_CODES.WIKI_RULE_REJECTED:
      return { kind: "ruleRejected", ruleId: typeof rule.rule_id === "string" ? rule.rule_id : "", message: typeof rule.message === "string" ? rule.message : message, lines: numbers(rule.lines) };
    case ERROR_CODES.WIKI_SECRET_REJECTED:
      return { kind: "secretRejected", lines: issueLines(d), message };
    case ERROR_CODES.WIKI_TOO_LARGE:
      return { kind: "tooLarge", limit: typeof d["limit"] === "number" ? d["limit"] : null, message };
    case ERROR_CODES.WIKI_PAGE_EXISTS:
      return { kind: "pageExists", message };
    case ERROR_CODES.WIKI_VERSION_NOT_FOUND:
      return { kind: "versionNotFound", message };
    case ERROR_CODES.WIKI_LINK_INSERT_UNAVAILABLE:
      return { kind: "linkInsertUnavailable" };
    case ERROR_CODES.FOLDERS_INVALID_PATH:
      return { kind: "invalidPath", message };
    case ERROR_CODES.PROJECT_FOLDER_MISSING:
      return { kind: "problem", message: m.problem.folderMissing };
    case ERROR_CODES.PROJECT_MANIFEST_INVALID:
      return { kind: "problem", message: m.problem.manifestInvalid };
    case ERROR_CODES.PROJECT_CONFIG_READONLY:
    case ERROR_CODES.WIKI_CONFIG_READONLY:
      return { kind: "problem", message: m.problem.configReadonly };
    case ERROR_CODES.PROJECT_NOT_FOUND:
      return { kind: "problem", message: m.problem.notFound };
    default:
      return { kind: "generic", message, code: error.code };
  }
}

/** 오류가 서버 코드 `code`인가. */
export function hasCode(error: unknown, code: string): error is ApiError {
  return error instanceof ApiError && error.code === code;
}

/** 서버 문장을 우선 쓰는 짧은 문구(칸 아래·토스트용). */
export function failureText(error: unknown, fallback: string): string {
  const f = classifyWikiError(error, fallback);
  switch (f.kind) {
    case "ruleRejected":
      return m.band.ruleRejected(f.ruleId, f.message);
    case "secretRejected":
      return f.message !== "" ? f.message : m.band.secretRejected(f.lines.join(", "));
    case "unavailable":
      return m.unavailable.title;
    case "conflict":
      return m.band.conflict;
    case "linkInsertUnavailable":
      return m.editor.insertLinkOff;
    case "pageNotFound":
      return fallback;
    case "notFound":
      return m.notFound;
    case "historyUnavailable":
      return fallback;
    default:
      return f.message;
  }
}

/** 실패에 서버 문장이 있으면 그것(없는 종류는 undefined). 오류 블록의 본문에 그대로 보인다. */
export function failureDetail(f: WikiFailure): string | undefined {
  switch (f.kind) {
    case "ruleRejected":
    case "secretRejected":
    case "tooLarge":
    case "pageExists":
    case "versionNotFound":
    case "invalidPath":
    case "problem":
    case "generic":
      return f.message;
    default:
      return undefined;
  }
}
