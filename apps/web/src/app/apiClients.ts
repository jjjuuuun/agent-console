import {
  createRestClient,
  createWsClient,
  type FetchLike,
  type RestClient,
  type WebSocketFactory,
  WS_AUTH_CLOSE_CODES,
  type WsClient,
  createRestIo,
} from "@agent-console/api-client";
import { createProjectsClient, type ProjectsClient } from "@agent-console/projects";

/**
 * 응답에서 읽은 "기능 구성이 바뀌었을 수 있다"는 신호. 켜져 있다고 믿던 기능의 REST가 404이거나(`not-found`),
 * 선택 포트가 없어 409 `feature_unavailable`이면(`unavailable`) 웹이 모듈 목록을 한 번 다시 읽는다.
 */
export type FeatureSignal = { kind: "not-found" } | { kind: "unavailable"; module: string; port: string };

/** 연결에 대한 읽기 전용 정보(서버 정보 화면·버전 점검용). 토큰은 없다. */
export interface ClientMeta {
  baseUrl: string;
  serverVersion: string;
  contractsVersion: string;
}

/** 앱이 쓰는 서버 클라이언트 묶음. */
export interface ApiClients {
  rest: RestClient;
  /** 프로젝트 REST(서버 프로젝트 모듈이 꺼져 있으면 호출하지 않는다). 전송은 `rest`와 같은 주소·토큰·fetch */
  projects: ProjectsClient;
  ws: WsClient;
  meta: ClientMeta;
}

export interface CreateApiClientsOptions {
  baseUrl: string;
  token?: string;
  fetch?: FetchLike;
  webSocket?: WebSocketFactory;
  /** REST가 401/403을 받았을 때 호출(토큰 만료 배너용). */
  onAuthRejected?: () => void;
  /** 기능 REST가 404 또는 409 `feature_unavailable`을 돌려줬을 때(모듈 목록 `/modules` 자체의 404는 제외). */
  onFeatureSignal?: (signal: FeatureSignal) => void;
  meta?: Partial<Omit<ClientMeta, "baseUrl">>;
}

/** 404·409를 보고 기능 신호를 낸다. 본문은 복제해서 읽으므로 호출자가 읽는 응답에는 영향이 없다. */
async function signalFeature(response: Response, input: string, emit: (signal: FeatureSignal) => void): Promise<void> {
  if (response.status === 404) {
    if (!/\/modules(\?|$)/.test(input)) emit({ kind: "not-found" });
    return;
  }
  if (response.status !== 409) return;
  try {
    const body = (await response.clone().json()) as { error?: { code?: unknown; details?: { module?: unknown; port?: unknown } } };
    if (body.error?.code === "feature_unavailable") {
      emit({ kind: "unavailable", module: String(body.error.details?.module ?? ""), port: String(body.error.details?.port ?? "") });
    }
  } catch {
    // 본문이 JSON이 아니면 신호 없음
  }
}

/** REST·WS 클라이언트를 같은 주소·토큰으로 만든다. */
export function createApiClients(options: CreateApiClientsOptions): ApiClients {
  const { baseUrl, token, onAuthRejected, onFeatureSignal } = options;
  const baseFetch: FetchLike = options.fetch ?? ((input, init) => globalThis.fetch(input, init));
  const guardedFetch: FetchLike = async (input, init) => {
    const response = await baseFetch(input, init);
    if (response.status === 401 || response.status === 403) onAuthRejected?.();
    if (onFeatureSignal !== undefined) await signalFeature(response, input, onFeatureSignal);
    return response;
  };
  const common = token === undefined ? { baseUrl } : { baseUrl, token };
  return {
    rest: createRestClient({ ...common, fetch: guardedFetch }),
    projects: createProjectsClient(createRestIo({ ...common, fetch: guardedFetch })),
    ws: createWsClient({
      ...common,
      noReconnectCloseCodes: WS_AUTH_CLOSE_CODES,
      ...(options.webSocket ? { webSocket: options.webSocket } : {}),
    }),
    meta: { baseUrl, serverVersion: options.meta?.serverVersion ?? "", contractsVersion: options.meta?.contractsVersion ?? "" },
  };
}

/** `GET /bootstrap`으로 토큰을 받아 클라이언트를 만든다. 실패하면 ApiError. */
export async function bootstrapClients(options: Omit<CreateApiClientsOptions, "token">): Promise<ApiClients> {
  const boot = await createRestClient({
    baseUrl: options.baseUrl,
    ...(options.fetch ? { fetch: options.fetch } : {}),
  }).getBootstrap();
  return createApiClients({
    ...options,
    token: boot.token,
    meta: { serverVersion: boot.server_version, contractsVersion: boot.contracts_version },
  });
}
