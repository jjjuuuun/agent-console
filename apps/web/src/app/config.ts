import type { FetchLike } from "@agent-console/api-client";

/** 배포 후 고칠 수 있는 정적 설정 파일(`/config.json`)의 모양. 모든 키는 선택이다. */
export interface RuntimeConfig {
  /** 서버 주소. 예: `http://127.0.0.1:8765`. 없으면 빌드 변수 → 같은 출처 순으로 대체한다. */
  apiBaseUrl?: string;
}

function isHttpUrl(value: unknown): value is string {
  if (typeof value !== "string") return false;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

/**
 * `/config.json`을 읽는다. 파일이 없거나(404, SPA 대체 HTML 포함) 깨졌거나 네트워크가 실패해도 오류가 아니다 —
 * 빈 설정을 돌려주고 호출자는 같은 출처로 계속한다.
 * @param fetchFn fetch 주입(테스트)
 * @param url 설정 파일 주소
 */
export async function loadRuntimeConfig(fetchFn: FetchLike, url: string): Promise<RuntimeConfig> {
  try {
    const response = await fetchFn(url, { cache: "no-store", headers: { Accept: "application/json" } });
    if (!response.ok) return {};
    const parsed: unknown = JSON.parse(await response.text());
    if (typeof parsed !== "object" || parsed === null) return {};
    const apiBaseUrl = (parsed as { apiBaseUrl?: unknown }).apiBaseUrl;
    return isHttpUrl(apiBaseUrl) ? { apiBaseUrl: apiBaseUrl.replace(/\/+$/, "") } : {};
  } catch {
    return {};
  }
}

/** 서버 주소 결정 순서: `/config.json`의 `apiBaseUrl` → 빌드 변수 → 페이지와 같은 출처. */
export function resolveApiBaseUrl(args: { config: RuntimeConfig; envUrl: string | undefined; origin: string }): string {
  if (args.config.apiBaseUrl !== undefined) return args.config.apiBaseUrl;
  if (args.envUrl !== undefined && args.envUrl !== "") return args.envUrl.replace(/\/+$/, "");
  return args.origin;
}
