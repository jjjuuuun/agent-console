import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

// README 예제가 패키지 이름으로 import하므로 테스트에서는 소스를 가리킨다.
// 하위 경로 export를 추가하면 alias도 함께 추가한다. 사내 의존(text-editor)은 development 조건으로 소스를 읽는다.
export default defineConfig({
  resolve: {
    conditions: ["development"],
    alias: {
      "@agent-console/memory-view/testing": fileURLToPath(new URL("./src/testing.ts", import.meta.url)),
      "@agent-console/memory-view": fileURLToPath(new URL("./src/index.ts", import.meta.url)),
    },
  },
  test: { include: ["test/**/*.test.ts", "src/**/*.test.{ts,tsx}"], environment: "happy-dom", testTimeout: 30_000 },
});
