// TS 패키지 이식성 정적 검사(순수 함수, design §3R.2.5 `pnpm pkg-lint`).
// 입력은 패키지 파일 내용 묶음이고 파일 시스템·프로세스를 모른다. 읽기는 fsutil.mjs가 한다.
import { builtinModules } from "node:module";

import { checkReadmeSync } from "./readme-sync.mjs";
import { DEFAULT_IN_HOUSE_PREFIXES, allDependencies, isInHouse } from "./workspace.mjs";

/** 종류별 필수 파일. */
export const REQUIRED_FILES = {
  lib: ["package.json", "tsconfig.json", "vitest.config.ts", "eslint.config.js", "README.md", "CHANGELOG.md", "LICENSE", "test/readme.test.ts"],
  config: ["package.json", "vitest.config.ts", "eslint.config.js", "README.md", "CHANGELOG.md", "LICENSE", "test/readme.test.ts"],
};
/** 종류별 필수 npm 스크립트. */
export const REQUIRED_SCRIPTS = {
  lib: ["build", "typecheck", "lint", "test"],
  config: ["lint", "test"],
};
const CODE_EXT = /\.(?:[cm]?[jt]sx?)$/;
const NODE_BUILTINS = new Set(builtinModules.flatMap((m) => [m, `node:${m}`]));
const INHOUSE_RANGE = /^(?:[\^~]\d+\.\d+\.\d+(?:-[\w.]+)?|>=\d+(?:\.\d+){0,2}\s*<\d+(?:\.\d+){0,2})$/;

/**
 * @typedef {{rule: string, file: string, message: string}} Violation
 * @typedef {{
 *   name?: string,
 *   kind: "lib" | "config",
 *   files: Record<string, string>,
 *   inHousePrefixes?: string[],
 *   tsconfigName?: string,
 * }} PackageInput  files: 패키지 폴더 기준 상대 경로 -> 텍스트 내용(node_modules·dist 제외)
 */

/** import·export-from·require·동적 import의 모듈 지정자를 뽑는다. */
export function extractSpecifiers(source) {
  const out = new Set();
  const patterns = [
    /\b(?:import|export)\s[^"'`;]*?\sfrom\s*["']([^"']+)["']/g,
    /\bimport\s*["']([^"']+)["']/g,
    /\bimport\s*\(\s*["']([^"']+)["']\s*\)/g,
    /\brequire\s*\(\s*["']([^"']+)["']\s*\)/g,
  ];
  for (const re of patterns) for (const m of source.matchAll(re)) out.add(m[1]);
  return [...out];
}

/** 모듈 지정자에서 패키지 이름만 남긴다. 상대 경로·내장·가상 모듈이면 null. */
export function packageNameOf(specifier) {
  if (specifier.startsWith(".") || specifier.startsWith("/") || specifier.includes(":") || NODE_BUILTINS.has(specifier)) return null;
  const parts = specifier.split("/");
  return specifier.startsWith("@") ? parts.slice(0, 2).join("/") : parts[0];
}

/** `from` 파일 폴더 기준으로 상대 지정자를 풀었을 때 패키지 밖으로 나가는지. */
export function escapesPackage(fromFile, specifier) {
  if (!specifier.startsWith(".")) return false;
  const stack = fromFile.split("/").slice(0, -1);
  for (const part of specifier.split("/")) {
    if (part === "" || part === ".") continue;
    if (part === "..") {
      if (stack.length === 0) return true;
      stack.pop();
    } else stack.push(part);
  }
  return false;
}

const parseJson = (text) => {
  try {
    return { value: JSON.parse(text) };
  } catch (e) {
    return { error: e instanceof Error ? e.message : String(e) };
  }
};

/** `@types/x` 로 선언된 타입 전용 패키지를 원래 이름으로 환산한다. */
const typesFor = (name) => `@types/${name.startsWith("@") ? name.slice(1).replace("/", "__") : name}`;

/**
 * 한 TS 패키지를 검사한다.
 * @param {PackageInput} input
 * @returns {Violation[]}
 */
