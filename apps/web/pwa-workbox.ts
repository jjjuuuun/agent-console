/**
 * PWA(workbox) 캐시 설정 중 자동 배치 엔진(elkjs) 자산 부분. `vite.config.ts`가 가져다 쓴다.
 *
 * elkjs 청크(`elk-api-*.js`)와 워커(`elk-worker.min-*.js`, 약 1.4MB)는 첫 [정리]를 열 때만 필요하다.
 * 사전 캐시에 넣으면 설치 때마다 받고, 워커가 커져 workbox 기본 상한(2MiB)을 넘는 날 조용히 빠진다.
 * 상한(`maximumFileSizeToCacheInBytes`)은 올리지 않고, 두 자산 모두 사전 캐시에서 빼서 런타임 CacheFirst로 둔다:
 * 첫 [정리] 때 받아 이후 오프라인에서도 쓴다. 한 번도 받은 적 없는 오프라인이면 [정리]는 "엔진을 불러오지 못했습니다"로 실패할 뿐 편집은 막히지 않는다.
 */

/** 사전 캐시에서 뺄 elk 자산 글롭(빌드 출력 기준 상대 경로). */
export const ELK_PRECACHE_IGNORES: readonly string[] = ["**/assets/elk-*.js"];

/** 런타임 캐시 대상 URL 경로 패턴(`/assets/elk-api-<해시>.js`, `/assets/elk-worker.min-<해시>.js`). */
export const ELK_RUNTIME_PATTERN = /\/assets\/elk-[^/]+\.js$/;

export const ELK_CACHE_NAME = "ac-elk-engine";

/**
 * workbox `runtimeCaching` 항목: elk 자산은 CacheFirst.
 * `urlPattern` 함수는 서비스 워커 파일에 소스 그대로 들어가므로 바깥 변수를 참조하면 안 된다(정규식을 안에 적는다. 테스트가 확인).
 */
export const elkRuntimeCaching = {
  urlPattern: ({ url }: { url: URL }): boolean => /\/assets\/elk-[^/]+\.js$/.test(url.pathname),
  handler: "CacheFirst" as const,
  options: {
    cacheName: ELK_CACHE_NAME,
    cacheableResponse: { statuses: [200] },
    expiration: { maxEntries: 8 },
  },
};
