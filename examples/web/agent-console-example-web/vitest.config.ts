import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

// README 예제가 패키지 이름으로 import하므로 테스트에서는 소스를 가리킨다.
// 이웃 패키지(log-view·arch-view·schema-form)는 `development` 조건으로 소스를 읽는다(앱과 같다).
export default defineConfig({
  resolve: {
    alias: { "@agent-console/example-web": fileURLToPath(new URL("./src/index.ts", import.meta.url)) },
    conditions: ["development"],
  },
  test: { include: ["test/**/*.test.ts", "src/**/*.test.{ts,tsx}"], environment: "happy-dom", testTimeout: 30_000 },
});
