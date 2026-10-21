// `pnpm portability [--package NAME]`: 패키지 폴더를 임시 폴더로 복사해 저장소 밖에서 설치·빌드·테스트가 되는지 본다(design §3R.2.5).
// 사내 의존은 dist/npm tarball(`pnpm pack:all` 결과)로만 받는다. 외부 의존은 npm 캐시·인덱스에서 받는다.
// 계획은 lib/plans.mjs의 순수 함수가 만들고, 여기서는 복사와 프로세스만 다룬다.
import { spawnSync } from "node:child_process";
import { cpSync, existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

import { discoverPackages, selectPackage } from "./lib/fsutil.mjs";
import { DEFAULT_NPM_DIR, PORTABILITY_ENV, formatResultTable, planPortability } from "./lib/plans.mjs";
import { resolvePrefixes } from "./lib/workspace.mjs";

export const USAGE = `사용: node scripts/pkgkit/portability.mjs [옵션]

옵션:
  --root DIR       저장소 루트 (기본 현재 폴더)
  --package NAME   한 패키지만 검사 (이름 또는 폴더 끝 이름)
  --under PREFIX   찾을 폴더 접두사 (기본 packages/ts/)
  --prefix P       사내 패키지 이름 접두사, 반복 가능 (기본: 루트 이름의 scope → 패키지들의 scope)
  --npm-dir DIR    tarball 폴더 (기본 ${DEFAULT_NPM_DIR}, 루트 기준)
  --keep           임시 폴더를 지우지 않는다
  -h, --help       이 도움말
먼저 \`pnpm pack:all\`로 tarball을 만든다. 실패가 있으면 종료 코드 1.`;

const SKIP = new Set(["node_modules", "dist", ".git", "coverage"]);

/**
 * 한 패키지를 임시 폴더에서 검사한다.
 * @returns {{name: string, ok: boolean, failedStep?: string, note?: string}}
 */
function checkOne(pkg, workspace, npmDir, keep, prefixes) {
  const plan = planPortability({ pkg, workspace, npmDir, sep, prefixes });
  if (plan.missing.length) return { name: pkg.name, ok: false, failedStep: "plan", note: `워크스페이스에 없는 사내 의존: ${plan.missing.join(", ")}` };
  const absent = Object.values(plan.tarballs).filter((f) => !existsSync(f));
  if (absent.length) return { name: pkg.name, ok: false, failedStep: "tarball", note: `tarball이 없다(pnpm pack:all 먼저): ${absent.map((f) => f.split(sep).pop()).join(", ")}` };

  const tmp = mkdtempSync(join(tmpdir(), "pkgkit-portability-"));
  try {
    cpSync(pkg.dir, tmp, { recursive: true, filter: (src) => !SKIP.has(src.split(sep).pop() ?? "") });
    writeFileSync(join(tmp, "package.json"), `${JSON.stringify(plan.rewritten, null, 2)}\n`);
    for (const step of plan.steps) {
      const r = spawnSync(step.cmd, step.args, { cwd: tmp, env: { ...process.env, ...PORTABILITY_ENV }, encoding: "utf8", shell: process.platform === "win32" });
      if (r.status !== 0) {
        const tail = `${r.stdout ?? ""}${r.stderr ?? ""}`.trim().split("\n").slice(-15).join("\n");
        return { name: pkg.name, ok: false, failedStep: step.label, note: `\n${tail}` };
      }
    }
    return { name: pkg.name, ok: true, note: keep ? tmp : "" };
  } finally {
    if (!keep) rmSync(tmp, { recursive: true, force: true });
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const argv = process.argv.slice(2);
  const opt = { root: ".", package: undefined, under: undefined, prefix: [], "npm-dir": DEFAULT_NPM_DIR, keep: false };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === "-h" || a === "--help") {
      console.log(USAGE);
      process.exit(0);
    } else if (a === "--keep") opt.keep = true;
    else if (a === "--prefix") opt.prefix.push(argv[++i]);
    else if (a === "--root" || a === "--package" || a === "--npm-dir" || a === "--under") opt[a.slice(2)] = argv[++i];
    else {
      console.error(`portability: 모르는 옵션 ${a}\n\n${USAGE}`);
      process.exit(2);
    }
  }
  const root = resolve(opt.root);
  let workspace;
  try {
    workspace = discoverPackages(root, { under: opt.under });
  } catch (err) {
    console.error(`portability: ${err instanceof Error ? err.message : err}`);
    process.exit(2);
  }
  const rootFile = join(root, "package.json");
  const prefixes = resolvePrefixes({
    explicit: opt.prefix,
    rootPackageJson: existsSync(rootFile) ? JSON.parse(readFileSync(rootFile, "utf8")) : null,
    packageNames: workspace.map((p) => p.name),
  });
  const targets = opt.package ? selectPackage(workspace, opt.package) : workspace;
  if (targets.length === 0) {
    console.error(`portability: 검사할 패키지가 없다${opt.package ? `: ${opt.package}` : ""}`);
    process.exit(2);
  }
  const rows = targets.map((p) => {
    console.log(`... ${p.name}`);
    return checkOne(p, workspace, resolve(root, opt["npm-dir"]), opt.keep, prefixes);
  });
  console.log(`\n${formatResultTable(rows)}`);
  process.exit(rows.every((r) => r.ok) ? 0 : 1);
}
