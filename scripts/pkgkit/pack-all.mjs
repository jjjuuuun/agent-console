// `pnpm pack:all`: 모든 패키지를 빌드하고 tarball로 묶어 dist/npm에 모은다(design §3R.2.5).
// 저장소 밖 이식 검사(portability)와 사내 설치의 입력이 된다.
import { spawnSync } from "node:child_process";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { DEFAULT_NPM_DIR, planPackAll } from "./lib/plans.mjs";

export const USAGE = `사용: node scripts/pkgkit/pack-all.mjs [--root DIR] [--out DIR] [--dry-run]

  --root DIR   저장소 루트 (기본 현재 폴더)
  --out DIR    tarball 폴더 (기본 ${DEFAULT_NPM_DIR}, 루트 기준)
  --dry-run    실행하지 않고 명령만 출력`;

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const argv = process.argv.slice(2);
  const opt = { root: ".", out: DEFAULT_NPM_DIR, dryRun: false };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === "-h" || a === "--help") {
      console.log(USAGE);
      process.exit(0);
    } else if (a === "--dry-run") opt.dryRun = true;
    else if (a === "--root" || a === "--out") opt[a.slice(2)] = argv[++i];
    else {
      console.error(`pack:all: 모르는 옵션 ${a}\n\n${USAGE}`);
      process.exit(2);
    }
  }
  const root = resolve(opt.root);
  for (const step of planPackAll({ outDir: resolve(root, opt.out) })) {
    console.log(`> ${step.cmd} ${step.args.join(" ")}`);
    if (opt.dryRun) continue;
    const r = spawnSync(step.cmd, step.args, { cwd: root, stdio: "inherit", shell: process.platform === "win32" });
    if (r.status !== 0) {
      console.error(`pack:all: ${step.label} 단계 실패`);
      process.exit(r.status ?? 1);
    }
  }
}
