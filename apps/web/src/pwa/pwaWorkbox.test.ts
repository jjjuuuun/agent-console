import { existsSync, readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { ELK_CACHE_NAME, ELK_PRECACHE_IGNORES, ELK_RUNTIME_PATTERN, elkRuntimeCaching } from "../../pwa-workbox";

// happy-dom은 URL을 file 스킴으로 두지 않으므로 경로는 이 파일 위치로 만든다
const webRoot = resolve(import.meta.dirname, "../..");
const dist = resolve(webRoot, "dist");

describe("PWA: elk 자산은 사전 캐시에서 빼고 런타임 캐시로 둔다 (graph-edges §4.4, E-5)", () => {
  it("런타임 패턴은 elk 청크·워커만 맞춘다", () => {
    for (const ok of ["/assets/elk-api-Z7C9yahg.js", "/assets/elk-worker.min-CBpdZsm8.js"]) expect(ELK_RUNTIME_PATTERN.test(ok)).toBe(true);
    for (const no of ["/assets/GraphEditor-DK7MWHdN.js", "/assets/elkish.js", "/api/elk-x.js", "/assets/elk-api.css"]) expect(ELK_RUNTIME_PATTERN.test(no)).toBe(false);
  });
  it("urlPattern 함수는 바깥 변수 없이 단독으로 동작한다(서비스 워커에 소스로 들어가므로)", () => {
    const standalone = new Function(`return (${elkRuntimeCaching.urlPattern.toString()})`)() as typeof elkRuntimeCaching.urlPattern;
    expect(standalone({ url: new URL("https://x.test/assets/elk-worker.min-abc.js") })).toBe(true);
    expect(standalone({ url: new URL("https://x.test/assets/index-abc.js") })).toBe(false);
  });
  it("CacheFirst이고 사전 캐시 제외 글롭이 같은 이름 규칙이다", () => {
    expect(elkRuntimeCaching.handler).toBe("CacheFirst");
    expect(elkRuntimeCaching.options.cacheName).toBe(ELK_CACHE_NAME);
    expect(ELK_PRECACHE_IGNORES).toEqual(["**/assets/elk-*.js"]);
  });
  it("vite.config.ts는 사전 캐시 상한(maximumFileSizeToCacheInBytes)을 올리지 않고 elk 설정을 연결한다", () => {
    const cfg = readFileSync(resolve(webRoot, "vite.config.ts"), "utf8");
    expect(cfg).not.toContain("maximumFileSizeToCacheInBytes");
    expect(cfg).toContain("...ELK_PRECACHE_IGNORES");
    expect(cfg).toContain("runtimeCaching: [elkRuntimeCaching]");
  });

  // 빌드 산출물 검사: `pnpm --filter @agent-console/web build` 뒤 dist에 elk 자산이 있을 때만 돈다
  // (웹 앱이 자동 배치 엔진을 번들에 넣으면 활성화된다. 빌드는 /mnt/c에서 1분 이상 걸려 단위 테스트가 직접 빌드하지 않는다).
  const assets = existsSync(`${dist}/assets`) ? readdirSync(`${dist}/assets`).filter((f) => /^elk-.+\.js$/.test(f)) : [];
  it.skipIf(assets.length === 0 || !existsSync(`${dist}/sw.js`))("dist/sw.js: elk 자산은 사전 캐시 목록에 없고 런타임 CacheFirst 경로가 있다", () => {
    const sw = readFileSync(`${dist}/sw.js`, "utf8");
    for (const f of assets) expect(sw).not.toContain(f);
    expect(sw).toContain(ELK_CACHE_NAME);
    expect(sw).toContain("CacheFirst");
    expect(sw).not.toContain("ELK_RUNTIME_PATTERN");
  });
});
