// 새 TS 패키지 만들기(순수 함수 + 템플릿 읽기). `new-package.mjs` CLI가 이 모듈을 쓴다.
// 템플릿은 층으로 쌓는다: common -> 종류(lib|config). 뒤 층이 같은 경로를 덮어쓴다.
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import { applyOverlay, mergeJson, renderTree } from "./template.mjs";

/** 새 패키지의 개발 의존 기본 버전. 루트 package.json을 읽을 수 있으면 `devVersionsFromRoot`가 덮어쓴다. */
export const DEFAULT_DEV_VERSIONS = {
  eslint: "^10.12.0",
  eslint_js: "^10.0.1",
  globals: "^17.13.0",
  happy_dom: "^21.0.1",
  react_hooks: "^7.1.1",
  types_node: "^26.6.5",
  typescript: "^6.0.3",
  typescript_eslint: "^8.71.2",
  vitest: "^5.0.4",
};
const ROOT_KEYS = {
  eslint: "eslint",
  eslint_js: "@eslint/js",
  globals: "globals",
  happy_dom: "happy-dom",
  react_hooks: "eslint-plugin-react-hooks",
  types_node: "@types/node",
  typescript: "typescript",
  typescript_eslint: "typescript-eslint",
  vitest: "vitest",
};

/**
 * 루트 package.json의 devDependencies로 기본 버전을 덮어쓴다(같은 저장소의 버전과 맞추기 위해).
 * @param {Record<string, any> | null | undefined} rootPackageJson
 * @returns {Record<string, string>}
 */
export function devVersionsFromRoot(rootPackageJson) {
  const dev = rootPackageJson?.devDependencies ?? {};
  return Object.fromEntries(Object.entries(DEFAULT_DEV_VERSIONS).map(([k, fallback]) => [k, dev[ROOT_KEYS[k]] ?? fallback]));
}

export class NewPackageArgsError extends Error {}

export const USAGE = `사용: pnpm new-package --kind {lib,config} [옵션] NAME

NAME은 \`@scope/이름\` 또는 이름만(--scope 기본 @agent-console).

옵션:
  --kind KIND         lib | config (필수)
  --scope S           NAME에 scope가 없을 때 붙일 scope (기본 @agent-console)
  --description TEXT  package.json·README 설명
  --dom               테스트 환경을 happy-dom으로(기본 node)
  --dir PATH          만들 폴더 (기본 packages/ts/<kind>/<이름>)
  --root DIR          저장소 루트 (기본 현재 폴더)
  --dry-run           파일을 쓰지 않고 목록만 보인다
  -h, --help          이 도움말`;

/**
 * 명령행 인자를 읽는다.
 * @param {string[]} argv
 * @returns {{help: boolean, kind: string, name: string, scope: string, description: string, dom: boolean, dir: string | undefined, root: string, dryRun: boolean}}
 * @throws {NewPackageArgsError}
 */
export function parseNewPackageArgs(argv) {
  const o = { help: false, kind: "", name: "", scope: "@agent-console", description: "", dom: false, dir: undefined, root: ".", dryRun: false };
  const valued = { "--kind": "kind", "--scope": "scope", "--description": "description", "--dir": "dir", "--root": "root" };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "-h" || arg === "--help") o.help = true;
    else if (arg === "--dom") o.dom = true;
    else if (arg === "--dry-run") o.dryRun = true;
    else if (arg in valued) {
      i += 1;
      if (i >= argv.length) throw new NewPackageArgsError(`${arg} 값이 없다`);
      o[valued[arg]] = argv[i];
    } else if (arg.startsWith("-")) throw new NewPackageArgsError(`모르는 옵션: ${arg}`);
    else if (o.name) throw new NewPackageArgsError(`이름이 둘이다: ${o.name}, ${arg}`);
    else o.name = arg;
  }
  if (o.help) return o;
  if (!["lib", "config"].includes(o.kind)) throw new NewPackageArgsError("--kind는 lib 또는 config여야 한다");
  if (!o.name) throw new NewPackageArgsError("패키지 이름이 없다");
  return o;
}

/**
 * 이름을 풀어 scope·짧은 이름·전체 이름으로 나눈다.
 * @param {string} name
 * @param {string} defaultScope
 * @returns {{full: string, scope: string, short: string}}
 * @throws {NewPackageArgsError}
 */
export function splitName(name, defaultScope) {
  const m = /^(?:(@[a-z0-9][\w.-]*)\/)?([a-z0-9][a-z0-9._-]*)$/.exec(name);
  if (!m) throw new NewPackageArgsError(`패키지 이름이 올바르지 않다: ${name}`);
  const scope = m[1] ?? defaultScope;
  if (!/^@[a-z0-9][\w.-]*$/.test(scope)) throw new NewPackageArgsError(`scope가 올바르지 않다: ${scope}`);
  return { full: `${scope}/${m[2]}`, scope, short: m[2] };
}

/**
 * 템플릿 값을 만든다.
 * @param {object} args
 * @param {string} args.name 전체 이름
 * @param {string} args.scope
 * @param {string} [args.description]
 * @param {boolean} [args.dom]
 * @param {"lib" | "config"} args.kind
 * @param {Record<string, string>} [args.devVersions]
 * @param {number} [args.year]
 * @param {string} [args.version]
 * @returns {Record<string, unknown>}
 */
export function makeVars({ name, scope, description = "", dom = false, kind, devVersions = DEFAULT_DEV_VERSIONS, year = new Date().getFullYear(), version = "0.1.0" }) {
  const [major, minor] = version.split(".");
  return {
    name,
    kind,
    version,
    year,
    description: description || `${name} 패키지`,
    testEnvironment: dom ? "happy-dom" : "node",
    entry: kind === "config" ? "index.js" : "src/index.ts",
    eslintConfigName: `${scope}/eslint-config`,
    tsconfigName: `${scope}/tsconfig`,
    inhouseRange: `^${major}.${minor}.0`,
    dev: devVersions,
  };
}

/** 폴더 아래 모든 파일을 읽는다(상대 경로 -> 내용). */
function readTree(dir) {
  const out = {};
  const walk = (rel) => {
    for (const e of readdirSync(join(dir, rel), { withFileTypes: true })) {
      const next = rel ? `${rel}/${e.name}` : e.name;
      if (e.isDirectory()) walk(next);
      else out[next] = readFileSync(join(dir, next), "utf8");
    }
  };
  walk("");
  return out;
}

/**
 * 템플릿 층을 디스크에서 읽는다.
 * @param {string} templatesDir `scripts/pkgkit/templates/ts`
 * @param {"lib" | "config"} kind
 * @returns {Record<string, string>[]} 앞 층부터
 */
export function loadLayers(templatesDir, kind) {
  return [readTree(join(templatesDir, "common")), readTree(join(templatesDir, kind))];
}

/**
 * 층을 렌더링해 패키지 파일 묶음을 만든다.
 * @param {Record<string, string>[]} layers
 * @param {Record<string, unknown>} vars
 * @param {{dom?: boolean}} [options] dom이면 package.json devDependencies에 happy-dom을 더한다
 * @returns {Record<string, string>} 상대 경로 -> 내용
 */
export function buildPackageFiles(layers, vars, options = {}) {
  let files = {};
  for (const layer of layers) files = applyOverlay(files, renderTree(layer, vars));
  if (options.dom) {
    const dev = /** @type {Record<string, string>} */ (vars.dev);
    const pkg = mergeJson(JSON.parse(files["package.json"]), { devDependencies: { "happy-dom": dev.happy_dom } });
    files["package.json"] = `${JSON.stringify(pkg, null, 2)}\n`;
  }
  return files;
}
