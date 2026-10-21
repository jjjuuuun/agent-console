/**
 * 기능 클라이언트가 공유하는 전송 인터페이스와 작은 도구들.
 * 기능 클라이언트(`clients/*`)는 서로를 import하지 않고 이 파일(전송 계약)만 안다.
 * 전송 구현(토큰·재시도 없음·오류 변환)은 `createRestIo`(`transport.ts`)가 만든다.
 */

import type { Issue } from "@agent-console/contracts";

const enc = encodeURIComponent;
export { enc };

/** 헤더 이름 -> 값(요청 헤더). */
export type Headers = Record<string, string>;

/** `ETag`를 `version_hash`로 풀어 함께 돌려주는 응답. 서버가 ETag를 주지 않으면 `version_hash`는 undefined. */
export interface Versioned<T> {
  value: T;
  version_hash: string | undefined;
  /** 저장은 됐지만 경고할 이슈(응답 헤더 `X-Console-Issues`, design §3R.7). 헤더가 없거나 비었으면 undefined */
  issues?: Issue[] | undefined;
}

/** 응답 헤더 이름: 저장은 하되 경고하는 이슈(Issue 배열 JSON). */
export const ISSUES_HEADER = "X-Console-Issues";

/**
 * `X-Console-Issues` 값(Issue 배열 JSON)을 읽는다. 없거나 깨졌거나 빈 배열이면 undefined(경고 표시는 부가 정보라 실패시키지 않는다).
 */
export function parseIssuesHeader(value: string | null | undefined): Issue[] | undefined {
  if (value === null || value === undefined || value === "") return undefined;
  try {
    const parsed: unknown = JSON.parse(value);
    if (!Array.isArray(parsed)) return undefined;
    const issues = parsed.filter((x): x is Issue => typeof x === "object" && x !== null && typeof (x as Issue).message === "string");
    return issues.length === 0 ? undefined : issues;
  } catch {
    return undefined;
  }
}

/** 바이너리 응답: 본문 + 서버가 준 파일 이름·형식. */
export interface BlobResponse {
  blob: Blob;
  /** `Content-Disposition`의 파일 이름. 없으면 undefined */
  filename: string | undefined;
  /** `Content-Type`(없으면 빈 문자열) */
  contentType: string;
  /** `ETag`(따옴표·`W/` 제거). 없으면 undefined */
  etag?: string | undefined;
}

/** 기능 클라이언트가 쓰는 전송 함수. 실패는 모두 `ApiError`. */
export interface RestIo {
  request<T>(method: string, path: string, opts?: { body?: unknown; headers?: Headers }): Promise<T>;
  requestVersioned<T>(
    method: string,
    path: string,
    opts?: { body?: unknown; bytes?: Uint8Array; text?: string; headers?: Headers },
  ): Promise<Versioned<T>>;
  /** 본문을 텍스트로 받는다(`ETag` 포함). */
  requestText(method: string, path: string, opts?: { text?: string; headers?: Headers }): Promise<Versioned<string>>;
  /** 본문을 바이너리로 받는다(토큰 헤더가 필요한 다운로드용). */
  requestBlob(method: string, path: string, opts?: { body?: unknown; headers?: Headers }): Promise<BlobResponse>;
}

export function withHeaders(headers: Headers | undefined): { headers?: Headers } {
  return headers === undefined ? {} : { headers };
}

export function ifMatch(hash: string | undefined): Headers | undefined {
  return hash === undefined ? undefined : { "If-Match": hash };
}

/** 값이 있는 키만 쿼리 문자열로(`?a=1&b=x`, 없으면 빈 문자열). */
export function query(params: object | undefined): string {
  if (params === undefined) return "";
  const parts: string[] = [];
  for (const [k, v] of Object.entries(params as Record<string, unknown>)) {
    if (v === undefined || v === null) continue;
    parts.push(`${enc(k)}=${enc(String(v))}`);
  }
  return parts.length === 0 ? "" : `?${parts.join("&")}`;
}

/**
 * 정의 하나의 기본 경로. `collection`은 컬렉션 경로(예: `/agents`), 싱글턴(설정)은 `id`를 생략한다.
 * 컬렉션 표는 서버(`DEFAULT_VERSIONED_COLLECTIONS`)와 같은 데이터이며 호출하는 앱이 가진다.
 */
export function definitionBase(collection: string, id?: string): string {
  return id === undefined ? collection : `${collection}/${enc(id)}`;
}

/** `a/b c.md` -> `a/b%20c.md`(구분자 `/`는 유지). */
export function encodePath(path: string): string {
  return path.split("/").map(enc).join("/");
}

/** `Content-Disposition`에서 파일 이름을 읽는다(`filename*=UTF-8''...` 우선). */
export function filenameFromDisposition(value: string | null): string | undefined {
  if (value === null) return undefined;
  const star = /filename\*\s*=\s*([^']*)'[^']*'([^;]+)/i.exec(value);
  if (star?.[2] !== undefined) {
    try {
      return decodeURIComponent(star[2].trim());
    } catch {
      // 아래 일반형으로
    }
  }
  const plain = /filename\s*=\s*"([^"]*)"|filename\s*=\s*([^;]+)/i.exec(value);
  const name = plain?.[1] ?? plain?.[2]?.trim();
  return name === undefined || name === "" ? undefined : name;
}
