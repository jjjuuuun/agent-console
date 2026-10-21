import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

// README 예제가 패키지 이름으로 import하므로 테스트에서는 소스를 가리킨다.
// 하위 경로 export를 추가하면 alias도 함께 추가한다.
export default defineConfig({
  resolve: { alias: { "@agent-console/chat": fileURLToPath(new URL("./src/index.ts", import.meta.url)) } },
  test: { include: ["test/**/*.test.ts", "src/**/*.test.{ts,tsx}"], environment: "happy-dom" },
});
