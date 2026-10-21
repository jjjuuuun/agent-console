/**
 * @agent-console/api-client 공개 API.
 * 서버 REST(`createRestClient`)와 WebSocket(`createWsClient`)을 계약 타입으로 감싼 순수 TS 클라이언트.
 * 서버 주소·토큰·fetch·WebSocket 구현은 모두 인자로 받는다(React·DOM 전역 의존 없음).
 */
import { createRestClient, type RestClient, type RestClientOptions } from "./rest";
import { createWsClient, type WsClient, type WsClientOptions } from "./ws";

export const PACKAGE_NAME = "@agent-console/api-client" as const;

export { ApiError, NETWORK_ERROR_CODE } from "./errors";
export { createRestClient } from "./rest";
export type {
  FetchLike,
  HandoffParams,
  ListConversationsParams,
  ListGraphsParams,
  ListInteractionsParams,
  ListResourcesParams,
  ListRunEventsParams,
  ListRunsParams,
  ListTurnsParams,
  LogArchiveFormat,
  LogArchiveParams,
  LogQueryParams,
  PostMessageResult,
  RestClient,
  RestClientOptions,
  Versioned,
} from "./rest";
export type { TokenSource } from "./token";
export { definitionBase, encodePath, filenameFromDisposition, ISSUES_HEADER, parseIssuesHeader } from "./io";
export type { BlobResponse, RestIo } from "./io";
export { createRestIo } from "./transport";
export type { ExportArchive } from "./clients/exports";
export { logQuery } from "./clients/logs";
export type { ResourceFileContent } from "./clients/resources";
export type { VersionFileContent } from "./clients/versions";
export {
  createWsClient,
  WS_AUTH_CLOSE_CODES,
  WS_CLOSE_FORBIDDEN,
  WS_CLOSE_UNAUTHORIZED,
} from "./ws";
export type {
  BackoffOptions,
  ConnectionStatus,
  SubscribeOptions,
  Subscription,
  TimerApi,
  WebSocketFactory,
  WebSocketLike,
  WsClient,
  WsClientOptions,
} from "./ws";

export interface ApiClientOptions extends Omit<RestClientOptions, "fetch">, Pick<
  WsClientOptions,
  "backoff" | "timers" | "random" | "nextId" | "onError" | "webSocket" | "stableMs" | "noReconnectCloseCodes"
> {
  fetch?: RestClientOptions["fetch"];
}

/** REST와 WS 클라이언트를 같은 주소·토큰으로 함께 만든다. */
export function createClient(options: ApiClientOptions): { rest: RestClient; ws: WsClient } {
  const { fetch, webSocket, backoff, timers, random, nextId, onError, stableMs, noReconnectCloseCodes, ...common } =
    options;
  const rest = createRestClient({ ...common, ...(fetch ? { fetch } : {}) });
  const ws = createWsClient({
    ...common,
    ...(webSocket ? { webSocket } : {}),
    ...(backoff ? { backoff } : {}),
    ...(timers ? { timers } : {}),
    ...(random ? { random } : {}),
    ...(nextId ? { nextId } : {}),
    ...(onError ? { onError } : {}),
    ...(stableMs !== undefined ? { stableMs } : {}),
    ...(noReconnectCloseCodes ? { noReconnectCloseCodes } : {}),
  });
  return { rest, ws };
}
