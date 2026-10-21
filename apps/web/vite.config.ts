import { readFileSync } from "node:fs";
import react from "@vitejs/plugin-react";
import { defaultClientConditions, defineConfig, loadEnv } from "vite";
import { VitePWA } from "vite-plugin-pwa";
import { ELK_PRECACHE_IGNORES, elkRuntimeCaching } from "./pwa-workbox";

const APP_NAME = "Agent Console";

/**
 * 개발·미리보기 서버: `/api`, `/ws`를 Agent Console 서버로 넘긴다(같은 출처로 동작).
 * 대상 주소는 환경 변수로 정한다(코드에 포트 고정 없음):
 *   AGENT_CONSOLE_SERVER_URL=http://127.0.0.1:8765   (우선)
 *   또는 서버와 같은 AGENT_CONSOLE_HOST / AGENT_CONSOLE_PORT (기본 127.0.0.1 / 서버 기본 포트 8765)
 * 서버 주소를 직접 부르려면 배포한 `config.json`의 `apiBaseUrl`(서버 허용 출처 설정 필요).
 *
 * PWA: manifest + 서비스 워커는 정적 파일만 캐시한다. 자동 배치 엔진(elk) 자산은 사전 캐시에서 빼고 런타임 캐시로 둔다(`pwa-workbox.ts`). `/api`·`/ws`·`config.json`은 캐시·대체 응답에서 제외한다.
 */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "AGENT_CONSOLE_");
  const target =
    env["AGENT_CONSOLE_SERVER_URL"] ||
    `http://${env["AGENT_CONSOLE_HOST"] || "127.0.0.1"}:${env["AGENT_CONSOLE_PORT"] || "8765"}`;
  const proxy = {
    "/api": { target, changeOrigin: true },
    "/ws": { target, changeOrigin: true, ws: true },
  };
  const pkg = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf8")) as { version: string };
  return {
    plugins: [
      react(),
      VitePWA({
        registerType: "prompt",
        injectRegister: false,
        manifest: {
          name: APP_NAME,
          short_name: APP_NAME,
          description: "Agent Console",
          start_url: "/",
          scope: "/",
          display: "standalone",
          background_color: "#111827",
          theme_color: "#111827",
          lang: "ko",
          icons: [
            { src: "icon-192.png", sizes: "192x192", type: "image/png" },
            { src: "icon-512.png", sizes: "512x512", type: "image/png" },
            { src: "icon-maskable-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
          ],
        },
        workbox: {
          globPatterns: ["**/*.{js,css,html,svg,png,woff2}"],
          globIgnores: ["config.json", ...ELK_PRECACHE_IGNORES],
          navigateFallback: "index.html",
          navigateFallbackDenylist: [/^\/api\//, /^\/ws/, /^\/config\.json/],
          runtimeCaching: [elkRuntimeCaching],
          cleanupOutdatedCaches: true,
        },
      }),
    ],
    // 사내 패키지는 exports의 development 조건(소스)을 쓴다: 앱 빌드가 패키지 dist 빌드를 기다리지 않는다.
    resolve: { conditions: [...defaultClientConditions, "development"] },
    define: { "import.meta.env.VITE_APP_VERSION": JSON.stringify(pkg.version) },
    // 빌드 출력 폴더(기본 dist). 같은 저장소에서 e2e를 동시에 돌리는 작업이 서로의 빌드를 덮어쓰지 않게 환경변수로 바꿀 수 있다.
    build: { outDir: process.env["AGENT_CONSOLE_WEB_OUTDIR"] || "dist" },
    // /mnt/c(WSL에서 본 Windows 디스크)는 파일 변경 이벤트가 오지 않는다: AGENT_CONSOLE_WATCH_POLLING=1이면 polling으로 감시한다(기본 꺼짐, 간격 AGENT_CONSOLE_WATCH_INTERVAL ms).
    server: {
      proxy,
      ...(process.env["AGENT_CONSOLE_WATCH_POLLING"] === "1"
        ? { watch: { usePolling: true, interval: Number(process.env["AGENT_CONSOLE_WATCH_INTERVAL"]) || 500 } }
        : {}),
    },
    preview: { proxy },
  };
});
