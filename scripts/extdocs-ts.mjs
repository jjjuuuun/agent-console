// `pnpm extdocs-check`: TS 쪽 확장 지점 선언 대조(design §8R.2·§8R.3).
// 읽을 곳·표 이름은 scripts/extdocs/extdocs.yaml(`ts_package_globs`·`ts_table`)이 정한다.
//  1) 각 패키지·앱 package.json의 `<ts_table>.extensionPoints`를 declaration.schema.json으로 형식 검사
//  2) `interface`·`registration.export`의 `@패키지#이름`이 그 패키지 공개 export에 있는지 TypeScript 컴파일러 API로 확인
// 선언이 없는 패키지는 통과한다. 출력: `오류 [code] where: message` (+ `--json`).
// 기호 표기: `@pkg#이름`(패키지 공개 진입점) · `@pkg/경로/파일.tsx#이름`(앱처럼 진입점이 없을 때 그 파일, 패키지 폴더 기준).
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createRequire } from "node:module";

import { parse as parseYaml } from "yaml";

import { validate } from "./extdocs-ts-lib/json-schema.mjs";

const here = dirname(fileURLToPath(import.meta.url));

export const USAGE = `사용: node scripts/extdocs-ts.mjs [옵션]

옵션:
  --root DIR      저장소 루트 (기본 현재 폴더)
  --config PATH   extdocs.yaml (기본 <root>/scripts/extdocs/extdocs.yaml, 없으면 이 스크립트 옆 것)
  --schema PATH   declaration.schema.json (기본 설정 파일 옆)
  --json          결과를 JSON으로 출력 { declarations, findings }
  --help
`;

export function parseArgs(argv) {
  const out = { root: process.cwd(), config: null, schema: null, json: false, help: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--") continue;
    else if (a === "--json") out.json = true;
    else if (a === "--help" || a === "-h") out.help = true;
    else if (a === "--root" || a === "--config" || a === "--schema") {
      const v = argv[++i];
      if (v === undefined) throw new Error(`${a}에 값이 필요합니다`);
      out[a.slice(2)] = v;
    } else throw new Error(`모르는 옵션: ${a}`);
  }
  return out;
}

/** glob(`*` 한 단계만) 목록을 폴더로 푼다. */
export function globDirs(root, patterns) {
  const found = new Set();
  for (const pattern of patterns) {
    let bases = [root];
    for (const seg of pattern.split("/")) {
      const next = [];
      for (const b of bases) {
        if (seg === "*") {
          if (!existsSync(b)) continue;
          for (const name of readdirSync(b).sort()) {
            const p = join(b, name);
            if (statSync(p).isDirectory() && name !== "node_modules") next.push(p);
          }
        } else next.push(join(b, seg));
      }
      bases = next;
    }
    for (const b of bases) if (existsSync(join(b, "package.json"))) found.add(b);
  }
  return [...found].sort();
}

const posix = (p) => p.split("\\").join("/");

/** 패키지 폴더들에서 선언을 모은다. 형식 오류·JSON 오류는 findings로. */
export function collectDeclarations({ root, packageGlobs, table, schema }) {
  const packages = [];
  const declarations = [];
  const findings = [];
  for (const dir of globDirs(root, packageGlobs)) {
    const file = join(dir, "package.json");
    const where = posix(relative(root, file));
    let pkg;
    try {
      pkg = JSON.parse(readFileSync(file, "utf8"));
    } catch (e) {
      findings.push({ level: "error", code: "json-invalid", where, message: `package.json을 읽지 못함: ${e.message}` });
      continue;
    }
    packages.push({ name: pkg.name ?? posix(relative(root, dir)), dir, pkg });
    const raw = pkg[table];
    if (!raw || typeof raw !== "object" || !("extensionPoints" in raw)) continue;
    const errors = validate(schema, raw.extensionPoints);
    for (const e of errors) {
      findings.push({ level: "error", code: "schema-invalid", where: `${where}#${table}.extensionPoints`, message: `${e.path}: ${e.message}` });
    }
    if (errors.length > 0) continue;
    for (const [slug, point] of Object.entries(raw.extensionPoints)) {
      declarations.push({ slug, package: pkg.name ?? null, file: where, point });
    }
  }
  return { packages, declarations, findings };
}

