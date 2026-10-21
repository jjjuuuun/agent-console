// 파일 시스템 어댑터: 패키지 폴더를 읽어 순수 함수 입력으로 만든다. 판단은 하지 않는다.
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

import { isCovered, readWorkspacePatterns } from "./workspace.mjs";

const SKIP_DIRS = new Set(["node_modules", "dist", ".git", "coverage", ".turbo", ".vite"]);
const TEXT_FILE = /(?:\.(?:[cm]?[jt]sx?|json|md|css|ya?ml|txt)|\/LICENSE|^LICENSE|\.gitignore)$/;

/**
 * 폴더 아래 텍스트 파일을 모두 읽는다(node_modules·dist 등 제외).
 * @param {string} dir 패키지 폴더
 * @returns {Record<string, string>} `/` 구분 상대 경로 -> 내용
 */
export function readPackageFiles(dir) {
  const out = {};
  const walk = (rel) => {
    for (const entry of readdirSync(join(dir, rel), { withFileTypes: true })) {
      const next = rel ? `${rel}/${entry.name}` : entry.name;
      if (entry.isDirectory()) {
        if (!SKIP_DIRS.has(entry.name)) walk(next);
      } else if (TEXT_FILE.test(next)) out[next] = readFileSync(join(dir, next), "utf8");
    }
  };
  walk("");
  return out;
}

/**
 * 패키지 종류를 정한다. package.json의 `agentConsole.kind` 표식이 먼저고,
 * 표식이 없을 때만 경로 단계에 `config`가 있는지로 추정한다.
 * @param {string} relDir
 * @param {Record<string, any> | null} [packageJson]
 * @returns {"lib" | "config"}
 */
export function inferKind(relDir, packageJson = null) {
  const marked = packageJson?.agentConsole?.kind;
  if (marked === "lib" || marked === "config") return marked;
  return relDir.split("/").includes("config") ? "config" : "lib";
}

/**
 * 워크스페이스 패턴에 맞는 패키지 폴더를 찾는다.
 * @param {string} root 저장소 루트
 * @param {{under?: string}} [options] under: 이 접두사 아래 패턴만 본다(기본 `packages/ts/`)
 * @returns {{relDir: string, dir: string, name: string, version: string, packageJson: Record<string, any>}[]}
 */
export function discoverPackages(root, options = {}) {
  const under = options.under ?? "packages/ts/";
  const wsFile = join(root, "pnpm-workspace.yaml");
  if (!existsSync(wsFile)) throw new Error(`pnpm-workspace.yaml이 없다: ${root} (--root로 저장소 루트를 지정한다)`);
  const patterns = readWorkspacePatterns(readFileSync(wsFile, "utf8"));
  const found = [];
  const walk = (rel, depth) => {
    if (depth > 4) return;
    for (const entry of readdirSync(join(root, rel), { withFileTypes: true })) {
      if (!entry.isDirectory() || SKIP_DIRS.has(entry.name)) continue;
      const next = rel ? `${rel}/${entry.name}` : entry.name;
      if (isCovered(patterns, next) && next.startsWith(under) && existsSync(join(root, next, "package.json"))) {
        const packageJson = JSON.parse(readFileSync(join(root, next, "package.json"), "utf8"));
        found.push({ relDir: next, dir: join(root, next), name: packageJson.name, version: packageJson.version, packageJson });
      } else if (statSync(join(root, next)).isDirectory()) walk(next, depth + 1);
    }
  };
  const start = under.replace(/\/$/, "");
  if (!existsSync(join(root, start))) throw new Error(`패키지 폴더가 없다: ${start} (--under로 바꿀 수 있다)`);
  walk(start, 0);
  return found.sort((a, b) => a.relDir.localeCompare(b.relDir));
}

/** 이름(`@scope/x`) 또는 폴더(상대 경로·마지막 단계)로 패키지를 고른다. */
export function selectPackage(packages, selector) {
  return packages.filter((p) => p.name === selector || p.relDir === selector || p.relDir.endsWith(`/${selector}`) || p.name.endsWith(`/${selector}`));
}
