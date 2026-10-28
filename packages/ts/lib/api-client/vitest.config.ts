import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

// README 예제가 패키지 이름으로 import하므로 테스트에서는 소스를 가리킨다.
// 하위 경로 export(기능 클라이언트·io·transport)도 같은 방식으로 소스를 가리킨다(package.json exports와 같은 표).
const src = (p: string) => fileURLToPath(new URL(`./src/${p}`, import.meta.url));
const subpaths = ["core", "catalog", "agents", "graphs", "runs", "chat", "interactions", "usage", "resources", "imports", "exports", "settings", "versions", "logs", "memory", "architecture"];
export default defineConfig({
  resolve: {
    alias: [
      ...subpaths.map((f) => ({ find: `@agent-console/api-client/${f}`, replacement: src(`clients/${f}.ts`) })),
      { find: "@agent-console/api-client/io", replacement: src("io.ts") },
      { find: "@agent-console/api-client/transport", replacement: src("transport.ts") },
      { find: /^@agent-console\/api-client$/, replacement: src("index.ts") },
    ],
  },
  test: { include: ["test/**/*.test.ts", "src/**/*.test.{ts,tsx}"], environment: "happy-dom" },
});