const asList = (v) => (v === undefined || v === null ? [] : Array.isArray(v) ? v : [v]);

/** 선언이 내는 기호 목록: `interface` 항목과 `registration.export`. */
export function declaredSymbols(point) {
  const out = [];
  for (const s of asList(point.interface)) out.push({ field: "interface", symbol: s });
  for (const s of asList(point.registration?.export)) out.push({ field: "registration.export", symbol: s });
  return out;
}

/** `@pkg/sub/path.tsx#Name` → { pkg, subpath, name }. 패키지 이름은 `@scope/name` 또는 `name`. */
export function parseSymbol(symbol) {
  const hash = symbol.indexOf("#");
  if (hash <= 0 || hash === symbol.length - 1) return null;
  const left = symbol.slice(0, hash);
  const name = symbol.slice(hash + 1);
  const parts = left.split("/");
  const nameParts = left.startsWith("@") ? 2 : 1;
  if (parts.length < nameParts || parts.slice(0, nameParts).some((p) => p === "")) return null;
  return { pkg: parts.slice(0, nameParts).join("/"), subpath: parts.slice(nameParts).join("/") || null, name };
}

const SOURCE_EXT = [".ts", ".tsx", ".mts", ".js", ".jsx", ".mjs"];
const fromDist = (p) => p.replace(/^\.\/(dist)\//, "./src/").replace(/\.d\.ts$/, ".ts").replace(/\.js$/, ".ts");

/** 패키지의 공개 진입 소스 파일을 찾는다: exports["."].development → src/index.* → types/main을 src로 되돌린 것. */
export function entryFile(dir, pkg) {
  const dot = pkg.exports?.["."] ?? pkg.exports;
  const candidates = [];
  if (typeof dot === "object" && dot !== null) candidates.push(dot.development, dot.import, dot.default, dot.types);
  else if (typeof dot === "string") candidates.push(dot);
  candidates.push(...SOURCE_EXT.map((e) => `./src/index${e}`), pkg.types, pkg.module, pkg.main);
  for (const c of candidates) {
    if (typeof c !== "string") continue;
    for (const p of [c, fromDist(c)]) {
      const f = join(dir, p);
      if (existsSync(f) && statSync(f).isFile() && !f.endsWith(".d.ts")) return f;
    }
  }
  return null;
}

/** 파일의 공개 export 이름 집합(`export *`·재수출 포함). TypeScript 컴파일러 API. */
export function exportNames(ts, file, root, cache) {
  const key = resolve(file);
  if (cache.has(key)) return cache.get(key);
  const options = {
    allowJs: true,
    noEmit: true,
    skipLibCheck: true,
    jsx: ts.JsxEmit.ReactJSX,
    target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.ESNext,
    moduleResolution: ts.ModuleResolutionKind.Bundler,
    customConditions: ["development"],
    types: [],
  };
  const host = ts.createCompilerHost(options, true);
  host.getCurrentDirectory = () => root;
  const program = ts.createProgram([key], options, host);
  const source = program.getSourceFile(key);
  const checker = program.getTypeChecker();
  const symbol = source ? checker.getSymbolAtLocation(source) : undefined;
  // 모듈이 아닌 파일(export 없음)은 symbol이 없다 → 빈 집합.
  const names = new Set(symbol ? checker.getExportsOfModule(symbol).map((s) => s.getName()) : []);
  cache.set(key, names);
  return names;
}

function loadTypeScript(root) {
  for (const base of [join(root, "package.json"), join(here, "..", "package.json")]) {
    try {
      return createRequire(base)("typescript");
    } catch {
      /* 다음 후보 */
    }
  }
  throw new Error("typescript를 찾지 못했습니다 (pnpm install 필요)");
}

/** 선언의 기호가 실제 export인지 대조한다. */
export function checkSymbols({ root, packages, declarations, ts }) {
  const findings = [];
  const byName = new Map(packages.map((p) => [p.name, p]));
  const cache = new Map();
  for (const d of declarations) {
    for (const { field, symbol } of declaredSymbols(d.point)) {
      const where = `${d.file}#${d.slug}.${field}`;
      const err = (code, message) => findings.push({ level: "error", code, where, message: `${symbol}: ${message}` });
      const parsed = parseSymbol(symbol);
      if (!parsed) {
        err("symbol-malformed", "`@패키지#이름` 형식이 아닙니다");
        continue;
      }
      const target = byName.get(parsed.pkg);
      if (!target) {
        err("package-unknown", `워크스페이스에 패키지 ${parsed.pkg}가 없습니다 (ts_package_globs 안이어야 합니다)`);
        continue;
      }
      const file = parsed.subpath ? resolveSub(target.dir, parsed.subpath) : entryFile(target.dir, target.pkg);
      if (!file) {
        err("entry-missing", parsed.subpath ? `파일 ${parsed.subpath}를 찾지 못했습니다` : "공개 진입 파일(exports \".\" 또는 src/index.ts)을 찾지 못했습니다");
        continue;
      }
      const name = parsed.name.split(".")[0];
      if (!exportNames(ts, file, root, cache).has(name)) {
        err("symbol-missing", `${posix(relative(root, file))}에서 export되지 않습니다`);
      }
    }
  }
  return findings;
}

function resolveSub(dir, sub) {
  for (const c of [sub, ...SOURCE_EXT.map((e) => sub + e), ...SOURCE_EXT.map((e) => join(sub, `index${e}`))]) {
    const f = join(dir, c);
    if (existsSync(f) && statSync(f).isFile()) return f;
  }
  return null;
}

/** 전체 실행. 반환: { declarations, findings }. */
export function run({ root, configPath, schemaPath, ts }) {
  const cfgFile = configPath ?? [join(root, "scripts/extdocs/extdocs.yaml"), join(here, "extdocs/extdocs.yaml")].find(existsSync);
  if (!cfgFile) throw new Error("extdocs.yaml을 찾지 못했습니다 (--config)");
  const config = parseYaml(readFileSync(cfgFile, "utf8"));
  const schemaFile = schemaPath ?? join(dirname(cfgFile), "declaration.schema.json");
  const schema = JSON.parse(readFileSync(schemaFile, "utf8"));
  const collected = collectDeclarations({
    root,
    packageGlobs: config.ts_package_globs ?? [],
    table: config.ts_table ?? "agentConsole",
    schema,
  });
  const findings = [...collected.findings];
  // 형식이 틀린 선언은 기호 대조에서 빠진다(이미 오류로 보고됨).
  if (collected.declarations.length > 0) {
    findings.push(...checkSymbols({ root, packages: collected.packages, declarations: collected.declarations, ts: ts ?? loadTypeScript(root) }));
  }
  return {
    declarations: collected.declarations.map((d) => ({ slug: d.slug, package: d.package, file: d.file })),
    findings,
  };
}

export const formatFinding = (f) => `${f.level === "error" ? "오류" : "경고"} [${f.code}] ${f.where}: ${f.message}`;

export function main(argv) {
  let args;
  try {
    args = parseArgs(argv);
  } catch (e) {
    console.error(`${e.message}\n\n${USAGE}`);
    return 2;
  }
  if (args.help) {
    console.log(USAGE);
    return 0;
  }
  let result;
  try {
    result = run({
      root: resolve(args.root),
      configPath: args.config ? resolve(args.config) : null,
      schemaPath: args.schema ? resolve(args.schema) : null,
    });
  } catch (e) {
    console.error(`extdocs-check: ${e.message}`);
    return 2;
  }
  const errors = result.findings.filter((f) => f.level === "error");
  if (args.json) console.log(JSON.stringify(result, null, 2));
  else {
    for (const f of result.findings) console.log(formatFinding(f));
    console.log(`TS 확장 지점 선언 ${result.declarations.length}개, 오류 ${errors.length}건`);
  }
  return errors.length > 0 ? 1 : 0;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) process.exit(main(process.argv.slice(2)));
