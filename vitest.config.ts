import { availableParallelism } from "node:os";

import { defineConfig } from "vitest/config";

// 루트 실행은 프로젝트들을 모아 돌린다: 패키지는 자기 vitest.config.ts(저장소 밖에서도 같은 설정으로 돈다),
// 앱·스크립트는 여기서 정의한다. DOM 환경은 happy-dom(/mnt/c에서 jsdom 로딩이 느림).
// 개별 파일이 다른 환경이 필요하면 파일 상단 지시자로 덮어쓴다.
// 워커 수: /mnt/c(WSL)에서는 워커 기동이 느려 한꺼번에 많이 띄우면 vitest의 기동 제한(90초, vitest 5에서 설정 불가)을 넘겨
// "Timeout starting forks runner"가 간헐적으로 난다. 동시 기동 수를 제한하고, 환경에 맞게 VITEST_MAX_WORKERS로 바꾼다.
// 패키지별 vitest.config.ts는 maxWorkers를 따로 두지 않으므로(저장소 밖 단독 실행), 같은 sequence.groupOrder 안에서
// 프로젝트 간 maxWorkers가 달라지지 않게 환경변수로 내보내 모든 프로젝트가 같은 값을 쓰게 한다.
const maxWorkers = Number(process.env["VITEST_MAX_WORKERS"] ?? "") || Math.max(1, Math.min(4, availableParallelism() - 1));
process.env["VITEST_MAX_WORKERS"] = String(maxWorkers);

export default defineConfig({
  test: {
    maxWorkers,
    projects: [
      "packages/ts/*/*/vitest.config.ts",
      { test: { name: "web", include: ["apps/web/src/**/*.test.{ts,tsx}"], environment: "happy-dom" } },
      { test: { name: "scripts", include: ["scripts/**/*.test.mjs"], environment: "happy-dom" } },
    ],
  },
});
