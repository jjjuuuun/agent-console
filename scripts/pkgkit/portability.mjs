// `pnpm portability [--package NAME]`: 패키지 폴더를 임시 폴더로 복사해 저장소 밖에서 설치·빌드·테스트가 되는지 본다(design §3R.2.5).
// 대상은 pnpm 워크스페이스 멤버에서 앱(`agentConsole.kind: "app"`)을 뺀 전부다(packages/ts와 examples/web 예제 포함).
// 사내 의존은 dist/npm tarball(`pnpm pack:all` 결과)로만 받는다. 필요한 tarball이 없으면 pack:all을 먼저 돌린다(`--pack`이면 늘).
// 외부 의존은 npm 캐시·인덱스에서 받는다.
// 계획은 lib/plans.mjs의 순수 함수가 만들고, 여기서는 복사와 프로세스만 다룬다.
import { spawnSync } from "node:child_process";
import { cpSync, existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

import { discoverPackages, selectPackage } from "./lib/fsutil.mjs";
import { DEFAULT_NPM_DIR, PORTABILITY_ENV, decidePack, formatResultTable, planPortability, portabilityTargets } from "./lib/plans.mjs";
import { resolvePrefixes } from "./lib/workspace.mjs";
import { runPackAll } from "./pack-all.mjs";

export const USAGE = `사용: node scripts/pkgkit/portability.mjs [옵션]

옵션:
  --root DIR       저장소 루트 (기본 현재 폴더)
  --package NAME   한 패키지만 검사 (이름 또는 폴더 끝 이름)
  --under PREFIX   검사 대상을 이 폴더 접두사로 좁힌다 (기본: 워크스페이스 전체에서 앱을 뺀 것)
  --pack           tarball이 있어도 먼저 pack:all로 다시 만든다 (소스를 고친 뒤)
  --prefix P       사내 패키지 이름 접두사, 반복 가능 (기본: 루트 이름의 scope → 패키지들의 scope)
  --npm-dir DIR    tarball 폴더 (기본 ${DEFAULT_NPM_DIR}, 루트 기준)
  --keep           임시 폴더를 지우지 않는다
  -h, --help       이 도움말
필요한 tarball이 없으면 \`pnpm pack:all\`을 스스로 먼저 돌린다. 실패가 있으면 종료 코드 1.`;

const SKIP = new Set(["node_modules", "dist", ".git", "coverage"]);

/**
 * 한 패키지를 임시 폴더에서 검사한다.
 * @returns {{name: string, ok: boolean, failedStep?: string, note?: string}}
 */
function checkOne(pkg, plan, keep) {
  if (plan.missing.length) return { name: pkg.name, ok: false, failedStep: "plan", note: `워크스페이스에 없는 사내 의존: ${plan.missing.join(", ")}` };
  const absent = Object.values(plan.tarballs).filter((f) => !existsSync(f));
  if (absent.length) return { name: pkg.name, ok: false, failedStep: "tarball", note: `pack:all 뒤에도 tarball이 없다(pack:all 대상 밖 패키지?): ${absent.map((f) => f.split(sep).pop()).join(", ")}` };

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
  const opt = { root: ".", package: undefined, under: undefined, prefix: [], "npm-dir": DEFAULT_NPM_DIR, keep: false, pack: false };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === "-h" || a === "--help") {
      console.log(USAGE);
      process.exit(0);
    } else if (a === "--keep") opt.keep = true;
    else if (a === "--pack") opt.pack = true;
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
    // 의존 닫힘은 워크스페이스 전체에서 찾는다(예제가 packages/ts 패키지를 쓰므로 --under로 좁혀도 그대로).
    workspace = discoverPackages(root, { under: "" });
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
  const scoped = portabilityTargets(workspace, { under: opt.under });
  const targets = opt.package ? selectPackage(scoped, opt.package) : scoped;
  if (targets.length === 0) {
    console.error(`portability: 검사할 패키지가 없다${opt.package ? `: ${opt.package}` : ""}`);
    process.exit(2);
  }
  const npmDir = resolve(root, opt["npm-dir"]);
  const plans = targets.map((pkg) => planPortability({ pkg, workspace, npmDir, sep, prefixes }));
  const { pack, absent } = decidePack({ plans, exists: existsSync, force: opt.pack });
  if (pack) {
    console.log(opt.pack ? "--pack: tarball을 다시 만든다" : `tarball이 없어 먼저 pack:all을 돌린다: ${absent.map((f) => f.split(sep).pop()).join(", ")}`);
    const r = runPackAll({ root, outDir: npmDir });
    if (!r.ok) {
      console.error(`portability: pack:all ${r.failedStep} 단계 실패`);
      process.exit(r.status ?? 1);
    }
  }
  const rows = targets.map((p, i) => {
    console.log(`... ${p.name}`);
    return checkOne(p, plans[i], opt.keep);
  });
  console.log(`\n${formatResultTable(rows)}`);
  process.exit(rows.every((r) => r.ok) ? 0 : 1);
}
