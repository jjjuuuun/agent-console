import { registerSW } from "virtual:pwa-register";
import type { UpdateSource } from "./PwaContext";
import { createUpdateSource } from "./updateSource";

/**
 * 서비스 워커를 등록하고 새 버전 대기 상태를 `UpdateSource`로 노출한다.
 * `virtual:pwa-register`는 Vite 빌드/개발 서버에서만 풀리므로 이 파일은 `main.tsx`만 import한다.
 * 최초 설치는 갱신으로 알리지 않는다(`createUpdateSource`).
 */
export function registerServiceWorker(): UpdateSource {
  return createUpdateSource({
    register: (hooks) => registerSW(hooks),
    hasController: () => typeof navigator !== "undefined" && "serviceWorker" in navigator && navigator.serviceWorker.controller !== null,
  });
}
