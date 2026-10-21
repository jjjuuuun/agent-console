import { ApiError, NETWORK_ERROR_CODE, toApiError } from "./errors";
import { filenameFromDisposition, type BlobResponse } from "./io";
import { resolveToken, type TokenSource } from "./token";

export interface BlobRequestOptions {
  /** `http://127.0.0.1:8765/api/v1` 처럼 접두어까지 붙은 주소 */
  base: string;
  token?: TokenSource | undefined;
  fetch: (input: string, init?: RequestInit) => Promise<Response>;
  method: string;
  path: string;
  body?: unknown;
  headers?: Record<string, string> | undefined;
}

function parseEtag(value: string | null): string | undefined {
  if (value === null || value === "") return undefined;
  return value.replace(/^W\//, "").replace(/^"|"$/g, "");
}

/** 바이너리 응답 요청(토큰 헤더 포함). 실패 본문은 JSON 오류로 읽어 `ApiError`로 던진다. */
export async function requestBlob(o: BlobRequestOptions): Promise<BlobResponse> {
  const headers: Record<string, string> = { Accept: "*/*", ...o.headers };
  const token = resolveToken(o.token);
  if (token !== undefined && token !== "") headers["X-Console-Token"] = token;
  const init: RequestInit = { method: o.method, headers };
  if (o.body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(o.body);
  }
  let response: Response;
  try {
    response = await o.fetch(o.base + o.path, init);
  } catch (cause) {
    const message = cause instanceof Error ? cause.message : "네트워크 오류";
    throw new ApiError(0, { code: NETWORK_ERROR_CODE, message }, { cause });
  }
  if (!response.ok) {
    const text = await response.text();
    let parsed: unknown;
    try {
      parsed = text === "" ? undefined : JSON.parse(text);
    } catch {
      parsed = undefined;
    }
    throw toApiError(response.status, parsed, parsed === undefined ? text : "");
  }
  return {
    blob: await response.blob(),
    filename: filenameFromDisposition(response.headers.get("Content-Disposition")),
    contentType: response.headers.get("Content-Type") ?? "",
    etag: parseEtag(response.headers.get("ETag")),
  };
}
