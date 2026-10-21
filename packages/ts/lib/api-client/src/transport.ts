/**
 * 전송 구현: 주소·토큰·fetch를 받아 `RestIo`를 만든다. 기능 클라이언트는 이 함수의 결과(`RestIo`)만 받는다.
 * 하위 경로 `@agent-console/api-client/io`로도 공개한다(기능 클라이언트를 하나만 쓰는 쪽용).
 */
import { requestBlob as requestBlobRaw } from "./blob";
import { ApiError, NETWORK_ERROR_CODE, toApiError } from "./errors";
import { ISSUES_HEADER, parseIssuesHeader, type RestIo, type Versioned } from "./io";
import { resolveToken, type TokenSource } from "./token";

/** fetch 호환 함수(브라우저·Node 기본 fetch 또는 테스트용 가짜). */
export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export interface RestClientOptions {
  /** 서버 주소. 예: `http://127.0.0.1:8765` (끝의 `/`는 무시). 경로 접두어 `/api/v1`는 클라이언트가 붙인다. */
  baseUrl: string;
  /** 쓰기 요청의 `X-Console-Token`. 문자열 또는 매번 읽는 함수. 없으면 헤더를 보내지 않는다. */
  token?: TokenSource;
  /** fetch 구현 주입. 기본은 전역 `fetch`. */
  fetch?: FetchLike;
}

const API_PREFIX = "/api/v1";

/** `"<hash>"`, `W/"<hash>"` → `<hash>`. */
function parseEtag(value: string | null): string | undefined {
  if (value === null || value === "") return undefined;
  return value.replace(/^W\//, "").replace(/^"|"$/g, "");
}

/**
 * 전송 함수 묶음을 만든다.
 * @param options 서버 주소·토큰·fetch 주입
 */
export function createRestIo(options: RestClientOptions): RestIo {
  const base = options.baseUrl.replace(/\/+$/, "") + API_PREFIX;

  async function requestRaw(
    method: string,
    path: string,
    opts: { body?: unknown; text?: string; bytes?: Uint8Array; headers?: Record<string, string> } = {},
  ): Promise<{ text: string; parsed: unknown; etag: string | undefined; response: Response }> {
    const doFetch = options.fetch ?? globalThis.fetch.bind(globalThis);
    const headers: Record<string, string> = { Accept: "application/json", ...opts.headers };
    const token = resolveToken(options.token);
    if (token !== undefined && token !== "") headers["X-Console-Token"] = token;
    const init: RequestInit = { method, headers };
    if (opts.text !== undefined) {
      if (headers["Content-Type"] === undefined) headers["Content-Type"] = "text/plain; charset=utf-8";
      init.body = opts.text;
    } else if (opts.bytes !== undefined) {
      if (headers["Content-Type"] === undefined) headers["Content-Type"] = "application/octet-stream";
      init.body = opts.bytes as BodyInit;
    } else if (opts.body !== undefined) {
      headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(opts.body);
    }

    let response: Response;
    try {
      response = await doFetch(base + path, init);
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "네트워크 오류";
      throw new ApiError(0, { code: NETWORK_ERROR_CODE, message }, { cause });
    }

    const text = await response.text();
    let parsed: unknown;
    if (text !== "") {
      try {
        parsed = JSON.parse(text);
      } catch {
        parsed = undefined;
      }
    }
    if (!response.ok) throw toApiError(response.status, parsed, parsed === undefined ? text : "");
    return { text, parsed, etag: parseEtag(response.headers.get("ETag")), response };
  }

  async function request<T>(method: string, path: string, opts: { body?: unknown; headers?: Record<string, string> } = {}): Promise<T> {
    return (await requestRaw(method, path, opts)).parsed as T;
  }

  /** JSON 응답 + `ETag`. */
  async function requestVersioned<T>(
    method: string,
    path: string,
    opts: { body?: unknown; text?: string; bytes?: Uint8Array; headers?: Record<string, string> } = {},
  ): Promise<Versioned<T>> {
    const r = await requestRaw(method, path, opts);
    const issues = parseIssuesHeader(r.response.headers.get(ISSUES_HEADER));
    return { value: r.parsed as T, version_hash: r.etag, ...(issues === undefined ? {} : { issues }) };
  }

  return {
    request,
    requestVersioned,
    requestText: async (method, path, opts = {}) => {
      const r = await requestRaw(method, path, opts);
      const issues = parseIssuesHeader(r.response.headers.get(ISSUES_HEADER));
      return { value: r.text, version_hash: r.etag, ...(issues === undefined ? {} : { issues }) };
    },
    requestBlob: (method, path, opts = {}) =>
      requestBlobRaw({
        base,
        token: options.token,
        fetch: options.fetch ?? globalThis.fetch.bind(globalThis),
        method,
        path,
        body: opts.body,
        headers: opts.headers,
      }),
  };
}
