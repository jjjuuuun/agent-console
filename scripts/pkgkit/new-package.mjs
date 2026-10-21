// `pnpm new-package --kind {lib,config} NAME`: 템플릿으로 새 TS 패키지를 만든다(design §3R.2.5).
// 루트 파일은 고치지 않는다. 워크스페이스 패턴(pnpm-workspace.yaml)에 안 맞는 위치면 알려 주기만 한다.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { NewPackageArgsError, USAGE, buildPackageFiles, devVersionsFromRoot, loadLayers, makeVars, parseNewPackageArgs, splitName } from "./lib/scaffold.mjs";
import { isCovered, readWorkspacePatterns } from "./lib/workspace.mjs";

const TEMPLATES = join(dirname(fileURLToPath(import.meta.url)), "templates", "ts");

/**
 * 새 패키지를 만든다.
 * @param {ReturnType<typeof parseNewPackageArgs>} opts
 * @returns {{dir: string, relDir: string, files: string[], covered: boolean | null}}
 */
export function createPackage(opts) {
  const root = resolve(opts.root);
  const { full, scope, short } = splitName(opts.name, opts.scope);
  const relDir = (opts.dir ?? `packages/ts/${opts.kind}/${short}`).replace(/\\/g, "/").replace(/\/$/, "");
  const dir = resolve(root, relDir);
  if (existsSync(dir)) throw new NewPackageArgsError(`이미 있는 폴더다: ${relDir}`);

  const rootPkgFile = join(root, "package.json");
  const rootPkg = existsSync(rootPkgFile) ? JSON.parse(readFileSync(rootPkgFile, "utf8")) : null;
  const vars = makeVars({ name: full, scope, description: opts.description, dom: opts.dom, kind: opts.kind, devVersions: devVersionsFromRoot(rootPkg) });
  const files = buildPackageFiles(loadLayers(TEMPLATES, opts.kind, opts.draft), vars, { dom: opts.dom });

  if (!opts.dryRun) {
    for (const [rel, content] of Object.entries(files)) {
      const target = join(dir, rel);
      mkdirSync(dirname(target), { recursive: true });
      writeFileSync(target, content, "utf8");
    }
  }
  const wsFile = join(root, "pnpm-workspace.yaml");
  const covered = existsSync(wsFile) ? isCovered(readWorkspacePatterns(readFileSync(wsFile, "utf8")), relDir) : null;
  return { dir, relDir, files: Object.keys(files).sort(), covered };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const opts = parseNewPackageArgs(process.argv.slice(2));
    if (opts.help) {
      console.log(USAGE);
    } else {
      const r = createPackage(opts);
      console.log(`${opts.dryRun ? "(dry-run) " : ""}${r.relDir}\n${r.files.map((f) => `  ${f}`).join("\n")}`);
      if (r.covered === false) console.warn(`주의: pnpm-workspace.yaml 패턴에 ${r.relDir}이(가) 들어 있지 않다. 패턴을 추가해야 pnpm이 연결한다.`);
      console.log("\n다음: pnpm install, 그리고 pnpm --filter <이름> test");
    }
  } catch (err) {
    if (!(err instanceof NewPackageArgsError)) throw err;
    console.error(`pnpm new-package: ${err.message}\n\n${USAGE}`);
    process.exit(2);
  }
}
