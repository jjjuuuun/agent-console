import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

// README 예제가 패키지 이름으로 import하므로 테스트에서는 소스를 가리킨다.
// 하위 경로 export를 추가하면 alias도 함께 추가한다.
export default defineConfig({
  resolve: { alias: { "@agent-console/graph-editor": fileURLToPath(new URL("./src/index.ts", import.meta.url)) } },
  test: { include: ["test/**/*.test.ts", "src/**/*.test.{ts,tsx}"], environment: "happy-dom",
    // React Flow 렌더 테스트는 고부하(load 30+)에서 5초 기본 상한을 넘는다. 시간 단언이 아니라 멈춤 방지용 상한이므로 넉넉히 둔다(5.2R.42).
    testTimeout: 30_000,
  },
});
