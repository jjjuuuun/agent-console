import { ApiError, NETWORK_ERROR_CODE, type FetchLike, type WebSocketFactory } from "@agent-console/api-client";
import { bootstrapClients, type ApiClients, type FeatureSignal } from "./apiClients";
import { loadRuntimeConfig, resolveApiBaseUrl } from "./config";

/** 부팅 실패. 어느 주소로 시도했는지와 CORS 추정 여부를 함께 담는다(토큰은 담지 않는다). */
export class BootError extends Error {
  readonly baseUrl: string;
  /** 네트워크 오류인데 서버 주소가 다른 출처 — 허용 출처 설정 문제일 가능성이 있다 */
  readonly corsSuspected: boolean;

  constructor(baseUrl: string, cause: unknown, corsSuspected: boolean) {
    super(cause instanceof Error ? cause.message : "서버에 연결하지 못했습니다", { cause });
    this.name = "BootError";
    this.baseUrl = baseUrl;
    this.corsSuspected = corsSuspected;
  }
}

export interface BootOptions {
  /** 이 페이지의 출처(`window.location.origin`) */
  origin: string;
  /** 정적 설정 파일 주소 */
  configUrl: string;
  /** 빌드 변수 `VITE_AGENT_CONSOLE_API_URL` */
  envUrl?: string | undefined;
  fetch?: FetchLike;
  webSocket?: WebSocketFactory;
  onAuthRejected: () => void;
  onFeatureSignal?: (signal: FeatureSignal) => void;
}

function sameOrigin(a: string, b: string): boolean {
  try {
    return new URL(a).origin === new URL(b).origin;
  } catch {
    return false;
  }
}

/**
 * 부팅 순서: `/config.json`(서버 주소) → `GET /bootstrap`(토큰) → 클라이언트.
 * 설정 파일이 없어도 오류가 아니다. 서버 연결 실패는 {@link BootError}.
 */
export async function bootClients(options: BootOptions): Promise<ApiClients> {
  const fetchFn: FetchLike = options.fetch ?? ((input, init) => globalThis.fetch(input, init));
  const config = await loadRuntimeConfig(fetchFn, options.configUrl);
  const baseUrl = resolveApiBaseUrl({ config, envUrl: options.envUrl, origin: options.origin });
  try {
    return await bootstrapClients({
      baseUrl,
      fetch: fetchFn,
      onAuthRejected: options.onAuthRejected,
      ...(options.onFeatureSignal ? { onFeatureSignal: options.onFeatureSignal } : {}),
      ...(options.webSocket ? { webSocket: options.webSocket } : {}),
    });
  } catch (cause) {
    const network = cause instanceof ApiError && cause.code === NETWORK_ERROR_CODE;
    throw new BootError(baseUrl, cause, network && !sameOrigin(baseUrl, options.origin));
  }
}