export function lintTsPackage(input) {
  const { kind, files } = input;
  const prefixes = input.inHousePrefixes ?? DEFAULT_IN_HOUSE_PREFIXES;
  const tsconfigName = input.tsconfigName ?? `${prefixes[0]}tsconfig`;
  /** @type {Violation[]} */
  const out = [];
  const add = (rule, file, message) => out.push({ rule, file, message });

  for (const f of REQUIRED_FILES[kind]) if (!(f in files)) add("required-file", f, `필수 파일이 없다: ${f}`);

  let pkg = null;
  if ("package.json" in files) {
    const parsed = parseJson(files["package.json"]);
    if (parsed.error) add("package-json", "package.json", `JSON을 읽을 수 없다: ${parsed.error}`);
    else pkg = parsed.value;
  }
  if (pkg) lintPackageJson(pkg, kind, prefixes, add);

  // tsconfig*.json: 패키지 밖 경로·상대 extends
  for (const [file, text] of Object.entries(files)) {
    if (!/^tsconfig(?:\.[\w-]+)?\.json$/.test(file)) continue;
    const parsed = parseJson(text.replace(/^\s*\/\/.*$/gm, ""));
    if (parsed.error) {
      add("tsconfig", file, `JSON을 읽을 수 없다: ${parsed.error}`);
      continue;
    }
    const cfg = parsed.value;
    const extendsList = [].concat(cfg.extends ?? []);
    for (const e of extendsList) {
      if (typeof e === "string" && e.startsWith(".") && escapesPackage(file, e)) {
        add("tsconfig-extends", file, `extends가 패키지 밖을 가리킨다: ${e} (공용 설정은 ${tsconfigName} 패키지로 받는다)`);
      }
    }
    const paths = [...(cfg.include ?? []), ...(cfg.exclude ?? []), ...(cfg.files ?? []), ...(cfg.references ?? []).map((r) => r.path)];
    for (const p of paths) if (typeof p === "string" && p.startsWith("..")) add("external-path", file, `패키지 밖 경로: ${p}`);
    for (const targets of Object.values(cfg.compilerOptions?.paths ?? {})) {
      for (const t of targets) if (typeof t === "string" && t.startsWith("..")) add("external-path", file, `paths가 패키지 밖을 가리킨다: ${t}`);
    }
  }

  // 소스: 패키지 밖 상대 import, 다른 패키지 내부 직접 참조, 선언하지 않은 의존
  const declared = new Set(pkg ? Object.keys(allDependencies(pkg)) : []);
  const self = pkg?.name;
  for (const [file, text] of Object.entries(files)) {
    if (!CODE_EXT.test(file)) continue;
    for (const spec of extractSpecifiers(text)) {
      if (escapesPackage(file, spec)) {
        add("escaping-import", file, `패키지 밖 상대 경로 import: ${spec}`);
        continue;
      }
      const dep = packageNameOf(spec);
      if (!dep) continue;
      if (isInHouse(dep, prefixes) && /\/(?:src|dist|test|tests)(?:\/|$)/.test(spec.slice(dep.length))) {
        add("deep-import", file, `다른 패키지 내부를 직접 참조한다: ${spec} (공개 exports만 쓴다)`);
      }
      if (dep !== self && !declared.has(dep) && !declared.has(typesFor(dep))) {
        add("undeclared-dep", file, `package.json에 선언하지 않은 의존: ${dep}`);
      }
    }
  }

  if ("README.md" in files && "test/readme.test.ts" in files) {
    for (const msg of checkReadmeSync(files["README.md"], files["test/readme.test.ts"])) add("readme-sync", "README.md", msg);
  }
  return out;
}

