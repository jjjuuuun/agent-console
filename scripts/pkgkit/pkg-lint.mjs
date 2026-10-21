// `pnpm pkg-lint`: TS 패키지가 저장소 밖에서도 설치·테스트되는 모양인지 정적으로 검사한다(design §3R.2.5).
// 판단은 lib/lint-rules.mjs의 순수 함수가 한다. 여기서는 폴더를 읽고 결과를 출력한다.
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { inferKind, discoverPackages, readPackageFiles, selectPackage } from "./lib/fsutil.mjs";
import { formatViolations, lintTsPackage } from "./lib/lint-rules.mjs";
import { resolvePrefixes } from "./lib/workspace.mjs";

export const USAGE = `사용: node scripts/pkgkit/pkg-lint.mjs [옵션]

옵션:
  --root DIR       저장소 루트 (기본 현재 폴더)
  --package NAME   이름 또는 폴더 끝 이름으로 한 패키지만 검사
  --under PREFIX   찾을 폴더 접두사 (기본 packages/ts/)
  --prefix P       사내 패키지 이름 접두사, 반복 가능 (기본: 루트 이름의 scope → 패키지들의 scope)
  --json           결과를 JSON으로 출력
  -h, --help       이 도움말
종료 코드: 위반이 있으면 1.`;

/**
 * 패키지 폴더들을 검사한다.
 * @param {string} root
 * @param {{package?: string, under?: string, prefix?: string[]}} [options]
 * @returns {{dir: string, violations: import("./lib/lint-rules.mjs").Violation[]}[]}
 */
export function lintWorkspace(root, options = {}) {
  let packages = discoverPackages(root, { under: options.under });
  if (options.package) {
    packages = selectPackage(packages, options.package);
    if (packages.length === 0) throw new Error(`패키지를 찾을 수 없다: ${options.package}`);
  }
  const rootFile = join(root, "package.json");
  const prefixes = resolvePrefixes({
    explicit: options.prefix,
    rootPackageJson: existsSync(rootFile) ? JSON.parse(readFileSync(rootFile, "utf8")) : null,
    packageNames: packages.map((p) => p.name),
  });
  return packages.map((p) => ({ dir: p.relDir, violations: lintTsPackage({ kind: inferKind(p.relDir, p.packageJson), files: readPackageFiles(p.dir), inHousePrefixes: prefixes }) }));
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const argv = process.argv.slice(2);
  const opt = { root: ".", package: undefined, under: undefined, prefix: [], json: false };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === "-h" || a === "--help") {
      console.log(USAGE);
      process.exit(0);
    } else if (a === "--json") opt.json = true;
    else if (a === "--prefix") opt.prefix.push(argv[++i]);
    else if (a === "--root" || a === "--package" || a === "--under") opt[a.slice(2)] = argv[++i];
    else {
      console.error(`pkg-lint: 모르는 옵션 ${a}\n\n${USAGE}`);
      process.exit(2);
    }
  }
  try {
    const results = lintWorkspace(resolve(opt.root), opt);
    console.log(opt.json ? JSON.stringify(results, null, 2) : formatViolations(results));
    process.exit(results.some((r) => r.violations.length > 0) ? 1 : 0);
  } catch (err) {
    console.error(`pkg-lint: ${err instanceof Error ? err.message : err}`);
    process.exit(2);
  }
}
