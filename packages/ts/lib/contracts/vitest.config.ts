import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

// README 예제가 패키지 이름으로 import하므로 테스트에서는 소스를 가리킨다.
// 하위 경로(`@agent-console/contracts/<하위 모듈>`)는 생성된 하위 모듈 파일로 보낸다.
const generated = fileURLToPath(new URL("./src/generated/", import.meta.url));
export default defineConfig({
  resolve: {
    alias: [
      { find: /^@agent-console\/contracts$/, replacement: fileURLToPath(new URL("./src/index.ts", import.meta.url)) },
      { find: /^@agent-console\/contracts\/([a-z_]+)$/, replacement: `${generated}$1.ts` },
    ],
  },
  test: { include: ["test/**/*.test.ts", "src/**/*.test.{ts,tsx}"], environment: "happy-dom" },
});