function lintPackageJson(pkg, kind, prefixes, add) {
  const f = "package.json";
  if (typeof pkg.name !== "string" || !pkg.name) add("package-json", f, "name이 없다");
  if (typeof pkg.version !== "string" || !/^\d+\.\d+\.\d+(?:-[\w.]+)?$/.test(pkg.version)) add("package-json", f, `version이 semver가 아니다: ${pkg.version}`);
  if (pkg.private !== true) add("package-json", f, "private: true여야 한다(배포는 사람 결정, MD-11)");
  if (!pkg.license) add("package-json", f, "license가 없다");
  if (pkg.type !== "module") add("package-json", f, 'type은 "module"이어야 한다');

  const depFields = ["dependencies", "devDependencies", "peerDependencies", "optionalDependencies"];
  for (const field of depFields) {
    for (const [dep, range] of Object.entries(pkg[field] ?? {})) {
      if (typeof range !== "string") continue;
      if (/^(?:workspace|link):/.test(range) || (/^file:/.test(range) && range.includes(".."))) {
        add("workspace-protocol", f, `${field}.${dep}: 저장소 안에서만 되는 의존 문법 ${range} (일반 버전 범위를 쓴다)`);
      } else if (isInHouse(dep, prefixes) && !INHOUSE_RANGE.test(range)) {
        add("inhouse-range", f, `${field}.${dep}: 사내 의존은 ^0.x.y 범위여야 한다(현재 ${range})`);
      }
    }
  }
  for (const key of ["overrides", "resolutions"]) {
    for (const [dep, range] of Object.entries(pkg[key] ?? {})) {
      if (typeof range === "string" && /^(?:workspace|link):/.test(range)) add("workspace-protocol", f, `${key}.${dep}: ${range}`);
    }
  }

  for (const s of REQUIRED_SCRIPTS[kind]) if (!pkg.scripts?.[s]) add("scripts", f, `스크립트가 없다: ${s}`);
  for (const [name, cmd] of Object.entries(pkg.scripts ?? {})) {
    if (typeof cmd === "string" && /(^|[\s"'=])\.\.\//.test(cmd)) add("external-path", f, `scripts.${name}이 패키지 밖 경로를 쓴다: ${cmd}`);
  }

  for (const field of ["main", "module", "types"]) {
    const v = pkg[field];
    if (typeof v === "string" && /(^|\/)src\//.test(v) && CODE_EXT.test(v)) add("exports", f, `${field}가 소스(${v})를 가리킨다. exports의 development 조건으로 옮긴다`);
  }
  if (kind === "lib") lintExports(pkg, add);
}

function lintExports(pkg, add) {
  const f = "package.json";
  if (!pkg.exports || typeof pkg.exports !== "object") {
    add("exports", f, "exports가 없다");
    return;
  }
  if (!Array.isArray(pkg.files) || !pkg.files.some((x) => String(x).replace(/^\.\//, "").startsWith("dist"))) add("exports", f, 'files에 "dist"가 없어 tarball에 빌드 결과가 들지 않는다');
  for (const [key, target] of Object.entries(pkg.exports)) {
    if (typeof target === "string") {
      if (CODE_EXT.test(target)) add("exports", f, `exports["${key}"]가 조건 없는 코드 경로(${target})다. development→src, default→dist로 나눈다`);
      continue;
    }
    if (target === null || typeof target !== "object") continue;
    const dev = target.development;
    const def = target.default;
    if (typeof dev !== "string" || !/^\.\/src\//.test(dev)) add("exports", f, `exports["${key}"].development는 ./src/ 아래 파일이어야 한다`);
    if (typeof def !== "string" || !/^\.\/dist\//.test(def)) add("exports", f, `exports["${key}"].default는 ./dist/ 아래 빌드 결과여야 한다`);
    if (typeof target.types === "string" && !/^\.\/dist\//.test(target.types)) add("exports", f, `exports["${key}"].types는 ./dist/ 아래여야 한다`);
  }
}

/**
 * 위반을 사람이 읽는 줄로 만든다.
 * @param {{dir: string, violations: Violation[]}[]} results
 * @returns {string}
 */
export function formatViolations(results) {
  const lines = [];
  for (const r of results) {
    if (r.violations.length === 0) lines.push(`ok    ${r.dir}`);
    else {
      lines.push(`FAIL  ${r.dir}`);
      for (const v of r.violations) lines.push(`        [${v.rule}] ${v.file}: ${v.message}`);
    }
  }
  const bad = results.filter((r) => r.violations.length > 0).length;
  lines.push(bad === 0 ? `\n패키지 ${results.length}개 모두 통과` : `\n${bad}/${results.length}개 패키지에 위반이 있다`);
  return lines.join("\n");
}
